"""POST /api/simulate: one complete simulated run (console/serverless.py), about 7-10 seconds."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root

from console.serverless import simulate  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _reply(self, code, obj):
        data = json.dumps(obj, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            self._reply(200, simulate(json.loads(self.rfile.read(n) or b"{}")))
        except (ValueError, KeyError, TypeError) as e:
            self._reply(400, {"error": str(e)})
