"""
build.py — pre-compile all .dok pages to HTML for static hosting.

Run:  python build.py
Out:  dist/          ← ready to deploy to Vercel / Netlify / GitHub Pages

Structure:
  pages/index.dok    → dist/index.html
  pages/docs.dok     → dist/docs/index.html
  pages/examples/    → dist/examples/index.html  (side-by-side layout)
  playground.html    → dist/playground/index.html
  public/static/     → dist/static/
"""

import subprocess
import sys
import shutil
import tempfile
from pathlib import Path

ROOT     = Path(__file__).parent
DIST     = ROOT / "dist"
PAGES    = ROOT / "pages"
EXAMPLES = ROOT / "pages" / "examples"
PUBLIC   = ROOT / "public"

EXAMPLE_META = [
    ("invoice.dok", "Invoice"),
    ("arabic.dok",  "Arabic RTL Document"),
    ("metrics.dok", "Report with Metrics"),
    ("flow.dok",    "Process Flow"),
]

# ── Helpers ───────────────────────────────────────────────────

def dok_to_html(dok_path: Path) -> str:
    """Compile a .dok file to HTML string via CLI."""
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
        {nav("/",            "Home",       "home")}
        {nav("/docs/",       "Docs",       "docs")}
        {nav("/examples/",   "Examples",   "examples")}
        {nav("/playground/", "Playground", "playground")}
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


def write(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"  ✓  {path.relative_to(DIST)}")


def build_examples_page() -> str:
    parts = ["""
      <div class="examples-header">
        <h1>Examples</h1>
        <p>Each example is compiled from a <code>.dok</code> file —
           exactly what you get in DOCX and HTML output.</p>
      </div>
    """]

    for i, (filename, title) in enumerate(EXAMPLE_META, 1):
        path = EXAMPLES / filename
        if not path.exists():
            print(f"  ⚠  examples/{filename} not found, skipping")
            continue

        source  = path.read_text(encoding="utf-8")
        escaped = (source
                   .replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;"))
        try:
            rendered = dok_to_html(path)
        except RuntimeError as e:
            rendered = f"<pre style='color:red'>{e}</pre>"
            print(f"  ✗  examples/{filename}: {e}")

        parts.append(f"""
        <div class="example-block">
          <div class="example-header">
            <span class="example-num">{i}</span>
            <h2>{title}</h2>
          </div>
          <div class="example-cols">
            <div class="example-source">
              <div class="pane-label">source <span>.dok</span></div>
              <pre class="source-pre"><code>{escaped}</code></pre>
            </div>
            <div class="example-preview">
              <div class="pane-label">output <span>rendered</span></div>
              <div class="rendered-output">{rendered}</div>
            </div>
          </div>
        </div>
        """)

    return wrap("\n".join(parts), title="Examples", active="examples")


# ── Build ─────────────────────────────────────────────────────

def main():
    print(f"\n  cleaning dist/...")
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    # Static files
    if PUBLIC.exists():
        shutil.copytree(PUBLIC, DIST / "public"  )
        # also copy static to dist/static so /static/ paths work
        shutil.copytree(PUBLIC / "static", DIST / "static")
        print(f"  ✓  static/")
    elif (ROOT / "static").exists():
        shutil.copytree(ROOT / "static", DIST / "static")
        print(f"  ✓  static/")

    # Playground — copy as-is
    pg = ROOT / "playground.html"
    if pg.exists():
        (DIST / "playground").mkdir(parents=True, exist_ok=True)
        shutil.copy(pg, DIST / "playground" / "index.html")
        print(f"  ✓  playground/index.html")

    print(f"\n  compiling pages...")

    # Home
    write(DIST / "index.html",
          wrap(dok_to_html(PAGES / "index.dok"), title="Home", active="home"))

    # Docs
    write(DIST / "docs" / "index.html",
          wrap(dok_to_html(PAGES / "docs.dok"), title="Docs", active="docs"))

    # Examples — built dynamically with side-by-side layout
    print(f"\n  compiling examples...")
    write(DIST / "examples" / "index.html", build_examples_page())

    print(f"\n  done → dist/")
    print(f"  deploy: vercel --prod\n")


if __name__ == "__main__":
    main()