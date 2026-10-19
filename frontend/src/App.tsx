import { lazy, Suspense, useEffect, useState } from 'react'
import type { Architecture, Development } from './model'
import { floorPlanAreaM2 } from './planArea'

type PlanOption = { id: number; split: string | null; available?: boolean }
type Catalog = { sources: string[]; presets: PlanOption[]; results: PlanOption[]; total: number }
type Diagnostic = { code: string; message: string; entity_ids?: string[] }
type Metrics = {
  hub_count: number; length_m: number; crossings: number; overlap_m: number;
  bends: number; route_cost: number; area_gap_m2: number
}
type Validation = {
  is_valid: boolean; violations: Diagnostic[]; warnings: Diagnostic[];
  recomputed_metrics: Metrics | null
}
type Timings = {
  load_s: number; normalize_s: number | null; solve_s: number;
  validate_s: number; render_export_s: number; total_s: number
}
type ComparisonAlternative = {
  validation: Validation; output_image: string; development: Development; submission: unknown
}
type Comparison = {
  criterion: 'zero_crossings' | 'zero_overlap' | null; candidate_count: number;
  qualifying_candidate_count: number; clearance_m: number;
  alternative_search_hub_count: number | null; alternative_search_candidate_count: number;
  alternative_search_qualifying_candidate_count: number;
  alternative: ComparisonAlternative | null
}
type RunResult = {
  plan_id: number; source: string; status: string; lower_bound_hubs: number | null;
  validation: Validation; diagnostics: Diagnostic[]; timings: Timings;
  input_image: string; output_image: string | null; development: Development;
  architecture: Architecture;
  submission: unknown | null; fallback_nodes: number; comparison: Comparison | null
}
type ApiError = { code: string; message: string; diagnostics?: Diagnostic[] }
type RunStage = { id: string; label: string; status: 'upcoming' | 'active' | 'completed' | 'skipped' | 'failed' }
type ProgressState = {
  stages: RunStage[]; active_stage: string | null; failed_stage: string | null;
  counters: Record<string, number>; elapsed_s: number
}
type ProgressEvent = { type: 'progress'; active_stage: string | null; stages: RunStage[]; counters: Record<string, number>; elapsed_s: number; failed_stage?: string | null }
type TerminalEvent = { type: 'complete'; state: ProgressState; result: RunResult } | { type: 'error'; state: ProgressState; stage: string; error: ApiError }

const presets = [4944, 14433, 13033, 14926]
const ViewerPanel = lazy(() => import('./ViewerPanel'))
const number = (value: number, digits = 2) => value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })
const stageCounterKeys: Record<string, string[]> = {
  prepare_geometry: ['eligible_rooms', 'legal_hub_locations', 'routing_grid_vertices', 'routing_grid_edges', 'clearance_attempt'],
  search: ['current_hub_count', 'hub_count_attempts', 'partition_patterns_examined', 'connected_partitions_found', 'candidate_combinations_evaluated', 'ring_route_attempts', 'astar_states_expanded', 'clearance_attempt', 'legal_hub_locations'],
}
const counterLabels: Record<string, string> = {
  eligible_rooms: 'Eligible rooms', legal_hub_locations: 'Legal hub locations found',
  routing_grid_vertices: 'Routing grid vertices', routing_grid_edges: 'Routing grid edges',
  clearance_attempt: 'Clearance attempt', current_hub_count: 'Current hub count',
  hub_count_attempts: 'Hub counts attempted', partition_patterns_examined: 'Room assignment patterns examined',
  connected_partitions_found: 'Connected partitions found', candidate_combinations_evaluated: 'Hub combinations evaluated',
  ring_route_attempts: 'Ring routes attempted', astar_states_expanded: 'A* states expanded',
}

function initialProgress(): ProgressState {
  return {
    stages: [
      { id: 'load_plan', label: 'Load plan', status: 'active' },
      { id: 'normalize_plan', label: 'Normalize local plan', status: 'upcoming' },
      { id: 'prepare_geometry', label: 'Prepare routing geometry', status: 'upcoming' },
      { id: 'search', label: 'Search connected territories and closed rings', status: 'upcoming' },
      { id: 'validate', label: 'Independently check solution', status: 'upcoming' },
      { id: 'render_export', label: 'Render and export results', status: 'upcoming' },
    ],
    active_stage: 'load_plan', failed_stage: null, counters: {}, elapsed_s: 0,
  }
}

