import { lazy, Suspense, useEffect, useState } from 'react'
import type { Architecture, Development } from './model'

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
type RunResult = {
  plan_id: number; source: string; status: string; lower_bound_hubs: number | null;
  validation: Validation; diagnostics: Diagnostic[]; timings: Timings;
  input_image: string; output_image: string | null; development: Development;
  architecture: Architecture;
  submission: unknown | null; fallback_nodes: number
}
type ApiError = { code: string; message: string; diagnostics?: Diagnostic[] }

const presets = [14433, 13033, 14926]
const ViewerPanel = lazy(() => import('./ViewerPanel'))
const number = (value: number, digits = 2) => value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })

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

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [selected, setSelected] = useState<number>(14433)
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [started, setStarted] = useState(0)
  const [jsonTab, setJsonTab] = useState<'submission' | 'development'>('submission')

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      api<Catalog>(`/api/catalog?source=local&q=${encodeURIComponent(query)}&limit=60`)
        .then(setCatalog)
        .catch((failure: unknown) => setError(asApiError(failure)))
    }, 180)
    return () => window.clearTimeout(timeout)
  }, [query])

  useEffect(() => {
    if (selected === 14433 && query === '' && catalog?.presets.find(item => item.id === 14433)?.available === false && catalog.results.length) {
      setSelected(catalog.results[0].id)
    }
  }, [catalog, query, selected])

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
  }

  async function run() {
    setBusy(true)
    setResult(null)
    setError(null)
    const start = Date.now()
    setStarted(start)
    setElapsed(0)
    try {
      const data = await api<RunResult>('/api/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'local', plan_id: selected }),
      })
      setResult(data)
      setJsonTab('submission')
    } catch (failure) {
      setError(asApiError(failure))
    } finally {
      setElapsed((Date.now() - start) / 1000)
      setBusy(false)
    }
  }

  const metrics = result?.validation.recomputed_metrics
  const previewUrl = `/api/plans/${selected}/preview?source=local`
  const candidates = (catalog?.results ?? []).filter(item => query.length > 0 || !presets.includes(item.id))

  return <div className="page-shell">
    <header className="topbar">
      <div className="brand"><Mark /><div><strong>Cable Ring <em>Studio</em></strong><span>PLAN · SOLVE · VERIFY</span></div></div>
      <div className="topbar-right"><span className="live-dot" /> LOCAL DATASET <span className="edition">/ 2026</span></div>
    </header>

    <main className="main-wrap">
      <section className="intro">
        <div className="eyebrow"><span>01 / FLOOR PLAN LAB</span><span>HUB PLACEMENT + CLOSED RINGS</span></div>
        <div className="intro-grid"><div><h1>From floor plan<br />to <i>feasible rings.</i></h1><p>Choose a plan, run the solver, and inspect every hub, cable leg, and checked metric in one place.</p></div><div className="intro-aside"><span className="aside-line" /><p>One input.<br />One checked solution.<br />Every number accounted for.</p><span className="aside-index">FIG. 01 / CABLE ROUTING</span></div></div>
      </section>

      <div className="work-grid">
        <aside className="picker panel">
          <div className="panel-head"><span>01</span><div><h2>Plan picker</h2><p>Local dataset · IDs from split.json</p></div></div>
          <div className="field-note">Runs use the trusted ResPlan archive on this localhost server. Every plan is normalized and solved when selected.</div>
          <div className="section-label"><span>FEATURED PLANS</span><span>03</span></div>
          <div className="preset-list">{presets.map((id, index) => <button type="button" className={`preset ${selected === id ? 'selected' : ''}`} onClick={() => choose(id)} disabled={busy || !catalog?.presets.find(p => p.id === id)?.available} key={id} aria-pressed={selected === id}>
            <span className="preset-thumb"><img src={`/api/plans/${id}/preview?source=local`} alt={`Floor plan ${id} thumbnail`} loading="lazy" /></span>
            <span className="preset-copy"><small>FEATURED 0{index + 1}</small><strong>{id}</strong><span>{catalog?.presets.find(p => p.id === id)?.split ?? 'Dataset'}</span></span>
            <span className="preset-arrow">↗</span>
          </button>)}</div>
          <label className="search-label" htmlFor="plan-search">FIND A PLAN ID</label>
          <div className="search-wrap"><span aria-hidden="true">⌕</span><input id="plan-search" type="search" inputMode="numeric" placeholder="Search split.json IDs" value={query} onChange={event => setQuery(event.target.value)} disabled={busy} /></div>
          <div className="search-results" aria-label="Matching plan IDs">{candidates.slice(0, 24).map(item => <button key={item.id} type="button" onClick={() => choose(item.id)} aria-pressed={selected === item.id}>{item.id}<span>{item.split}</span></button>)}{query && catalog?.total === 0 && <p>No matching ID in split.json.</p>}{catalog && catalog.total > 24 && <small>{catalog.total} matches · showing the first 24. Keep typing to narrow.</small>}</div>
          <button className="run-button" type="button" onClick={run} disabled={busy || !catalog?.sources.includes('local')}>{busy ? <><span className="spinner" /> RUNNING · {number(elapsed, 1)} S</> : <>RUN PLAN {selected} <span>↗</span></>}</button>
          <p className="picker-foot">Fixed nodes may be development fallbacks. The checker verifies every result independently.</p>
        </aside>

        <div className="content-stack">
          <section className="comparison panel">
            <div className="section-top"><div><span className="kicker">02 / VISUAL COMPARISON</span><h2>Floor-plan workspace</h2></div><span className="plan-badge">PLAN #{selected}</span></div>
            {error && <div className="alert" role="alert"><strong>{error.code.replaceAll('_', ' ')}</strong><p>{error.message}</p>{elapsed > 0 && <p>Elapsed before failure: {number(elapsed, 1)} s</p>}{error.diagnostics?.map((item, index) => <p key={index}>{item.code}: {item.message}</p>)}</div>}
            <div className="image-grid">
              <div className="image-card"><div className="image-title"><span className="image-number">A</span><div><strong>Input floor plan</strong><small>ROOMS · NODES · PORTALS</small></div></div><div className="image-frame"><img key={selected} src={result?.input_image ?? previewUrl} alt={`Input floor plan ${selected}`} /></div></div>
              <div className="image-card"><div className="image-title"><span className="image-number coral">B</span><div><strong>Checked output</strong><small>HUBS · TERRITORIES · RINGS</small></div></div><div className={`image-frame ${!result?.output_image ? 'empty-frame' : ''}`}>{result?.output_image ? <img src={result.output_image} alt={`Checked solution for plan ${selected}`} /> : <div><span>◇</span><strong>{busy ? 'Solving floor plan…' : 'Output awaits a run'}</strong><small>{busy ? `${number(elapsed, 1)} seconds elapsed` : 'Select a plan and press Run plan'}</small></div>}</div></div>
            </div>
            <div className="comparison-foot"><span><i className="legend-node" /> FIXED NODE</span><span><i className="legend-hub" /> HUB</span><span><i className="legend-route" /> CABLE RING</span><span className="comparison-status">{result ? (result.validation.is_valid ? '✓ INDEPENDENT CHECK PASSED' : '✕ CHECK FAILED') : 'READY TO RUN'}</span></div>
          </section>

          {result?.validation.is_valid && (result.status === 'feasible' || result.status === 'best_known') && <Suspense fallback={<section className="viewer-panel panel">Preparing the 3D viewer…</section>}><ViewerPanel plan={result.development.plan} solution={result.development.solution} architecture={result.architecture} violations={result.validation.violations} warnings={result.validation.warnings} /></Suspense>}

          {result && <>
            <section className="results panel"><div className="section-top"><div><span className="kicker">04 / VERIFIED RESULT</span><h2>Numbers behind the plan</h2></div><span className={`status-pill ${result.validation.is_valid ? 'good' : 'bad'}`}>{result.status.replaceAll('_', ' ').toUpperCase()}</span></div>
              <div className="result-context">{result.status === 'best_known' ? 'Best solution found within the solver search; global optimality is not proven.' : result.validation.is_valid ? 'Independent validation passed.' : 'Independent validation found violations.'}{result.fallback_nodes > 0 && ` ${result.fallback_nodes} fixed nodes are development fallbacks.`}</div>
              {metrics && <><div className="metrics-grid"><Metric label="HUB COUNT" value={String(metrics.hub_count)} note={`Lower bound ${result.lower_bound_hubs ?? '—'}`} /><Metric label="ROUTE COST · J" value={number(metrics.route_cost, 3)} note="Checked objective" /><Metric label="TOTAL LENGTH · L" value={`${number(metrics.length_m, 2)} m`} /><Metric label="AREA GAP" value={`${number(metrics.area_gap_m2, 2)} m²`} /></div>
                <div className="formula"><div><span className="kicker">THE J CALCULATION</span><strong>J = L + 5X + O + 0.5B</strong></div><div className="formula-values"><span>{number(metrics.length_m, 3)}<small>L · METRES</small></span><b>+</b><span>{metrics.crossings * 5}<small>5 × {metrics.crossings} CROSSINGS</small></span><b>+</b><span>{number(metrics.overlap_m, 3)}<small>O · METRES</small></span><b>+</b><span>{number(metrics.bends * .5, 2)}<small>0.5 × {metrics.bends} BENDS</small></span><b>=</b><span className="formula-total">{number(metrics.route_cost, 3)}<small>J · TOTAL</small></span></div></div></>}
              {(result.diagnostics.length > 0 || result.validation.violations.length > 0 || result.validation.warnings.length > 0) && <details className="diagnostics"><summary>Diagnostics · {result.diagnostics.length + result.validation.violations.length + result.validation.warnings.length}</summary>{[...result.diagnostics, ...result.validation.violations, ...result.validation.warnings].map((item, index) => <p key={index}><strong>{item.code}</strong> {item.message}</p>)}</details>}
            </section>

            <section className="runtime panel"><div className="section-top"><div><span className="kicker">05 / RUNTIME</span><h2>Where the time went</h2></div><strong className="total-time">{number(result.timings.total_s, 2)} s <small>SERVER RUN</small></strong></div><div className="time-grid"><Metric label="LOAD" value={`${number(result.timings.load_s, 2)} s`} /><Metric label="NORMALIZE" value={result.timings.normalize_s === null ? 'N/A' : `${number(result.timings.normalize_s, 2)} s`} /><Metric label="SOLVE" value={`${number(result.timings.solve_s, 2)} s`} /><Metric label="VALIDATE" value={`${number(result.timings.validate_s, 2)} s`} /><Metric label="RENDER + EXPORT" value={`${number(result.timings.render_export_s, 2)} s`} /></div><p className="timing-note">Measured on the server for this run. Preview loading and browser transfer are outside the server total; cold and warm runs can differ.</p></section>

            <section className="exports panel"><div className="section-top"><div><span className="kicker">06 / OUTPUT FILES</span><h2>Inspect the JSON</h2></div></div><div className="json-tabs" role="tablist" aria-label="JSON output"><button type="button" role="tab" aria-selected={jsonTab === 'submission'} onClick={() => setJsonTab('submission')}>Slide 8 submission · provisional</button><button type="button" role="tab" aria-selected={jsonTab === 'development'} onClick={() => setJsonTab('development')}>Development Plan + Solution</button></div><p className="export-note">{jsonTab === 'submission' ? 'Metre coordinates and slide-8 fields. The organizer has not published a complete machine-readable schema.' : 'Drawing-unit interchange validated against the shared development schema.'}</p>{jsonTab === 'submission' && !result.submission ? <div className="no-export">Submission export is available only after independent validation passes.</div> : <><pre className="json-preview">{JSON.stringify(jsonTab === 'submission' ? result.submission : result.development, null, 2)}</pre><button className="download-button" type="button" onClick={() => saveJson(`${jsonTab === 'submission' ? 'slide8_submission' : 'development'}_${selected}.json`, jsonTab === 'submission' ? result.submission : result.development)}>DOWNLOAD {jsonTab === 'submission' ? 'SUBMISSION' : 'DEVELOPMENT'} JSON ↓</button></>}</section>
          </>}
        </div>
      </div>
      <footer><span>CABLE RING STUDIO</span><span>RESPLAN / CHECKED GEOMETRY / 2026</span></footer>
    </main>
  </div>
}
