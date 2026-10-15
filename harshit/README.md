# Harshit workspace

Ownership: normalized input and geometry.

Start with these modules when implementation begins:

- `ingestion/`: ResPlan loading and canonical plan conversion
- `geometry/`: room components, unit conversion, clearance, obstacles, portals, traversability, and reusable legality queries
- `tests/`: fixtures and tests for all owned behavior

Produce normalized `Plan` data through `../shared/schema/common.schema.json`. Hand off stable IDs, scale, rooms, nodes, obstacles, and verified portals. Sana owns solution validation; Priyanshu owns optimization. Log each meaningful step in `../docs/progress/harshit.md`.

## Current thin slice

`ingestion.normalize_plan(raw, rules=Rules(), fixed_nodes=None)` converts one trusted ResPlan item into a schema-shaped `Plan` and separate diagnostics. `load_trusted_plan(path, plan_id)` reads a locally trusted pickle archive; never use it for uploads. `fixed_nodes` is keyed by stable room ID such as `room:living:000` and uses drawing-unit `(x, y)` pairs. Unspecified points are deterministic **development fallback** nodes, not organizer points. Defaults are five nodes and 100 m² per hub, both configurable.

The normalized Plan stores only geometrically evidenced doors or unobstructed shared-boundary portals. `geometry.portal_graph(plan, allow_excluded_transit=False)` derives deterministic room adjacency from these endpoints; excluded-room transit is an explicit option. An unverified connection is reported as a diagnostic. The current shared schema has no diagnostics field, so a fatal geometry or node error returns `plan=None` with structured diagnostics. Nonfatal unresolved doors and disconnected rooms remain visible in the result. Open-passage inference is conservative and needs validation against organizer rules. ResPlan `land` overlays the building and is not emitted as an interior room; the internal boundary defines exterior space.

Run `python -m pytest tests` from this directory after installing `shapely`, `jsonschema`, and `pytest`. The tests use a labelled synthetic fixture. The older `C:/Users/harsh/Desktop/HACKHIVE/tests/` cover scale inspection and an unrelated routing prototype; they do not validate this shared Plan output. The ResPlan archive is available at `C:/Users/harsh/Desktop/HACKHIVE/archive/ResPlan.pkl` for selected-item smoke tests; it is not committed here.

