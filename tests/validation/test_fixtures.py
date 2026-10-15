"""Test that shared canonical fixtures are schema-valid against common.schema.json."""

import json
from pathlib import Path
import jsonschema
import pytest

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "shared" / "schema" / "common.schema.json"


@pytest.fixture(scope="module")
def common_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_canonical_combined_schema_valid(common_schema):
    combined_path = FIXTURES_DIR / "canonical_combined.json"
    with open(combined_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validates full interchange object (schema_version, plan, solution)
    jsonschema.validate(instance=data, schema=common_schema)


def test_canonical_plan_defs_valid(common_schema):
    plan_path = FIXTURES_DIR / "canonical_two_room_plan.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)

    plan_schema = {
        "$schema": common_schema["$schema"],
        "$defs": common_schema["$defs"],
        "$ref": "#/$defs/plan",
    }
    jsonschema.validate(instance=plan_data, schema=plan_schema)


def test_canonical_solution_defs_valid(common_schema):
    sol_path = FIXTURES_DIR / "canonical_valid_solution.json"
    with open(sol_path, "r", encoding="utf-8") as f:
        sol_data = json.load(f)

    sol_schema = {
        "$schema": common_schema["$schema"],
        "$defs": common_schema["$defs"],
        "$ref": "#/$defs/solution",
    }
    jsonschema.validate(instance=sol_data, schema=sol_schema)
