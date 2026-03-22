"""
dok-site/server.py

Startup: compiles pages/*.dok + pages/examples/*.dok → HTML (once, in memory)
Runtime: serves compiled HTML + static files + playground live preview

Usage:
  python server.py        # http://localhost:8000
  python server.py 9000
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
EXAMPLES_DIR = HERE / "pages" / "examples"

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


# ── Build examples page from individual .dok files ────────────
EXAMPLE_META = [
    ("invoice.dok", "Invoice"),
    ("arabic.dok",  "Arabic RTL Document"),
    ("metrics.dok", "Report with Metrics"),
    ("flow.dok",    "Process Flow"),
]

def build_examples_page() -> bytes:
    parts = []
    parts.append("""
      <div class="examples-header">
        <h1>Examples</h1>
        <p>Each example below is compiled from a <code>.dok</code> file — exactly what you get in DOCX and HTML output.</p>
      </div>
    """)

    for i, (filename, title) in enumerate(EXAMPLE_META, 1):
        path = EXAMPLES_DIR / filename
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        try:
            rendered = dok_to_html(path)
            print(f"  ✓  examples/{filename}")
        except RuntimeError as e:
            rendered = f"<pre style='color:red'>{e}</pre>"
            print(f"  ✗  examples/{filename}: {e}")

        # Escape source for display in textarea
        escaped = source.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        parts.append(f"""
        <div class="example-block">
          <div class="example-header">
            <span class="example-num">{i}</span>
            <h2>{title}</h2>
            <a class="try-btn" href="/playground?source={filename}">Try in Playground →</a>
          </div>
          <div class="example-cols">
            <div class="example-source">
              <div class="pane-label">source  <span>.dok</span></div>
              <pre class="source-pre"><code>{escaped}</code></pre>
            </div>
            <div class="example-preview">
              <div class="pane-label">output  <span>rendered HTML</span></div>
              <div class="rendered-output">
                {rendered}
              </div>
            </div>
          </div>
        </div>
        """)

    body = "\n".join(parts)
    full = wrap(body, title="Examples", active="examples")
    return full.encode()


# ── Pre-compile static pages at startup ───────────────────────
STATIC_PAGES = {
    "/":     ("pages/index.dok", "Home",  "home"),
    "/docs": ("pages/docs.dok",  "Docs",  "docs"),
}

print("\n  compiling pages...")
COMPILED: dict[str, bytes] = {}

for route, (rel, title, active) in STATIC_PAGES.items():
    path = HERE / rel
    try:
        html = wrap(dok_to_html(path), title=title, active=active)
        COMPILED[route] = html.encode()
        print(f"  ✓  {rel}")
    except Exception as e:
        COMPILED[route] = f"<pre style='color:red'>{e}</pre>".encode()
        print(f"  ✗  {rel}: {e}")

print("  compiling examples...")
COMPILED["/examples"] = build_examples_page()


# ── MIME types ────────────────────────────────────────────────
MIMES = {
    ".css": "text/css",
    ".js":  "application/javascript",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}


# ── Request handler ───────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()}  {fmt % args}")

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        # Pre-compiled pages
        if path in COMPILED:
            return self._send(200, "text/html", COMPILED[path])

        # Playground
        if path == "/playground":
            return self._send(200, "text/html", PLAYGROUND.read_bytes())

        # Static files
        if path.startswith("/static/"):
            f = HERE / path.lstrip("/")
            if f.exists():
                return self._send(200, MIMES.get(f.suffix, "application/octet-stream"), f.read_bytes())

        self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        """Playground live preview — raw dok source in, raw HTML out."""
        if self.path not in ("/preview", "/api/preview"):
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