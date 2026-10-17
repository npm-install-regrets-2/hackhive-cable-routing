# Fast floor plans for the judge demo

Date: 2026-10-17. These are curated demo examples, not a representative runtime benchmark.

## Recommended order

| Plan ID | Split | Eligible rooms | H / lower bound | Checked J | Local solver time | Why show it |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 12014 | Validation | 3 | 1 / 1 | 22.4604 | 0.91 s median | Fast single-ring example across three eligible rooms |
| 8063 | Test | 4 | 2 / 2 | 34.7645 | 3.44 s median | Fast two-territory example, with zero crossings and overlap |

The independent validator accepts both saved solutions with no violations, and both combined JSON files validate against `shared/schema/common.schema.json`. The hub counts equal the capacity lower bound, so no solution can use fewer hubs under the configured rules. The route costs are the best found by this bounded solver; global minimum `J` is not proven. Both plans use deterministic development-fallback nodes because the ResPlan archive has no organizer-provided nodes.

## How the plans were selected

Using `random.Random(1729)`, sample 120 IDs each from the ResPlan validation and test splits. Normalize the samples, then screen for two to six eligible rooms and an arithmetic hub lower bound of one or two. Time the current production `cable_planner.solver.solve` on 15 selected small plans with a 15- or 25-second timeout. Fourteen completed and independently validated; one exceeded 15 seconds. The fastest checked one-hub option was 12014 (0.84 s on the first screen), and the fastest checked two-hub lower-bound option was 8063 (2.17 s on the first screen). Plan 4944 took 3.86 s but had one crossing and 1.11 m overlap; 13033 and 14433 are slower existing examples.

Run three further solves on each finalist in one local Python process. Plan 12014 took 0.836, 0.911, and 1.218 s; plan 8063 took 3.507, 3.401, and 3.436 s. Outputs and checked route costs were identical across these runs. Normalization took 0.013 s for 12014 and 0.011 s for 8063 in the screen. Rendering input and checked overlays took about 1.47 s and 1.25 s respectively in a separate run. Timings are local wall-clock observations, exclude app startup and archive loading, and do not predict hosted latency.

## Demo workflow

For the local Vite demo, start FastAPI and Vite as described in `README.md`, select the bundled plan **4944**, and run it. Show the selected and best found zero-crossing overlays, the checked metric table, and both JSON downloads. The earlier quick clean-ring examples **12014** and **8063** remain checked bundles in `examples/outputs/`; they are not featured in the Vite picker.

## Valid minimum-hub plans with crossing and overlap

| Plan ID | Split | H / lower bound | Crossings X | Overlap O | Checked J | Median local solver time | Use |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 4944 | Test | 2 / 2 | 1 | 1.112 m | 45.0814 | 3.506 s | Clearest compact example with both penalties |
| 8061 | Validation | 2 / 2 | 2 | 2.207 m | 59.0862 | 3.511 s | Longer shared line and two crossings |
| 8450 | Validation | 2 / 2 | 4 | 0.897 m | 70.4240 | 2.797 s | Additional crossing-heavy option; saved overlay in `tmp/judge_eval/` |

The overlap in 4944 is a 1.112 m retraced vertical stretch in its blue ring. In 8061, the orange ring shares a 2.207 m horizontal stretch. These are checked metric values, not hard-rule failures. The capacity lower bound proves that two hubs are necessary in each plan. The solver does **not** prove that these particular rings minimize J globally; present them as validated solutions with an optimal hub count.

## Side-by-side route comparison for plan 4944

The bounded search generates nine complete two-hub candidates at the selected cable-clearance setting. Two have zero crossings. The selected route has H = 2, L = 30.4697 m, X = 1, O = 1.1117 m, B = 17, J = 45.0814, and area gap = 84.6219 m². The best found zero-crossing route has H = 2, L = 38.4531 m, X = 0, O = 0, B = 20, J = 48.4531, and area gap = 57.4419 m². Its J is 3.3717 higher. Both independently validate and meet the proven two-hub lower bound. Hub positions and territory assignments may differ.

In the Vite demo, select **4944** and **Run plan 4944**. Show the two checked overlays, metric table, and official-format downloads. Explain that the crossing route wins the solver's bounded search because its total J is lower despite the crossing and overlap penalties. Call each route *best found within the bounded search*. Plan **8061** is available through the local archive search; when run, the app reports **No qualifying candidate found in this search**. That statement does not imply a zero-crossing route is impossible.

For this follow-up, normalize 400 IDs from each of the validation and test splits using `random.Random(261017)`, retain the 34 schema-shaped four-eligible-room plans with a two-hub arithmetic lower bound, and solve each with a 12-second timeout. All 34 completed; five independently valid solutions had both X > 0 and O > 0. Re-run the highlighted options three times individually and validate every output. The combined bundles for 4944 and 8061 are in `examples/outputs/`. A normalized 4944 input bundle is in `examples/inputs/` for the Vite demo.
