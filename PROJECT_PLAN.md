# Project Plan: Joint Hub Placement and Closed-Ring Cable Routing

## 1. Purpose

Build a working prototype that consumes an unseen ResPlan residential floor plan and produces:

- the minimum feasible number of hubs and their locations;
- an exclusive assignment of every eligible room and fixed node to one hub;
- a contiguous, capacity-compliant territory for every hub;
- one closed, non-branching, axis-aligned cable ring per hub;
- legal cable polylines that use doors or open passages, avoid walls/windows/exterior space, and return to their originating hubs;
- a visual overlay and matching JSON suitable for validation and scoring.

The most accurate literature label is **obstacle-aware capacitated location-routing with connected room territories and panel-rooted closed tours**. Ring-Star literature is useful for cycle formulations but is not the exact problem because every assigned node must lie on its hub's ring.

## 2. Source hierarchy and known contradiction

Use the following precedence when requirements conflict:

1. `Cable Ring Challenge - Problem Statement4.pptx` (eight slides and speaker notes), because it defines checker behaviour, exact metrics, updated capacities, hub clearance, and the submission example. The reviewed local copy is alongside this clone, not yet tracked in this repository.
2. The original cable-routing problem statement in `message.txt` and page 4 of `Problem statements Honeywell.pdf`.
3. ResPlan documentation and code, which describe the dataset rather than challenge rules.
4. Project assumptions documented here.

There is one material conflict:

- the older statement/PDF says **20 devices per control panel**;
- the newer detailed slides say **five nodes per hub** and give the lower bound `max(ceil(area/100), ceil(nodes/5))`.

This plan uses **five nodes per hub**. Keep the value configurable until the organizers confirm it in writing.

Canonical project terminology follows the detailed slides: **hub** and **node**, not panel and device. See `CONTEXT.md`.

## 3. Confirmed problem rules

### 3.1 Input geometry and scale

- ResPlan geometry is expressed in drawing units, not metres.
- `inner.area` is the plan's internal footprint in drawing units squared.
- `area` is the same footprint's declared area in square metres.
- Do not use `net_area`; the slides explicitly note it is zero in roughly 32% of plans, and the uploaded data contains additional extreme values.
- Convert once per plan:

```text
drawing_units_per_metre = sqrt(inner.area / area)
length_m = length_units / drawing_units_per_metre
area_m2 = area_units2 / drawing_units_per_metre^2
```

### 3.2 Rooms and fixed nodes

- Eligible types are `living`, `bedroom`, `kitchen`, and `storage`.
- Each polygon component is one eligible room.
- Every eligible room has exactly one fixed node.
- A node is an arbitrary interior point at least 0.5 m from walls.
- Teams may not move node points during optimization.
- Bathrooms, balconies, stairs, gardens, pools, parking, and land are excluded: they receive no node and no hub.

The uploaded ResPlan pickle does not contain these challenge-specific node points. The implementation must support organizer-supplied points and a deterministic fallback generator for development data.

### 3.3 Hubs and territories

- The solver chooses how many hubs to open and where to place them.
- Each eligible room and its node belong to exactly one hub.
- Each hub may own at most 100 m2 of eligible-room area.
- Each hub may own at most five nodes.
- Both capacity limits apply simultaneously.
- Assigned rooms must form a connected territory through legal doors/open passages; windows, wall-only adjacency, and the entrance do not establish connectivity.
- A hub must lie inside an eligible room assigned to that hub and at least 0.5 m from walls. A hub and node may share a room.
- Excluded-room polygons cannot contain a hub.

Use a finite, configurable candidate set, but validate every candidate against the confirmed eligible-room, assignment, wall-clearance, and geometry rules. The treatment of non-wall obstacles in hub clearance still needs an explicit policy.

### 3.4 Rings and physical cable routes

- Each selected hub owns exactly one ring.
- A ring begins at its hub, visits every assigned node exactly once, and returns to that same hub.
- Rings cannot branch, remain open, skip/repeat a node, or terminate at another hub.
- Cable polylines must be axis-aligned: every segment is horizontal or vertical.
- Cable may move between rooms only through verified doors or open passages.
- Cable may not cross walls, windows, or exterior space and must remain inside the internal boundary.
- Entering and leaving a single-door room through the same door is allowed. Both traversals count toward length; only portions on the same geometric line count toward overlap. Parallel out-and-back runs do not overlap.

