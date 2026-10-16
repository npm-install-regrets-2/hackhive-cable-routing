# Integration progress

## 2026-10-16 — Add configurable cable-to-wall clearance

- Status: done
- Changed: `cable_planner/solver/grid_router.py`; the solver accepts `cable_wall_clearance_m` (default 0.03 m), buffers wall obstacles by that amount, and adds offset Hanan-grid lanes. Fixed hub/node coordinates are unchanged.
- Why: saved plan 13033 and 14433 routes included segments within approximately 0.1 mm of wall geometry; wall-edge contact was being accepted and the grid offered no small-offset alternative.
- Checked: plan 14433 solved and passed independent validation with 0 violations. At 0 clearance it took 61.537 s with J=46.6841; at 0.03 m it took 67.066 s with J=47.1666, and minimum measured wall gap was 0.0628 m. The clearance change added about 5.5 s (~9%) on this run.
- Open: representative-plan runtime is dominated by the existing partition, hub-candidate, and ring-order search; verify door clearances before relying on the 0.03 m default for narrow openings.
- Next: tune route separation through shared open passages and keep the cost/runtime tradeoff visible.
- Commit/PR: pending

## 2026-10-17 — Avoid loading the local archive on initial page render

- Status: implemented
- Changed: `frontend/src/App.tsx`, `cable_planner/web/app.py`, `tests/web/test_app.py`, `README.md`
- Why: the initial view requested local previews for all featured plans, causing multiple first-use reads of a 300 MB pickle; server logs showed `MemoryError` in `pickle.load`.
- Changed: featured thumbnails and featured-plan selection now use bundled preview data. Local archive cache misses are serialized so concurrent local lookups share one cold unpickle.
- Checked: frontend production build passed; concurrent cold archive lookup test passed; cold bundled preview returned HTTP 200 in 0.87 s; `git diff --check` passed.
- Open: a cold local lookup still has to read the archive once when a non-bundled plan is selected.
- Next: monitor the first local-plan lookup on a memory-constrained machine.
- Commit/PR: pending

## 2026-10-16 — Improve floor overlay clarity

- Status: done
- Changed: `cable_planner/visualization/renderer.py`
- Why: distinguish room kinds and architectural features in the output diagram, keep labels legible over routes, and make co-located hub/node symbols readable
- Checked: `.venv\\Scripts\\python.exe -m pytest` (42 passed); the 13033 and 14433 routing-cost assertions passed with the existing solver
- Open: rendered cable geometry is unchanged; it can still be close to a wall in the underlying coordinates
- Next: review a representative generated overlay
- Commit/PR: `c6591d7` on `fix/floor-diagram-clarity`; push pending destination approval

## 2026-10-16 — Stop depicting open passages as doors

- Status: done
- Changed: `cable_planner/visualization/renderer.py`; only actual doors receive a portal stroke. Open passages remain visually open.
- Why: the thick marker over a shared open boundary looked like an imaginary door, even though the solver routed through the open passage.
- Checked: inspected plan 14433's normalized portal and wall geometry; its living–kitchen open passage is about 58.9 drawing units long, and cable legs 2 and 3 cross it at y=158.5 and y=160.41. Removed both the open-passage marker and the duplicated room-outline stroke from the opening in input and solution views.
- Open: cable paths still cross the same opening only 1.91 drawing units apart; increasing their separation may affect route cost and runtime.
- Next: review the updated overlay and choose a cable separation target if needed.
- Commit/PR: pending

## 2026-10-16 — Keep close hub and node symbols readable

