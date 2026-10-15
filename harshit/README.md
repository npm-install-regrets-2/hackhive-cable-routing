# Harshit workspace

Ownership: normalized input and independent verification.

Start with these modules when implementation begins:

- `ingestion/`: ResPlan loading and canonical plan conversion
- `geometry/`: room components, unit conversion, clearance, obstacles, portals, and traversability
- `validation/`: hard-constraint checks and independent metric recomputation
- `visualization/`: overlays generated from normalized plans and validated solutions
- `tests/`: fixtures and tests for all owned behavior

The workspace must emit normalized plans and consume solutions through `../shared/schema/common.schema.json`. Do not import optimizer internals from `../priyanshu/`.
