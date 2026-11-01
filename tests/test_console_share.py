"""The console's access key: without it nothing is served; the share link sets a cookie."""
import http.client
import threading

from console.server import serve


def _req(port, method, path, cookie=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=b"{}" if method == "POST" else None, headers={"Cookie": cookie} if cookie else {})
    r = c.getresponse()
    return r.status, r.getheader("Set-Cookie"), r.read()


def _start(tmp_path, key):
    srv = serve(0, runs_dir=tmp_path, key=key)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_key_required(tmp_path):
    srv, port = _start(tmp_path, "s3cret")
    try:
        assert _req(port, "GET", "/")[0] == 403
        assert _req(port, "GET", "/api/state")[0] == 403
        assert _req(port, "POST", "/api/run")[0] == 403
        assert _req(port, "GET", "/?key=wrong")[0] == 403
        status, cookie, _ = _req(port, "GET", "/?key=s3cret")
        assert status == 302 and cookie.startswith("pb_key=s3cret")
        assert _req(port, "GET", "/api/state", "pb_key=s3cret")[0] == 200
        assert _req(port, "GET", "/api/state", "pb_key=nope")[0] == 403
    finally:
        srv.shutdown()


def test_no_key_on_localhost(tmp_path):
    srv, port = _start(tmp_path, None)
    try:
        assert _req(port, "GET", "/")[0] == 200
        assert _req(port, "GET", "/api/state")[0] == 200
    finally:
        srv.shutdown()
