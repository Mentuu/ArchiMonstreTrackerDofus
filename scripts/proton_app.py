import atexit
import os
import subprocess
import sys
import time
import urllib.request


PORT = int(os.environ.get("PORT", "8000"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_server_proc = None


def _start_server():
    env = os.environ.copy()
    env["PORT"] = str(PORT)
    env["FLASK_DEBUG"] = "0"
    return subprocess.Popen(
        [sys.executable, "serve.py"],
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_server(timeout_sec: float = 20.0):
    deadline = time.time() + timeout_sec
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/local/tools/status", timeout=1.5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Server did not start in time: {last_error}")


def _shutdown_server():
    global _server_proc
    if _server_proc and _server_proc.poll() is None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=4)
        except Exception:
            _server_proc.kill()
    _server_proc = None


def main():
    global _server_proc
    try:
        import webview
    except Exception:
        print("Missing dependency: pywebview")
        print("Install with: pip install pywebview")
        raise

    _server_proc = _start_server()
    atexit.register(_shutdown_server)
    _wait_server()

    window = webview.create_window(
        title="Archimonster Proton App",
        url=BASE_URL,
        width=1280,
        height=860,
        min_size=(980, 700),
    )
    webview.start()
    _shutdown_server()


if __name__ == "__main__":
    main()
