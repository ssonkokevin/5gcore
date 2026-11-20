"""Repository-level guards for the location work.

Cheap checks that stop the Phase 0 intent from quietly eroding: the GMLC stays
out of this repo, the archived stub stays archived, and no operator secrets
enter the tree.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", "archive"}


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".docx"}:
            continue
        yield path


def test_no_vendor_ss7_library_is_referenced():
    offenders = []
    for path in iter_text_files():
        if path.name == Path(__file__).name:
            continue  # this test names the string it forbids
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if re.search(r"jss7", text, re.IGNORECASE):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        "the vendor SS7 library must not be referenced anywhere outside archive/: "
        f"{offenders}"
    )


def test_compose_has_no_gmlc_service():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert not re.search(r"^  gmlc:\s*$", compose, re.MULTILINE), (
        "the GMLC lives in its own repository (D1)"
    )


def test_env_example_does_not_carry_operator_secrets():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in ("OPERATOR_KEY", "MESSAGE_STORE_KEY", "JWT_SECRET"):
        match = re.search(rf"^{name}=(.*)$", env, re.MULTILINE)
        if match:
            assert match.group(1).strip() == "", (
                f"{name} must be empty in .env.example; a placeholder invites "
                "someone to commit a real key"
            )
    assert not re.search(r"^(K|KI|OPC?)=[0-9a-fA-F]{32}$", env, re.MULTILINE), (
        "no 128-bit key literal in .env.example"
    )


def test_dotenv_is_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.env$", ignore, re.MULTILINE)


def test_decision_docs_exist_and_are_numbered():
    decisions = (ROOT / "docs" / "location" / "DECISIONS.md").read_text(encoding="utf-8")
    numbers = [int(n) for n in re.findall(r"^## D(\d+)\.", decisions, re.MULTILINE)]
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"decisions must be sequential from D1, got {numbers}"
    )