### 3.5 Evaluation

Optimization is lexicographic:

1. Minimize hub count `H`.
2. For equal `H`, minimize `J = L + 5X + O + 0.5B`.
3. For equal `H` and `J`, prefer the smaller assigned-area gap between hubs.

Metric definitions:

- `L`: total polyline length in metres over every leg, including all return and retraced travel.
- `X`: points where cables meet away from a node or hub, within or between rings; one count per geometric point.
- `O`: shared collinear cable length in metres. If `k` legs cover a stretch, it contributes `(k - 1) * length`.
- `B`: direction changes along rings, including at nodes/hubs. A 90-degree turn counts once, a reversal counts once, and straight-through movement counts zero.
- Geometric tolerance is 1 mm: closer points are identical and lines within 1 mm are the same line.
- The checker recomputes metrics from submitted polylines; claimed metric values in JSON are ignored.
- Invalid or missing plan output scores zero.
- Slide 3's unweighted `L + X + O + B` heading is shorthand; slides 6-7 and the slide 1/5 notes give the weighted formula above.

## 4. Dataset assessment

### 4.1 What ResPlan supplies

The uploaded `archive/ResPlan.pkl` contains 17,000 plans with:

- semantic room polygons;
- walls, doors, windows, inner boundary, land, and outdoor features;
- a declared `area` value;
- a preliminary NetworkX room graph;
- unique numeric plan IDs.

It is a general spatial-AI dataset, not a challenge-ready cable-routing dataset. It does not contain fixed challenge node points, hubs, assignments, legal routes, scoring data, or the challenge JSON schema.

### 4.2 Measured edge cases

- 862 plans contain at least one invalid geometry, including 399 window and 364 door geometries.
- 261 plans contain multipart living geometry that the bundled graph collapses into one `living_0` node; challenge logic must instead treat each polygon as one room.
- Stored graph edge counts are 118,719 `via_door`, 77,018 `adjacency`, 16,730 `direct`, and 6,554 `via_window`.
- If only explicit door-like edges are traversable, 4,249 plans have eligible rooms in multiple components. Adding generic adjacency reduces this to one plan, demonstrating that adjacency mixes important openings with unsafe shared-wall relationships.
- 124 plans have multipart internal geometry.
- The raw data includes implausibly small/large declared areas and 448 inferred eligible rooms above 100 m2, but the challenge slides say scored plans are filtered to cases the reference solver can solve and contain no room above 100 m2.
- The slide 3 notes describe preliminary benchmark filters (eligible rooms between 2 and 100 m2 and room points in one connected free-space component), but explicitly say contiguity-constrained partition feasibility still requires a reference-solver check. Do not assume these filters alone prove feasibility.
- Eligible-room count ranges from two to ten. With the updated five-node capacity, node count can force additional hubs.
- The pickle graph and `resplan_utils.py` disagree: the pickle uses `adjacency`, while the utility describes `via_opening` and `fallback`. Treat both as untrusted inputs to normalization.

### 4.3 Dataset companion files

- `split.json` assigns plan IDs to machine-learning train, validation, test, and augmented sets. It is not the official hackathon-feasibility subset. Use it to avoid tuning and reporting on the same plans, not to infer challenge legality.
- `croissant.json` is dataset-catalog metadata: version, download URL, provenance, bias, license, and descriptive information. It contains no solver input.
- License metadata conflicts: README says CC BY 4.0 while Croissant says CC BY-NC-SA 4.0. Preserve attribution and assume the stricter terms pending clarification.
- Do not accept arbitrary pickle uploads. Pickle is executable; convert the trusted bundled dataset once into a safer normalized representation.

## 5. Chosen technical approach

### 5.1 Stack

