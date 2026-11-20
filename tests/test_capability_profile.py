"""The capability profile is a promise, so it is held to the schema."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

DOCS = Path(__file__).resolve().parents[1] / "docs" / "location"
SCHEMA = json.loads((DOCS / "capability-profile.schema.json").read_text(encoding="utf-8"))
PROFILE = json.loads((DOCS / "capability-profile.tenant-1.json").read_text(encoding="utf-8"))

VALIDATOR = Draft202012Validator(SCHEMA)


def errors_for(profile):
    return [e.message for e in VALIDATOR.iter_errors(profile)]


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


def test_tenant_one_profile_matches_the_schema():
    assert errors_for(PROFILE) == []


def test_every_declared_method_has_a_build_status():
    for rat, entry in PROFILE["rat"].items():
        assert set(entry["methods"]) <= set(entry["method_status"]), (
            f"{rat} declares a method without a status, which would let the API "
            "promise something unbuilt"
        )
        assert set(entry["method_status"]) <= set(entry["methods"])


def test_cell_id_only_rats_have_no_engine():
    for rat, entry in PROFILE["rat"].items():
        if entry["engine"] is None:
            assert entry["methods"] == ["CELL_ID"], (
                f"{rat} has no positioning engine, so cell-ID is its only method"
            )


def test_a_profile_without_tenant_is_rejected():
    broken = json.loads(json.dumps(PROFILE))
    del broken["tenant_id"]
    assert errors_for(broken)


def test_unknown_claim_is_rejected():
    broken = json.loads(json.dumps(PROFILE))
    broken["rat"]["LTE"]["nrppa"] = True
    broken["rat"]["LTE"]["surprise_capability"] = "yes"
    assert errors_for(broken)


def test_geometry_methods_require_several_trps():
    overclaim = json.loads(json.dumps(PROFILE))
    lte = overclaim["rat"]["LTE"]
    lte["methods"] = ["CELL_ID", "OTDOA"]
    lte["method_status"]["OTDOA"] = "BUILT"
    assert lte.get("trp_count", 0) < 2
    assert errors_for(overclaim), (
        "OTDOA with fewer than two transmission points must not validate: the "
        "geometry cannot produce a fix"
    )


def test_only_lab_plmns_are_claimed():
    for plmn in PROFILE["plmns"]:
        assert (plmn["mcc"], plmn["mnc"]) in {("001", "01"), ("999", "70")}


def test_profile_has_no_true_build_claims_yet():
    """Phase 0 builds nothing that measures. This guard is updated, not
    deleted, when a phase's exit test passes."""
    claimed = [
        (rat, method)
        for rat, entry in PROFILE["rat"].items()
        for method, status in entry["method_status"].items()
        if status == "BUILT"
    ]
    assert claimed == [], f"Phase 0 claims built methods: {claimed}"
