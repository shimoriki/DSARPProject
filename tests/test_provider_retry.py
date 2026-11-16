"""LocalProvider against a stub OpenAI-compatible server: 429 retry and uncapped output."""
import json
import socket
import threading
import time
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from dsarp.models import providers
from dsarp.models.providers import LocalProvider


def serve(statuses):
    """Answer each POST with the next status in `statuses` (the last one repeats); record bodies.
    An entry is a code, or (code, headers) to send rate-limit headers instead of Retry-After: 0."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            entry = statuses[min(len(seen), len(statuses)) - 1]
            if entry == "reset":   # drop the connection without answering, as a flaky host does
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            code, headers = entry if isinstance(entry, tuple) else (entry, None)
            body = (json.dumps({"choices": [{"message": {"content": "ok"}}]}) if code == 200
                    else '{"error": "rate limited"}').encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            if code == 429 and headers is None:
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


@pytest.fixture
def slept(monkeypatch):
    """Record waits instead of sleeping."""
    waits = []
    monkeypatch.setattr(providers.time, "sleep", waits.append)
    return waits


@pytest.mark.parametrize("headers, expected", [   # built at run time: timestamps go stale
    (lambda: {"Retry-After": "7"}, 7),
    (lambda: {"Retry-After": formatdate(time.time() + 30, usegmt=True)}, 30),
    (lambda: {"X-RateLimit-Reset": str(int((time.time() + 20) * 1000))}, 20),   # OpenRouter: epoch ms
])
def test_waits_as_long_as_the_server_says(slept, headers, expected):
    srv, seen, url = serve([(429, headers()), 200])
    try:
        assert LocalProvider("m", url).generate("hi").text == "ok"
        assert len(seen) == 2
        assert expected - 3 <= slept[-1] <= expected + 1
    finally:
        srv.shutdown()


def test_gives_up_at_once_when_the_limit_resets_too_late(slept):
    # A daily quota answers 429 with a reset hours away: waiting is not an option.
    srv, seen, url = serve([(429, {"X-RateLimit-Reset": str(int((time.time() + 3600) * 1000))})])
    try:
        with pytest.raises(RuntimeError, match="resets in"):
            LocalProvider("m", url, max_wait=300).generate("hi")
        assert len(seen) == 1
    finally:
        srv.shutdown()


def test_retries_a_dropped_connection(slept):
    srv, seen, url = serve(["reset", "reset", 200])
    try:
        assert LocalProvider("m", url).generate("hi").text == "ok"
        assert len(seen) == 3
    finally:
        srv.shutdown()


def test_does_not_retry_a_refused_connection(slept):
    # Nothing listening is a server that is down, not a flaky one: fail at once.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(RuntimeError, match="unreachable"):
        LocalProvider("m", "http://127.0.0.1:%d" % port).generate("hi")
    assert slept == []


def test_throttles_calls_to_min_interval(slept):
    srv, seen, url = serve([200])
    try:
        p = LocalProvider("m", url, min_interval=5)
        p.generate("hi")
        p.generate("hi")
        assert len(seen) == 2
        assert slept and 4 <= max(slept) <= 5
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
