"""Local web server for the console. Stdlib only.

    python -m console                 # http://127.0.0.1:8765, opens the browser
    python -m console --port 9000 --no-browser
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from console import runner

HERE = Path(__file__).resolve().parent


class Console:
    """Holds the one run at a time."""

    def __init__(self, runs_dir: Path = runner.RUNS):
        self.runs_dir = Path(runs_dir)
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

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
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


def serve(port: int = 8765, host: str = "127.0.0.1", runs_dir: Path = runner.RUNS) -> ThreadingHTTPServer:
    runner._router()  # route run-thread prints into the run's log
    srv = ThreadingHTTPServer((host, port), make_handler(Console(runs_dir)))
    srv.daemon_threads = True
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="Prebuilt console: drive a practice run from the browser")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = serve(a.port)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Prebuilt console at {url}  (Ctrl-C to quit)")
    if not a.no_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
