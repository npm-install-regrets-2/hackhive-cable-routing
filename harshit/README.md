# Harshit workspace

Ownership: normalized input and geometry.

Start with these modules when implementation begins:

- `ingestion/`: ResPlan loading and canonical plan conversion
- `geometry/`: room components, unit conversion, clearance, obstacles, portals, traversability, and reusable legality queries
- `tests/`: fixtures and tests for all owned behavior

Produce normalized `Plan` data through `../shared/schema/common.schema.json`. Hand off stable IDs, scale, rooms, nodes, obstacles, and verified portals. Sana owns solution validation; Priyanshu owns optimization. Log each meaningful step in `../docs/progress/harshit.md`.
