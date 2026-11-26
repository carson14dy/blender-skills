"""Serve a studio site folder locally under the artifact host's strict Content-Security-Policy.

    python3 csp_server.py DIR PORT [--host 127.0.0.1] [--csp POLICY]

The default policy mirrors what the published artifact enforces (no fetch() of data: URLs, scripts from https/self,
workers from blob/self). Testing on a bare local server hides CSP failures: the embedded glTF loader, for one, fails
silently under the real host if it fetches its data: buffer. Single byte ranges are supported so <video> elements
behave as on a real host. Used by smoke.py; also handy by hand.
"""
import argparse
import functools
import http.server
import os
import re
import sys

DEFAULT_CSP = ("default-src 'self' https: blob:; connect-src 'self' https: blob:; img-src 'self' https: data: blob:; "
               "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: blob:; style-src 'self' 'unsafe-inline' https:; "
               "worker-src blob: 'self'; font-src https: data:")

EXTRA_TYPES = {".wasm": "application/wasm", ".mjs": "text/javascript", ".js": "text/javascript",
               ".json": "application/json", ".gltf": "model/gltf+json", ".glb": "model/gltf-binary",
               ".mp4": "video/mp4", ".webm": "video/webm", ".splat": "application/octet-stream",
               ".ksplat": "application/octet-stream", ".spz": "application/octet-stream",
               ".sog": "application/octet-stream", ".ply": "application/octet-stream", ".svg": "image/svg+xml",
               ".pdf": "application/pdf", ".webp": "image/webp"}


class CSPHandler(http.server.SimpleHTTPRequestHandler):
    csp = DEFAULT_CSP
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **EXTRA_TYPES}

    def end_headers(self):
        self.send_header("Content-Security-Policy", self.csp)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def log_message(self, *a):
        pass

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (rng or "").strip())
        if not m or not os.path.isfile(path) or (not m.group(1) and not m.group(2)):
            return super().send_head()
        size = os.path.getsize(path)
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:                                   # suffix range: the last N bytes
            start, end = max(0, size - int(m.group(2))), size - 1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range_left = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_range_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            b = source.read(min(65536, left))
            if not b:
                break
            outputfile.write(b)
            left -= len(b)
        self._range_left = None


def make_server(directory, port, host="127.0.0.1", csp=DEFAULT_CSP):
    handler = type("H", (CSPHandler,), {"csp": csp})
    return http.server.ThreadingHTTPServer((host, port), functools.partial(handler, directory=directory))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir")
    ap.add_argument("port", type=int)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--csp", default=DEFAULT_CSP)
    a = ap.parse_args(argv)
    srv = make_server(os.path.abspath(a.dir), a.port, a.host, a.csp)
    print(f"serving {a.dir} on http://{a.host}:{srv.server_address[1]}/ (CSP on)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
