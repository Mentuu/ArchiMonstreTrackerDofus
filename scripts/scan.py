import json
import os
import sys
import time
import threading
from datetime import datetime
from typing import Dict, List, Tuple

# Third-party
try:
    import pyautogui  # UI automation + screenshot search (Pillow-based exact match)
except ImportError:
    print("Missing dependency: pyautogui. Install requirements with 'pip install -r requirements.txt'.")
    sys.exit(1)

try:
    from pynput import keyboard  # global hotkeys to capture search bar position + modes
except ImportError:
    print("Missing dependency: pynput. Install requirements with 'pip install -r requirements.txt'.")
    sys.exit(1)

try:
    import pyperclip  # clipboard for fast paste
except ImportError:
    print("Missing dependency: pyperclip. Install requirements with 'pip install -r requirements.txt'.")
    sys.exit(1)

# OpenCV (required for multi-scale template matching and for pyautogui confidence mode)
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore
    np = None   # type: ignore

# --- Config ----
TYPE_INTERVAL = 0.02            # typing speed (fallback)
POST_TYPE_DELAY = 1           # wait after typing before scanning (seconds)
SAVE_EVERY = 12                 # save intermediate progress every N names
IMAGE_FILE = "archimonsterImg.png"  # template to find on the screen
JSON_INPUT = "archimonstres_par_zone.json"
RESULTS_FILE = "results.json"
GRAYSCALE = True  # keep color
CONFIDENCE = 0.95  # tighter threshold to avoid many near-duplicate matches
STEP = 6           # skip pixels to reduce overlapping detections and speed
IOU_THRESHOLD = 0.6  # overlap above this -> treat as same icon

# --- Matching mode ---
# If True and OpenCV is available, use multi-scale template matching (size-invariant)
USE_MULTISCALE = True
# Scales to try around 1.0 (you can tune these for performance/robustness)
SCALE_FACTORS = [0.75, 0.85, 1.0, 1.15, 1.3]
# Threshold for cv2.TM_CCOEFF_NORMED scores used by multi-scale matcher
MULTISCALE_THRESHOLD = 0.88
# Skip too-small templates to avoid noisy matches
MIN_TEMPLATE_WH = 12

# --- Globals ---
search_bar_pos: Tuple[int, int] | None = None
start_event = threading.Event()
pack_archi_enabled = False             # when True, double-click highlights first match
scan_paused = False                    # toggled by F10 to pause/resume scan loop
kb_listener: keyboard.Listener | None = None
screen_w, screen_h = pyautogui.size()
leftRegion = (0, 0, screen_w // 2, screen_h)

# Cache for template image (for multi-scale mode)
_TPL_CACHE = {
    "path": None,        # type: ignore
    "img_gray": None,   # type: ignore
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def gather_names(data: Dict) -> List[str]:
    """Extract unique archimonster names from the zones JSON (key 'nom')."""
    seen = set()
    names: List[str] = []
    zones = data.get("zones", [])
    for zone in zones:
        for sz in zone.get("souszones", []):
            for archi in sz.get("archimonstres", []):
                name = archi.get("nom")
                if not name or not isinstance(name, str):
                    continue
                if name not in seen:
                    seen.add(name)
                    names.append(name)
    return names


def on_press(key):
    global search_bar_pos, scan_paused
    try:
        def is_key(target: keyboard.Key, vk: int | None = None) -> bool:
            if key == target:
                return True
            if vk is not None:
                try:
                    return getattr(key, "vk", None) == vk
                except Exception:
                    return False
            return False

        # F8 = capture search bar position under mouse (only once)
        if is_key(keyboard.Key.f8, 119) and not start_event.is_set():
            search_bar_pos = pyautogui.position()
            log(f"Search bar position captured at {search_bar_pos}.")
            log("Press F10 to pause/resume.")
            start_event.set()
        # F10 = pause/resume scan loop
        if is_key(keyboard.Key.f10, 121):
            scan_paused = not scan_paused
            state = "paused" if scan_paused else "resumed"
            log(f"Scan {state}.")
    except Exception:
        # Ignore any listener exceptions
        pass


def start_hotkey_listener() -> None:
    global kb_listener
    if kb_listener is None:
        kb_listener = keyboard.Listener(on_press=on_press)
        kb_listener.start()


def stop_hotkey_listener() -> None:
    global kb_listener
    if kb_listener is not None:
        kb_listener.stop()
        kb_listener = None


def wait_for_start_hotkey() -> Tuple[int, int]:
    start_hotkey_listener()
    log("Hover your mouse over the Dofus search bar, then press F8 to capture its position.")
    log("Tip: Keep Dofus visible in the foreground. F10 pauses/resumes.")
    start_event.wait()  # block until F8
    if not search_bar_pos:
        raise RuntimeError("Failed to capture search bar position.")
    return search_bar_pos  # type: ignore


def click_and_type(text: str, pos: Tuple[int, int]) -> None:
    # Bring focus to search bar
    pyautogui.click(pos[0], pos[1])
    time.sleep(0.05)
    # Copy to clipboard and paste (replace existing text)
    try:
        pyperclip.copy(text)
        time.sleep(0.02)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.03)
        pyautogui.hotkey('ctrl', 'v')
    except Exception as e:
        # Fallback to typing if clipboard/paste fails
        log(f"Pasting failed, falling back to typing: {e}")
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.03)
        pyautogui.press('backspace')
        time.sleep(0.03)
        pyautogui.typewrite(text, interval=TYPE_INTERVAL)


