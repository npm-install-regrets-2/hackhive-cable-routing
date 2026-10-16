# Master prompt: joint hub placement and cable-route optimization

You are working in the HackHive cable planner repository. Explore whether jointly optimizing hub placement, connected room assignments, cable-ring routes, and node-count balance can improve the current solver without making the production pipeline slower than an agreed runtime budget. Treat this as an experiment. Preserve a working baseline and keep the current solver available so the experiment can be discarded cleanly.

## Start from the checkpoint

1. Read `AGENTS.md`, `PROJECT_PLAN.md`, `CONTEXT.md`, `shared/schema/common.schema.json`, `docs/README.md`, and `docs/workstreams.md` before changing code.
2. Fetch `main` and verify the rollback tag `checkpoint/pre-joint-hub-route-search` is present. Record its commit SHA.
3. Create a separate branch such as `experiment/joint-hub-route-search`. Do not experiment directly on `main`.
4. Run the existing suite and capture the baseline results before implementation. Do not rely only on stored output JSON: run the current solver and independent validator on the same inputs used for every candidate algorithm.

## Understand the actual baseline before changing it

The current implementation already enumerates connected room partitions and tries combinations of hub candidates for each territory. Its search is bounded (currently at most 50 partitions and three hub candidates per territory), and each ring is constructed independently before the complete solution is ranked. Inspect the current code and measure the real behavior; do not assume this is a purely sequential “place hubs, then route cables” implementation. Identify where candidate placement is truncated, where routing decisions are local, and whether cross-ring crossings/overlap influence route construction or only final ranking.

Use the current `cable_planner.solver.grid_router.solve` path as the baseline. Keep its public interface and independently validated output contract stable. Prefer a separate experimental strategy/module or an explicit opt-in strategy flag over replacing the baseline implementation. The default app path must continue to use the current solver until a candidate has demonstrated a repeatable improvement and passed all checks.

## Experiment goal

Explore bounded algorithms that make the following decisions together, or revisit them through a measured improvement loop:

- connected room-to-hub territories;
- legal hub room and point selection, including refinement beyond the current finite candidate shortlist;
- node order and legal rectilinear paths for every hub’s closed ring;
- interactions between rings, including crossings and shared cable length;
- a more even distribution of nodes among hubs when the feasible solutions are otherwise comparable.

Possible approaches include larger/adaptive candidate sets, hub relocation after routing, beam search, local search, route alternatives, joint candidate/route neighborhoods, or a hybrid. Start with a small reproducible experiment and compare alternatives. Do not assume a particular method is better before measuring it.

## Rules the experiment must preserve

- Keep hard constraints hard: every eligible room and node is assigned exactly once; territories are connected through legal portals; configured area and node capacities hold; hubs remain in assigned eligible rooms with required clearance; routes are axis-aligned, legal, closed, and visit assigned nodes exactly once.
- Preserve input IDs, deterministic ordering, schema compatibility, drawing-unit geometry, and structured infeasibility/best-known status.
- Validate every candidate solution with `IndependentValidator` and the shared schema. Never use optimizer internals as a substitute for independent validation.
- Preserve the official ranking: minimize hub count first, then `J = L + 5X + O + 0.5B`, then assigned-area gap. Node balance is not a replacement for this score. Report node counts per hub and a balance measure as an additional diagnostic; use it only as a tie-break after the official ranking or as a separately reported experimental preference. If investigating a tradeoff that worsens J or area gap for balance, report the Pareto tradeoff explicitly and keep it out of the default score.
- Do not claim global optimality unless the algorithm proves it. Report “best known” when search is bounded or time-limited.
- Keep hub count minimal. Do not add hubs to reduce route cost or improve balance.

## Baseline and comparison protocol

At minimum, compare the baseline and each candidate on:

1. `examples/outputs/kaggle_13033_combined.json`
2. `examples/outputs/kaggle_14433_combined.json`
3. `tests/solver/fixtures/three_room_plan.json`
4. A small synthetic case where multiple hub placements and node splits are feasible, plus an infeasible or portal-constrained case that prevents balance.

For each case, record:

- status and whether minimum hub count is proven;
- hub count and node counts per hub;
- `L`, `X`, `O`, `B`, `J`, assigned-area gap, and the balance diagnostic;
- independent-validator result and schema-validation result;
- wall-clock runtime, including repeated runs where practical;
- search limits, number of candidates/partitions/routes evaluated, and any early stopping.

Use identical inputs, configuration, machine, and validation for baseline and candidate. Keep the baseline result if a candidate is infeasible, invalid, nondeterministic, outside the runtime budget, or fails to improve the official ranking. A balance-only benefit is not an official-score improvement; present it separately.

## Iteration and stopping

1. Establish a simple runtime budget based on measured baseline timings. Make it configurable for experiments.
2. Implement one change at a time, add focused regression tests for its behavior, and run relevant tests after each iteration.
3. Preserve the best independently validated candidate found so far; timeouts must return that solution with an honest status.
4. Run the full test suite before recommending adoption. The Streamlit AppTest uses Windows asyncio socket facilities; if the sandbox blocks them, run that suite in an environment that allows local socketpairs and report the reason.
5. Do not change challenge rules, the shared schema, or score formulas as part of search tuning. If the experiment requires such a change, stop and document the producer, consumers, compatibility effect, and migration first.
6. Do not push, deploy, or replace the default algorithm without the user’s explicit follow-up approval.

## Deliverables

- The baseline remains runnable and easy to restore from `checkpoint/pre-joint-hub-route-search`.
- The experimental algorithm is opt-in and has a clear fallback to the baseline.
- Tests cover joint placement/routing decisions, node-balance diagnostics, infeasible balance, determinism, and independent validation.
- A concise experiment report compares the baseline and each iteration, explains runtime/quality tradeoffs, states limitations, and recommends either adoption or rollback. If the candidate does not win under the agreed criteria, leave the production path on the baseline and keep or discard the experiment without merging it.
- Update the relevant progress log after each meaningful implementation step.
