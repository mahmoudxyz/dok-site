"""
api/preview.py — Vercel serverless function.
POST /api/preview  — receives raw dok source, returns compiled HTML.
"""

from http.server import BaseHTTPRequestHandler
import tempfile
import subprocess
import sys
from pathlib import Path


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        source = self.rfile.read(length).decode("utf-8")

        try:
            # Write source to temp .dok file
            with tempfile.NamedTemporaryFile(
                suffix=".dok", mode="w", encoding="utf-8", delete=False
            ) as f:
                f.write(source)
                dok_tmp = Path(f.name)

            # Compile via CLI
            out_tmp = dok_tmp.with_suffix(".html")
            result  = subprocess.run(
                [sys.executable, "-m", "dok", str(dok_tmp), str(out_tmp)],
                capture_output=True, text=True,
            )

            dok_tmp.unlink(missing_ok=True)

            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)

            html = out_tmp.read_text(encoding="utf-8")
            out_tmp.unlink(missing_ok=True)

            self._send(200, "text/html", html.encode())

        except RuntimeError as e:
            self._send(400, "text/plain", str(e).encode())
        except Exception as e:
            self._send(500, "text/plain", str(e).encode())

    def do_OPTIONS(self):
        # Handle CORS preflight
        self._send(200, "text/plain", b"")

    def _send(self, status: int, mime: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)