- Status: done
- Changed: `cable_planner/visualization/renderer.py`; when a hub is within 0.5 m of a fixed node, its rectangular badge moves aside with a leader and the actual hub point stays marked. Short room labels avoid hubs, nodes, and routes, and cable strokes render above labels.
- Why: plan 14433's H2 and N3 are only 1.23 drawing units apart; the large hub badge covered the short loop and node marker.
- Checked: rendered plan 14433's saved solution and independently validated it (0 violations, J=46.6841); the H2 label no longer covers N3 and the loop is visible. Rendering changes do not modify solver coordinates or cost. The current 0.03 m solve also validates with 0 violations, J=47.1666, in 66.022 s.
- Open: cable paths still cross the same open passage only 1.91 drawing units apart; increasing their separation may affect route cost and runtime.
- Next: compare the current 0.03 m route's H2 ring against the updated saved-solution preview if a new full solver output is needed.
- Commit/PR: pending

## 2026-10-16 — Speed up interaction-aware routing and clarify retraces

- Status: done
- Changed: `cable_planner/solver/grid_router.py`, `cable_planner/visualization/renderer.py`, `tests/solver/test_grid_router.py`, `tests/validation/test_visualization.py`
- Why: plan 14433 routing repeatedly scanned every Hanan-grid edge after each leg; the overlay also needed to distinguish true shared-line retraces from close parallel return legs.
- Changed: index graph edges by horizontal row and vertical column when applying existing route-interaction penalties, and remove the redundant graph reachability traversal before A*. Draw a two-headed arrow only over a geometric span shared by multiple cable legs. Preserve the hub's actual solver point and cost.
- Checked: focused penalty-equivalence and retrace-vs-parallel checks passed (2 passed). Plan 14433 at the existing 0.03 m wall clearance solved in 38.632 s (previous recorded run: 66.022 s), independently validated with zero violations, and kept the same J=47.166637, L=37.166637 m, X=0, O=0, B=20, and area gap=77.4652 m². Updated overlay saved as `tmp/plan14433-cable-fix.png`. The living–kitchen opening remains a verified 58.909-unit open passage; the two routes cross its boundary line at y=158.50 and 160.41 inside the opening range y=129.04–187.95. No wall obstacle intersects the opening.
- Check limitation: three selected checks passed, but the visualization test that allocates `tmp_path` could not set up/clean its pytest temporary directory under the sandbox; rendering itself was verified by the saved overlay and independent validation.
- Open: the two cables still pass 1.91 drawing units apart through the wide passage; this is separate parallel routing, not wall clearance or overlap.
- Next: review the updated diagram and determine whether additional visual separation in the open passage is desired.
- Commit/PR: pending

## 2026-10-16 — Apply additional runtime speedups

- Status: done
- Changed: `cable_planner/solver/grid_router.py`; merged the provided `runtime-speedup.patch` with the existing worktree changes.
- Changed: A* now stores parent pointers instead of copying full paths into each priority-queue entry, reads graph adjacency directly, and relies on A* itself to report unreachable targets. Visit permutations are considered in Manhattan lower-bound order and pruned once they cannot beat the best complete ring. Edge interaction penalties use a cached row/column edge index with interval lookups.
- Checked: four focused solver/renderer checks passed. Plan 14433 solved in 17.462 s with independent validation (zero violations): H=2, J=47.166637, L=37.166637 m, X=0, O=0, B=20, area gap=77.4652 m². This preserves the prior 38.632 s run's metrics and is about 73.5% faster than the recorded 66.022 s run. The updated image and solution JSON are in `tmp/`.
- Open: none introduced by the optimization; the living–kitchen open passage is unchanged and no wall obstacle crosses it.
- Next: review the updated overlay and merge when ready.
- Commit/PR: pending

## 2026-10-16 — Verify runtime patch against a clean base

- Status: done
- Changed: `cable_planner/solver/grid_router.py`; the supplied patch applies cleanly to a copy of `HEAD`. Its A*, Manhattan-order pruning, and cached edge index are integrated into the active solver, while the existing 0.03 m wall-clearance setting is preserved.
- Checked: in this environment, the patch applied to clean `HEAD` measured 17.704 s on plan 14433 and 5.899 s on plan 13033 (no wall-clearance feature in that base). The active solver measured 17.195 s and 5.601 s respectively with its existing configuration. Both plans independently validated with zero violations. Python is 3.14.5 on Windows 11 with NetworkX 3.7; timing differences from the user's 14.7 s / 4.8 s are therefore not evidence of missing patch hunks and likely reflect runtime environment or benchmark conditions.
- Open: a definitive timing comparison requires the same machine, Python/dependency versions, configuration, and timer boundaries.
- Next: none.
- Commit/PR: pending

