# HackHive cable-routing prototype

## Run the trusted local demo

The demo accepts a locally trusted ResPlan archive path and a numeric plan ID.
It does not accept arbitrary pickle uploads.

```powershell
streamlit run sana/demo/app.py
```

## Container

Build and run the UI:

```powershell
docker build -t hackhive-cable-routing .
docker run --rm -p 8501:8501 -v ${PWD}/archive:/app/archive hackhive-cable-routing
```

Open `http://localhost:8501`. The mounted archive is required because the raw
ResPlan pickle is intentionally not included in the image.

## Manually inspect input and output side by side

Start the demo with `streamlit run sana/demo/app.py` (or the container steps
above), then:

1. Set **Trusted ResPlan archive** to the local archive file, usually
   `E:\dev\HackHive\archive\ResPlan.pkl`.
2. Enter the numeric **Plan ID** to inspect (the default is `14433`).
3. Leave **Maximum assignment candidates** at `200` for a first run, then
   click **Run planner**.
4. Check **Normalization** first. If `ok` is false, read its diagnostics; the
   solver will not run for an unusable normalized plan.
5. Compare **Input floor plan** on the left with **Solver output and checked
   routes** on the right. Green rooms are eligible input rooms, grey rooms are
   excluded, yellow markers are fixed nodes, and the output adds hub stars,
   territory colors, and cable rings.
6. Read **Independent validation** for validity, violations, and recomputed
   metrics. A visually plausible route is not sufficient if validation fails.
7. Download the provisional metre export only for inspection; it is not yet
   the organizer's final submission format.

## Real-plan smoke run

```powershell
python priyanshu/benchmarks/real_smoke.py --archive E:\dev\HackHive\archive\ResPlan.pkl --plan-id 14433
```

## Selected-plan benchmark

```powershell
Push-Location priyanshu
python -m benchmarks.report --archive E:\dev\HackHive\archive\ResPlan.pkl --plan-ids 14433 3379 --output benchmark.json
Pop-Location
```
