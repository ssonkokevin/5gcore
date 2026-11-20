import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("pcf")

CONFIG_PATH = os.getenv("PCF_CONFIG", "/app/config/pcf.yaml")
RULES_PATH = os.getenv("PCF_PCC_RULES", "/app/config/pcc_rules.json")


def load_rules():
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"rules": []}


class Handler(BaseHTTPRequestHandler):
    rules = load_rules()

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._send(200, {"status": "ok", "nf": "pcf"})
            return
        if self.path.startswith("/npcf-smpolicycontrol/v1/sm-policies"):
            self._send(200, {"policies": [], "rules": self.rules.get("rules", [])})
            return
        if self.path.startswith("/npcf-am-policy-control/v1/policies"):
            self._send(200, {"policies": []})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.startswith("/npcf-smpolicycontrol/v1/sm-policies"):
            self._send(201, {"status": "created", "rules": self.rules.get("rules", [])})
            return
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


def main():
    host = os.getenv("PCF_HOST", "0.0.0.0")
    port = int(os.getenv("PCF_PORT", "7777"))
    log.info("Starting PCF stub on %s:%s (config=%s)", host, port, CONFIG_PATH)
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