## 2026-10-16 — Route and display open passages as free space

- Status: done
- Changed: `cable_planner/solver/grid_router.py`, `cable_planner/visualization/renderer.py`, `tests/solver/test_grid_router.py`, `tests/validation/test_visualization.py`
- Changed: added evenly distributed route lanes every ~0.4 m along open passages, a soft 0.5 m preference between parallel cable runs, and a faint dashed blue passage indicator labelled as free space. The duplicate A*, permutation-pruning, and edge-index runtime hunks in the supplied patch were not reapplied; the active optimized code remains in place.
- Checked: five focused checks passed. Plans 14433 and 13033 independently validated with zero violations. With the new passage lanes and spacing preference, plan 14433 runs in 25.537 s at J=47.842788; plan 13033 runs in 7.019 s at J=32.092319. Compared with the preceding active solver, costs rose by 0.676 and 0.810 respectively, while route overlap and crossings remain zero. Refreshed plan-14433 overlay saved as `tmp/plan14433-open-passage.png`.
- Open: the added passage lanes enlarge the route graph and increase solve time despite the unchanged runtime optimization. The soft spacing preference trades a small amount of reported J for visually separated parallel runs.
- Next: review the new passage indication and decide whether the separation preference's current cost/runtime tradeoff is acceptable.
- Commit/PR: pending

## 2026-10-16 — Consolidate the working solver and demo into one package

- Status: complete
- Changed: `cable_planner/`, `tests/`, root project configuration, repository documentation
- Why: promote the verified 31.6972 plan-13033 grid router and checked Streamlit demo from temporary developer folders into a single maintained package
- Checked: direct package import selects `cable_planner.solver.grid_router.solve`; plan 13033 validates with zero crossings and route cost 31.6972; full suite passes (42 tests); Streamlit app check completes without errors and reports 31.6972; metre exporter returns the expected provisional format.
- Open: none for this integration pass.
- Next: changes are ready to fast-forward into `main`.
- Commit/PR: `d930234` integrates the package; merge from `origin/main` recorded in the following merge commit.

## 2026-10-16 — Deploy the Streamlit demo

- Status: complete
- Changed: `cable_planner/demo/app.py`, `tests/validation/test_streamlit_app.py`, `README.md`
- Why: the local demo depended on a 300 MB ignored ResPlan pickle, which is unavailable in a hosted Streamlit app and must not be exposed as an arbitrary pickle upload.
- Changed: added checked-in normalized JSON examples (plans 13033 and 14433) as cloud-ready run inputs while preserving the trusted local archive option.
- Checked: Streamlit AppTest passed (1 test); Windows temporary-directory cleanup printed a permission warning after the successful test result.
- Checked: Streamlit Community Cloud rejected the deployment from `main` because the `npm-install-regrets-2` GitHub organization restricts OAuth app access. No organization permissions were changed.
- After the organization authorized Streamlit Community Cloud, the deployment succeeded from `main`.
- Deployed: https://hackhive-cable-planner.streamlit.app/ from `main`, entry point `cable_planner/demo/app.py`.
- Checked: hosted plan 13033 solved with J=32.0923 and passed independent validation; floor-plan input/output overlays and submission download rendered.
- Open: none.
- Next: none.
- Commit/PR: app support `14e674d`; live URL and README link recorded in follow-up commit.

## 2026-10-16 — Hide local archive controls on the hosted app

