"""Schema rules that must hold for every location table.

These tests read the SQL, not a database, so they run on any host. The
database-backed checks come later behind the `db` marker.
"""

from pathlib import Path
import re

import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "database" / "location"
SCHEMA_FILES = sorted(SCHEMA_DIR.glob("*.sql"))

TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\)\s*ENGINE",
    re.DOTALL,
)


def load_schema_tables():
    tables = {}
    for path in SCHEMA_FILES:
        text = path.read_text(encoding="utf-8")
        for match in TABLE_RE.finditer(text):
            tables[match.group(1)] = match.group(2)
    return tables


def columns_of(body: str):
    names = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        if line.upper().startswith(
            ("PRIMARY KEY", "KEY ", "UNIQUE KEY", "CONSTRAINT", "INDEX ")
        ):
            continue
        name = line.split()[0].strip("`,")
        names.append(name.lower())
    return names


def primary_key_of(body: str):
    match = re.search(r"PRIMARY KEY\s*\(([^)]*)\)", body)
    assert match, "every table needs an explicit primary key"
    return [part.strip().lower() for part in match.group(1).split(",")]


TABLES = load_schema_tables()


def test_schema_files_are_present_and_parse():
    assert SCHEMA_FILES, "no SQL files under database/location"
    # The bookkeeping table plus the four domain tables.
    expected = {
        "tbl_lcs_schema_version",
        "tbl_location_tenant",
        "tbl_lcs_cell",
        "tbl_lcs_session",
        "tbl_lcs_result",
        "tbl_ue_lcs_capability",
    }
    assert expected <= set(TABLES), f"missing tables: {expected - set(TABLES)}"


# Infrastructure tables: the schema log applies to the database as a whole and
# the tenant registry is keyed by the tenant itself.
NO_TENANT_COLUMN = {"tbl_lcs_schema_version"}


@pytest.mark.parametrize("table", sorted(set(TABLES) - NO_TENANT_COLUMN))
def test_every_data_table_carries_a_tenant(table):
    body = TABLES[table]
    assert "tenant_id" in columns_of(body), f"{table} has no tenant_id (D11)"


def test_only_the_schema_log_lacks_a_tenant_column():
    without = {t for t in TABLES if "tenant_id" not in columns_of(TABLES[t])}
    assert without == NO_TENANT_COLUMN, (
        f"unexpected table without tenant_id: {without - NO_TENANT_COLUMN}"
    )
    assert primary_key_of(TABLES["tbl_location_tenant"]) == ["tenant_id"]


@pytest.mark.parametrize("table", sorted(set(TABLES) - NO_TENANT_COLUMN))
def test_tenant_leads_the_primary_key(table):
    assert primary_key_of(TABLES[table])[0] == "tenant_id", (
        f"{table} must key on tenant_id first so one tenant's rows can never "
        "collide with another's"
    )


def test_result_table_enforces_the_honesty_envelope():
    columns = columns_of(TABLES["tbl_lcs_result"])
    for required in (
        "method",
        "methods_attempted",
        "shape",
        "uncertainty_m",
        "confidence",
        "age_seconds",
        "accuracy_fulfilled",
    ):
        assert required in columns, f"result table missing {required} (D10)"


def test_result_rows_are_append_only_in_the_schema():
    text = "\n".join(path.read_text(encoding="utf-8") for path in SCHEMA_FILES)
    assert not re.search(r"\bDROP\s+TABLE\b", text, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", text, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\b", text, re.IGNORECASE)


def test_scripts_are_idempotent():
    for path in SCHEMA_FILES:
        text = path.read_text(encoding="utf-8")
        creates = re.findall(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?", text)
        guarded = re.findall(r"CREATE TABLE IF NOT EXISTS\s+", text)
        assert len(creates) == len(guarded), f"{path.name}: CREATE TABLE without IF NOT EXISTS"
        inserts = re.findall(r"INSERT\s+(?:IGNORE\s+)?", text, re.IGNORECASE)
        guarded_inserts = re.findall(r"INSERT IGNORE", text, re.IGNORECASE)
        assert len(inserts) == len(guarded_inserts), f"{path.name}: INSERT without IGNORE"


def test_json_columns_are_not_indexed():
    for table, body in TABLES.items():
        json_columns = {
            line.split()[0].strip("`,").lower()
            for line in body.splitlines()
            if " JSON" in line.upper() and not line.strip().startswith("--")
        }
        for key_line in re.findall(r"^\s*KEY[^(]*\(([^)]*)\)", body, re.MULTILINE):
            indexed = {part.strip().lower() for part in key_line.split(",")}
            assert not (indexed & json_columns), (
                f"{table} indexes a JSON column: {indexed & json_columns}"
            )


def test_schema_records_its_version():
    text = "\n".join(path.read_text(encoding="utf-8") for path in SCHEMA_FILES)
    assert re.search(
        r"INSERT IGNORE INTO tbl_lcs_schema_version\s*\(script", text
    ), "each schema script must record itself in tbl_lcs_schema_version"


def test_ddl_parses_as_mysql():
    """A grammar check, not an execution. MariaDB itself is exercised by the
    `db`-marked tests once a server is available."""
    sqlglot = pytest.importorskip("sqlglot", reason="sqlglot not installed")
    for path in SCHEMA_FILES:
        statements = sqlglot.parse(path.read_text(encoding="utf-8"), read="mysql")
        creates = [s for s in statements if s is not None and s.key == "create"]
        assert creates, f"{path.name} produced no CREATE statements"
        for statement in creates:
            assert statement.args.get("this"), f"{path.name}: CREATE without a target"