# Simple IoU-based de-duplication for pyautogui/pyscreeze Box results
def _rect_iou(a, b):
    ax1, ay1, aw, ah = a.left, a.top, a.width, a.height
    bx1, by1, bw, bh = b.left, b.top, b.width, b.height
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0

def _dedup_overlaps(boxes, iou_threshold: float = IOU_THRESHOLD):
    if not boxes:
        return boxes
    # sort for stable selection
    boxes = sorted(boxes, key=lambda b: (b.left, b.top))
    kept = []
    for b in boxes:
        if all(_rect_iou(b, k) < iou_threshold for k in kept):
            kept.append(b)
    return kept


class _Box:
    # Minimal Box-like class to interop with _dedup_overlaps
    def __init__(self, left: int, top: int, width: int, height: int):
        self.left = int(left)
        self.top = int(top)
        self.width = int(width)
        self.height = int(height)


def _ensure_tpl_loaded(template_path: str):
    # Load and cache grayscale template for OpenCV multi-scale
    if _TPL_CACHE["path"] == template_path and _TPL_CACHE["img_gray"] is not None:
        return
    if cv2 is None:
        return
    tpl = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE if GRAYSCALE else cv2.IMREAD_COLOR)
    if tpl is None:
        raise FileNotFoundError(f"Failed to load template via OpenCV: {template_path}")
    _TPL_CACHE["path"] = template_path
    _TPL_CACHE["img_gray"] = tpl


def highlight_first_match(box: _Box | None) -> None:
    """Double-click on first match when Make a pack archi mode is enabled."""
    if box is None or not pack_archi_enabled:
        return
    
    center_x = box.left + box.width // 2
    center_y = box.top + box.height // 2
    
    # Small delay before double-clicking
    time.sleep(0.3)
    
    # Double-click on the first match with delay between clicks
    pyautogui.click(center_x, center_y)
    time.sleep(0.1)
    pyautogui.click(center_x, center_y)
    
    # Small delay after double-clicking
    time.sleep(0.3)
    
    log(f"Double-clicked first match at ({center_x}, {center_y})")


