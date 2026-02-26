import json
import os
import subprocess
import sys
import time
import threading
from urllib.parse import urlencode

import requests
from flask import Flask, request, send_from_directory, jsonify, Response

BASE_URL = "https://www.metamob.fr/api"
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'metamob.config.json')
RESULTS_FILE = os.path.join(os.path.dirname(__file__), 'results.json')
ZONES_FILE = os.path.join(os.path.dirname(__file__), 'archimonstres_par_zone.json')

app = Flask(__name__, static_folder='.', static_url_path='')

# Simple in-process lock to serialize results.json writes
_results_lock = threading.Lock()
_tool_lock = threading.Lock()
_scan_proc = None


# --- Profile helpers (store multiple profiles inside one results.json) ---
def _safe_profile(name: str | None) -> str | None:
    if not name:
        return None
    v = name.strip().lower()
    return v if v in {"kourial", "mikhal"} else None


def _load_all_results() -> dict:
    """Load the entire results.json as a dict. Back-compat: if file is a single
    payload (has top-level 'counts'), wrap it under profiles.activeProfile.
    """
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    else:
        data = {}

    # If already in new format
    if isinstance(data, dict) and 'profiles' in data and isinstance(data['profiles'], dict):
        return data

    # Old format: make it the active profile and mirror
    if isinstance(data, dict) and 'counts' in data:
        wrapped = {
            'profiles': {
                'default': data
            },
            'activeProfile': 'default'
        }
        # Also mirror top-level fields to keep back-compat for direct readers
        wrapped.update(data)
        return wrapped

    # Empty file
    return {
        'profiles': {},
        'activeProfile': 'default'
    }


def _extract_profile_from_request() -> str:
    try:
        prof = request.args.get('profile')  # type: ignore[attr-defined]
    except Exception:
        prof = None
    prof = _safe_profile(prof) or 'default'
    return prof


def _tool_is_running(proc) -> bool:
    return proc is not None and proc.poll() is None


def _clean_tool_refs() -> None:
    global _scan_proc
    if _scan_proc is not None and _scan_proc.poll() is not None:
        _scan_proc = None


def _spawn_tool(script_path: str, cwd: str, profile: str):
    env = os.environ.copy()
    env['ARCHI_PROFILE'] = profile
    env['PYTHONUNBUFFERED'] = '1'
    return subprocess.Popen(
        [sys.executable, script_path],
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _read_profile_payload(all_data: dict, profile: str) -> dict:
    payload = (all_data.get('profiles') or {}).get(profile)
    if isinstance(payload, dict):
        return payload
    # default minimal payload
    return {"counts": {}, "timestamp": __import__('datetime').datetime.utcnow().isoformat() + 'Z'}


def _write_profile_payload(all_data: dict, profile: str, payload: dict) -> dict:
    profiles = all_data.get('profiles') or {}
    profiles[profile] = payload
    all_data['profiles'] = profiles
    all_data['activeProfile'] = profile
    # Mirror selected profile to top-level for back-compat with direct file readers
    for k in list(all_data.keys()):
        if k not in {'profiles', 'activeProfile'}:
            del all_data[k]
    all_data.update(payload)
    return all_data


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg or {}, f, ensure_ascii=False, indent=2)


def build_headers():
    cfg = load_config()
    headers = {}
    api_key = (cfg.get('apiKey') or '').strip()
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"
    # Propagate JSON
    headers['Content-Type'] = 'application/json'
    return headers


def _proxy_passthrough(method, path, params=None, body=None):
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    headers = build_headers()
    resp = requests.request(method, url, headers=headers, json=body)
    excluded = {'Content-Encoding', 'Transfer-Encoding', 'Connection'}
    headers_out = [(k, v) for k, v in resp.headers.items() if k not in excluded]
    return Response(resp.content, status=resp.status_code, headers=headers_out)


def _api_json(method, path, params=None, body=None):
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.request(method, url, headers=build_headers(), params=params, json=body, timeout=20)
    except requests.exceptions.RequestException as exc:
        # Build a fake response so callers get a proper error instead of a 500
        from types import SimpleNamespace
        fake = SimpleNamespace(
            ok=False, status_code=504,
            content=str(exc).encode(), text=str(exc),
            headers={}, json=lambda: None
        )
        return fake, {'error': f'Metamob API unreachable: {exc}'}
    payload = None
    try:
        payload = resp.json()
    except Exception:
        payload = None
    return resp, payload