- Status: complete
- Changed: `cable_planner/demo/app.py`, `cable_planner/demo/environment.py`, `tests/validation/test_streamlit_environment.py`
- Why: the hosted app displayed a local archive path field, which users could mistake for a way to read files from their own computers. Streamlit resolves paths on the app server.
- Changed: use the browser host from `st.context.url` to expose only bundled examples on Streamlit Community Cloud; keep the trusted archive option for local sessions. Show a message explaining the limitation.
- Checked: deployment-source checks and Streamlit AppTest passed (3 tests). Pytest's Windows temporary-directory cleanup emitted a permission warning after the passing result.
- Checked: after pushing to `main`, the hosted app showed only the example selector and the local-file explanation; the archive path control was absent.
- Open: none.
- Next: none.
- Commit/PR: `eb0a343`

## 2026-10-16 — Document Windows local setup with the Python launcher

- Status: complete
- Changed: `README.md`; document `py -3 -m venv`, the environment's Python executable, pip bootstrap for an existing pip-less environment, local archive selection, and MSYS2 interpreter note.
- Why: PowerShell resolved bare `python` to MSYS2's Python, which has no pip.
- Checked: verified the Windows Python launcher and existing project environment paths in the workspace.
- Open: none.
- Next: none.
- Commit/PR: pending

## 2026-10-16 — Keep hubs separated from fixed nodes and render single-node loops

- Status: done
- Changed: `cable_planner/solver/grid_router.py`, `cable_planner/visualization/renderer.py`, `tests/solver/test_grid_router.py`
- Why: prevent hub/node overlap and give single-node territories a visible closed ring when a legal offset exists.
- Checked: `git apply --check` passed; focused solver and independent-validator coverage passed after the test migration.
- Open: none.
- Next: none.
- Commit/PR: pending

## 2026-10-16 — Prefer greater cable wall clearance with feasible fallbacks

- Status: done
- Changed: `cable_planner/solver/grid_router.py`, `tests/solver/test_grid_router.py`
- Why: request a visibly larger default cable-to-wall clearance and retry smaller configured clearances only when the solver reports infeasibility.
- Checked: `git apply --check` passed; solver tests passed after adding a regression for fallback order.
- Open: none.
- Next: none.
- Commit/PR: pending

## 2026-10-16 — Move placement coverage to the active solver

- Status: done
- Changed: `tests/validation/test_hub_placement_scenarios.py`, `tests/solver/test_grid_router.py`
- Why: the placement scenarios were still exercising the retired `thin_slice` solver; migrate them to the app's `grid_router` implementation and cover hub/node separation and clearance fallback.
- Checked: `python -m pytest tests/solver/test_grid_router.py tests/validation/test_hub_placement_scenarios.py -q` (16 passed); full suite `python -m pytest tests -q` (51 passed in 117.54s) outside the sandbox because Streamlit AppTest requires a Windows asyncio socketpair.
- Open: none.
- Next: none.
- Commit/PR: pending

## 2026-10-16 — Checkpoint baseline before joint hub-route experiments

- Status: done
- Changed: `docs/experiments/joint-hub-route-optimization-prompt.md`, `docs/progress/integration.md`; checkpoint tag planned as `checkpoint/pre-joint-hub-route-search`
- Why: preserve the validated production pipeline before testing broader hub-placement and ring-route search.
- Checked: the full suite passed (51 tests in 117.54s); verified the current search caps and per-ring routing boundary in `grid_router.py`.
- Open: none.
- Next: clone or fetch `main`, verify the tag, and create the experiment branch using the saved prompt.
- Commit/PR: pending

## 2026-10-16 — React floor-plan demo and checked API