- Python 3.11+
- Shapely for vector geometry, repair, containment, collision, and measurement
- NumPy for numerical/grid operations
- NetworkX for traversability and territory graphs
- Google OR-Tools CP-SAT for hub selection and room assignment
- OR-Tools Routing for per-hub node ordering
- Grid-based rectilinear A* for the first legal routing implementation
- Pydantic for normalized inputs, solutions, diagnostics, and output validation
- Streamlit for the hackathon interface
- Matplotlib for deterministic overlays; Plotly for optional interactive inspection
- pytest for unit, property, and scenario tests
- Docker for reproducible execution

OpenCV is not part of the core pipeline because ResPlan already supplies vector geometry. It may be used only for raster previews or future non-ResPlan image input.

### 5.2 Planned upgrades

1. Replace grid A* with a **portal-aware orthogonal visibility graph**, not an ordinary diagonal visibility graph.
2. Improve finite hub-candidate generation and local refinement while keeping the optimization model discrete and testable.

### 5.3 Decomposition strategy

Use a staged solver with repair rather than one monolithic model:

```text
trusted ResPlan input
  -> normalize and validate geometry
  -> build eligible rooms and fixed nodes
  -> classify portals and construct traversability graph
  -> generate legal hub candidates
  -> solve minimum-hub connected assignment
  -> compute legal pairwise rectilinear routes
  -> solve one closed node order per hub
  -> reconstruct complete ring polylines
  -> improve J without increasing hub count
  -> independently validate and render
```

The stages must expose explicit failure diagnostics; an infeasible plan is a valid outcome, while a partially valid solution is not.

## 6. Normalized data contract

Never mutate the raw ResPlan pickle. Convert each selected plan into a challenge model containing:

- plan ID and provenance;
- drawing-units-per-metre scale;
- repaired internal boundary and obstacle geometries;
- room instances split one per polygon component;
- room type, geometry, and computed square-metre area;
- fixed node per eligible room plus clearance validation;
- excluded-room geometries;
- verified portals with source evidence and confidence;
- normalized traversability graph;
- finite legal hub candidates;
- preprocessing warnings, repairs, and feasibility status.

Portal records should retain both raw and normalized meanings, for example:

```json
{
  "source_type": "adjacency",
  "normalized_type": "open_passage",
  "traversable": true,
  "confidence": 0.93
}
```

The shared schema is the internal interchange contract: `Plan` and `Solution` coordinates remain in drawing units, with physical measurements in `_m`/`_m2` fields. Slide 8 shows a different, abridged team-submission JSON shape: coordinates in metres (drawing units divided by scale, with a lower-left origin and upward `y`), `hubs` with `closed_sequence` and `route_segments`, and advisory `reported_metrics`. Add a separately tested export adapter that also normalizes the origin/orientation if needed; do not silently relabel the internal JSON as the challenge submission. An organizer-provided machine-readable schema, if released, supersedes both this development contract and any assumptions drawn from the abridged slide example.

## 7. Detailed implementation plan

### Phase 0 - Lock the contract

Deliverables:

- retain the reviewed eight-slide deck and its speaker notes as the current rule source;
- obtain the machine-readable fixed-node input format (the deck confirms fixed points but does not specify their JSON structure);
- confirm the complete machine-readable submission schema (slide 8 is abridged);
- confirm whether cable may traverse excluded interior rooms;
- confirm how open passages are represented in organizer input.

Until resolved, keep these policies configurable and clearly label fallback behaviour in the demo.

Acceptance:

- every unresolved organizer question has a recorded answer or explicit project default;
- one versioned challenge configuration controls capacity, tolerances, allowed transit spaces, and the confirmed 0.5 m hub/node wall clearances.

### Phase 1 - Trusted loader and geometry normalization

Implement:

- trusted-only ResPlan pickle loader;
- plan-ID lookup and optional use of `split.json`;
- missing categories normalized to empty geometry;
- `make_valid` repair with before/after diagnostics;
- rejection of empty, dimension-collapsed, or materially distorted repairs;
- polygon-component splitting, including multipart living rooms;
- scale calculation from `inner.area` and `area`;
- metre-space helpers and 1 mm tolerance constants.

Acceptance:

- all selected development plans load without silent geometry exceptions;
- no eligible room is lost through multipolygon merging;
- capacity calculations use square metres and never `net_area`;
- every repair is auditable.

### Phase 2 - Eligible rooms and fixed nodes

Implement:

- canonical eligible/excluded type mapping;
- official node-point loader interface;
- deterministic fallback node generator using an inward 0.5 m clearance region;
- validation for containment, uniqueness, wall clearance, and one node per eligible polygon;
- explicit infeasibility if a room is over 100 m2 or cannot contain a legal node.

Acceptance:

- exactly one immutable node exists per eligible polygon;
- no node exists in an excluded room;
- all accepted nodes meet clearance within tolerance.

### Phase 3 - Portal and traversability model

Implement:

- direct door-to-space contact analysis using contact length, avoiding corner-induced third-room links;
- geometric reclassification of ambiguous adjacency into open passage, shared-wall adjacency, or artifact;
- hard rejection of window transitions;
- legal transit-space policy controlled by configuration;
- connected-component and reachability diagnostics;
- portal coordinates usable by the pathfinder.

Acceptance:

- every traversability edge has physical portal evidence;
- no route can cross between rooms through a window or plain wall;
- known single-door rooms remain routable with retracing.

### Phase 4 - Hub candidates and minimum-hub assignment

Implement:

- finite candidate generation only in legally allowed internal space;
- candidate reachability, eligible-room ownership, and 0.5 m wall-clearance validation;
- lower bound `max(ceil(total_area/100), ceil(node_count/5))`;
- CP-SAT variables for opened hubs and exclusive room assignments;
- both capacity constraints;
- territory connectivity using flow constraints, iterative connectivity cuts, or connected constructive assignment plus repair;
- search hub counts upward from the lower bound until a feasible solution is found;
- secondary assignment costs based on legal-path distance and compactness, without sacrificing minimum hub count.

Acceptance:

- every eligible room is assigned exactly once;
- every selected hub has at least one node;
- area and node capacities hold exactly;
- each territory is connected through verified portals;
- the solver records whether minimality is proven or only best-known under a time limit.

### Phase 5 - Rectilinear pathfinding

Implement:

- free-space grid in drawing units derived from metre-configured resolution;
- walls, windows, and exterior as blocked cells with configurable clearance;
- doors/open passages as explicit cross-boundary portals;
- four-directional A* or guarded eight-directional logic with diagonal output forbidden;
- endpoint-to-grid attachment for fixed nodes and hubs;
- path simplification that preserves only horizontal/vertical segments;
- final Shapely segment validation after simplification;
- explicit unreachable-pair results rather than arbitrary large distances;
- path cache for every relevant hub-node and node-node pair.

Acceptance:

- every returned segment is axis-aligned and inside free space;
- no path crosses an obstacle or unverified boundary;
- an unreachable pair cannot be chosen by the ordering solver;
- retraced door routes are supported.

### Phase 6 - Closed-ring ordering

Implement:

- per-hub legal distance matrix from cached A* paths;
- OR-Tools closed routing with the hub as both start and end;
- exactly-once visit of every assigned node;
- path reconstruction for every consecutive stop pair;
- rejection of subtours, branches, foreign-hub endings, and missing legs.

Acceptance:

- each selected hub produces exactly one closed sequence;
- each assigned node occurs exactly once in its sequence;
- concatenated geometry begins and ends at the same hub.

### Phase 7 - Scoring and improvement

Implement an independent checker-like metrics module:

- convert all geometry to metres before scoring;
- sum all leg lengths including returns and retraces;
- detect crossings excluding shared node/hub endpoints;
- compute collinear overlap with multiplicity `(k - 1)`;
- count 90-degree turns and reversals, including at nodes and hubs;
- snap/equate geometry using the 1 mm rule;
- calculate `J` exactly;
- compute assigned-area-gap tie-break.

Then improve fixed-hub-count solutions through safe local moves:

- reorder nodes within a ring;
- swap rooms/nodes between adjacent territories while preserving capacity/connectivity;
- select alternative legal pairwise paths;
- relocate a hub among legal candidates;
- accept moves lexicographically by `(H, J, area_gap)`.

