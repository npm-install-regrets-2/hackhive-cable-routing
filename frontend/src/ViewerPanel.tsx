import { useEffect, useMemo, useRef, useState } from 'react'
import FloorPlan3D, { hubColor } from './FloorPlan3D'
import type { Architecture, Plan, Solution } from './model'
import { buildRouteTrack, reachedStops, routePosition } from './routeMath'

type Diagnostic = { code: string; message: string; entity_ids?: string[] }
type Props = {
  plan: Plan; solution: Solution; architecture: Architecture;
  violations: Diagnostic[]; warnings: Diagnostic[]
}
type Playback = 'ready' | 'playing' | 'paused' | 'complete'
const format = (value: number, digits = 2) => value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })

export default function ViewerPanel({ plan, solution, architecture, violations, warnings }: Props) {
  const [selectedHubId, setSelectedHubId] = useState(solution.hubs[0]?.id ?? '')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [playback, setPlayback] = useState<Playback>('ready')
  const [progressM, setProgressM] = useState(0)
  const [animationElapsed, setAnimationElapsed] = useState(0)
  const [speed, setSpeed] = useState(1.2)
  const [cameraCommand, setCameraCommand] = useState<{ mode: 'reset' | 'top'; serial: number }>({ mode: 'reset', serial: 0 })
  const lastFrame = useRef<number | null>(null)

  const routeData = useMemo(() => {
    try {
      return { tracks: new Map(solution.rings.map(ring => [ring.hub_id, buildRouteTrack(ring, plan.drawing_units_per_metre)])), error: null }
    } catch (error) {
      return { tracks: null, error: error instanceof Error ? error.message : 'Cable geometry could not be visualized.' }
    }
  }, [plan, solution])
  const track = routeData.tracks?.get(selectedHubId)
  const ring = solution.rings.find(item => item.hub_id === selectedHubId)
  const hub = solution.hubs.find(item => item.id === selectedHubId)
  const assignments = solution.assignments.filter(item => item.hub_id === selectedHubId)
  const node = plan.nodes.find(item => item.id === selectedNodeId)
  const selectedAssignment = solution.assignments.find(item => item.node_id === selectedNodeId)
  const assignedArea = assignments.reduce((sum, item) => sum + (plan.rooms.find(room => room.id === item.room_id)?.area_m2 ?? 0), 0)
  const percent = track && track.lengthM > 0 ? Math.min(100, progressM / track.lengthM * 100) : 0
  const destination = track && playback === 'complete' ? selectedHubId : track ? routePosition(track, progressM).segment.destinationId === selectedHubId && progressM > 0 ? `RETURN TO ${selectedHubId}` : routePosition(track, progressM).segment.destinationId : '—'
  const reached = track ? reachedStops(track, progressM) : []
  const relevantIds = new Set([selectedHubId, ...assignments.flatMap(item => [item.node_id, item.room_id])])
  const issues = [...violations, ...warnings].filter(item => item.entity_ids?.some(id => relevantIds.has(id)))
  const boundary = plan.internal_boundary.exterior
  const minX = Math.min(...boundary.map(point => point.x))
  const minY = Math.min(...boundary.map(point => point.y))

  useEffect(() => {
    if (playback !== 'playing' || !track) return
    let frame = 0
    lastFrame.current = null
    const tick = (timestamp: number) => {
      if (lastFrame.current !== null) {
        const delta = Math.min((timestamp - lastFrame.current) / 1000, 0.1)
        setAnimationElapsed(previous => previous + delta)
        setProgressM(previous => Math.min(track.lengthM, previous + delta * speed))
      }
      lastFrame.current = timestamp
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playback, speed, track])

  useEffect(() => {
    if (track && progressM >= track.lengthM && playback === 'playing') setPlayback('complete')
  }, [progressM, track, playback])

  function selectHub(id: string) {
    setSelectedHubId(id)
    setSelectedNodeId(null)
    setProgressM(0)
    setAnimationElapsed(0)
    setPlayback('ready')
  }

  function selectNode(id: string) {
    const owner = solution.assignments.find(item => item.node_id === id)?.hub_id
    if (owner && owner !== selectedHubId) selectHub(owner)
    setSelectedNodeId(id)
  }

  function restart() {
    setProgressM(0)
    setAnimationElapsed(0)
    setPlayback('playing')
  }

  if (!routeData.tracks || !hub || !ring || !track) {
    return <section className="viewer-panel panel"><div className="section-top"><div><span className="kicker">03 / SPATIAL VIEW</span><h2>Technical 3D viewer</h2></div></div>
      <div className="no-export">{routeData.error ?? 'No checked closed cable ring is available for 3D playback.'}</div></section>
  }

  return <section className="viewer-panel panel" aria-label="Interactive 3D floor-plan visualization">
    <div className="section-top"><div><span className="kicker">03 / SPATIAL VIEW</span><h2>Walk the checked route</h2></div><span className="status-pill good">VALIDATED GEOMETRY</span></div>
    <p className="viewer-intro">Actual room footprints, portal positions and cable vertices from the checked solution. Wall height and opening width are schematic because the source is a 2D plan.</p>
    <div className="viewer-layout">
      <div className="viewer-stage">
        <div className="viewer-toolbar"><span>ORBIT · ZOOM · PAN</span><div><button type="button" onClick={() => setCameraCommand(value => ({ mode: 'top', serial: value.serial + 1 }))}>TOP VIEW</button><button type="button" onClick={() => setCameraCommand(value => ({ mode: 'reset', serial: value.serial + 1 }))}>RESET CAMERA</button></div></div>
        <FloorPlan3D plan={plan} solution={solution} architecture={architecture} selectedHubId={selectedHubId} selectedNodeId={selectedNodeId} progressM={progressM} cameraCommand={cameraCommand} onSelectHub={selectHub} onSelectNode={selectNode} />
        <div className="viewer-legend"><span><i className="legend-wall" /> WALL</span><span><i className="legend-window" /> WINDOW</span><span><i className="legend-door" /> DOOR</span><span><i className="legend-opening" /> OPEN PASSAGE</span><span><i className="legend-3d-node" /> NODE</span><span><i className="legend-3d-cable" /> CABLE</span></div>
      </div>
      <div className="viewer-controls">
        <div className="control-heading"><span className="kicker">CLOSED LOOPS</span><strong>{solution.hubs.length} hubs · {plan.nodes.length} nodes</strong></div>
        <div className="hub-list" aria-label="Select a hub loop">{solution.hubs.map((item, index) => {
          const length = routeData.tracks?.get(item.id)?.lengthM ?? 0
          const count = solution.assignments.filter(assignment => assignment.hub_id === item.id).length
          return <button key={item.id} type="button" className={selectedHubId === item.id ? 'selected' : ''} aria-pressed={selectedHubId === item.id} onClick={() => selectHub(item.id)}><i style={{ background: hubColor(index) }} /><span><strong>{item.id}</strong><small>{count} nodes · {format(length)} m loop</small></span><b>↗</b></button>
        })}</div>
        <div className="loop-detail"><div className="loop-detail-head"><strong>{hub.id} · CANONICAL LOOP</strong><span>{format(track.lengthM)} m</span></div>
          <p className="sequence">{ring.stop_ids.map((id, index) => <span key={`${id}-${index}`} className={reached.includes(id) ? 'reached' : ''}>{id}{index < ring.stop_ids.length - 1 && <b>→</b>}</span>)}</p>
          <div className="capacity-grid"><span>ROOM AREA <strong>{format(assignedArea)} / {format(plan.rules.max_area_m2_per_hub, 0)} m²</strong></span><span>NODE CAPACITY <strong>{assignments.length} / {plan.rules.max_nodes_per_hub}</strong></span></div>
          <div className="hub-validation">{issues.length ? issues.map((issue, index) => <p key={index}><strong>{issue.code}</strong> {issue.message}</p>) : <p>Independent validation: no issues for this hub or its assigned nodes.</p>}</div>
        </div>
        <div className="playback-controls"><div className="control-heading"><span className="kicker">CABLE TRAVERSAL</span><strong>{playback === 'complete' ? 'LOOP COMPLETE · RETURNED TO HUB' : playback.toUpperCase()}</strong></div>
          <div className="play-buttons"><button type="button" onClick={() => playback === 'complete' ? restart() : setPlayback('playing')} disabled={playback === 'playing'}>{playback === 'playing' ? 'PLAYING' : playback === 'complete' ? 'PLAY AGAIN' : progressM > 0 ? 'RESUME' : 'PLAY'}</button><button type="button" onClick={() => setPlayback('paused')} disabled={playback !== 'playing'}>PAUSE</button><button type="button" onClick={restart}>RESTART</button></div>
          <div className="progress-track" role="progressbar" aria-label="Cable traversal progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{ width: `${percent}%` }} /></div>
          <div className="playback-stats"><span>PROGRESS <strong>{format(percent, 0)}%</strong></span><span>ELAPSED <strong>{format(animationElapsed, 1)} s</strong></span><span>DESTINATION <strong>{destination}</strong></span><span>EST. DURATION <strong>{format(track.lengthM / speed, 1)} s</strong></span><span>REMAINING <strong>{format(Math.max(0, track.lengthM - progressM) / speed, 1)} s</strong></span></div>
          <label className="speed-control" htmlFor="simulation-speed">SIMULATED SPEED <strong>{format(speed, 2)} m/s</strong></label><input id="simulation-speed" type="range" min="0.25" max="5" step="0.25" value={speed} onChange={event => setSpeed(Number(event.target.value))} />
          <p className="simulation-note">Simulation time is for viewing only. The solver does not supply cable velocity; changing speed leaves route geometry and JSON unchanged.</p>
        </div>
        <div className="node-selector"><span className="kicker">ASSIGNED NODES</span><div>{plan.nodes.map(item => {
          const owner = solution.assignments.find(assignment => assignment.node_id === item.id)?.hub_id
          return <button key={item.id} type="button" aria-pressed={selectedNodeId === item.id} onClick={() => selectNode(item.id)}><span>{item.id}</span><small>{owner}</small></button>
        })}</div></div>
        <div className="node-info" aria-live="polite">{node && selectedAssignment ? <><strong>{node.id}</strong><dl><dt>ROOM</dt><dd>{node.room_id}</dd><dt>ASSIGNED HUB</dt><dd>{selectedAssignment.hub_id}</dd><dt>RING POSITION</dt><dd>{(solution.rings.find(item => item.hub_id === selectedAssignment.hub_id)?.stop_ids.indexOf(node.id) ?? -1)} of {assignments.length}</dd><dt>SOURCE POSITION</dt><dd>({format(node.point.x)}, {format(node.point.y)}) drawing units</dd><dt>LOCAL POSITION</dt><dd>({format((node.point.x - minX) / plan.drawing_units_per_metre)}, {format((node.point.y - minY) / plan.drawing_units_per_metre)}) m</dd></dl></> : <p>Select a node to inspect its room, hub, ring position and coordinates. Playback remains hub-rooted.</p>}</div>
      </div>
    </div>
  </section>
}