async function streamRun(request: { source: string; plan_id: number; compare: boolean; alternative_hub_count?: number }, onProgress: (state: ProgressState) => void): Promise<RunResult> {
  let response: Response
  try {
    response = await fetch('/api/runs/stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
    })
  } catch (failure) { throw asApiError(failure) }
  if (!response.ok) {
    let body: { detail?: unknown }
    try { body = await response.json() }
    catch { throw { code: 'invalid_response', message: `Planner returned HTTP ${response.status} without JSON.` } as ApiError }
    throw asApiError(body.detail)
  }
  if (!response.body) throw { code: 'stream_unavailable', message: 'Planner did not open the progress stream.' } as ApiError

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminal: TerminalEvent | null = null
  const consumeLine = (line: string) => {
    if (!line.trim()) return
    const event = JSON.parse(line) as ProgressEvent | TerminalEvent
    if (event.type === 'progress') onProgress({ ...event, failed_stage: event.failed_stage ?? null })
    else {
      terminal = event
      onProgress(event.state)
    }
  }
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) consumeLine(line)
    if (done) break
  }
  if (buffer.trim()) consumeLine(buffer)
  const terminalEvent = terminal as TerminalEvent | null
  if (!terminalEvent) throw { code: 'stream_incomplete', message: 'Planner closed the progress stream before returning a result.' } as ApiError
  if (terminalEvent.type === 'error') throw asApiError(terminalEvent.error)
  return terminalEvent.result
}

function asApiError(value: unknown): ApiError {
  if (typeof value === 'object' && value !== null && 'code' in value && 'message' in value &&
      typeof value.code === 'string' && typeof value.message === 'string') return value as ApiError
  if (value instanceof Error) return { code: 'network_error', message: value.message }
  return { code: 'request_failed', message: 'The planner did not return a usable response.' }
}

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(url, options) }
  catch (failure) { throw asApiError(failure) }
  let body: { detail?: unknown } & Record<string, unknown>
  try { body = await response.json() }
  catch { throw { code: 'invalid_response', message: `Planner returned HTTP ${response.status} without JSON.` } as ApiError }
  if (!response.ok) {
    throw asApiError(body.detail)
  }
  return body as T
}

function saveJson(name: string, value: unknown) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

