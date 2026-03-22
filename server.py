"""
dok-site/server.py — pure Python stdlib, no dependencies beyond dok.

Startup: compiles all pages/*.dok → HTML strings (once, in memory)
Runtime: serves those strings + static files + playground

Usage:
  python server.py          # http://localhost:8000
  python server.py 9000     # custom port
"""

import sys
import subprocess
import tempfile
import traceback
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

HERE       = Path(__file__).parent
STATIC_DIR = HERE / "static"
PLAYGROUND = HERE / "playground.html"

# ── Compile one .dok file → HTML string via CLI ───────────────
def dok_to_html(dok_path: Path) -> str:
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out = Path(f.name)
    result = subprocess.run(
        [sys.executable, "-m", "dok", str(dok_path), str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    html = out.read_text(encoding="utf-8")
    out.unlink(missing_ok=True)
    return html

# ── Base HTML shell ───────────────────────────────────────────
def wrap(body: str, title: str = "dok", active: str = "") -> str:
    def nav(href, label, key):
        cls = 'class="nav-active"' if active == key else ""
        return f'<a href="{href}" {cls}>{label}</a>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title} — dok</title>
  <link rel="stylesheet" href="/static/style.css"/>
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <a href="/" class="logo">dok</a>
      <span class="logo-sub">document markup language</span>
      <nav>
        {nav("/",           "Home",       "home")}
        {nav("/docs",       "Docs",       "docs")}
        {nav("/examples",   "Examples",   "examples")}
        {nav("/playground", "Playground", "playground")}
        <a href="https://github.com/mahmoudxyz/dok"
           target="_blank" class="nav-github">GitHub ↗</a>
      </nav>
    </div>
  </header>
  <main class="site-main">{body}</main>
  <footer class="site-footer">
    <div class="footer-inner">
      <span>dok — MIT License</span> <span>·</span>
      <a href="https://github.com/mahmoudxyz/dok">GitHub</a> <span>·</span>
      <a href="https://pypi.org/project/dok">PyPI</a>
    </div>
  </footer>
</body>
</html>"""

# ── Pre-compile all pages at startup ─────────────────────────
PAGES = {
    "/":         ("pages/index.dok",    "Home",     "home"),
    "/docs":     ("pages/docs.dok",     "Docs",     "docs"),
    "/examples": ("pages/examples.dok", "Examples", "examples"),
}

print("  compiling pages...")
COMPILED: dict[str, bytes] = {}
for route, (rel, title, active) in PAGES.items():
    path = HERE / rel
    try:
        html = wrap(dok_to_html(path), title=title, active=active)
        COMPILED[route] = html.encode()
        print(f"  ✓  {rel}")
    except Exception as e:
        print(f"  ✗  {rel}: {e}")
        COMPILED[route] = f"<pre style='color:red'>{e}</pre>".encode()

# ── MIME types ────────────────────────────────────────────────
MIMES = {
    ".css": "text/css",
    ".js":  "application/javascript",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}

# ── Handler ───────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()}  {fmt % args}")

    # GET ── compiled pages, static files, playground ──────────
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path in COMPILED:
            return self._send(200, "text/html", COMPILED[path])

        if path == "/playground":
            return self._send(200, "text/html", PLAYGROUND.read_bytes())

        if path.startswith("/static/"):
            f = HERE / path.lstrip("/")
            if f.exists():
                return self._send(200, MIMES.get(f.suffix, "application/octet-stream"), f.read_bytes())

        self._send(404, "text/plain", b"Not found")

    # POST /preview ── playground live compile ─────────────────
    def do_POST(self):
        if self.path != "/preview":
            return self._send(404, "text/plain", b"Not found")

        length = int(self.headers.get("Content-Length", 0))
        source = self.rfile.read(length).decode("utf-8")

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".dok", mode="w", encoding="utf-8", delete=False
            ) as f:
                f.write(source)
                tmp = Path(f.name)
            html = dok_to_html(tmp)
            tmp.unlink(missing_ok=True)
            self._send(200, "text/html", html.encode())
        except RuntimeError as e:
            self._send(400, "text/plain", str(e).encode())

    # ── helper ────────────────────────────────────────────────
    def _send(self, status: int, mime: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

# ── Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"\n  dok site  →  http://localhost:{port}")
    print(f"  Ctrl+C to stop\n")
    HTTPServer(("", port), Handler).serve_forever()