- Status: done
- Changed: `frontend/`, `cable_planner/web/`, three bundled normalized plans in `examples/inputs/`, the slide-style exporter, Docker and dependency files, API tests, and README
- Why: let visitors pick three presets or a local `split.json` ID, compare normalized input with independently checked output, and see measured runtime stages and every term of `J`
- Checked: React production build passed; 56 repository tests passed, then all six focused web tests passed after adding malformed-geometry coverage; live bundled runs of 13033, 14433, and 14926 and a local archive run of 14926 all passed independent validation and produced both JSON views; browser checks at 360, 390, 820, and 1440 px found no page-level horizontal overflow
- Open: Docker engine is unavailable in this environment, so the container build was not run; the organizer's complete machine-readable submission schema is still unavailable, so the slide-8 export remains explicitly provisional
- Next: smoke-test the Docker image on a machine with Docker and review the UI/API change before merging
- Commit/PR: pending

## 2026-10-16 — Place fallback nodes clear of interior walls

- Status: done
- Changed: `cable_planner/ingestion/normalize.py`, `tests/ingestion/test_normalize.py`
- Why: plan 11927's kitchen had legal node space, but the room-only pole of inaccessibility landed 0.323 m from an interior wall and caused normalization to fail at the 0.5 m clearance rule.
- Changed: when the first development fallback is illegal, search the room inset after subtracting wall and window clearance buffers; keep organizer-supplied nodes immutable and report a clearer error when no fallback point exists.
- Checked: eight ingestion tests passed and the full repository suite passed (59 tests); local plan 11927 normalized with five nodes, solved with two hubs, passed independent validation, and produced schema-valid development JSON. After restarting the local server, its preview returned HTTP 200 and its run returned a valid two-hub solution with both images and the provisional submission (63.6947 s measured total).
- Open: organizer-supplied fixed nodes and the final organizer submission schema remain unavailable.
- Next: review the change before merging.
- Commit/PR: pending

## 2026-10-16 — Explain plan 11928 source-geometry failure

- Status: done
- Changed: `cable_planner/ingestion/normalize.py`, `tests/ingestion/test_normalize.py`
- Why: plan 11928 contains a 1.43144 m2 living fragment outside its internal boundary and two living fragments with only about 0.178 m and 0.00407 m maximum room-boundary clearance. Neither can satisfy the required 0.5 m node clearance; two doors also touch three room polygons each.
- Changed: boundary and fallback-node diagnostics now report measured outside area and approximate room-boundary clearance, so the user can distinguish unrecoverable source geometry from a fallback placement bug. No source components are silently discarded and no ambiguous door is assigned to a guessed pair.
- Checked: nine ingestion tests and six web tests passed outside the Windows sandbox; after restarting the local server, the 11928 preview returned HTTP 422 with the measured structured diagnostics.
- Open: plan 11928 needs corrected source polygons or an explicitly approved rule for excluding these labeled living fragments before it can produce a valid output.
- Next: obtain corrected source geometry if this ID must be runnable.
- Commit/PR: pending

## 2026-10-17 — Local dataset picker and interactive route viewer

- Status: done
- Changed: `frontend/`, `cable_planner/web/`, `tests/web/`, `README.md`
- Why: focus the React interface on localhost data from trusted `ResPlan.pkl` and `split.json`, make the 2D input/output diagrams readable, and expose the independently checked physical route in 3D.
- Changed: removed the bundled/local source choice from the React UI; stacked the input and checked output views at full width; added a dataset-backed picker, route-aware 3D architectural display, dynamic hub/node selection, exact-polyline ring playback, camera controls, and simulated speed controls. Line-shaped and polygon-shaped windows render as translucent architectural features; fitted camera distance responds to the scene aspect ratio.
- Checked: `npm run build` and `npm test` pass (3 route tests); the web/API suite passes (8 tests), including local split lookup, previews, schema-valid output, provisional export gating, and polygon/line window geometry; `git diff --check` passes. A live local 13033 run independently validated and displayed three dynamic hub controls, stacked 2D plans, and the 3D viewer. The production build emits a 610 KB lazy Three.js viewer chunk (156 KB gzip).
- Open: Docker engine is unavailable, so the image build has not been smoke-tested. Wall height and opening width are schematic because source plans are 2D; submission export remains provisional until an organizer schema is published.
- Next: review and merge the integration change.
- Commit/PR: pending

