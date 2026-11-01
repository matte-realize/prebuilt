"""GET /api/realprint: our real Form Studio 1 test plate and its micrometer readings."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the repo root

from console.runner import real_print  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = json.dumps(real_print(), separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