function Mark() {
  return <span className="brand-mark" aria-hidden="true"><span /><span /><span /><span /></span>
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="metric"><span className="metric-label">{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>
}

function RunProgressView({ progress, elapsed, failed }: { progress: ProgressState; elapsed: number; failed: boolean }) {
  const activeStage = progress.stages.find(stage => stage.id === (progress.failed_stage ?? progress.active_stage))
  const visibleCounters = (stageCounterKeys[progress.failed_stage ?? progress.active_stage ?? ''] ?? [])
    .filter(key => progress.counters[key] !== undefined)
  return <div className="run-progress-view">
    <div className="run-progress-heading">
      <strong>{failed ? `Stopped during ${activeStage?.label ?? 'the run'}` : activeStage?.label ?? 'Preparing run…'}</strong>
      <small>{number(elapsed, 1)} seconds elapsed</small>
    </div>
    <span className="sr-only" aria-live="polite">{activeStage?.label ?? ''}</span>
    <ol className="run-stage-list" aria-label="Plan run stages">
      {progress.stages.map(stage => <li className={`run-stage ${stage.status}`} key={stage.id} aria-current={stage.status === 'active' ? 'step' : undefined}>
        <span className="run-stage-marker" aria-hidden="true">{stage.status === 'completed' ? '✓' : stage.status === 'skipped' ? '–' : stage.status === 'failed' ? '!' : stage.status === 'active' ? '◌' : '·'}</span>
        <span>{stage.label}{stage.status === 'skipped' ? ' · skipped' : ''}</span>
      </li>)}
    </ol>
    {visibleCounters.length > 0 && <div className="run-counter-grid" aria-label="Live solver counters">
      {visibleCounters.map(key => <div className="run-counter" key={key}><small>{counterLabels[key]}</small><strong>{number(progress.counters[key], 0)}</strong></div>)}
    </div>}
  </div>
}

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [selected, setSelected] = useState<number>(4944)
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [started, setStarted] = useState(0)
  const [jsonTab, setJsonTab] = useState<'submission' | 'development'>('submission')
  const [reportBusy, setReportBusy] = useState(false)
  const [runProgress, setRunProgress] = useState<ProgressState | null>(null)

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      api<Catalog>(`/api/catalog?source=local&q=${encodeURIComponent(query)}&limit=60`)
        .then(setCatalog)
        .catch(() => api<Catalog>(`/api/catalog?source=bundled&q=${encodeURIComponent(query)}&limit=60`)
          .then(setCatalog)
          .catch((failure: unknown) => setError(asApiError(failure))))
    }, 180)
    return () => window.clearTimeout(timeout)
  }, [query])

  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 100)
    return () => window.clearInterval(timer)
  }, [busy, started])

  function choose(id: number) {
    if (busy) return
    setSelected(id)
    setResult(null)
    setError(null)
    setRunProgress(null)
  }

  async function run() {
    setBusy(true)
    setResult(null)
    setError(null)
    setRunProgress(initialProgress())
    const start = Date.now()
    setStarted(start)
    setElapsed(0)
    try {
      const data = await streamRun({ source: presets.includes(selected) ? 'bundled' : 'local', plan_id: selected, compare: true, ...(selected === 16416 ? { alternative_hub_count: 2 } : {}) }, setRunProgress)
      setResult(data)
      setJsonTab('submission')
    } catch (failure) {
      setError(asApiError(failure))
    } finally {
      setElapsed((Date.now() - start) / 1000)
      setBusy(false)
    }
  }

  async function downloadPdfReport() {
    if (!result || reportBusy) return
    setReportBusy(true)
    setError(null)
    try {
      const response = await fetch('/api/reports/pdf', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result }),
      })
      if (!response.ok) {
        let detail: unknown
        try { detail = (await response.json()).detail } catch { /* use the HTTP status below */ }
        throw asApiError(detail ?? new Error(`Report generation failed (HTTP ${response.status}).`))
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `cable-ring-plan-${result.plan_id}-report.pdf`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (failure) {
      setError(asApiError(failure))
    } finally {
      setReportBusy(false)
    }
  }

  const metrics = result?.validation.recomputed_metrics
  const floorAreaM2 = result ? floorPlanAreaM2(result.development.plan) : null
  const comparison = result?.comparison?.criterion ? result.comparison : null
  const alternative = comparison?.alternative
  const alternativeMetrics = alternative?.validation.recomputed_metrics
  const comparisonLabel = comparison?.criterion === 'zero_crossings' ? 'zero crossings' : 'zero overlap'
  const comparisonRows = metrics && alternativeMetrics ? [
    ['H', String(metrics.hub_count), String(alternativeMetrics.hub_count)],
    ['L · m', number(metrics.length_m, 4), number(alternativeMetrics.length_m, 4)],
    ['X', String(metrics.crossings), String(alternativeMetrics.crossings)],
    ['O · m', number(metrics.overlap_m, 4), number(alternativeMetrics.overlap_m, 4)],
    ['B', String(metrics.bends), String(alternativeMetrics.bends)],
    ['J', number(metrics.route_cost, 4), number(alternativeMetrics.route_cost, 4)],
    ['Area gap · m²', number(metrics.area_gap_m2, 4), number(alternativeMetrics.area_gap_m2, 4)],
  ] : []
  const previewSource = presets.includes(selected) ? 'bundled' : 'local'
  const previewUrl = `/api/plans/${selected}/preview?source=${previewSource}`
  const candidates = (catalog?.results ?? []).filter(item => query.length > 0 || !presets.includes(item.id))

  return <div className="page-shell">
    <header className="topbar">
      <div className="brand"><Mark /><div><strong>Cable Ring <em>Studio</em></strong><span>PLAN · SOLVE · VERIFY</span></div></div>
      <div className="topbar-right"><span className="live-dot" /> BUNDLED + LOCAL <span className="edition">/ 2026</span></div>
    </header>

    <main className="main-wrap">
      <section className="intro">
        <div className="eyebrow"><span>01 / FLOOR PLAN LAB</span><span>HUB PLACEMENT + CLOSED RINGS</span></div>
        <div className="intro-grid"><div><h1>From floor plan<br />to <i>feasible rings.</i></h1><p>Choose a plan, run the solver, and inspect every hub, cable leg, and checked metric in one place.</p></div><div className="intro-aside"><span className="aside-line" /><p>One input.<br />Checked route choices.<br />Every number accounted for.</p><span className="aside-index">FIG. 01 / CABLE ROUTING</span></div></div>
      </section>

      <div className="work-grid">
        <aside className="picker panel">
          <div className="panel-head"><span>01</span><div><h2>Plan picker</h2><p>Featured examples + local split.json IDs</p></div></div>
          <div className="field-note">Featured plans use checked-in normalized geometry. Other IDs use the trusted ResPlan archive on this server and are normalized when run.</div>
          <div className="section-label"><span>FEATURED PLANS</span><span>04</span></div>
          <div className="preset-list">{presets.map((id, index) => <button type="button" className={`preset ${selected === id ? 'selected' : ''}`} onClick={() => choose(id)} disabled={busy} key={id} aria-pressed={selected === id}>
            <span className="preset-thumb"><img src={`/api/plans/${id}/preview?source=bundled`} alt={`Floor plan ${id} thumbnail`} loading="lazy" /></span>
            <span className="preset-copy"><small>{id === 4944 ? 'JUDGE COMPARISON' : `FEATURED 0${index + 1}`}</small><strong>{id}</strong><span>{catalog?.presets.find(p => p.id === id)?.split ?? 'Bundled'}</span></span>
            <span className="preset-arrow">↗</span>
          </button>)}</div>
          <label className="search-label" htmlFor="plan-search">FIND A PLAN ID</label>
          <div className="search-wrap"><span aria-hidden="true">⌕</span><input id="plan-search" type="search" inputMode="numeric" placeholder="Search split.json IDs" value={query} onChange={event => setQuery(event.target.value)} disabled={busy} /></div>
          <div className="search-results" aria-label="Matching plan IDs">{candidates.slice(0, 24).map(item => <button key={item.id} type="button" onClick={() => choose(item.id)} aria-pressed={selected === item.id}>{item.id}<span>{item.split}</span></button>)}{query && catalog?.total === 0 && <p>No matching ID in split.json.</p>}{catalog && catalog.total > 24 && <small>{catalog.total} matches · showing the first 24. Keep typing to narrow.</small>}</div>
          <button className="run-button" type="button" onClick={run} disabled={busy || (!presets.includes(selected) && !catalog?.sources.includes('local'))}>{busy ? <><span className="spinner" /> RUNNING · {number(elapsed, 1)} S</> : <>RUN PLAN {selected} <span>↗</span></>}</button>
          <p className="picker-foot">Fixed nodes may be development fallbacks. The checker verifies every result independently.</p>
        </aside>

        <div className="content-stack">
          <section className="comparison panel">
            <div className="section-top"><div><span className="kicker">02 / VISUAL COMPARISON</span><h2>Floor-plan workspace</h2></div><span className="plan-badge">PLAN #{selected}</span></div>
            {floorAreaM2 !== null && <div className="floor-area"><span>WHOLE FLOOR-PLAN AREA</span><strong>{number(floorAreaM2, 2)} m²</strong><small>Inside the plan boundary, excluding holes</small></div>}
            {error && <div className="alert" role="alert"><strong>{error.code.replaceAll('_', ' ')}</strong><p>{error.message}</p>{elapsed > 0 && <p>Elapsed before failure: {number(elapsed, 1)} s</p>}{error.diagnostics?.map((item, index) => <p key={index}>{item.code}: {item.message}</p>)}</div>}
            <div className="image-grid">
              <div className="image-card"><div className="image-title"><span className="image-number">A</span><div><strong>{alternative ? 'Selected best found route' : 'Input floor plan'}</strong><small>{alternative ? 'INDEPENDENTLY CHECKED' : 'ROOMS · NODES · PORTALS'}</small></div></div><div className="image-frame"><img key={selected} src={alternative ? result?.output_image ?? previewUrl : result?.input_image ?? previewUrl} alt={alternative ? `Selected route for plan ${selected}` : `Input floor plan ${selected}`} /></div></div>
              <div className="image-card"><div className="image-title"><span className="image-number coral">B</span><div><strong>{alternative ? `Best found ${comparisonLabel} route` : 'Checked output'}</strong><small>{alternative ? 'INDEPENDENTLY CHECKED' : 'HUBS · TERRITORIES · RINGS'}</small></div></div><div className={`image-frame ${!result?.output_image ? 'empty-frame' : ''}`}>{alternative ? <img src={alternative.output_image} alt={`${comparisonLabel} alternative for plan ${selected}`} /> : result?.output_image ? <img src={result.output_image} alt={`Checked solution for plan ${selected}`} /> : busy && runProgress ? <RunProgressView progress={runProgress} elapsed={elapsed} failed={false} /> : error && runProgress ? <RunProgressView progress={runProgress} elapsed={elapsed} failed /> : <div><span>◇</span><strong>Output awaits a run</strong><small>Select a plan and press Run plan</small></div>}</div></div>
            </div>
            {result && alternative && comparison && metrics && alternativeMetrics && <div className="route-comparison">
              <p><strong>Best found within this bounded search.</strong> {comparison.alternative_search_hub_count !== null ? <>The selected {metrics.hub_count}-hub search generated {comparison.candidate_count} complete candidates and found no {comparisonLabel} route. A separate {comparison.alternative_search_hub_count}-hub search generated {comparison.alternative_search_candidate_count} complete candidates; {comparison.alternative_search_qualifying_candidate_count} had {comparisonLabel}. </> : <>{comparison.qualifying_candidate_count} of {comparison.candidate_count} generated complete candidates had {comparisonLabel}. Both use {metrics.hub_count} hubs at </>}{number(comparison.clearance_m, 2)} m cable clearance; hub positions and territory assignments may differ. {metrics.hub_count === result.lower_bound_hubs ? 'The selected hub count is proven minimal.' : 'The selected hub count is best known.'} A global minimum J is not proven.</p>
              <div className="route-table-wrap"><table><caption>Checked route metrics</caption><thead><tr><th scope="col">Metric</th><th scope="col">Selected</th><th scope="col">Alternative</th></tr></thead><tbody>{comparisonRows.map(([label, selectedValue, alternativeValue]) => <tr key={label}><th scope="row">{label}</th><td>{selectedValue}</td><td>{alternativeValue}</td></tr>)}</tbody></table></div>
              <div className="route-difference">Alternative J − selected J <strong>{alternativeMetrics.route_cost - metrics.route_cost >= 0 ? '+' : ''}{number(alternativeMetrics.route_cost - metrics.route_cost, 4)}</strong></div>
              <div className="route-downloads"><button type="button" onClick={() => saveJson(`slide8_submission_${selected}_selected.json`, result.submission)} disabled={!result.submission}>DOWNLOAD SELECTED CHECKED JSON ↓</button><button type="button" onClick={() => saveJson(`slide8_submission_${selected}_alternative.json`, alternative.submission)}>DOWNLOAD ALTERNATIVE CHECKED JSON ↓</button></div>
              <details className="route-input"><summary>View input floor plan</summary><img src={result.input_image} alt={`Input floor plan ${selected}`} /></details>
            </div>}
            {comparison && !alternative && <p className="no-alternative" role="status">No qualifying candidate found in this search</p>}
            <div className="comparison-foot"><span><i className="legend-node" /> FIXED NODE</span><span><i className="legend-hub" /> HUB</span><span><i className="legend-route" /> CABLE RING</span><span className="comparison-status">{result ? (result.validation.is_valid ? '✓ INDEPENDENT CHECK PASSED' : '✕ CHECK FAILED') : 'READY TO RUN'}</span></div>
          </section>

          {result?.validation.is_valid && (result.status === 'feasible' || result.status === 'best_known') && <Suspense fallback={<section className="viewer-panel panel">Preparing the 3D viewer…</section>}><ViewerPanel plan={result.development.plan} solution={result.development.solution} architecture={result.architecture} violations={result.validation.violations} warnings={result.validation.warnings} /></Suspense>}

          {result && <>
            <section className="results panel"><div className="section-top"><div><span className="kicker">04 / VERIFIED RESULT</span><h2>Numbers behind the plan</h2></div><span className={`status-pill ${result.validation.is_valid ? 'good' : 'bad'}`}>{result.status.replaceAll('_', ' ').toUpperCase()}</span></div>
              <div className="result-context">{result.status === 'best_known' ? 'Best solution found within the solver search; global optimality is not proven.' : result.validation.is_valid ? 'Independent validation passed.' : 'Independent validation found violations.'}{result.fallback_nodes > 0 && ` ${result.fallback_nodes} fixed nodes are development fallbacks.`}</div>
              <button className="download-button report-download" type="button" onClick={downloadPdfReport} disabled={reportBusy}>{reportBusy ? 'PREPARING PDF…' : comparison ? 'DOWNLOAD SELECTED ROUTE PDF ↓' : 'DOWNLOAD COMPLETE PDF REPORT ↓'}</button>
              {metrics && <><div className="metrics-grid"><Metric label="HUB COUNT" value={String(metrics.hub_count)} note={`Lower bound ${result.lower_bound_hubs ?? '—'}`} /><Metric label="ROUTE COST · J" value={number(metrics.route_cost, 3)} note="Checked objective" /><Metric label="TOTAL LENGTH · L" value={`${number(metrics.length_m, 2)} m`} /><Metric label="AREA GAP" value={`${number(metrics.area_gap_m2, 2)} m²`} /></div>
                <div className="formula"><div><span className="kicker">THE J CALCULATION</span><strong>J = L + 5X + O + 0.5B</strong></div><div className="formula-values"><span>{number(metrics.length_m, 3)}<small>L · METRES</small></span><b>+</b><span>{metrics.crossings * 5}<small>5 × {metrics.crossings} CROSSINGS</small></span><b>+</b><span>{number(metrics.overlap_m, 3)}<small>O · METRES</small></span><b>+</b><span>{number(metrics.bends * .5, 2)}<small>0.5 × {metrics.bends} BENDS</small></span><b>=</b><span className="formula-total">{number(metrics.route_cost, 3)}<small>J · TOTAL</small></span></div></div></>}
              {(result.diagnostics.length > 0 || result.validation.violations.length > 0 || result.validation.warnings.length > 0) && <details className="diagnostics"><summary>Diagnostics · {result.diagnostics.length + result.validation.violations.length + result.validation.warnings.length}</summary>{[...result.diagnostics, ...result.validation.violations, ...result.validation.warnings].map((item, index) => <p key={index}><strong>{item.code}</strong> {item.message}</p>)}</details>}
            </section>

            <section className="runtime panel"><div className="section-top"><div><span className="kicker">05 / RUNTIME</span><h2>Where the time went</h2></div><strong className="total-time">{number(result.timings.total_s, 2)} s <small>SERVER RUN</small></strong></div><div className="time-grid"><Metric label="LOAD" value={`${number(result.timings.load_s, 2)} s`} /><Metric label="NORMALIZE" value={result.timings.normalize_s === null ? 'N/A' : `${number(result.timings.normalize_s, 2)} s`} /><Metric label="SOLVE" value={`${number(result.timings.solve_s, 2)} s`} /><Metric label="VALIDATE" value={`${number(result.timings.validate_s, 2)} s`} /><Metric label="RENDER + EXPORT" value={`${number(result.timings.render_export_s, 2)} s`} /></div><p className="timing-note">Measured on the server for this run. Preview loading and browser transfer are outside the server total; cold and warm runs can differ.{comparison && ' Comparison candidate checks are included in Solve.'}</p></section>

            <section className="exports panel"><div className="section-top"><div><span className="kicker">06 / OUTPUT FILES</span><h2>Inspect the JSON</h2></div></div><div className="json-tabs" role="tablist" aria-label="JSON output"><button type="button" role="tab" aria-selected={jsonTab === 'submission'} onClick={() => setJsonTab('submission')}>Slide 8 submission · provisional</button><button type="button" role="tab" aria-selected={jsonTab === 'development'} onClick={() => setJsonTab('development')}>Development Plan + Solution</button></div><p className="export-note">{jsonTab === 'submission' ? 'Metre coordinates and slide-8 fields. The organizer has not published a complete machine-readable schema.' : 'Drawing-unit interchange validated against the shared development schema.'}</p>{jsonTab === 'submission' && !result.submission ? <div className="no-export">Submission export is available only after independent validation passes.</div> : <><pre className="json-preview">{JSON.stringify(jsonTab === 'submission' ? result.submission : result.development, null, 2)}</pre><button className="download-button" type="button" onClick={() => saveJson(`${jsonTab === 'submission' ? 'slide8_submission' : 'development'}_${selected}.json`, jsonTab === 'submission' ? result.submission : result.development)}>DOWNLOAD {jsonTab === 'submission' ? 'SUBMISSION' : 'DEVELOPMENT'} JSON ↓</button></>}</section>
          </>}
        </div>
      </div>
      <footer><span>CABLE RING STUDIO</span><span>RESPLAN / CHECKED GEOMETRY / 2026</span></footer>
    </main>
  </div>
}