def _extract_data(payload):
    if isinstance(payload, dict) and 'data' in payload:
        return payload.get('data')
    return payload


def _resolve_username(pseudo: str) -> str:
    raw = (pseudo or '').strip()
    if not raw:
        return raw

    # Fast path: if direct profile works, keep as-is
    resp, _ = _api_json('GET', f"/v1/users/{raw}")
    if resp.ok:
        return raw

    # Fallback: search users and recover canonical username casing
    resp, payload = _api_json('GET', '/v1/users/search', params={'q': raw, 'limit': 50, 'offset': 0})
    if not resp.ok:
        return raw

    data = _extract_data(payload)
    if not isinstance(data, list):
        return raw

    wanted = raw.casefold()
    for item in data:
        if not isinstance(item, dict):
            continue
        uname = item.get('username')
        if isinstance(uname, str) and uname.casefold() == wanted:
            return uname

    # Secondary fallback: contains match
    for item in data:
        if not isinstance(item, dict):
            continue
        uname = item.get('username')
        if isinstance(uname, str) and wanted in uname.casefold():
            return uname

    return raw


def _resolve_quest_slug(pseudo: str, explicit_slug: str | None = None):
    if explicit_slug:
        return explicit_slug, None

    # pseudo is expected to be already resolved via _resolve_username()
    resp, payload = _api_json('GET', f"/v1/users/{pseudo}/quests", params={'limit': 50, 'offset': 0})
    if not resp.ok:
        return None, _proxy_passthrough('GET', f"/v1/users/{pseudo}/quests", params={'limit': 50, 'offset': 0})

    quests = _extract_data(payload)
    if not isinstance(quests, list) or len(quests) == 0:
        return None, (jsonify({'error': 'No quest found for this user'}), 404)

    # Prefer the most progressed quest, then the biggest template.
    def _score(q):
        if not isinstance(q, dict):
            return (-1, -1)
        cs = _to_int(q.get('current_step'), default=0)
        tpl = q.get('quest_template') if isinstance(q.get('quest_template'), dict) else {}
        mc = _to_int(tpl.get('monster_count'), default=0) if isinstance(tpl, dict) else 0
        return (cs, mc)

    best = sorted(quests, key=_score, reverse=True)[0]
    slug = best.get('slug') if isinstance(best, dict) else None
    if not slug:
        return None, (jsonify({'error': 'Unable to determine quest slug'}), 404)
    return slug, None


def _fetch_all_quest_monsters(pseudo: str, slug: str, monster_type: int | None = None):
    all_monsters = []
    limit = 200
    offset = 0
    total = None

    while True:
        params = {'limit': limit, 'offset': offset}
        if monster_type is not None:
            params['monster_type'] = monster_type
        resp, payload = _api_json('GET', f"/v1/users/{pseudo}/quests/{slug}", params=params)
        if not resp.ok:
            return None, Response(resp.content, status=resp.status_code, headers=[(k, v) for k, v in resp.headers.items() if k not in {'Content-Encoding', 'Transfer-Encoding', 'Connection'}])

        data_obj = _extract_data(payload)
        if not isinstance(data_obj, dict):
            return None, (jsonify({'error': 'Unexpected quest response format'}), 502)

        monsters = data_obj.get('monsters') or []
        if not isinstance(monsters, list):
            monsters = []
        all_monsters.extend(monsters)

        pagination = data_obj.get('pagination') or {}
        if isinstance(pagination, dict):
            total = pagination.get('total', total)
        offset += len(monsters)

        if len(monsters) == 0:
            break
        if isinstance(total, int) and offset >= total:
            break
        if len(monsters) < limit:
            break

    return all_monsters, None


def _to_int(v, default=0):
    try:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return default
            return int(s)
        return int(v)
    except Exception:
        return default


