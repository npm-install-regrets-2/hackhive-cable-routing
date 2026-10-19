# Dataset provenance and usage

Team: npminstallregrets | Problem statement: PS4 | Project: Cable Ring Planner

The hackathon supplied **ResPlan**, a third-party dataset. We did not collect or label a new floor-plan dataset. The source is [ResPlan on Kaggle, version 6](https://www.kaggle.com/datasets/resplan/resplan/versions/6), the version named by the supplied `croissant.json` metadata. The local `ResPlan.pkl` contains 17,000 residential floor plans and is approximately 300 MB.

| Supplied file | Use in this project |
| --- | --- |
| `ResPlan.pkl` | Trusted local input for plan geometry, semantic rooms, walls, doors, windows, declared area, and IDs. Normalization converts one selected item into a shared-schema Plan. |
| `split.json` | Identifies the dataset's train, validation, test, and augmented groups when selecting development examples. These are not the official challenge feasibility split. |
| `croissant.json` | Dataset version, source URL, and provenance metadata; not a solver input. |
| Dataset `README.md` and `LICENSE` | Source description and attribution; not solver inputs. |

The archive does **not** contain organizer-provided PS4 fixed nodes, selected hubs, room assignments, cable rings, or challenge scores. The examples in this package use deterministic `development_fallback` nodes. They are derived demonstration artifacts, never represented as organizer-supplied node coordinates. The team-produced data included here is normalized Plan/Solution JSON and visual output for selected plan IDs, not a replacement for the source archive.

The supplied metadata conflicts on licensing: its README and LICENSE state CC BY 4.0 for data, while its Croissant record states CC BY-NC-SA 4.0. This package preserves attribution and records the discrepancy without resolving it. Confirm the applicable terms with the dataset owner before redistributing the raw archive, especially for commercial use.

The 300 MB pickle is omitted from this GitHub report ZIP at the team's request. The organizer's OneDrive notice says to **upload datasets used**. A source link in this package may not meet that requirement; ask the organizers whether a link to the dataset they supplied is sufficient or whether they expect the dataset file itself. No OneDrive upload is performed by this package.