Acceptance:

- metrics agree with hand-calculated slide examples;
- optimization never adds a hub to reduce `J`;
- every improvement is fully revalidated before acceptance.

### Phase 8 - Validation, JSON, and visualization

Implement a validator separate from the optimizer that checks:

- input normalization and geometry validity;
- exactly one node per eligible polygon;
- exactly one room/node assignment;
- hub eligibility and capacity;
- hub containment in its own assigned eligible room and 0.5 m wall clearance;
- territory connectivity;
- ring closure, non-branching, and exactly-once visits;
- axis alignment;
- boundary containment and wall/window/exterior avoidance;
- portal-only room transitions;
- recomputed metrics and score.

The Streamlit interface should provide:

- plan/split selection or official challenge upload;
- raw and repaired geometry inspection;
- color-coded territories;
- fixed nodes and selected hubs;
- numbered ring order and directional arrows;
- cable polylines, portals, crossings, overlaps, and bends;
- capacity and validation summaries;
- downloadable JSON and PNG/SVG overlay.

Acceptance:

- the visual and JSON describe the identical solution;
- the metre-coordinate submission adapter reproduces the checked drawing-unit geometry and lengths;
- invalid outputs identify the exact failed rule;
- metrics shown in the UI come from the validator, not solver claims.

### Phase 9 - Packaging and benchmark

Implement:

- deterministic random seeds and solver time limits;
- Docker image and command-line entry point;
- cached normalized plans separated from raw data;
- development on train IDs, heuristic tuning on validation IDs, and final reporting on untouched test IDs;
- augmented plans as later robustness tests rather than initial examples;
- benchmark report containing feasibility rate, hub optimality/lower-bound gap, `J`, runtime, and failure categories.

Acceptance:

- a clean environment can reproduce a solution from a plan ID;
- unseen-plan processing produces either a fully valid solution or an explicit infeasibility/error result;
- no arbitrary pickle upload path is exposed.

## 8. Test strategy

### Unit tests

- scale conversion for lengths, areas, and 0.5 m clearance;
- empty/missing geometry normalization;
- polygon repair and multipart splitting;
- door contact versus corner contact;
- window/shared-wall rejection;
- node containment and clearance;
- hub containment, assigned-room ownership, and 0.5 m wall clearance;
- axis alignment and obstacle collision;
- crossing, overlap multiplicity, bend, reversal, and 1 mm tolerance;
- lower-bound and capacity arithmetic.

### Scenario tests

- one room, one node, one hub, closed out-and-back ring;
- single-door room requiring retrace;
- two adjacent rooms separated by a wall with no portal;
- two rooms connected by a window only;
- open kitchen/living passage;
- concave room and narrow corridor;
- multipart living geometry producing multiple nodes;
- disconnected `inner` components;
- room above 100 m2;
- six small rooms forcing two hubs by node count;
- 101 m2 total area forcing two hubs by area;
- assignment satisfying capacity but violating territory connectivity;
- crossing within one ring and between rings;
- collinear overlap versus parallel non-overlap;
- a straight out-and-back ring whose reversals at its node and hub each count as a bend;
- room-boundary crossing through a wall with no verified portal, even if the path avoids recorded obstacle polygons;
- path whose simplification would cut through a wall;
- unreachable node pair forbidden in TSP.

### Dataset regression suite

Maintain representative IDs for:

- invalid doors/windows;
- multipart living rooms;
- ambiguous adjacency;
- disconnected interior geometry;
- extreme declared areas;
- the window-dependent connectivity case (plan 3379);
- ordinary small and large valid layouts.

### End-to-end acceptance

For each accepted plan:

- validator reports zero hard-rule violations;
- hub count equals the proven minimum or is labelled best-known with its lower bound;
- independently recomputed `J` matches displayed/exported metrics;
- reloading exported JSON reproduces the same overlay and metrics.

## 9. Risk register