def _count_icons_on_screen_multiscale(template_path: str) -> int:
    if cv2 is None or np is None:
        # Fallback to pyautogui if OpenCV not available
        return _count_icons_on_screen_pyauto(template_path)

    _ensure_tpl_loaded(template_path)
    tpl = _TPL_CACHE["img_gray"]
    if tpl is None:
        return 0

    # Screenshot the region and convert to OpenCV format
    shot = pyautogui.screenshot(region=leftRegion)
    shot_np = np.array(shot)
    if GRAYSCALE:
        # shot_np is RGB; convert to grayscale
        img = cv2.cvtColor(shot_np, cv2.COLOR_RGB2GRAY)
    else:
        img = cv2.cvtColor(shot_np, cv2.COLOR_RGB2BGR)

    H_img, W_img = img.shape[:2]

    boxes: List[_Box] = []
    for s in SCALE_FACTORS:
        # Resize template for this scale
        h, w = tpl.shape[:2]
        w_s = max(1, int(w * s))
        h_s = max(1, int(h * s))
        if w_s < MIN_TEMPLATE_WH or h_s < MIN_TEMPLATE_WH:
            continue
        tpl_s = cv2.resize(tpl, (w_s, h_s), interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC)

        # If template becomes larger than image, skip
        if w_s > W_img or h_s > H_img:
            continue

        # Match
        res = cv2.matchTemplate(img, tpl_s, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= MULTISCALE_THRESHOLD)
        for (y, x) in zip(*loc):
            # x,y are in the screenshot coordinate system; map to screen region coords
            boxes.append(_Box(leftRegion[0] + x, leftRegion[1] + y, w_s, h_s))

    # Deduplicate overlapping boxes across scales
    boxes = _dedup_overlaps(boxes, IOU_THRESHOLD)
    
    # Highlight first match if Ctrl+Click mode is enabled
    if boxes:
        highlight_first_match(boxes[0])
    
    return len(boxes)


def _count_icons_on_screen_pyauto(template_path: str) -> int:
    # Use the precomputed leftRegion for speed
    boxes = list(pyautogui.locateAllOnScreen(
        template_path,
        region=leftRegion,
        confidence=CONFIDENCE,   # forces OpenCV backend if available
        grayscale=GRAYSCALE,
        step=STEP                 # reduces nearby duplicates
    ))
    boxes = _dedup_overlaps(boxes, IOU_THRESHOLD)
    
    # Highlight first match if Ctrl+Click mode is enabled
    if boxes:
        highlight_first_match(boxes[0])
    
    return len(boxes)


def count_icons_on_screen(template_path: str) -> int:
    if USE_MULTISCALE and cv2 is not None:
        return _count_icons_on_screen_multiscale(template_path)
    return _count_icons_on_screen_pyauto(template_path)


def _base_dir() -> str:
    env_base = (os.environ.get("ARCHI_BASE_DIR") or "").strip()
    if env_base:
        return os.path.abspath(env_base)
    return os.path.abspath(os.path.dirname(__file__))


def ensure_files_exist() -> Tuple[str, str]:
    here = _base_dir()
    image_path = os.path.join(here, IMAGE_FILE)
    json_path = os.path.join(here, JSON_INPUT)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Missing template image: {image_path}")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Missing JSON input: {json_path}")
    return json_path, image_path


def _safe_profile(name: str | None) -> str | None:
    if not name:
        return None
    raw = name.strip().lower()
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"_", "-"})
    return cleaned or None


