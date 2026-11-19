#!/usr/bin/env python3
"""Static contract checks for docker-compose.yml.

Run from the repository root:

    python scripts/check_stack.py

Exit code 0 means the stack file is internally consistent. These checks run
without Docker, so they work on a build host, in CI, and on a developer
laptop that has only Python and PyYAML.
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: python -m pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"

errors = []
warnings = []


def load():
    with COMPOSE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_DEFAULT = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]*)\}")


def host_ports(service_name, svc):
    """Return [(port:int, proto:str)] as published on the host."""
    out = []
    for entry in svc.get("ports", []) or []:
        text = str(entry)
        proto = "tcp"
        if "/" in text:
            text, proto = text.rsplit("/", 1)
        text = _DEFAULT.sub(r"\1", text)
        if "$" in text:
            warnings.append(f"{service_name}: unresolved variable in port {text}")
            continue
        parts = text.split(":")
        host = parts[-2] if len(parts) > 1 else parts[0]
        if "-" in host:
            warnings.append(f"{service_name}: port range {host} is not checked; use single ports")
            continue
        out.append((int(host), proto))
    return out


def code_dir(svc):
    """Repository directory backing a built service, from its Dockerfile."""
    dockerfile = str((svc.get("build") or {}).get("dockerfile", ""))
    match = re.match(r"docker/([^/]+)/Dockerfile$", dockerfile)
    return match.group(1) if match else None


def check_port_collisions(services, enabled_profiles, label):
    seen = defaultdict(list)
    for name, svc in services.items():
        profiles = set(svc.get("profiles") or [])
        if profiles and not profiles & enabled_profiles:
            continue
        for port, proto in host_ports(name, svc):
            seen[(port, proto)].append(name)
    for (port, proto), owners in sorted(seen.items()):
        if len(owners) > 1:
            errors.append(
                f"{label}: host port {port}/{proto} claimed by {', '.join(sorted(owners))}"
            )


def main():
    if not COMPOSE.exists():
        sys.exit(f"not found: {COMPOSE}")

    doc = load()
    services = doc.get("services") or {}

    check_port_collisions(services, set(), "default stack")
    check_port_collisions(services, {"free5gc"}, "default + free5gc")

    for name, svc in services.items():
        if not svc.get("container_name"):
            errors.append(f"{name}: missing container_name")
        if not svc.get("restart"):
            warnings.append(f"{name}: no restart policy")

        image = str(svc.get("image", ""))
        if image.startswith("free5gc/") and "free5gc" not in (svc.get("profiles") or []):
            errors.append(f"{name}: free5GC image outside the free5gc profile")

        base = code_dir(svc)
        if base:
            config_dir = ROOT / base / "config"
            if config_dir.is_dir() and any(config_dir.iterdir()):
                mounts = " ".join(str(v) for v in svc.get("volumes", []) or [])
                if f"./{base}/config" not in mounts:
                    errors.append(
                        f"{name}: {base}/config has files but the service does not mount it"
                    )

        if svc.get("build") and not svc.get("image"):
            build = svc["build"] or {}
            context = ROOT / str(build.get("context", "."))
            dockerfile = str(build.get("dockerfile", "Dockerfile"))
            if not (context / dockerfile).exists():
                errors.append(f"{name}: dockerfile not found: {dockerfile} (context {build.get('context', '.')})")

    # The location service must never contain a synthesised position again.
    gmlc_src = ROOT / "gmlc" / "src" / "gmlc_server.py"
    if gmlc_src.exists():
        text = gmlc_src.read_text(encoding="utf-8", errors="replace")
        for pattern, why in [
            (r"_simulate_location_lookup", "synthetic location helper present"),
            (r"37\.7749", "hard-coded latitude present"),
            (r"hashlib\.md5", "md5 used for positioning"),
        ]:
            if re.search(pattern, text):
                errors.append(f"gmlc_server.py: {why}")

    # Authentication must fail closed, never fabricate vectors.
    udm_src = ROOT / "udm" / "src" / "udm_server.py"
    if udm_src.exists():
        text = udm_src.read_text(encoding="utf-8", errors="replace")
        for pattern, why in [
            (r"def derive_5g_keys_simple", "non-3GPP key derivation still defined"),
            (r"# Fallback hash-based", "hash-based vector fallback still present"),
            (r'"(00"\s*\*\s*32)', "zero-filled auth vector still present"),
        ]:
            if re.search(pattern, text):
                errors.append(f"udm_server.py: {why}")

    # Positioning nodes must not synthesise coordinates.
    for rel in ("lmf/src/lmf_server.py", "amf/src/amf_server.py",
                "mme/src/mme_server.py"):
        src = ROOT / rel
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        for pattern, why in [
            (r"random\.(uniform|randint|random)", "random number used in a location node"),
            (r"37\.7749", "hard-coded latitude present"),
        ]:
            if re.search(pattern, text):
                errors.append(f"{rel}: {why}")

    # SUCI de-concealment must exist and must not embed a private key.
    suci_src = ROOT / "udm" / "src" / "suci.py"
    if not suci_src.exists():
        errors.append("udm/src/suci.py missing: Profile A/B de-concealment unavailable")
    else:
        text = suci_src.read_text(encoding="utf-8", errors="replace")
        if re.search(r"private_key\s*=\s*bytes\.fromhex\(\s*\"[0-9a-fA-F]{64}\"", text):
            errors.append("udm/src/suci.py: hard-coded private key")

    for name in ("nrf", "udm", "pcf", "smf", "upf", "gmlc", "hss",
                 "amf", "lmf", "mme"):
        if not (ROOT / name / "src").is_dir():
            warnings.append(f"{name}/src missing")
    if not (ROOT / "corelib").is_dir():
        warnings.append("corelib missing")

    if warnings:
        for item in warnings:
            print(f"WARN  {item}")
    if errors:
        for item in errors:
            print(f"FAIL  {item}")
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    print(f"OK    {len(services)} services, no host-port collisions, contracts satisfied")
    print(f"      {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
