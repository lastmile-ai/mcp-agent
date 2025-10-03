import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging

LOG = logging.getLogger("mcp_agent.health")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

def current_version():
    return os.getenv("MCP_AGENT_VERSION") or os.getenv("IMAGE_VERSION") or "dev"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            payload = {"status": "ok", "version": current_version()}
            body = json.dumps(payload).encode("utf-8")
            LOG.info("health_ok version=%s", payload["version"])
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

def serve(host: str = "0.0.0.0", port: int | None = None):
    port = int(port or os.getenv("PORT") or 8080)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()

def main():
    serve()

if __name__ == "__main__":
    main()