The 2026-10-15 deck/code audit found these *current implementation gaps*, not
changes to the challenge formulas: Priyanshu's thin slice reports `X = O = 0`
and counts only bends inside individual legs; Sana's checker recomputes the
metrics, but it does not yet enforce hub wall clearance, hub-room ownership by
its territory, or portal-only transitions for every cable boundary crossing.
The development `Solution` also needs the metre-coordinate submission adapter
described above. Passing current tests or the current checker is therefore not
yet proof that an output satisfies every rule on slide 3.

| Risk | Impact | Mitigation |
|---|---|---|
| Five-versus-twenty capacity conflict | Wrong hub count | Configurable rule; seek organizer confirmation; default to detailed slides |
| Missing official fixed nodes | Different challenge instances | Loader-first interface plus clearly labelled deterministic fallback |
| Hub clearance or assigned-room ownership omitted in code | Invalid candidate locations | Enforce the slide 3 rule in candidate generation and independent validation |
| Internal drawing-unit JSON mistaken for the metre-based submission | Invalid output | Add a distinct slide-8 export adapter and validate its coordinate/length conversion |
| Ambiguous ResPlan adjacency | Wall-crossing or false disconnection | Geometric portal reconstruction; never trust adjacency directly |
| Invalid polygon repair changes semantics | Incorrect rooms/obstacles | Audit area/topology changes and reject unsafe repairs |
| Grid resolution misses narrow doors | False unreachable paths | Scale-aware resolution, explicit portal injection, multi-resolution retry |
| Grid resolution is too fine | Runtime/memory blow-up | Adaptive resolution and pairwise-route caching |
| TSP uses unreachable arc | Invalid ring | Forbidden arcs and post-reconstruction validation |
| Metric implementation differs from checker | Lost score | Reproduce slide examples; centralize 1 mm tolerance; compare against official checker if released |
| Raw dataset differs from hidden feasible subset | Local failures not representative | Separate raw-data diagnostics from scored-benchmark assumptions |
| Pickle execution risk | Security | Trusted offline conversion only; safe normalized format for application runtime |
| License conflict | Usage uncertainty | Attribution and stricter-license assumption pending clarification |

## 10. Explicit defaults pending organizer clarification

- Node capacity: five per hub.
- Panel/device synonyms normalize to hub/node.
- `area`, not `net_area`, establishes scale.
- Every polygon component is a separate room.
- Invalid geometries use `make_valid`, with unsafe repairs rejected.
- Generic `adjacency` is non-traversable until geometric evidence proves an open passage.
- Windows are always blocked.
- Overlap is permitted and penalized, never globally forbidden.
- A* output is four-directional and axis-aligned.
- Hubs come from a finite candidate set inside allowed internal space and outside excluded rooms.
- Hub candidates must be inside an eligible room assigned to that hub and at least 0.5 m from walls; this is a confirmed rule, not an open assumption.
- The raw ResPlan test split is not assumed to be the official challenge benchmark.

## 11. Definition of done

The prototype is complete when it can take an unseen, challenge-valid ResPlan input and, without manual geometry edits:

1. normalize and validate the plan;
2. use the official fixed nodes or a documented development fallback;
3. find the minimum feasible hub count under the configured rules;
4. generate capacity-compliant, connected territories;
5. generate one legal closed axis-aligned ring per hub;
6. independently validate every hard rule;
7. compute `H`, `L`, `X`, `O`, `B`, `J`, and area gap with 1 mm tolerance;
8. export the slide-8 metre-coordinate submission JSON through a tested adapter and a matching visual overlay;
9. provide explicit diagnostics rather than silently emitting a partial solution;
10. reproduce the run in Docker with deterministic configuration and recorded solver limits.

## 12. Supporting material

- Original statement: `message.txt`
- General Honeywell overview: `Problem statements Honeywell.pdf`
- Detailed eight-slide deck and notes: `Cable Ring Challenge - Problem Statement4.pptx` (reviewed local copy alongside this clone; not tracked here)
- Earlier detailed rule screenshots: the five `WhatsApp Image 2026-10-15 ...` files in the repository root
- Dataset and utilities: `archive/`
- Literature review: `research/related-work.md`
- Canonical terminology: `CONTEXT.md`
