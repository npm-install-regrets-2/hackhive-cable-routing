# npminstallregrets_PS4

**GitHub repository:** https://github.com/npm-install-regrets-2/hackhive-cable-routing

**Code and report in this submission:** https://github.com/npm-install-regrets-2/hackhive-cable-routing/pull/7 (review PR, branch `feat/judge-route-comparison-current`)

Open `REPORT.pdf` first for the three-page overview of Honeywell PS4 and our approach. `archive/` contains the original organizer-provided ResPlan files, including `ResPlan.pkl`. `DATASET.md` explains their provenance, use, and unresolved license-metadata conflict. `REPRODUCE.md` gives local demo and validation instructions. `images/` contains full-resolution floor-plan figures; `examples/` contains independently checked development Plan + Solution JSON; `schema/` defines those JSON documents. `MANIFEST.md` lists each file and its SHA-256 checksum.

This combined report-and-dataset package has not been uploaded to OneDrive. The organizer's separate dataset-upload request remains to be completed.

The large pickle uses ZIP's LZMA compression so the single package stays below GitHub's file-size limit. Extract with Python 3.11+ (`python -m zipfile -e npminstallregrets_PS4.zip output_folder`) or another extractor that supports ZIP method 14; some built-in ZIP viewers do not.