def _legacy_item_to_patch(item: dict, neutral_quantity: int = 1):
    if not isinstance(item, dict):
        return None
    monster_id = item.get('monster_id', item.get('id'))
    if monster_id is None:
        return None
    monster_id = _to_int(monster_id, default=-1)
    if monster_id <= 0:
        return None

    quantity = item.get('quantity')
    if quantity is not None:
        q = _to_int(quantity, default=0)
        return {'monster_id': monster_id, 'quantity': max(0, min(30, q))}

    etat = (item.get('etat') or '').strip().lower() if isinstance(item.get('etat'), str) else ''
    quantite = item.get('quantite')

    if etat == 'recherche':
        q = max(0, neutral_quantity - 1)
    elif etat == 'aucun':
        q = neutral_quantity
    elif etat == 'propose':
        offered = _to_int(quantite, default=1)
        q = max(0, neutral_quantity + offered)
    else:
        q = _to_int(quantite, default=0)

    return {'monster_id': monster_id, 'quantity': max(0, min(30, q))}


def _as_bool(v, default=False):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {'1', 'true', 'yes', 'on', 'y'}


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


def _results_path_for_request() -> str:
    # Kept for symmetry; still a single file
    return RESULTS_FILE


def _load_results(path: str | None = None) -> dict:
    # Legacy helper: keep reading the active profile payload for compatibility
    data = _load_all_results()
    prof = data.get('activeProfile') or 'default'
    return _read_profile_payload(data, prof)


