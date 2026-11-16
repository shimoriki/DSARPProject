"""LocalProvider against a stub OpenAI-compatible server: 429 retry and uncapped output."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from dsarp.models.providers import LocalProvider


def serve(statuses):
    """Answer each POST with the next status in `statuses` (the last one repeats); record bodies."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            code = statuses[min(len(seen), len(statuses)) - 1]
            body = (json.dumps({"choices": [{"message": {"content": "ok"}}]}) if code == 200
                    else '{"error": "rate limited"}').encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            if code == 429:
                self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen, "http://127.0.0.1:%d" % srv.server_address[1]


def test_retries_429_until_success():
    srv, seen, url = serve([429, 429, 200])
    try:
        assert LocalProvider("m", url).generate("hi").text == "ok"
        assert len(seen) == 3
    finally:
        srv.shutdown()


def test_gives_up_after_retries():
    srv, seen, url = serve([429])
    try:
        with pytest.raises(RuntimeError, match="429"):
            LocalProvider("m", url, retries=2).generate("hi")
        assert len(seen) == 3
    finally:
        srv.shutdown()


def test_uncapped_leaves_max_tokens_to_the_server():
    srv, seen, url = serve([200])
    try:
        LocalProvider("m", url, uncapped=True).generate("hi", max_tokens=800)
        LocalProvider("m", url).generate("hi", max_tokens=800)
        assert "max_tokens" not in seen[0]
        assert seen[1]["max_tokens"] == 800
    finally:
        srv.shutdown()
