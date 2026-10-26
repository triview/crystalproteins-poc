"""Shared Playwright harness: serves the built viewer over HTTP. The viewer is self-contained
(three.js is bundled into the page), so the only outside request is the optional Google Fonts
stylesheet, which is answered with an empty sheet to keep the tests offline."""
from __future__ import annotations

import functools
import http.server
import threading


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory: str):
    h = functools.partial(Quiet, directory=directory)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def route_three(page):
    """Kept for the tests' call sites: keep fonts offline (three.js is in the page)."""
    page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))
