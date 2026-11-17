#!/usr/bin/env python3
"""Serve out/ like the claude.ai Artifact host: index.html wrapped in the platform skeleton and a CSP.

  /            page with the CSP the coordinator listed (scripts from the allowed CDNs; no 'wasm-unsafe-eval')
  /wasm/       same page, CSP plus 'wasm-unsafe-eval' (what WebAssembly needs)
  /frame.html  the page inside a sandboxed iframe (allow-scripts allow-same-origin), no xr permission
"""
import http.server, os, sys, functools

ROOT = sys.argv[1]
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
HERE = os.path.dirname(os.path.abspath(__file__))
SKEL = open(os.path.join(HERE, "skeleton-head.html")).read().rstrip("\n")
CDNS = "https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://code.jquery.com"
def csp(wasm=True):
    return ("default-src 'self'; script-src 'self' 'unsafe-inline' %s%s blob:; connect-src 'self' blob: data:; "
            "worker-src 'self' blob:; img-src 'self' blob: data:; media-src 'self' blob: data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com data:; "
            "frame-src 'self'" % ("'wasm-unsafe-eval' " if wasm else "", CDNS))

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def end_headers(self):
        self.send_header("Content-Security-Policy", csp(getattr(self, "wasm", False)))
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def do_GET(self):
        p = self.path.split("?")[0]
        self.wasm = p.startswith("/wasm/")
        if self.wasm:
            self.path = self.path[len("/wasm"):]; p = p[len("/wasm"):]
        if p == "/frame.html":
            body = ('<!doctype html><html><head><meta charset="utf-8"><title>frame</title><style>html,body{margin:0;height:100%%}'
                    'iframe{border:0;width:100%%;height:100%%}</style></head><body><iframe sandbox="allow-scripts allow-same-origin allow-forms allow-modals" '
                    'src="/index.html%s"></iframe></body></html>' % (("?" + self.path.split("?", 1)[1]) if "?" in self.path else "")).encode()
            return self._send(body)
        if p in ("/", "/index.html"):
            body = (SKEL + "\n" + open(os.path.join(ROOT, "index.html")).read() + "</body></html>\n").encode()
            return self._send(body)
        return super().do_GET()
    ALLOWED = set(".html .css .js .mjs .wasm .json .map .geojson .webmanifest .txt .md .csv .xml .svg .png .jpg .jpeg .gif .webp .avif .ico .woff .woff2 .ttf .otf .mp3 .wav .ogg .mp4 .webm .pdf".split())
    def send_head(self):
        ext = os.path.splitext(self.path.split("?")[0])[1].lower()
        if ext not in self.ALLOWED:
            sys.stderr.write("UNSERVED %s\n" % self.path); sys.stderr.flush()
            self.send_error(404, "extension not served by the artifact host"); return None
        return super().send_head()
    def _send(self, body):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

H.extensions_map.update({".glb": "model/gltf-binary", ".spz": "application/octet-stream", ".json": "application/json", ".js": "text/javascript", ".md": "text/markdown"})
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=ROOT)).serve_forever()