def _atomic_write(path: str, payload: dict):
    tmp = path + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _gather_all_names() -> list[str]:
    """Collect all archimonstre names from zones file to recompute derived fields."""
    try:
        with open(ZONES_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        names = []
        seen = set()
        for zone in d.get('zones', []):
            for sz in zone.get('souszones', []):
                for a in sz.get('archimonstres', []):
                    n = a.get('nom')
                    if isinstance(n, str) and n not in seen:
                        names.append(n)
                        seen.add(n)
        return names
    except Exception:
        return []


def _recompute_derived_fields(payload: dict) -> dict:
    """Given a results payload with counts, recompute a few common derived fields."""
    counts: dict = payload.get('counts') or {}
    names = _gather_all_names()
    if not names:
        # If we cannot load names, just keep counts and timestamp
        payload['needed'] = []
        payload['duplicates'] = []
        payload['totalDuplicates'] = 0
        payload['totalFound'] = sum(1 for v in counts.values() if (v or 0) >= 1)
        payload['totalFoundItems'] = sum((v or 0) for v in counts.values())
        return payload

    payload['total'] = len(names)
    needed = []
    dups = []
    for n in names:
        v = int(counts.get(n, 0) or 0)
        if v <= 0:
            needed.append(n)
        if v > 1:
            dups.append({"name": n, "count": v, "extra": max(0, v - 1)})

    payload['needed'] = needed
    payload['duplicates'] = dups
    payload['totalDuplicates'] = sum(x['extra'] for x in dups)
    payload['totalFound'] = sum(1 for n in names if int(counts.get(n, 0) or 0) >= 1)
    payload['totalFoundItems'] = sum(int(counts.get(n, 0) or 0) for n in names)
    return payload


def _normalize_validated_steps(values) -> list[int]:
    if not isinstance(values, list):
        return []
    out = set()
    for v in values:
        n = _to_int(v, default=-1)
        if n >= 1:
            out.add(n)
    return sorted(out)


@app.route('/api/results', methods=['GET'])
def get_results():
    all_data = _load_all_results()
    prof = _extract_profile_from_request()
    data = _read_profile_payload(all_data, prof)
    # Disable caching to always get fresh file
    resp = jsonify(data)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/results/update', methods=['POST'])
def update_result_count():
    body = request.get_json(silent=True) or {}
    name = body.get('name')
    if not isinstance(name, str) or not name:
        return jsonify({"error": "Invalid 'name'"}), 400
    # Either delta or set
    has_delta = 'delta' in body
    has_set = 'set' in body
    if not has_delta and not has_set:
        return jsonify({"error": "Provide 'delta' or 'set'"}), 400
    try:
        with _results_lock:
            all_data = _load_all_results()
            prof = _extract_profile_from_request()
            payload = _read_profile_payload(all_data, prof)
            counts = payload.get('counts') or {}
            old_val = int(counts.get(name, 0) or 0)
            if has_set:
                new_val = int(body.get('set'))
            else:
                new_val = old_val + int(body.get('delta'))
            new_val = max(0, int(new_val))
            counts[name] = new_val
            payload['counts'] = counts
            payload['timestamp'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
            payload = _recompute_derived_fields(payload)
            all_data = _write_profile_payload(all_data, prof, payload)
            _atomic_write(RESULTS_FILE, all_data)
            return jsonify({"ok": True, "name": name, "old": old_val, "new": new_val})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/results/reset', methods=['POST'])
def reset_results_counts():
    try:
        with _results_lock:
            all_data = _load_all_results()
            prof = _extract_profile_from_request()
            payload = _read_profile_payload(all_data, prof)
            payload['counts'] = {}
            payload['timestamp'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
            payload = _recompute_derived_fields(payload)
            all_data = _write_profile_payload(all_data, prof, payload)
            _atomic_write(RESULTS_FILE, all_data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/results/validated-steps', methods=['POST'])
def update_validated_steps():
    body = request.get_json(silent=True) or {}
    try:
        with _results_lock:
            all_data = _load_all_results()
            prof = _extract_profile_from_request()
            payload = _read_profile_payload(all_data, prof)

            current = _normalize_validated_steps(payload.get('validatedSteps') or [])
            current_set = set(current)

            # Full replace mode
            if isinstance(body.get('steps'), list):
                new_steps = _normalize_validated_steps(body.get('steps'))
            else:
                # Toggle mode
                step = _to_int(body.get('step'), default=-1)
                if step < 1:
                    return jsonify({"error": "Invalid 'step'"}), 400
                validated = body.get('validated', True)
                if bool(validated):
                    current_set.add(step)
                else:
                    current_set.discard(step)
                new_steps = sorted(current_set)

            payload['validatedSteps'] = new_steps
            payload['timestamp'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
            all_data = _write_profile_payload(all_data, prof, payload)
            _atomic_write(RESULTS_FILE, all_data)

        return jsonify({"ok": True, "validatedSteps": new_steps})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/results/trade', methods=['POST'])
def apply_trade():
    """Apply a trade by decrementing given names and incrementing received names.
    Body: { "give": [names...], "receive": [names...] }
    Returns updated results payload.
    """
    body = request.get_json(silent=True) or {}
    give = body.get('give') or []
    receive = body.get('receive') or []
    if not isinstance(give, list) or not isinstance(receive, list):
        return jsonify({"error": "'give' and 'receive' must be arrays"}), 400

    # Normalize and dedupe; only keep string names
    give_set = {str(n) for n in give if isinstance(n, str) and n.strip()}
    recv_set = {str(n) for n in receive if isinstance(n, str) and n.strip()}

    # Optional: filter to known names to prevent typos from creating keys
    valid = set(_gather_all_names())
    if valid:
        give_set = {n for n in give_set if n in valid}
        recv_set = {n for n in recv_set if n in valid}

    try:
        with _results_lock:
            all_data = _load_all_results()
            prof = _extract_profile_from_request()
            payload = _read_profile_payload(all_data, prof)
            counts = payload.get('counts') or {}

            # Decrement for given names
            for n in give_set:
                old = int(counts.get(n, 0) or 0)
                counts[n] = max(0, old - 1)

            # Increment for received names
            for n in recv_set:
                old = int(counts.get(n, 0) or 0)
                counts[n] = max(0, old) + 1

            payload['counts'] = counts
            payload['timestamp'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
            payload = _recompute_derived_fields(payload)
            all_data = _write_profile_payload(all_data, prof, payload)
            _atomic_write(RESULTS_FILE, all_data)
        # Return full updated payload (no-store)
        resp = jsonify(payload)
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/metamob/config', methods=['GET', 'POST'])
def metamob_config():
    if request.method == 'GET':
        cfg = load_config()
        safe = {k: cfg.get(k) for k in ('apiKey', 'pseudo')}
        return jsonify(safe)
    data = request.get_json(silent=True) or {}
    cfg = load_config()
    cfg.update({
        'apiKey': data.get('apiKey', cfg.get('apiKey')),
        'pseudo': data.get('pseudo', cfg.get('pseudo')),
    })
    cfg.pop('userKey', None)
    save_config(cfg)
    return jsonify({'ok': True})


def proxy_request(method, path, params=None, body=None):
    return _proxy_passthrough(method, path, params=params, body=body)


@app.route('/api/metamob/user/<pseudo>', methods=['GET'])
def get_user(pseudo):
    canonical = _resolve_username(pseudo)
    return proxy_request('GET', f"/v1/users/{canonical}")


# Alias route to match frontend fallbacks
@app.route('/api/metamob/utilisateurs/<pseudo>', methods=['GET'])
def get_user_alias(pseudo):
    canonical = _resolve_username(pseudo)
    return proxy_request('GET', f"/v1/users/{canonical}")


@app.route('/api/metamob/user/<pseudo>/monstres', methods=['GET', 'PUT'])
def user_monstres(pseudo):
    quest_slug = request.args.get('questSlug')
    canonical = _resolve_username(pseudo)

    if request.method == 'GET':
        slug, err = _resolve_quest_slug(canonical, quest_slug)
        if err is not None:
            return err

        monsters, err = _fetch_all_quest_monsters(canonical, slug, monster_type=3)
        if err is not None:
            return err

        out = []
        for m in monsters:
            if not isinstance(m, dict):
                continue
            name_obj = m.get('name') if isinstance(m.get('name'), dict) else {}
            name = name_obj.get('fr') or name_obj.get('en') or name_obj.get('es') or ''
            # v1 listing returns: quantity, offer, want (not owned/status/trade_*)
            owned = _to_int(m.get('quantity'), default=0)
            offer = _to_int(m.get('offer'), default=0)
            want = _to_int(m.get('want'), default=0)

            out.append({
                'id': m.get('id'),
                'nom': name,
                'type': 'archimonstre',
                'recherche': 1 if want > 0 else 0,
                'propose': 1 if offer > 0 else 0,
                'owned': owned,
                'status': offer - want,   # positive → propose, negative → recherche
                'trade_offer': offer,
                'trade_want': want,
                'step': m.get('step')
            })

        resp = jsonify(out)
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    # PUT
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'error': 'Invalid JSON payload'}), 400

    slug, err = _resolve_quest_slug(canonical, quest_slug)
    if err is not None:
        return err

    raw_items = None
    if isinstance(payload, dict) and isinstance(payload.get('monsters'), list):
        raw_items = payload.get('monsters')
    elif isinstance(payload, list):
        raw_items = payload
    else:
        return jsonify({'error': 'Expected an array payload or {"monsters": [...]}'}), 400

    # Determine the neutral quantity baseline from quest settings.
    # In Metamob v1, status is derived from: owned - parallel_quests.
    # So to represent legacy "aucun", we should set owned = parallel_quests.
    neutral_quantity = 1
    qresp, qpayload = _api_json('GET', f"/v1/users/{canonical}/quests/{slug}", params={'limit': 1, 'offset': 0})
    if qresp.ok:
        qdata = _extract_data(qpayload)
        if isinstance(qdata, dict):
            neutral_quantity = max(1, _to_int(qdata.get('parallel_quests'), default=1))

    patch_items = []
    for item in raw_items:
        mapped = _legacy_item_to_patch(item, neutral_quantity=neutral_quantity)
        if mapped is not None:
            patch_items.append(mapped)

    if not patch_items:
        return jsonify({'error': 'No valid monster updates found in payload'}), 400

    updated = 0
    for chunk in _chunk(patch_items, 200):
        resp, _ = _api_json('PATCH', f"/v1/quests/{slug}/monsters", body={'monsters': chunk})
        if not resp.ok:
            if resp.status_code == 404:
                return jsonify({'error': f'Quête "{slug}" non trouvée. Vérifiez que le pseudo correspond au propriétaire de la clé API configurée.'}), 403
            excluded = {'Content-Encoding', 'Transfer-Encoding', 'Connection'}
            headers_out = [(k, v) for k, v in resp.headers.items() if k not in excluded]
            return Response(resp.content, status=resp.status_code, headers=headers_out)
        updated += len(chunk)

    return jsonify({'ok': True, 'slug': slug, 'updated_count': updated})


@app.route('/api/metamob/user/<pseudo>/monstres/force-trades', methods=['POST'])
def user_monstres_force_trades(pseudo):
    """Force trade_offer for owned archimonstres in validated steps."""
    quest_slug = request.args.get('questSlug')
    canonical = _resolve_username(pseudo)
    slug, err = _resolve_quest_slug(canonical, quest_slug)
    if err is not None:
        return err

    body = request.get_json(silent=True) or {}
    validated_steps = body.get('validatedSteps', [])
    if not isinstance(validated_steps, list) or not validated_steps:
        return jsonify({'error': 'validatedSteps array required'}), 400
    validated_set = set(int(s) for s in validated_steps if isinstance(s, (int, float)))

    monsters, err = _fetch_all_quest_monsters(canonical, slug, monster_type=3)
    if err is not None:
        return err

    # Fetch parallel_quests from quest settings.
    # Metamob formula: status = quantity - parallel_quests
    # To make an archi "proposé" automatically, we add a fictitious +1 to quantity
    # so that status = (quantity + 1) - parallel_quests > 0.
    # Example: qty=1, parallel_quests=1 → send qty=2 → status=2-1=1 → proposé
    parallel_quests = 1
    qresp, qpayload = _api_json('GET', f"/v1/users/{canonical}/quests/{slug}", params={'limit': 1, 'offset': 0})
    if qresp.ok:
        qdata = _extract_data(qpayload)
        if isinstance(qdata, dict):
            parallel_quests = max(1, _to_int(qdata.get('parallel_quests'), default=1))

    # Find archimonstres in validated steps with quantity > 0
    targets = []
    for m in monsters:
        if not isinstance(m, dict):
            continue
        step = _to_int(m.get('step'), default=0)
        qty = _to_int(m.get('quantity'), default=0)
        mid = _to_int(m.get('id'), default=-1)
        if step in validated_set and qty > 0 and mid > 0:
            # Add parallel_quests so status becomes positive → proposé auto
            new_qty = min(30, qty + parallel_quests)
            targets.append({'monster_id': mid, 'quantity': new_qty})

    if not targets:
        return jsonify({'ok': True, 'slug': slug, 'forced': 0, 'total_targets': 0, 'message': 'Aucun archi à forcer (0 possédé dans les étapes validées).'})

    # Batch update quantities via /monsters endpoint (no rate limit needed)
    forced = 0
    errors = []
    for chunk in _chunk(targets, 200):
        resp, _ = _api_json('PATCH', f"/v1/quests/{slug}/monsters", body={'monsters': chunk})
        if resp.ok:
            forced += len(chunk)
        else:
            errors.append({'status': getattr(resp, 'status_code', 0), 'count': len(chunk)})

    result = {'ok': True, 'slug': slug, 'forced': forced, 'total_targets': len(targets)}
    if errors:
        result['errors'] = errors[:5]
    return jsonify(result)


@app.route('/api/metamob/quest-settings/<pseudo>', methods=['GET', 'PATCH'])
def quest_settings(pseudo):
    """GET: fetch quest settings.  PATCH: update quest parameters."""
    quest_slug = request.args.get('questSlug')
    canonical = _resolve_username(pseudo)
    slug, err = _resolve_quest_slug(canonical, quest_slug)
    if err is not None:
        return err

    if request.method == 'GET':
        resp, payload = _api_json(
            'GET', f"/v1/users/{canonical}/quests/{slug}",
            params={'limit': 1, 'offset': 0})
        if not resp.ok:
            excluded = {'Content-Encoding', 'Transfer-Encoding', 'Connection'}
            headers_out = [(k, v) for k, v in resp.headers.items() if k not in excluded]
            return Response(resp.content, status=resp.status_code, headers=headers_out)
        qdata = _extract_data(payload)
        if not isinstance(qdata, dict):
            return jsonify({'error': 'Unexpected response format'}), 502
        FIELDS = [
            'slug', 'character_name', 'parallel_quests', 'current_step',
            'show_trades', 'trade_mode',
            'trade_offer_threshold', 'trade_want_threshold',
            'never_offer_normal', 'never_want_normal',
            'never_offer_boss', 'never_want_boss',
            'never_offer_arch', 'never_want_arch',
        ]
        out = {k: qdata.get(k) for k in FIELDS}
        return jsonify(out)

    # PATCH
    body = request.get_json(silent=True) or {}
    # NOTE: current_step is excluded — Metamob API returns 500 when it is sent (their bug)
    ALLOWED = {
        'character_name', 'parallel_quests', 'show_trades',
        'trade_mode', 'trade_offer_threshold', 'trade_want_threshold',
        'never_offer_normal', 'never_want_normal',
        'never_offer_boss', 'never_want_boss',
        'never_offer_arch', 'never_want_arch',
    }
    patch_body = {k: v for k, v in body.items() if k in ALLOWED}
    if not patch_body:
        return jsonify({'error': 'No valid fields to update'}), 400

    resp, payload = _api_json('PATCH', f"/v1/quests/{slug}", body=patch_body)
    if not resp.ok:
        if resp.status_code == 404:
            return jsonify({'error': f'Quête "{slug}" non trouvée. Vérifiez que le pseudo correspond au propriétaire de la clé API configurée.'}), 403
        excluded = {'Content-Encoding', 'Transfer-Encoding', 'Connection'}
        headers_out = [(k, v) for k, v in resp.headers.items() if k not in excluded]
        return Response(resp.content, status=resp.status_code, headers=headers_out)
    return jsonify(_extract_data(payload) or {'ok': True})


@app.route('/api/metamob/user/<pseudo>/monstres/reinitialiser', methods=['PUT'])
def user_monstres_reset(pseudo):
    quest_slug = request.args.get('questSlug')
    canonical = _resolve_username(pseudo)
    slug, err = _resolve_quest_slug(canonical, quest_slug)
    if err is not None:
        return err

    monsters, err = _fetch_all_quest_monsters(canonical, slug, monster_type=3)
    if err is not None:
        return err

    reset_items = []
    for m in monsters:
        if not isinstance(m, dict):
            continue
        mid = _to_int(m.get('id'), default=-1)
        if mid > 0:
            reset_items.append({'monster_id': mid, 'quantity': 0})

    if not reset_items:
        return jsonify({'ok': True, 'slug': slug, 'updated_count': 0})

    updated = 0
    for chunk in _chunk(reset_items, 200):
        resp, _ = _api_json('PATCH', f"/v1/quests/{slug}/monsters", body={'monsters': chunk})
        if not resp.ok:
            excluded = {'Content-Encoding', 'Transfer-Encoding', 'Connection'}
            headers_out = [(k, v) for k, v in resp.headers.items() if k not in excluded]
            return Response(resp.content, status=resp.status_code, headers=headers_out)
        updated += len(chunk)

    return jsonify({'ok': True, 'slug': slug, 'updated_count': updated})


@app.route('/api/metamob/monstres', methods=['GET'])
def list_monstres():
    params = dict(request.args)
    return proxy_request('GET', '/v1/monsters', params=params)


@app.route('/api/local/tools/status', methods=['GET'])
def local_tools_status():
    with _tool_lock:
        _clean_tool_refs()
        return jsonify({
            'scan': {
                'running': _tool_is_running(_scan_proc),
                'pid': _scan_proc.pid if _tool_is_running(_scan_proc) else None,
            },
        })


@app.route('/api/local/scan/start', methods=['POST'])
def local_scan_start():
    global _scan_proc
    body = request.get_json(silent=True) or {}
    profile = _safe_profile(body.get('profile')) or _extract_profile_from_request()
    with _tool_lock:
        _clean_tool_refs()
        if _tool_is_running(_scan_proc):
            return jsonify({'ok': False, 'error': 'Scan already running', 'pid': _scan_proc.pid}), 409
        _scan_proc = _spawn_tool('scan.py', os.path.dirname(__file__), profile)
        return jsonify({'ok': True, 'pid': _scan_proc.pid, 'profile': profile})


@app.route('/api/local/scan/stop', methods=['POST'])
def local_scan_stop():
    global _scan_proc
    with _tool_lock:
        _clean_tool_refs()
        if not _tool_is_running(_scan_proc):
            return jsonify({'ok': True, 'stopped': False, 'message': 'Scan not running'})
        _scan_proc.terminate()
        return jsonify({'ok': True, 'stopped': True})


@app.route('/<path:path>')
def serve_static(path):
    # Serve any other static asset
    return send_from_directory('.', path)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
