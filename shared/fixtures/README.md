# Shared Canonical Fixtures

This directory contains hand-checked, schema-valid reference fixtures for cross-workspace testing and validation.

## `canonical_two_room_plan.json` & `canonical_valid_solution.json`

A minimal, fully verified 2-room layout designed to test:
1. Exact unit conversion (10 drawing units per metre).
2. Connected 2-room territory through a verified 1-metre door portal.
3. Single closed ring starting and ending at `hub_1`.
4. Door crossing and retrace into/out of a single-door room (`room_bedroom`).
5. Collinear overlap calculation `O`.
6. Bend and reversal counting `B` (including at hubs and nodes).
7. Crossings calculation `X` (zero crossings).
8. Slide-based objective cost `J = L + 5X + O + 0.5B`.

### Geometric layout

- Scale: `drawing_units_per_metre = 10.0` (1 unit = 0.1 m).
- Internal boundary: `[0, 100] x [0, 50]` (10.0 m x 5.0 m = 50.0 m²).
- `room_living`: `[0, 60] x [0, 50]` (6.0 m x 5.0 m = 30.0 m²).
  - Fixed node `node_living`: `(20.0, 25.0)`. Wall clearance = min(20, 40, 25, 25) = 20 units = 2.0 m >= 0.5 m.
  - Hub `hub_1`: `(10.0, 10.0)`.
- `room_bedroom`: `[60, 100] x [0, 50]` (4.0 m x 5.0 m = 20.0 m²).
  - Fixed node `node_bedroom`: `(80.0, 25.0)`. Wall clearance = min(20, 20, 25, 25) = 20 units = 2.0 m >= 0.5 m.
- Shared wall: `x = 60.0`, with door portal `portal_door_1` from `(60.0, 20.0)` to `(60.0, 30.0)`.
- Wall obstacles:
  - `wall_shared_lower`: `(60.0, 0.0)` to `(60.0, 20.0)`.
  - `wall_shared_upper`: `(60.0, 30.0)` to `(60.0, 50.0)`.

### Cable ring and route legs

- Ring sequence: `hub_1` -> `node_living` -> `node_bedroom` -> `hub_1`.
- Leg 1 (`hub_1` -> `node_living`):
  - Polyline: `[(10.0, 10.0), (10.0, 25.0), (20.0, 25.0)]`
  - Segments:
    - `(10, 10) -> (10, 25)`: vertical, length 15 units = 1.5 m
    - `(10, 25) -> (20, 25)`: horizontal, length 10 units = 1.0 m
  - Leg 1 length: 2.5 m
- Leg 2 (`node_living` -> `node_bedroom`):
  - Polyline: `[(20.0, 25.0), (60.0, 25.0), (80.0, 25.0)]`
  - Passes through door portal at `(60.0, 25.0)`
  - Segment: horizontal straight line, length 60 units = 6.0 m
  - Leg 2 length: 6.0 m
- Leg 3 (`node_bedroom` -> `hub_1`):
  - Polyline: `[(80.0, 25.0), (60.0, 25.0), (20.0, 25.0), (20.0, 10.0), (10.0, 10.0)]`
  - Passes through door portal at `(60.0, 25.0)` and returns to `node_living` at `(20.0, 25.0)` before heading to `hub_1`
  - Segments:
    - `(80, 25) -> (60, 25)`: horizontal West, length 20 units = 2.0 m
    - `(60, 25) -> (20, 25)`: horizontal West, length 40 units = 4.0 m
    - `(20, 25) -> (20, 10)`: vertical South, length 15 units = 1.5 m
    - `(20, 10) -> (10, 10)`: horizontal West, length 10 units = 1.0 m
  - Leg 3 length: 8.5 m

### Metric arithmetic

- Total length `L`:
  `L = 2.5 + 6.0 + 8.5 = 17.0 m`.
- Shared collinear overlap `O`:
  - Along line `y = 25.0`, Leg 2 covers `x in [20.0, 80.0]` and Leg 3 covers `x in [20.0, 80.0]`.
  - The shared collinear interval is `x in [20.0, 80.0]`, length 60 units = 6.0 m.
  - Number of overlapping legs `k = 2`, contributing `(2 - 1) * 6.0 m = 6.0 m`.
  - `O = 6.0 m`.
- Crossings `X`:
  - All cable intersections occur at fixed nodes (`node_living`, `node_bedroom`) or the hub (`hub_1`).
  - No meetings occur away from a node or hub.
  - `X = 0`.
- Bends `B`:
  1. At `hub_1` `(10, 10)`: Arrival direction is West `(-1, 0)`; departure direction is North `(0, 1)`. 90° turn = 1 bend.
  2. At `(10, 25)` (Leg 1 vertex): North to East. 90° turn = 1 bend.
  3. At `node_living` `(20, 25)`: Leg 1 enters East; Leg 2 leaves East. Straight-through = 0 bends.
  4. At `node_bedroom` `(80, 25)`: Leg 2 enters East `(1, 0)`; Leg 3 leaves West `(-1, 0)`. 180° reversal = 1 bend.
  5. At `node_living` `(20, 25)` (on Leg 3): West to South. 90° turn = 1 bend.
  6. At `(20, 10)` (Leg 3 vertex): South to West. 90° turn = 1 bend.
  - Total bends `B = 1 + 1 + 0 + 1 + 1 + 1 = 5 bends`.
- Objective score `J`:
  `J = L + 5X + O + 0.5B = 17.0 + 5*(0) + 6.0 + 0.5*(5) = 25.5`.
- Area gap:
  Only 1 hub opened, so `area_gap_m2 = 0.0 m²`.
- Hub count:
  `H = 1`.
