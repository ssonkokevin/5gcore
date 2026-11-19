"""Stack contracts — run without Docker or a live service.

    python tests/test_stack_contract.py
    python -m unittest discover -s tests
"""

import importlib.util
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"


def load_compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def load_checker():
    spec = importlib.util.spec_from_file_location("check_stack", ROOT / "scripts" / "check_stack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStaticContracts(unittest.TestCase):
    def test_check_stack_passes(self):
        checker = load_checker()
        self.assertEqual(checker.main(), 0, "scripts/check_stack.py reported errors")

    def test_every_custom_session_peer_is_the_custom_upf(self):
        services = load_compose()["services"]
        self.assertIn("N4_SMF_UPF_ADDR=custom-upf", services["custom-smf"]["environment"])
        self.assertIn("custom-upf", services["custom-smf"]["depends_on"])

    def test_custom_nfs_discover_via_the_custom_nrf(self):
        services = load_compose()["services"]
        for name in ("custom-pcf", "custom-smf", "hss"):
            env = services[name]["environment"]
            self.assertIn("NRF_ADDR=custom-nrf", env, f"{name} points at the wrong NRF")

    def test_free5gc_ports_leave_38412_free(self):
        services = load_compose()["services"]
        for name, svc in services.items():
            if "free5gc" not in (svc.get("profiles") or []):
                continue
            for entry in svc.get("ports", []) or []:
                self.assertFalse(str(entry).startswith("38412:"), f"{name} still claims host port 38412")

    def test_every_compose_variable_is_documented(self):
        text = COMPOSE.read_text(encoding="utf-8")
        documented = ENV_EXAMPLE.read_text(encoding="utf-8")
        used = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", text))
        missing = sorted(v for v in used if not re.search(rf"^{v}=", documented, re.M))
        self.assertEqual(missing, [], f"undocumented variables: {missing}")

    def test_every_published_port_is_parameterised(self):
        services = load_compose()["services"]
        hard = []
        for name, svc in services.items():
            for entry in svc.get("ports", []) or []:
                if not str(entry).strip('"').startswith("${"):
                    hard.append(f"{name}: {entry}")
        self.assertEqual(hard, [], "host ports must be ${X_HOST_PORT:-default}")

    def test_host_port_override_does_not_move_the_container_listener(self):
        services = load_compose()["services"]
        self.assertIn("AMF_PORT=8001", services["custom-amf"]["environment"])
        self.assertIn("LMF_PORT=8003", services["custom-lmf"]["environment"])
        self.assertIn("MME_SLG_PORT=3875", services["custom-mme"]["environment"])
        self.assertIn("MME_HTTP_PORT=8075", services["custom-mme"]["environment"])

    def test_env_override_is_honoured_in_collision_checks(self):
        checker = load_checker()
        services = load_compose()["services"]
        env = {key: "8080" for key in ("DB_HOST_PORT", "HSSDB_HOST_PORT", "REDIS_HOST_PORT")}
        checker.errors.clear()
        checker.check_port_collisions(services, set(), "test", env)
        self.assertTrue(
            any("8080/tcp" in item for item in checker.errors),
            "an .env override that collides must be reported",
        )

    def test_stp_config_is_rendered_not_committed(self):
        template = (ROOT / "stp" / "config" / "osmo-stp.cfg.template").read_text(encoding="utf-8")
        self.assertIn("point-code ${STP_LOCAL_PC}", template)
        self.assertIn("${STP_ROUTES}", template)
        self.assertTrue((ROOT / "docker" / "stp" / "entrypoint.sh").exists())
        for path in (ROOT / "stp" / "config").glob("*"):
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith(("route ", "point-code ")):
                    self.assertIn("${", stripped, f"{path.name}: literal point code committed")

    def test_gmlc_has_no_position_synthesis(self):
        source = (ROOT / "gmlc" / "src" / "gmlc_server.py").read_text(encoding="utf-8")
        for token in ("_simulate_location_lookup", "hashlib.md5", "37.7749"):
            self.assertNotIn(token, source)

    def test_udm_has_no_fabricated_vectors(self):
        source = (ROOT / "udm" / "src" / "udm_server.py").read_text(encoding="utf-8")
        for token in ("derive_5g_keys_simple", "derive_2g3g_keys_simple", "# Fallback hash-based"):
            self.assertNotIn(token, source)
        self.assertIn("CRYPTO_UNAVAILABLE", source)

    def test_udm_and_hss_share_corelib_milenage(self):
        for name in ("udm/src/udm_server.py", "hss/src/nhss_server.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("from corelib.milenage import", source, name)
            self.assertNotIn("class MilenageCrypto", source, name)
            self.assertNotIn("HMAC.new", source, f"{name} still fabricates keys")
            self.assertNotIn("hashlib.sha256((op", source, f"{name} still has an OPc fallback")
            self.assertNotIn("hashlib.sha256((row[", source, f"{name} still hashes a vector")
        for name in ("udm", "hss"):
            dockerfile = (ROOT / "docker" / name / "Dockerfile").read_text(encoding="utf-8")
            self.assertIn("COPY ./corelib/ /app/corelib/", dockerfile, name)

    def test_location_chain_registers_with_the_custom_nrf(self):
        services = load_compose()["services"]
        for name in ("custom-amf", "custom-lmf"):
            self.assertIn("NRF_ADDR=custom-nrf", services[name]["environment"])
            self.assertIn("custom-nrf", services[name]["depends_on"])

    def test_custom_amf_does_not_publish_an_ngap_port(self):
        services = load_compose()["services"]
        ports = [str(p) for p in services["custom-amf"].get("ports", [])]
        self.assertFalse(any("38412" in p for p in ports), "NGAP is not implemented; do not publish it")

    def test_mme_is_slg_only(self):
        services = load_compose()["services"]
        ports = " ".join(str(p) for p in services["custom-mme"].get("ports", []))
        self.assertIn("3875", ports)
        self.assertNotIn("36412", ports)
        self.assertNotIn("2123", ports)

    def test_suci_module_ships_with_the_udm(self):
        self.assertTrue((ROOT / "udm" / "src" / "suci.py").exists())
        dockerfile = (ROOT / "docker" / "udm" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("cryptography", dockerfile)

    def test_reference_and_custom_stacks_are_separated(self):
        services = load_compose()["services"]
        for name, svc in services.items():
            if str(svc.get("image", "")).startswith("free5gc/"):
                self.assertIn("free5gc", svc.get("profiles") or [], f"{name} is always-on")

    def test_udr_fronts_the_authentication_subscription(self):
        services = load_compose()["services"]
        udr = services["custom-udr"]
        self.assertIn("UDR_PORT=8006", udr["environment"])
        self.assertEqual(udr["ports"], ["${UDR_HOST_PORT:-8006}:8006/tcp"])
        self.assertIn("healthcheck", udr)
        self.assertIn("NRF_ADDR=custom-nrf", udr["environment"])
        self.assertTrue((ROOT / "docker" / "udr" / "Dockerfile").exists())

        udm = services["custom-udm"]
        self.assertIn("UDR_ADDR=custom-udr", udm["environment"])
        self.assertIn("custom-udr", udm["depends_on"])

    def test_udm_does_not_advance_sqn_in_sql(self):
        source = (ROOT / "udm" / "src" / "udm_server.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "UPDATE tbl_subscriber SET sqn=",
            source,
            "SQN must be advanced through the UDR's conditional PATCH",
        )
        self.assertIn("_generate_with_sqn_cas", source)

    def test_udr_is_a_conditional_store(self):
        source = (ROOT / "udr" / "src" / "udr_server.py").read_text(encoding="utf-8")
        for token in ("If-Match", "PRECONDITION_REQUIRED", "FOR UPDATE", "AND sqn="):
            self.assertIn(token, source, f"UDR lost its conditional-write guard: {token}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
