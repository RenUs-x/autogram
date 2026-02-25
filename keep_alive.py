import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        # Это заставит UptimeRobot видеть "200 OK" вместо "501"
        self.send_response(200)
        self.end_headers()

def run():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

def keep_alive():
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()


def start():
    """Backward-compatible entrypoint used by main.py."""
    keep_alive()
