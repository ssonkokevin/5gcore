import json
import logging
import os
import signal
import socket
import threading
import time

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("upf")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def udp_listener(name, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    log.info("%s listener on UDP %s", name, port)
    while True:
        try:
            data, addr = s.recvfrom(4096)
            log.info("%s received %s bytes from %s (stub, not forwarded)", name, len(data), addr)
        except OSError:
            break


def main():
    cfg_dir = os.getenv("UPF_CONFIG_DIR", "/app/config")
    dpe = load_json(os.path.join(cfg_dir, "dpe.json"))
    cpe = load_json(os.path.join(cfg_dir, "cpe.json"))
    mgr = load_json(os.path.join(cfg_dir, "dpeMgr.json"))

    n4_port = int(os.getenv("PFCP_PORT", "8805"))
    n3_port = int(os.getenv("GTPU_PORT", "2152"))
    mode = os.getenv("DATA_PATH_MODE", "single_pass")

    log.info("Starting UPF stub (mode=%s, dpdk=%s, dpi=%s, cgnat=%s)",
             mode, os.getenv("DPDK_ENABLED", "false"),
             os.getenv("DPI_ENABLED", "false"), os.getenv("CGNAT_ENABLED", "false"))
    log.info("DPE config: group=%s features=%s", dpe.get("dpe_group"), dpe.get("up_function_features"))
    log.info("CPE config: max_session=%s threads=%s", cpe.get("single_dpe_max_session"), cpe.get("max_thread_num"))
    log.info("DPE mgr: port=%s container=%s", mgr.get("mgmt_port"), mgr.get("container_deployment"))

    threads = [
        threading.Thread(target=udp_listener, args=("PFCP/N4", n4_port), daemon=True),
        threading.Thread(target=udp_listener, args=("GTP-U/N3", n3_port), daemon=True),
    ]
    for t in threads:
        t.start()

    stop = threading.Event()

    def _shutdown(*_):
        log.info("Shutdown signal received")
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    while not stop.is_set():
        time.sleep(5)


if __name__ == "__main__":
    main()