def _resolve_profile(profile: str | None = None) -> str:
    # Priority: explicit arg -> env var -> metamob.config.json -> results activeProfile -> default
    if profile:
        return _safe_profile(profile) or "default"

    env_profile = _safe_profile(os.environ.get("ARCHI_PROFILE"))
    if env_profile:
        return env_profile

    here = _base_dir()
    cfg_path = os.path.join(here, "metamob.config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f) or {}
            cfg_profile = _safe_profile(cfg.get("profile") or cfg.get("activeProfile") or cfg.get("defaultProfile"))
            if cfg_profile:
                return cfg_profile
        except Exception:
            pass

    results_path = os.path.join(here, RESULTS_FILE)
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                payload = json.load(f) or {}
            active = _safe_profile(payload.get("activeProfile"))
            if active:
                return active
        except Exception:
            pass

    return "default"


def _load_all_results(path: str) -> Dict:
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    else:
        data = {}
    if 'profiles' in data and isinstance(data.get('profiles'), dict):
        return data
    # Old flat format: wrap into default and mirror
    if 'counts' in data:
        wrapped = {
            'profiles': {'default': data},
            'activeProfile': 'default'
        }
        wrapped.update(data)
        return wrapped
    return {'profiles': {}, 'activeProfile': 'default'}


def save_results_profile(path: str, profile: str, payload: Dict) -> None:
    data = _load_all_results(path)
    profiles = data.get('profiles') or {}
    profiles[profile] = payload
    data['profiles'] = profiles
    data['activeProfile'] = profile
    # mirror to top-level for back-compat
    for k in list(data.keys()):
        if k not in {'profiles', 'activeProfile'}:
            del data[k]
    data.update(payload)
    tmp = path + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def make_payload(names: List[str], counts: Dict[str, int], scanned: int) -> Dict:
    needed = [n for n, k in counts.items() if k <= 0]
    duplicates = [{"name": n, "count": k, "extra": max(0, k - 1)} for n, k in counts.items() if k > 1]
    total_found_unique = sum(1 for k in counts.values() if k >= 1)
    total_found_items = sum(counts.values())
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "scanned": scanned,
        "total": len(names),
        "counts": counts,
        "needed": needed,
        "duplicates": duplicates,
        "totalDuplicates": sum(d["extra"] for d in duplicates),
        "totalFound": total_found_unique,      # unique names with >=1 found
        "totalFoundItems": total_found_items,  # sum of all counts
        "note": "F8=start (capture search bar). F10=pause/resume. Move mouse to top-left to abort.",
        "matchMode": "cv2_multiscale" if (USE_MULTISCALE and cv2 is not None) else "pyautogui_exact",
        "grayscale": GRAYSCALE,
    }


def main(profile: str | None = None):
    global pack_archi_enabled
    pyautogui.FAILSAFE = True  # move mouse to top-left corner to abort
    pack_archi_enabled = (os.environ.get("ARCHI_PACK_MODE", "0").strip() == "1")

    # Validate inputs exist
    json_path, image_path = ensure_files_exist()

    profile = _resolve_profile(profile)
    log(f"Using profile: {profile}")

    # Load names
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    names = gather_names(data)
    total_expected = 286  # per user statement

    log(f"Loaded {len(names)} unique archimonster names from JSON (expected ~{total_expected}).")

    # Capture search bar position and keep listener active for mode toggles
    pos = wait_for_start_hotkey()

    # Iterate and scan
    counts: Dict[str, int] = {}
    scanned = 0

    try:
        for name in names:
            while scan_paused:
                time.sleep(0.15)
            click_and_type(name, pos)

            time.sleep(POST_TYPE_DELAY)
            try:
                c = count_icons_on_screen(image_path)
            except Exception as e:
                log(f"Error while scanning for '{name}': {e}")
                c = 0
            counts[name] = c
            scanned += 1

            if scanned % SAVE_EVERY == 0:
                payload = make_payload(names, counts, scanned)
                save_results_profile(os.path.join(os.path.dirname(json_path), RESULTS_FILE), profile, payload)
                log(f"Progress saved after {scanned} scans.")

        # Finalize results
        result = make_payload(names, counts, scanned)
        out_path = os.path.join(os.path.dirname(json_path), RESULTS_FILE)
        save_results_profile(out_path, profile, result)
        log(f"Done. Scanned {scanned}/{len(names)} names. Results saved to: {out_path}")
    finally:
        stop_hotkey_listener()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrupted by user.")
