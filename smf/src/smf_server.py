import json
import logging
import os
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("smf")

CONFIG_PATH = os.getenv("SMF_CONFIG", "/app/config/smf.yaml")
N4_PROFILE = os.getenv("SMF_N4_PROFILE", "/app/config/n4_profile.json")


class Handler(BaseHTTPRequestHandler):
    sessions = {}

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._send(200, {"status": "ok", "nf": "smf"})
            return
        if self.path.startswith("/nsmf-pdusession/v1/sm-contexts"):
            self._send(200, {"sessions": list(self.sessions.values())})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.startswith("/nsmf-pdusession/v1/sm-contexts"):
            sm_id = str(uuid.uuid4())
            ctx = {"id": sm_id, "state": "created", "dnn": os.getenv("SMF_DNN", "internet")}
            self.sessions[sm_id] = ctx
            log.info("SM context created id=%s (PFCP association target per %s)", sm_id, N4_PROFILE)
            self._send(201, ctx)
            return
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


def main():
    host = os.getenv("SMF_HOST", "0.0.0.0")
    port = int(os.getenv("SMF_PORT", "7777"))
    pfcp_port = int(os.getenv("PFCP_PORT", "8805"))
    log.info("Starting SMF stub on %s:%s (N4/PFCP port %s, config=%s)", host, port, pfcp_port, CONFIG_PATH)
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
