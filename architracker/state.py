from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import reflex as rx
import requests


APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ZONES_FILE = DATA_DIR / "archimonstres_par_zone.json"
RESULTS_FILE = DATA_DIR / "results.json"
CHARACTERS_FILE = DATA_DIR / "characters.json"
CONFIG_FILE = DATA_DIR / "metamob.config.json"
SCAN_SCRIPT = APP_ROOT / "scripts" / "scan.py"
LOG_DIR = APP_ROOT / "logs"
METAMOB_BASE_URL = "https://www.metamob.fr/api"

FILE_LOCK = threading.Lock()
DEFAULT_PROFILE = "kourial"
SCAN_STAGING_PROFILE = "__scan_staging__"
DEFAULT_SERVERS = [
    "Dakal",
    "Kourial",
    "Mikhal",
    "Brial",
    "Rafal",
    "Salar",
    "Hell Mina",
    "Imagiro",
    "Orukam",
    "Tal Kasha",
    "Tylezia",
    "Ombre",
]


def _to_int(value, default=0) -> int:
    try:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return default
            return int(stripped)
        return int(value)
    except Exception:
        return default


def _chunk(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _safe_profile(name: str | None) -> str:
    if not name:
        return DEFAULT_PROFILE
    value = name.strip().lower()
    cleaned = "".join(char for char in value if char.isalnum() or char in {"_", "-"})
    return cleaned or DEFAULT_PROFILE


def _profile_label(server: str, name: str) -> str:
    return f"{server} - {name}"


def _load_characters() -> list[dict]:
    chars: list[dict] = []
    if CHARACTERS_FILE.exists():
        try:
            raw = json.loads(CHARACTERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                cid = _safe_profile(str(item.get("id", "") or ""))
                name = str(item.get("name", "") or "").strip()
                server = str(item.get("server", "") or "").strip()
                if cid and name and server:
                    chars.append({"id": cid, "name": name, "server": server})

    if chars:
        return chars

    legacy_profiles = sorted((_load_all_results().get("profiles") or {}).keys())
    chars = [
        {"id": _safe_profile(pid), "name": str(pid).strip().title(), "server": "Other"}
        for pid in legacy_profiles
        if pid and pid != SCAN_STAGING_PROFILE
    ]
    if not chars:
        chars = [
            {"id": "kourial", "name": "Kourial", "server": "Kourial"},
            {"id": "mikhal", "name": "Mikhal", "server": "Mikhal"},
        ]
    _save_characters(chars)
    return chars


def _save_characters(characters: list[dict]) -> None:
    sanitized: list[dict] = []
    for char in characters:
        if not isinstance(char, dict):
            continue
        cid = _safe_profile(str(char.get("id", "") or ""))
        name = str(char.get("name", "") or "").strip()
        server = str(char.get("server", "") or "").strip()
        if cid and name and server:
            sanitized.append({"id": cid, "name": name, "server": server})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTERS_FILE.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_for_search(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _normalize_for_tokens(value: str) -> str:
    base = _normalize_for_search(value or "")
    out = []
    for char in base:
        out.append(char if char.isalnum() else " ")
    return " ".join("".join(out).split())


def _load_all_results() -> dict:
    if RESULTS_FILE.exists():
        try:
            raw = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    else:
        raw = {}

    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        return raw

    if isinstance(raw, dict) and "counts" in raw:
        return {"profiles": {"default": raw}, "activeProfile": "default", **raw}

    return {"profiles": {}, "activeProfile": "kourial"}


def _read_profile_payload(data: dict, profile: str) -> dict:
    payload = (data.get("profiles") or {}).get(profile)
    if isinstance(payload, dict):
        return payload
    return {"counts": {}, "validatedSteps": [], "timestamp": datetime.now(timezone.utc).isoformat()}


def _write_profile_payload(data: dict, profile: str, payload: dict) -> dict:
    profiles = data.get("profiles") or {}
    profiles[profile] = payload
    data["profiles"] = profiles
    data["activeProfile"] = profile
    for key in list(data.keys()):
        if key not in {"profiles", "activeProfile"}:
            del data[key]
    data.update(payload)
    return data


def _load_monsters() -> tuple[list[dict], list[str], list[int]]:
    raw = json.loads(ZONES_FILE.read_text(encoding="utf-8"))
    monsters: list[dict] = []
    souszones: set[str] = set()
    steps: set[int] = set()

    for zone in raw.get("zones", []):
        zone_name = zone.get("zone", "")
        for souszone_payload in zone.get("souszones", []):
            souszone = souszone_payload.get("souszone", "")
            souszones.add(souszone)
            for archi in souszone_payload.get("archimonstres", []):
                step = int(archi.get("etape", 0))
                steps.add(step)
                monsters.append(
                    {
                        "id": int(archi.get("id", 0)),
                        "name": archi.get("nom", ""),
                        "step": step,
                        "zone": zone_name,
                        "souszone": souszone,
                        "image_url": archi.get("image_url", ""),
                    }
                )
    return monsters, sorted(souszones), sorted(steps)


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        loaded = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _save_config(config: dict) -> None:
    payload = config if isinstance(config, dict) else {}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_metamob_headers() -> tuple[dict, str]:
    cfg = _load_config()
    if not isinstance(cfg, dict):
        cfg = {}
    api_key = str(cfg.get("apiKey", "") or "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers, api_key


def _api_json(method: str, path: str, params: dict | None = None, body: dict | list | None = None):
    headers, _ = _build_metamob_headers()
    url = f"{METAMOB_BASE_URL}{path}"
    try:
        resp = requests.request(method, url, headers=headers, params=params, json=body, timeout=25)
    except requests.exceptions.RequestException as exc:
        return None, {"error": f"Metamob API unreachable: {exc}"}

    payload = None
    try:
        payload = resp.json()
    except Exception:
        payload = None
    return resp, payload


def _extract_data(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _resolve_username(pseudo: str) -> str:
    raw = (pseudo or "").strip()
    if not raw:
        return raw

    resp, _ = _api_json("GET", f"/v1/users/{raw}")
    if resp is not None and resp.ok:
        return raw

    resp, payload = _api_json("GET", "/v1/users/search", params={"q": raw, "limit": 50, "offset": 0})
    if resp is None or not resp.ok:
        return raw

    data = _extract_data(payload)
    if not isinstance(data, list):
        return raw

    wanted = raw.casefold()
    for item in data:
        if not isinstance(item, dict):
            continue
        username = item.get("username")
        if isinstance(username, str) and username.casefold() == wanted:
            return username

    for item in data:
        if not isinstance(item, dict):
            continue
        username = item.get("username")
        if isinstance(username, str) and wanted in username.casefold():
            return username

    return raw


def _resolve_quest_slug(username: str, explicit_slug: str | None = None) -> tuple[str | None, str | None]:
    if explicit_slug:
        return explicit_slug, None
    resp, payload = _api_json("GET", f"/v1/users/{username}/quests", params={"limit": 50, "offset": 0})
    if resp is None:
        return None, "Metamob API unreachable while loading quests."
    if not resp.ok:
        return None, f"Failed to load quests: HTTP {resp.status_code}"

    quests = _extract_data(payload)
    if not isinstance(quests, list) or not quests:
        return None, "No quest found for this user."

    def _score(quest):
        if not isinstance(quest, dict):
            return (-1, -1)
        current_step = _to_int(quest.get("current_step"), default=0)
        template = quest.get("quest_template") if isinstance(quest.get("quest_template"), dict) else {}
        monster_count = _to_int(template.get("monster_count"), default=0) if isinstance(template, dict) else 0
        return current_step, monster_count

    best = sorted(quests, key=_score, reverse=True)[0]
    slug = best.get("slug") if isinstance(best, dict) else None
    if not slug:
        return None, "Unable to determine quest slug."
    return str(slug), None


def _fetch_all_quest_monsters(username: str, slug: str, monster_type: int | None = None) -> tuple[list[dict] | None, str | None]:
    monsters: list[dict] = []
    limit = 200
    offset = 0
    total = None

    while True:
        params = {"limit": limit, "offset": offset}
        if monster_type is not None:
            params["monster_type"] = monster_type
        resp, payload = _api_json("GET", f"/v1/users/{username}/quests/{slug}", params=params)
        if resp is None:
            return None, "Metamob API unreachable while loading monsters."
        if not resp.ok:
            return None, f"Failed to load monsters: HTTP {resp.status_code}"

        data = _extract_data(payload)
        if not isinstance(data, dict):
            return None, "Unexpected quest response format."

        page_monsters = data.get("monsters") or []
        if not isinstance(page_monsters, list):
            page_monsters = []
        monsters.extend(page_monsters)

        pagination = data.get("pagination") or {}
        if isinstance(pagination, dict):
            total = pagination.get("total", total)
        offset += len(page_monsters)

        if len(page_monsters) == 0:
            break
        if isinstance(total, int) and offset >= total:
            break
        if len(page_monsters) < limit:
            break

    return monsters, None


class TrackerState(rx.State):
    profile: str = DEFAULT_PROFILE
    active_tab: str = "tracker"
    active_filter: str = "all"
    active_step: int = 0
    active_souszone: str = "all"
    search_query: str = ""

    monsters: list[dict] = []
    souszones: list[str] = []
    steps: list[int] = []
    counts: dict[str, int] = {}
    validated_steps: list[int] = []

    tool_status: str = "Scanner status unknown"
    scan_status_tone: str = "neutral"
    scan_status_updated_at: str = ""
    scan_pid: int = 0
    scanner_mode: str = "scan"

    mm_pseudo: str = ""
    mm_api_key: str = ""
    mm_body: str = ""
    mm_status: str = ""
    last_updated: str = ""
    mm_settings_loaded: bool = False
    mm_qs_character_name: str = ""
    mm_qs_parallel_quests: str = "1"
    mm_qs_current_step: str = "1"
    mm_qs_trade_mode: str = "0"
    mm_qs_offer_threshold: str = ""
    mm_qs_want_threshold: str = ""
    mm_qs_show_trades: bool = True
    mm_qs_never_offer_normal: bool = False
    mm_qs_never_want_normal: bool = False
    mm_qs_never_offer_boss: bool = False
    mm_qs_never_want_boss: bool = False
    mm_qs_never_offer_arch: bool = False
    mm_qs_never_want_arch: bool = False
    trade_offer_mode: str = "dup"
    other_pseudo: str = ""
    other_ingame: str = ""
    other_wants_text: str = ""
    other_offers_text: str = ""
    compare_give: list[str] = []
    compare_receive: list[str] = []
    selected_give: list[str] = []
    selected_receive: list[str] = []
    trade_status: str = ""

    characters: list[dict] = []
    selected_server: str = "all"
    new_character_server: str = "Dakal"
    new_character_name: str = ""
    character_status: str = ""

    scan_assign_profile: str = ""
    scan_result_ready: bool = False

    @rx.event
    def initialize(self):
        self.monsters, self.souszones, self.steps = _load_monsters()
        self.characters = _load_characters()
        self._ensure_profile_selection()
        self._load_profile_data()
        cfg = _load_config()
        if not isinstance(cfg, dict):
            cfg = {}
        self.mm_pseudo = str(cfg.get("pseudo", "") or "")
        self.mm_api_key = str(cfg.get("apiKey", "") or "")
        self.scan_assign_profile = self.profile
        self.refresh_scan_status()

    def _ensure_profile_selection(self):
        available = {char["id"] for char in self.characters if isinstance(char, dict) and char.get("id")}
        if self.profile in available:
            return
        if available:
            self.profile = sorted(available)[0]
            return
        self.profile = DEFAULT_PROFILE

    def _find_character(self, profile_id: str) -> dict | None:
        for char in self.characters:
            if isinstance(char, dict) and str(char.get("id")) == profile_id:
                return char
        return None

    @rx.var
    def server_options(self) -> list[str]:
        servers = sorted({str(c.get("server")) for c in self.characters if isinstance(c, dict) and c.get("server")})
        ordered = [srv for srv in DEFAULT_SERVERS if srv in servers]
        extras = [srv for srv in servers if srv not in ordered]
        return ["all"] + ordered + extras

    @rx.var
    def new_character_server_options(self) -> list[str]:
        return DEFAULT_SERVERS

    @rx.var
    def character_cards(self) -> list[dict]:
        if self.selected_server == "all":
            return self.characters
        return [char for char in self.characters if str(char.get("server")) == self.selected_server]

    @rx.var
    def quest_selector_options(self) -> list[str]:
        source = self.characters if self.selected_server == "all" else self.character_cards
        labels: list[str] = []
        for char in source:
            if not isinstance(char, dict):
                continue
            labels.append(_profile_label(str(char.get("server", "")), str(char.get("name", ""))))
        return labels

    @rx.var
    def current_profile_label(self) -> str:
        match = self._find_character(self.profile)
        if not match:
            return self.profile
        return _profile_label(str(match.get("server", "")), str(match.get("name", "")))

    @rx.var
    def current_character_name(self) -> str:
        match = self._find_character(self.profile)
        if not match:
            return ""
        return str(match.get("name", ""))

    @rx.var
    def scan_assign_options(self) -> list[str]:
        labels: list[str] = []
        for char in self.characters:
            if not isinstance(char, dict):
                continue
            labels.append(_profile_label(str(char.get("server", "")), str(char.get("name", ""))))
        return labels

    @rx.var
    def scan_assign_label(self) -> str:
        match = self._find_character(self.scan_assign_profile)
        if not match:
            return ""
        return _profile_label(str(match.get("server", "")), str(match.get("name", "")))

    def _effective_mm_pseudo(self) -> str:
        return (self.current_character_name or "").strip()

    def _load_profile_data(self):
        all_data = _load_all_results()
        payload = _read_profile_payload(all_data, self.profile)
        loaded_counts = payload.get("counts") or {}
        self.counts = {str(k): int(v) for k, v in loaded_counts.items() if isinstance(v, (int, float))}
        self.validated_steps = sorted(
            {int(v) for v in (payload.get("validatedSteps") or []) if isinstance(v, (int, float)) and int(v) >= 1}
        )
        self.last_updated = str(payload.get("timestamp", ""))

    def _save_profile_data(self):
        payload = {
            "counts": self.counts,
            "validatedSteps": self.validated_steps,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scanned": len(self.counts),
            "total": len(self.monsters),
        }
        with FILE_LOCK:
            all_data = _load_all_results()
            all_data = _write_profile_payload(all_data, self.profile, payload)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            RESULTS_FILE.write_text(json.dumps(all_data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.last_updated = payload["timestamp"]

    @rx.event
    def set_active_tab(self, tab: str):
        self.active_tab = "scanner" if tab == "scan" or tab == "pack" else tab

    @rx.event
    def set_profile(self, profile: str):
        next_profile = _safe_profile(profile)
        if not self._find_character(next_profile):
            self.character_status = "Selected quest is not linked to a character."
            return
        self.profile = next_profile
        self.scan_assign_profile = next_profile
        self._load_profile_data()

    @rx.event
    def set_profile_from_label(self, label: str):
        for char in self.characters:
            if not isinstance(char, dict):
                continue
            if _profile_label(str(char.get("server", "")), str(char.get("name", ""))) == label:
                profile_id = str(char.get("id", ""))
                self.profile = profile_id
                self.scan_assign_profile = profile_id
                self._load_profile_data()
                return

    @rx.event
    def set_scan_assign_from_label(self, label: str):
        for char in self.characters:
            if not isinstance(char, dict):
                continue
            if _profile_label(str(char.get("server", "")), str(char.get("name", ""))) == label:
                self.scan_assign_profile = str(char.get("id", ""))
                return

    @rx.event
    def set_selected_server(self, server: str):
        self.selected_server = server if server in self.server_options else "all"
        filtered_ids = {str(char.get("id")) for char in self.character_cards}
        if self.profile not in filtered_ids and filtered_ids:
            self.profile = sorted(filtered_ids)[0]
            self._load_profile_data()

    @rx.event
    def set_new_character_server(self, server: str):
        self.new_character_server = server if server in DEFAULT_SERVERS else DEFAULT_SERVERS[0]

    @rx.event
    def set_new_character_name(self, value: str):
        self.new_character_name = value

    @rx.event
    def add_character(self):
        name = (self.new_character_name or "").strip()
        server = (self.new_character_server or "").strip() or DEFAULT_SERVERS[0]
        if not name:
            self.character_status = "Character name is required."
            return
        base_id = _safe_profile(f"{server}_{name}")
        next_id = base_id
        taken = {str(c.get("id")) for c in self.characters if isinstance(c, dict)}
        suffix = 2
        while next_id in taken:
            next_id = f"{base_id}_{suffix}"
            suffix += 1
        self.characters = self.characters + [{"id": next_id, "name": name, "server": server}]
        _save_characters(self.characters)
        self.profile = next_id
        self.scan_assign_profile = next_id
        self.new_character_name = ""
        self.character_status = f"Character '{name}' added on {server}."
        self._load_profile_data()

    @rx.event
    def remove_character(self, profile_id: str):
        target = _safe_profile(profile_id)
        if not self._find_character(target):
            return
        if len(self.characters) <= 1:
            self.character_status = "At least one character must remain."
            return
        self.characters = [char for char in self.characters if str(char.get("id")) != target]
        _save_characters(self.characters)
        if self.profile == target:
            self._ensure_profile_selection()
            self._load_profile_data()
        if self.scan_assign_profile == target:
            self.scan_assign_profile = self.profile
        self.character_status = "Character removed."

    @rx.event
    def set_active_filter(self, value: str):
        self.active_filter = value

    @rx.event
    def set_active_souszone(self, value: str):
        self.active_souszone = value

    @rx.event
    def set_active_step(self, value: int):
        self.active_step = value

    @rx.event
    def set_search_query(self, value: str):
        self.search_query = value

    @rx.event
    def reset_filters(self):
        self.active_filter = "all"
        self.active_step = 0
        self.active_souszone = "all"
        self.search_query = ""

    @rx.event
    def update_quantity(self, name: str, delta: int):
        current = int(self.counts.get(name, 0))
        self.counts[name] = max(0, current + int(delta))
        self._save_profile_data()

    @rx.event
    def validate_active_step(self):
        if self.active_step > 0 and self.active_step not in self.validated_steps:
            self.validated_steps = sorted(self.validated_steps + [self.active_step])
            self._save_profile_data()

    @rx.event
    def unvalidate_active_step(self):
        if self.active_step > 0 and self.active_step in self.validated_steps:
            self.validated_steps = [step for step in self.validated_steps if step != self.active_step]
            self._save_profile_data()

    @rx.event
    def refresh_scan_status(self):
        if self.scan_pid and self._is_pid_running(self.scan_pid):
            self._set_scan_status(f"Scan running (pid {self.scan_pid})", "running")
            return
        was_running = self.scan_pid != 0
        self.scan_pid = 0
        if was_running:
            self._set_scan_status(f"Scan finished for selected character: {self.current_profile_label}.", "warning")
            return
        self._set_scan_status("Scan stopped", "neutral")

    def _set_scan_status(self, message: str, tone: str = "neutral"):
        self.tool_status = message
        self.scan_status_tone = tone
        self.scan_status_updated_at = datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def _is_pid_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    @rx.event
    def start_scan(self, pack_mode: bool = False):
        if self.scan_pid and self._is_pid_running(self.scan_pid):
            self._set_scan_status(f"Scan already running (pid {self.scan_pid})", "running")
            return
        if not SCAN_SCRIPT.exists():
            self._set_scan_status(f"scan.py not found at {SCAN_SCRIPT}", "error")
            return
        env = dict(os.environ)
        env["ARCHI_PROFILE"] = self.profile
        env["ARCHI_BASE_DIR"] = str(DATA_DIR)
        env["ARCHI_PACK_MODE"] = "1" if pack_mode else "0"
        env["PYTHONUNBUFFERED"] = "1"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        out_log = LOG_DIR / "scan.out.log"
        err_log = LOG_DIR / "scan.err.log"
        proc = subprocess.Popen(
            [sys.executable, str(SCAN_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=open(out_log, "a", encoding="utf-8"),
            stderr=open(err_log, "a", encoding="utf-8"),
        )
        time.sleep(0.7)
        if proc.poll() is not None:
            self.scan_pid = 0
            self._set_scan_status(f"Scan failed to start. Check {err_log}", "error")
            return
        self.scan_pid = int(proc.pid)
        if not self.scan_assign_profile:
            self.scan_assign_profile = self.profile
        self._set_scan_status(
            f"{'Pack runner' if pack_mode else 'Scan'} started for {self.current_profile_label} (pid {self.scan_pid})",
            "running",
        )

    @rx.event
    def stop_scan(self):
        if not self.scan_pid:
            self._set_scan_status("No scan process to stop", "warning")
            return
        try:
            os.kill(self.scan_pid, signal.SIGTERM)
            self._set_scan_status(f"Stop signal sent to scan (pid {self.scan_pid})", "warning")
        except Exception as err:
            self._set_scan_status(f"Failed to stop scan: {err}", "error")
        self.scan_pid = 0

    @rx.event
    def assign_scan_to_character(self):
        target = _safe_profile(self.scan_assign_profile or self.profile)
        if not self._find_character(target):
            self._set_scan_status("Pick a valid character before assigning scan data.", "error")
            return

        all_data = _load_all_results()
        staging = _read_profile_payload(all_data, SCAN_STAGING_PROFILE)
        counts = staging.get("counts") if isinstance(staging, dict) else None
        if not isinstance(counts, dict) or not counts:
            self._set_scan_status("No completed scan data found to assign.", "error")
            return

        payload = dict(staging)
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        all_data = _write_profile_payload(all_data, target, payload)
        profiles = all_data.get("profiles") or {}
        if isinstance(profiles, dict) and SCAN_STAGING_PROFILE in profiles:
            del profiles[SCAN_STAGING_PROFILE]
            all_data["profiles"] = profiles
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RESULTS_FILE.write_text(json.dumps(all_data, ensure_ascii=False, indent=2), encoding="utf-8")

        self.profile = target
        self.scan_result_ready = False
        self._load_profile_data()
        character = self._find_character(target)
        label = _profile_label(str(character.get("server", "")), str(character.get("name", ""))) if character else target
        self._set_scan_status(f"Scan data assigned to {label}.", "running")

    @rx.event
    def start_pack_runner(self):
        self.start_scan(pack_mode=True)

    @rx.event
    def set_scanner_mode(self, mode: str):
        self.scanner_mode = "pack" if mode == "pack" else "scan"

    @rx.event
    def start_scanner(self):
        if self.scanner_mode == "pack":
            self.start_pack_runner()
        else:
            self.start_scan()

    @rx.event
    def set_mm_pseudo(self, value: str):
        self.mm_pseudo = value

    @rx.event
    def set_mm_api_key(self, value: str):
        self.mm_api_key = value

    @rx.event
    def save_mm_api_key(self):
        value = (self.mm_api_key or "").strip()
        cfg = _load_config()
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["apiKey"] = value
        _save_config(cfg)
        self.mm_status = "Metamob API key saved."

    @rx.event
    def set_mm_body(self, value: str):
        self.mm_body = value

    @rx.event
    def generate_mm_body(self):
        monsters = [{"monster_id": m["id"], "quantity": int(self.counts.get(m["name"], 0))} for m in self.monsters]
        self.mm_body = json.dumps({"monsters": monsters}, ensure_ascii=False, indent=2)
        self.mm_status = f"Generated {len(monsters)} monsters in API v1 format."

    @rx.event
    def send_metamob_update(self):
        pseudo = self._effective_mm_pseudo()
        if not pseudo:
            self.mm_status = "No selected character available for Metamob pseudo."
            return
        headers, api_key = _build_metamob_headers()
        if not api_key:
            self.mm_status = "Metamob API key missing in metamob.config.json."
            return
        if not (self.mm_body or "").strip():
            self.mm_status = "JSON body is empty."
            return

        try:
            payload = json.loads(self.mm_body)
        except Exception as err:
            self.mm_status = f"Invalid JSON: {err}"
            return

        raw_items = payload.get("monsters") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            self.mm_status = 'Expected payload as [{"monster_id","quantity"}] or {"monsters":[...]}'
            return

        username = _resolve_username(pseudo)
        slug, err = _resolve_quest_slug(username)
        if err or not slug:
            self.mm_status = err or "Unable to resolve quest."
            return

        patch_items: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            monster_id = _to_int(item.get("monster_id", item.get("id")), default=-1)
            if monster_id <= 0:
                continue
            quantity = _to_int(item.get("quantity"), default=0)
            patch_items.append({"monster_id": monster_id, "quantity": max(0, min(30, quantity))})

        if not patch_items:
            self.mm_status = "No valid monster updates found in payload."
            return

        updated = 0
        for chunk in _chunk(patch_items, 200):
            resp, _ = _api_json("PATCH", f"/v1/quests/{slug}/monsters", body={"monsters": chunk})
            if resp is None:
                self.mm_status = "Metamob API unreachable."
                return
            if not resp.ok:
                self.mm_status = f"Update failed: HTTP {resp.status_code}"
                return
            updated += len(chunk)

        self.mm_status = f"Profile updated: {updated} monsters patched."

    @rx.event
    def force_validated_trades(self):
        pseudo = self._effective_mm_pseudo()
        if not pseudo:
            self.mm_status = "No selected character available for Metamob pseudo."
            return
        headers, api_key = _build_metamob_headers()
        if not api_key:
            self.mm_status = "Metamob API key missing in metamob.config.json."
            return
        if not self.validated_steps:
            self.mm_status = "No validated steps selected in tracker."
            return

        username = _resolve_username(pseudo)
        slug, err = _resolve_quest_slug(username)
        if err or not slug:
            self.mm_status = err or "Unable to resolve quest."
            return

        monsters, err = _fetch_all_quest_monsters(username, slug, monster_type=3)
        if err or monsters is None:
            self.mm_status = err or "Unable to load quest monsters."
            return

        qresp, qpayload = _api_json("GET", f"/v1/users/{username}/quests/{slug}", params={"limit": 1, "offset": 0})
        parallel_quests = 1
        if qresp is not None and qresp.ok:
            qdata = _extract_data(qpayload)
            if isinstance(qdata, dict):
                parallel_quests = max(1, _to_int(qdata.get("parallel_quests"), default=1))

        validated_set = set(int(step) for step in self.validated_steps)
        targets: list[dict] = []
        for monster in monsters:
            if not isinstance(monster, dict):
                continue
            step = _to_int(monster.get("step"), default=0)
            qty = _to_int(monster.get("quantity"), default=0)
            monster_id = _to_int(monster.get("id"), default=-1)
            if step in validated_set and qty > 0 and monster_id > 0:
                targets.append({"monster_id": monster_id, "quantity": min(30, qty + parallel_quests)})

        if not targets:
            self.mm_status = "No owned archimonsters in validated steps to force."
            return

        forced = 0
        for chunk in _chunk(targets, 200):
            resp, _ = _api_json("PATCH", f"/v1/quests/{slug}/monsters", body={"monsters": chunk})
            if resp is None:
                self.mm_status = "Metamob API unreachable."
                return
            if not resp.ok:
                self.mm_status = f"Force trades failed: HTTP {resp.status_code}"
                return
            forced += len(chunk)

        self.mm_status = f"Forced offers on {forced}/{len(targets)} monsters."

    @rx.event
    def reset_metamob_monsters(self):
        pseudo = self._effective_mm_pseudo()
        if not pseudo:
            self.mm_status = "No selected character available for Metamob pseudo."
            return
        headers, api_key = _build_metamob_headers()
        if not api_key:
            self.mm_status = "Metamob API key missing in metamob.config.json."
            return

        username = _resolve_username(pseudo)
        slug, err = _resolve_quest_slug(username)
        if err or not slug:
            self.mm_status = err or "Unable to resolve quest."
            return

        monsters, err = _fetch_all_quest_monsters(username, slug, monster_type=3)
        if err or monsters is None:
            self.mm_status = err or "Unable to load quest monsters."
            return

        reset_items: list[dict] = []
        for monster in monsters:
            monster_id = _to_int(monster.get("id"), default=-1) if isinstance(monster, dict) else -1
            if monster_id > 0:
                reset_items.append({"monster_id": monster_id, "quantity": 0})

        updated = 0
        for chunk in _chunk(reset_items, 200):
            resp, _ = _api_json("PATCH", f"/v1/quests/{slug}/monsters", body={"monsters": chunk})
            if resp is None:
                self.mm_status = "Metamob API unreachable."
                return
            if not resp.ok:
                self.mm_status = f"Reset failed: HTTP {resp.status_code}"
                return
            updated += len(chunk)

        self.mm_status = f"Profile reset complete: {updated} monsters."

    @rx.event
    def load_quest_settings(self):
        pseudo = self._effective_mm_pseudo()
        if not pseudo:
            self.mm_status = "No selected character available for Metamob pseudo."
            return
        _, api_key = _build_metamob_headers()
        if not api_key:
            self.mm_status = "Metamob API key missing in metamob.config.json."
            return

        username = _resolve_username(pseudo)
        slug, err = _resolve_quest_slug(username)
        if err or not slug:
            self.mm_status = err or "Unable to resolve quest."
            return

        resp, payload = _api_json("GET", f"/v1/users/{username}/quests/{slug}", params={"limit": 1, "offset": 0})
        if resp is None:
            self.mm_status = "Metamob API unreachable."
            return
        if not resp.ok:
            self.mm_status = f"Failed to load settings: HTTP {resp.status_code}"
            return

        data = _extract_data(payload)
        if not isinstance(data, dict):
            self.mm_status = "Unexpected quest settings response."
            return

        self.mm_qs_character_name = str(data.get("character_name", "") or "")
        self.mm_qs_parallel_quests = str(_to_int(data.get("parallel_quests"), default=1))
        self.mm_qs_current_step = str(_to_int(data.get("current_step"), default=1))
        self.mm_qs_trade_mode = str(_to_int(data.get("trade_mode"), default=0))
        self.mm_qs_offer_threshold = (
            "" if data.get("trade_offer_threshold") in (None, "") else str(_to_int(data.get("trade_offer_threshold")))
        )
        self.mm_qs_want_threshold = (
            "" if data.get("trade_want_threshold") in (None, "") else str(_to_int(data.get("trade_want_threshold")))
        )
        self.mm_qs_show_trades = bool(data.get("show_trades", True))
        self.mm_qs_never_offer_normal = bool(data.get("never_offer_normal"))
        self.mm_qs_never_want_normal = bool(data.get("never_want_normal"))
        self.mm_qs_never_offer_boss = bool(data.get("never_offer_boss"))
        self.mm_qs_never_want_boss = bool(data.get("never_want_boss"))
        self.mm_qs_never_offer_arch = bool(data.get("never_offer_arch"))
        self.mm_qs_never_want_arch = bool(data.get("never_want_arch"))
        self.mm_settings_loaded = True
        self.mm_status = "Quest settings loaded."

    @rx.event
    def save_quest_settings(self):
        pseudo = self._effective_mm_pseudo()
        if not pseudo:
            self.mm_status = "No selected character available for Metamob pseudo."
            return
        _, api_key = _build_metamob_headers()
        if not api_key:
            self.mm_status = "Metamob API key missing in metamob.config.json."
            return

        username = _resolve_username(pseudo)
        slug, err = _resolve_quest_slug(username)
        if err or not slug:
            self.mm_status = err or "Unable to resolve quest."
            return

        body: dict = {
            "character_name": self.mm_qs_character_name or None,
            "parallel_quests": _to_int(self.mm_qs_parallel_quests, default=1),
            "show_trades": self.mm_qs_show_trades,
            "trade_mode": _to_int(self.mm_qs_trade_mode, default=0),
            "never_offer_normal": 1 if self.mm_qs_never_offer_normal else 0,
            "never_want_normal": 1 if self.mm_qs_never_want_normal else 0,
            "never_offer_boss": 1 if self.mm_qs_never_offer_boss else 0,
            "never_want_boss": 1 if self.mm_qs_never_want_boss else 0,
            "never_offer_arch": 1 if self.mm_qs_never_offer_arch else 0,
            "never_want_arch": 1 if self.mm_qs_never_want_arch else 0,
        }
        offer_threshold = (self.mm_qs_offer_threshold or "").strip()
        want_threshold = (self.mm_qs_want_threshold or "").strip()
        if offer_threshold:
            body["trade_offer_threshold"] = _to_int(offer_threshold, default=0)
        if want_threshold:
            body["trade_want_threshold"] = _to_int(want_threshold, default=0)
        body = {key: value for key, value in body.items() if value is not None}

        resp, payload = _api_json("PATCH", f"/v1/quests/{slug}", body=body)
        if resp is None:
            self.mm_status = "Metamob API unreachable."
            return
        if not resp.ok:
            self.mm_status = f"Failed to save settings: HTTP {resp.status_code}"
            return

        self.mm_status = "Quest settings saved."

    @rx.event
    def set_mm_qs_character_name(self, value: str):
        self.mm_qs_character_name = value

    @rx.event
    def set_mm_qs_parallel_quests(self, value: str):
        self.mm_qs_parallel_quests = value

    @rx.event
    def set_mm_qs_trade_mode(self, value: str):
        self.mm_qs_trade_mode = value

    @rx.event
    def set_mm_qs_offer_threshold(self, value: str):
        self.mm_qs_offer_threshold = value

    @rx.event
    def set_mm_qs_want_threshold(self, value: str):
        self.mm_qs_want_threshold = value

    @rx.event
    def set_mm_qs_show_trades(self, value: bool):
        self.mm_qs_show_trades = bool(value)

    @rx.event
    def set_mm_qs_never_offer_normal(self, value: bool):
        self.mm_qs_never_offer_normal = bool(value)

    @rx.event
    def set_mm_qs_never_want_normal(self, value: bool):
        self.mm_qs_never_want_normal = bool(value)

    @rx.event
    def set_mm_qs_never_offer_boss(self, value: bool):
        self.mm_qs_never_offer_boss = bool(value)

    @rx.event
    def set_mm_qs_never_want_boss(self, value: bool):
        self.mm_qs_never_want_boss = bool(value)

    @rx.event
    def set_mm_qs_never_offer_arch(self, value: bool):
        self.mm_qs_never_offer_arch = bool(value)

    @rx.event
    def set_mm_qs_never_want_arch(self, value: bool):
        self.mm_qs_never_want_arch = bool(value)

    @rx.event
    def set_trade_offer_mode(self, value: str):
        self.trade_offer_mode = "x3" if value == "x3" else "dup"

    @rx.event
    def set_other_pseudo(self, value: str):
        self.other_pseudo = value

    @rx.event
    def set_other_wants_text(self, value: str):
        self.other_wants_text = value

    @rx.event
    def set_other_offers_text(self, value: str):
        self.other_offers_text = value

    def _name_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for monster in self.monsters:
            name = monster["name"]
            key = _normalize_for_tokens(name)
            index.setdefault(key, []).append(name)
        return index

    def _parse_pasted_names(self, text: str) -> list[str]:
        index = self._name_index()
        raw_tokens = [token.strip() for token in (text or "").replace(";", ",").replace("\n", ",").split(",") if token.strip()]
        matched: set[str] = set()
        for token in raw_tokens:
            key = _normalize_for_tokens(token)
            if key in index:
                for name in index[key]:
                    matched.add(name)
                continue
            if len(key) >= 4:
                for idx_key, names in index.items():
                    if key in idx_key:
                        for name in names:
                            matched.add(name)
        return sorted(matched)

    @staticmethod
    def _extract_ingame_pseudo(profile_data) -> str:
        if not isinstance(profile_data, dict):
            return ""
        payload = _extract_data(profile_data) if "data" in profile_data else profile_data
        if not isinstance(payload, dict):
            return ""

        def pick(obj, key: str) -> str:
            val = obj.get(key) if isinstance(obj, dict) else None
            return val.strip() if isinstance(val, str) and val.strip() else ""

        contact = pick(payload, "contact")
        if contact:
            return contact
        for nested_key in ("utilisateur", "user"):
            nested = payload.get(nested_key)
            nested_contact = pick(nested, "contact")
            if nested_contact:
                return nested_contact
        for key in (
            "pseudoJeu",
            "pseudo_jeu",
            "pseudoInGame",
            "pseudo_ingame",
            "inGame",
            "ingame",
            "ig",
            "nickname",
            "username",
            "pseudo",
            "name",
        ):
            value = pick(payload, key)
            if value:
                return value
        return ""

    @rx.event
    def load_other_player(self):
        pseudo = (self.other_pseudo or "").strip()
        if not pseudo:
            self.trade_status = "Set opponent pseudo first."
            return
        _, api_key = _build_metamob_headers()
        if not api_key:
            self.trade_status = "Metamob API key missing in metamob.config.json."
            return

        username = _resolve_username(pseudo)
        slug, err = _resolve_quest_slug(username)
        if err or not slug:
            self.trade_status = err or "Unable to resolve opponent quest."
            return

        monsters, err = _fetch_all_quest_monsters(username, slug, monster_type=3)
        if err or monsters is None:
            self.trade_status = err or "Unable to load opponent monsters."
            return

        wants: list[str] = []
        offers: list[str] = []
        id_to_name = {int(m["id"]): m["name"] for m in self.monsters if int(m.get("id", 0)) > 0}
        for item in monsters:
            if not isinstance(item, dict):
                continue
            monster_id = _to_int(item.get("id"), default=-1)
            name_obj = item.get("name") if isinstance(item.get("name"), dict) else {}
            name = (
                id_to_name.get(monster_id)
                or name_obj.get("fr")
                or name_obj.get("en")
                or name_obj.get("es")
                or ""
            )
            if not name:
                continue
            if _to_int(item.get("want"), default=0) > 0:
                wants.append(name)
            if _to_int(item.get("offer"), default=0) > 0:
                offers.append(name)

        self.other_wants_text = ", ".join(sorted(set(wants)))
        self.other_offers_text = ", ".join(sorted(set(offers)))

        profile_resp, profile_payload = _api_json("GET", f"/v1/users/{username}")
        if profile_resp is not None and profile_resp.ok:
            self.other_ingame = self._extract_ingame_pseudo(profile_payload)
        else:
            self.other_ingame = ""

        self.trade_status = f"Loaded opponent lists: {len(set(wants))} wants, {len(set(offers))} offers."
        self.run_trade_compare()

    @rx.event
    def run_trade_compare(self):
        other_wants = self._parse_pasted_names(self.other_wants_text)
        other_offers = self._parse_pasted_names(self.other_offers_text)

        validated = set(self.validated_steps)
        my_offers: list[str] = []
        my_wants: list[str] = []
        for monster in self.monsters:
            qty = int(self.counts.get(monster["name"], 0))
            step = int(monster["step"])
            if qty <= 0 and step not in validated:
                my_wants.append(monster["name"])
            if qty > 1 or (qty >= 1 and step in validated):
                if self.trade_offer_mode == "x3":
                    if qty >= 3:
                        my_offers.append(monster["name"])
                else:
                    my_offers.append(monster["name"])

        other_wants_set = set(other_wants)
        other_offers_set = set(other_offers)
        self.compare_give = sorted([name for name in my_offers if name in other_wants_set])
        self.compare_receive = sorted([name for name in my_wants if name in other_offers_set])

        self.selected_give = [name for name in self.selected_give if name in self.compare_give]
        self.selected_receive = [name for name in self.selected_receive if name in self.compare_receive]
        self.trade_status = f"Compare ready: give {len(self.compare_give)}, receive {len(self.compare_receive)}."

    @rx.event
    def toggle_select_give(self, name: str):
        if name in self.selected_give:
            self.selected_give = [x for x in self.selected_give if x != name]
        else:
            self.selected_give = self.selected_give + [name]

    @rx.event
    def toggle_select_receive(self, name: str):
        if name in self.selected_receive:
            self.selected_receive = [x for x in self.selected_receive if x != name]
        else:
            self.selected_receive = self.selected_receive + [name]

    @rx.event
    def apply_trade_commit(self):
        give = self.selected_give if self.selected_give else self.compare_give
        receive = self.selected_receive if self.selected_receive else self.compare_receive
        if not give and not receive:
            self.trade_status = "No trade items to apply."
            return

        for name in give:
            self.counts[name] = max(0, int(self.counts.get(name, 0)) - 1)
        for name in receive:
            self.counts[name] = max(0, int(self.counts.get(name, 0)) + 1)
        self._save_profile_data()
        self.selected_give = []
        self.selected_receive = []
        self.run_trade_compare()
        self.trade_status = f"Trade applied. Gave {len(give)}, received {len(receive)}."

    @rx.var
    def validated_steps_label(self) -> str:
        if not self.validated_steps:
            return "Validated steps: none"
        return "Validated steps: " + ", ".join(str(step) for step in self.validated_steps)

    @rx.var
    def souszone_options(self) -> list[str]:
        return ["all"] + self.souszones

    @rx.var
    def filtered_monsters(self) -> list[dict]:
        query = _normalize_for_search(self.search_query)
        validated = set(self.validated_steps)
        output: list[dict] = []

        for monster in self.monsters:
            name = monster["name"]
            qty = int(self.counts.get(name, 0))
            step = int(monster["step"])

            if self.active_filter == "needed" and qty > 0:
                continue
            if self.active_filter == "collected" and qty <= 0:
                continue
            if self.active_filter == "duplicate" and not (1 < qty < 3):
                continue
            if self.active_filter == "triple" and qty < 3:
                continue
            if self.active_step != 0 and step != self.active_step:
                continue
            if self.active_souszone != "all" and monster["souszone"] != self.active_souszone:
                continue
            if query and query not in _normalize_for_search(name):
                continue

            status = "needed"
            if qty >= 3:
                status = "triple"
            elif qty > 1:
                status = "duplicate"
            elif qty > 0:
                status = "collected"
            elif step in validated:
                status = "validated"

            output.append({**monster, "qty": qty, "status": status})
        return output

    @rx.var
    def totals(self) -> dict[str, int]:
        total_collected = 0
        total_needed = 0
        total_duplicate = 0
        total_triple = 0
        validated = set(self.validated_steps)

        for monster in self.monsters:
            qty = int(self.counts.get(monster["name"], 0))
            if qty > 0:
                total_collected += 1
            if qty == 0 and int(monster["step"]) not in validated:
                total_needed += 1
            if 1 < qty < 3:
                total_duplicate += 1
            if qty >= 3:
                total_triple += 1

        return {
            "all": len(self.monsters),
            "needed": total_needed,
            "collected": total_collected,
            "duplicate": total_duplicate,
            "triple": total_triple,
        }

    @rx.var
    def wants_list(self) -> list[str]:
        validated = set(self.validated_steps)
        wants: list[str] = []
        for monster in self.monsters:
            qty = int(self.counts.get(monster["name"], 0))
            if qty <= 0 and int(monster["step"]) not in validated:
                wants.append(monster["name"])
        return wants

    @rx.var
    def offers_list(self) -> list[str]:
        validated = set(self.validated_steps)
        offers: list[str] = []
        for monster in self.monsters:
            qty = int(self.counts.get(monster["name"], 0))
            if qty > 1 or (qty >= 1 and int(monster["step"]) in validated):
                offers.append(f"{monster['name']} ({qty}x)")
        return offers

    @rx.var
    def wants_text(self) -> str:
        return ", ".join(self.wants_list)

    @rx.var
    def offers_text(self) -> str:
        return ", ".join(self.offers_list)

    @rx.var
    def metamob_estimate(self) -> str:
        return f"Auto estimate: {len(self.wants_list)} wanted, {len(self.offers_list)} offered"

    @rx.var
    def trade_message(self) -> str:
        give = self.selected_give if self.selected_give else self.compare_give
        receive = self.selected_receive if self.selected_receive else self.compare_receive
        target = (self.other_ingame or self.other_pseudo or "").strip()
        prefix = f"/w {target} " if target else ""
        return (
            f"{prefix}Salut! Je peux te donner: {', '.join(give)}. "
            f"Contre {', '.join(receive)}. Tu es partant pour un échange ?"
        )
