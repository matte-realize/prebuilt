"""Local web server for the console. Stdlib only.

    python -m console                 # http://127.0.0.1:8765, opens the browser
    python -m console --port 9000 --no-browser
    python -m console --share         # public link through a Cloudflare quick tunnel, guarded by an access key
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import secrets
import shutil
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, unquote, urlparse

from console import runner

HERE = Path(__file__).resolve().parent


class Console:
    """Holds the one run at a time."""

    def __init__(self, runs_dir: Path = runner.RUNS, key: str | None = None):
        self.runs_dir = Path(runs_dir)
        self.key = key  # when set, every request needs it (?key= once, then a cookie)
        self.run: runner.Run | None = None
        self.lock = threading.Lock()
        self._defaults = None

    def defaults(self) -> dict:
        if self._defaults is None:
            self._defaults = runner.prereg_defaults()
        return self._defaults

    def start(self, body: dict) -> runner.Run:
        with self.lock:
            if self.run and self.run.status in ("starting", "running", "waiting"):
                raise ValueError("a run is in progress: stop it first")
            self.run = runner.Run(runner.Settings.from_dict(body), self.runs_dir).start()
            return self.run

    def current(self) -> runner.Run:
        if not self.run:
            raise ValueError("no run")
        return self.run

    def state(self) -> dict:
        return {"defaults": self.defaults(), "run": self.run.view() if self.run else None}


def make_handler(con: Console):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet: the page polls every second
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _authorized(self) -> bool:
            if not con.key:
                return True
            jar = SimpleCookie(self.headers.get("Cookie") or "")
            return "pb_key" in jar and secrets.compare_digest(jar["pb_key"].value, con.key)

        def _deny(self):
            self._send(403, b"Prebuilt console: open the share link that includes ?key=...", "text/plain; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path
            if path in ("/", "/index.html"):
                given = parse_qs(u.query).get("key", [""])[0]
                if con.key and given and secrets.compare_digest(given, con.key):
                    cookie = f"pb_key={con.key}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400"
                    return self._send(302, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})
                if not self._authorized():
                    return self._deny()
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if not self._authorized():
                return self._deny()
            if path == "/api/state":
                return self._json(con.state())
            if path.startswith("/runs/"):
                return self._static(unquote(path[len("/runs/"):]))
            self._json({"error": "not found"}, 404)

        def _static(self, rel: str):
            root = con.runs_dir.resolve()
            f = (root / rel).resolve()
            if not f.is_relative_to(root) or not f.is_file():
                return self._json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            extra = {"Content-Disposition": f'attachment; filename="{f.name}"'} if f.suffix in (".stl", ".csv", ".pkl") else {}
            self._send(200, f.read_bytes(), ctype, extra)

        def do_POST(self):
            path = urlparse(self.path).path
            if not self._authorized():
                return self._deny()
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if path == "/api/run":
                    con.start(body)
                    return self._json(con.state())
                run = con.current()
                if path == "/api/answer":
                    run.answer(int(body["id"]), str(body.get("answer", "")))
                elif path == "/api/measure":
                    run.submit_measurements(int(body["id"]), list(body["rows"]),
                                            "sim-fill" if body.get("source") == "sim-fill" else "hand")
                elif path == "/api/fill":
                    return self._json({"rows": run.fill(int(body["id"]))})
                elif path == "/api/designs":
                    return self._json(run.designs(str(body["site"])))
                elif path == "/api/corrected":
                    return self._json(run.corrected(str(body["site"]), str(body["kind"]), float(body["target"])))
                elif path == "/api/stop":
                    run.stop()
                elif path == "/api/viewer":
                    if not (run.dir / "state.pkl").exists():
                        raise ValueError("nothing to show yet: the seed plates aren't done")
                    return self._json({"url": runner.build_viewer(run)})
                else:
                    return self._json({"error": "not found"}, 404)
                return self._json(con.state())
            except (ValueError, KeyError, TypeError, RuntimeError) as e:
                return self._json({"error": str(e)}, 400)

    return Handler


def serve(port: int = 8765, host: str = "127.0.0.1", runs_dir: Path = runner.RUNS,
          key: str | None = None) -> ThreadingHTTPServer:
    runner._router()  # route run-thread prints into the run's log
    srv = ThreadingHTTPServer((host, port), make_handler(Console(runs_dir, key)))
    srv.daemon_threads = True
    return srv


def tunnel(port: int) -> tuple[subprocess.Popen, str]:
    """Start a Cloudflare quick tunnel to the local port; return the process and its public https URL."""
    exe = shutil.which("cloudflared")
    if not exe:
        raise SystemExit("--share needs cloudflared: brew install cloudflared")
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    for line in proc.stderr:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            threading.Thread(target=lambda: [None for _ in proc.stderr], daemon=True).start()  # keep draining
            return proc, m.group(0)
    raise SystemExit("cloudflared exited before giving a URL")


def main() -> None:
    ap = argparse.ArgumentParser(description="Prebuilt console: drive a run from the browser")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to serve your local network")
    ap.add_argument("--share", action="store_true", help="public link via a Cloudflare quick tunnel, with an access key")
    ap.add_argument("--key", help="access key (default: random when sharing or serving beyond localhost)")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    key = a.key or (secrets.token_urlsafe(16) if a.share or a.host != "127.0.0.1" else None)
    srv = serve(a.port, a.host, key=key)
    local = f"http://127.0.0.1:{a.port}/" + (f"?key={key}" if key else "")
    print(f"Prebuilt console at {local}  (Ctrl-C to quit)")
    proc = None
    if a.share:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        proc, public = tunnel(a.port)
        print(f"Share link (anyone with it can drive the console): {public}/?key={key}", flush=True)
    elif a.host != "127.0.0.1":
        print(f"On your network: http://<this machine's IP>:{a.port}/?key={key}")
    if not a.no_browser:
        threading.Timer(0.5, webbrowser.open, (local,)).start()
    try:
        if proc:
            proc.wait()
        else:
            srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if proc:
            proc.terminate()
        srv.server_close()


if __name__ == "__main__":
    main()