## 2026-10-17 — Place 2D plans side by side above the 3D viewer

- Status: done
- Changed: `frontend/src/style.css`
- Why: show the input and checked output floor plans together for direct comparison, with the existing 3D viewer following beneath them.
- Changed: use two equal-width 2D panels on desktop and stack them below 760 px; reduce desktop image-frame height to suit the two-column layout. The 3D section remains the next section after the comparison.
- Checked: production frontend build passed, all 3 route tests passed, and `git diff --check` passed.
- Open: a post-build browser inspection was blocked by the browser URL policy; the desktop/mobile grid behavior is verified in the compiled CSS.
- Next: none.
- Commit/PR: pending

## 2026-10-17 — Fix plan preview label overlap and image clipping

- Status: done
- Changed: `cable_planner/web/app.py`, `frontend/src/style.css`, `tests/web/test_app.py`, `tests/validation/test_visualization.py`
- Why: selecting plan 13033 showed overlapping labels in the input preview, and the fixed-height image frame clipped the lower floor-plan geometry.
- Changed: previews now use the same 12x10-inch plot layout as post-run input images at a lower DPI. The 2D image frame follows the image's natural aspect ratio instead of hiding overflow. Added checks for readable 13033 labels and full-size preview images across all three presets.
- Checked: full Python test suite passed (63 tests); frontend production build and all three frontend tests passed; `git diff --check` passed. Vite reports the expected large Three.js viewer chunk.
- Open: Docker engine is unavailable, so the image build has not been smoke-tested.
- Next: finish frontend verification and review the integration change.
- Commit/PR: pending

## 2026-10-17 — Prevent label collisions on dense dataset plans

- Status: done
- Changed: `cable_planner/visualization/renderer.py`, `tests/validation/test_visualization.py`
- Why: dense local plans can still have room and node ID labels colliding even when rendered at the full plot size.
- Changed: place node and room IDs into nearby free display space with collision checks; omit a label only when the drawing cannot fit it without overlap. Added a stress test with twelve IDs sharing the same anchor.
- Checked: full Python suite passed (64 tests), including all three preview endpoints and the dense-label stress test.
- Open: the local development server must reload/restart to use the updated renderer; no listener was found on port 8000 during verification.
- Next: reload the local frontend/backend and review a dense plan preview.
- Commit/PR: pending

## 2026-10-17 — Match selected preview to post-run input image

- Status: done
- Changed: `cable_planner/web/app.py`, `cable_planner/visualization/renderer.py`, `tests/web/test_app.py`
- Why: the selected-plan preview used 110 DPI, while the post-run input used the renderer's 200 DPI default, so the same plan appeared at different relative scales.
- Changed: both paths now use the exact same render settings and PNG export. Collision placement runs after final plot bounds are established, and preview responses disable caching to avoid stale thumbnails.
- Checked: the preview test compares each preset's PNG byte-for-byte with the post-run input render and checks the no-store header; full backend suite passed (64 tests).
- Open: the local development server must reload/restart to use the updated renderer.
- Next: run verification and reload the local service.
- Commit/PR: pending
## 2026-10-17 — Add opt-in internal-boundary clipping

- Status: implemented, then removed at user request; see the following entry
- Changed: `cable_planner/ingestion/normalize.py`, `cable_planner/web/app.py`, `frontend/src/App.tsx`, `frontend/src/style.css`, `tests/ingestion/test_normalize.py`, `tests/web/test_app.py`, `README.md`
- Why: plan 993085 has eligible room polygons extending beyond the internal boundary; the selected policy is explicit opt-in clipping because it changes geometry and scoring.
- Changed: added `clip_outside_rooms=False` to normalization and the run/preview APIs. When enabled, only rooms that strict mode would reject are intersected with the internal boundary. A clipped result must remain one valid polygon. Updated room geometry, area, fallback-node placement, and portal extraction use the clipped polygon; per-room diagnostics report removed area. The plan picker checkbox is off by default and applies identically to the preview and run.
- Checked: normalization tests pass (10); explicit local-loader clipping test passes; frontend production build passes; `git diff --check` passes. The full `tests/web/test_app.py` run did not complete in this environment after 60 seconds, while the focused loader test completed successfully.
- Open: verify the opt-in against plan 993085 with the full local archive and solver, then restart the local service to use the UI change.
- Next: superseded by the removal entry below.
- Commit/PR: `aef1a1b` pushed to `main`

