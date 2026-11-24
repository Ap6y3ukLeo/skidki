"""Приёмник данных из браузера: POST с телом JSON дописывает строки в data/ingest/5ka.jsonl.

Запуск: .venv\\Scripts\\python.exe ingest.py
Слушает только 127.0.0.1:8765 — снаружи недоступен.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

OUT = Path("data/ingest")
OUT.mkdir(parents=True, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        print("OPTIONS", self.path, dict(self.headers).get("Access-Control-Request-Private-Network"), flush=True)
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            items = json.loads(raw)
        except Exception:
            self.send_response(400)
            self._cors()
            self.end_headers()
            return

        name = self.path.strip("/").replace("/", "-") or "default"
        target = OUT / f"{name}.jsonl"
        with target.open("a", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("приёмник на http://127.0.0.1:8765")
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