## 2026-10-17 — Remove opt-in room clipping

- Status: reverted at user request
- Changed: reverted `aef1a1b`; restored strict normalization and removed the checkbox, API parameters, and clipping tests/documentation.
- Why: the user requested removal of the clipping feature.
- Checked: normalization suite passed (9 tests), frontend production build passed, and `git diff --check` passed.
- Open: none
- Next: push the removal to `main`.
- Commit/PR: pending

## 2026-10-17 — Add downloadable completed-run PDF report

- Status: done
- Changed: `pyproject.toml`, `uv.lock`, `cable_planner/web/app.py`, `cable_planner/web/report.py`, `frontend/src/App.tsx`, `frontend/src/style.css`, `README.md`
- Why: keep the selected run's source and checked output images, checked metrics, diagnostics, timing, development JSON, submission JSON, architecture, and run metadata together in a portable report.
- Changed: added a PDF report endpoint and a download button in the verified-result panel. ReportLab is a declared project dependency and is imported only when a report is requested so missing runtime installation does not prevent the rest of the UI/API from starting.
- Checked: added and locked ReportLab 4.5.1. Generated a representative 38-page PDF from a checked plan result, rendered it to PNG, visually inspected the cover, input image, and JSON appendix, and confirmed all report sections are present. The frontend TypeScript/Vite production build passed.
- Open: none.
- Next: none.
- Commit/PR: pending

## 2026-10-17 — Stream truthful solver progress

- Status: implemented
- Changed: `cable_planner/web/app.py`, `cable_planner/web/run_progress.py`, `cable_planner/solver/grid_router.py`, `frontend/src/App.tsx`, `frontend/src/style.css`, `frontend/vite.config.ts`, `tests/web/test_app.py`, `tests/solver/test_grid_router.py`
- Why: make solver activity visible during longer runs without inventing a percent or finish time, and retain the established synchronous API response.
- Changed: added `POST /api/runs/stream` with newline-delimited progress, result, and structured error events. The UI shows an ordered six-stage timeline in the checked-output placeholder, elapsed seconds, and observed solver counts. Bundled plans mark local normalization skipped. Added optional solver callbacks and batched counter emission; no search passes were added.
- Checked: solver and web suites passed (28 tests); after the final solver callback batching adjustment, focused solver/web tests passed (10 tests). Frontend production build and `compileall` passed. The synchronous and streamed result test compares their completed output; streamed tests cover stage states, counters, success, and failure.
- Checked: repeated 13,033-plan runs showed 1.44% median overhead (baseline runs varied by about 1.7%). A 14,433-plan run measured 1.01% faster with instrumentation, within expected run-to-run variation. The progress path adds no solver passes.
- Checked: manually streamed a 13,033 short run (8.38 s total), a 14,433 longer run (28.79 s), and an unavailable-plan failure. Stage order and bundled normalization skip were correct; live A* counts increased during search; the failure named `load_plan`. The updated frontend is open at `http://localhost:5173/`.
- Fixed: all requests from the existing `5173` page were reaching an older API on `8000`, which did not expose the stream route. The local dev proxy and README now default to the updated API on `8001`, with `CABLE_RING_API_PROXY` as an override.
- Checked: `POST http://127.0.0.1:5173/api/runs/stream` returned HTTP 200 and a complete result with live counters through validation and export.
- Open: none.
- Next: none.
- Commit/PR: pending
