import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import type { Architecture, Plan, Point, Polygon, Solution } from './model'
import { buildRouteTrack, reachedStops, routePosition, type RouteSegment, type RouteTrack } from './routeMath'

const palette = ['#ed6f5c', '#6e7448', '#417c91', '#ad7b39', '#84608a', '#49715d', '#b76061', '#7261a1']
export function hubColor(index: number): string {
  if (index < palette.length) return palette[index]
  return `hsl(${Math.round((index * 137.508) % 360)} 43% 43%)`
}

type ViewerProps = {
  plan: Plan; solution: Solution; architecture: Architecture;
  selectedHubId: string; selectedNodeId: string | null; progressM: number;
  cameraCommand: { mode: 'reset' | 'top'; serial: number };
  onSelectHub: (id: string) => void; onSelectNode: (id: string) => void
}
type CablePiece = { mesh: THREE.Mesh; segment: RouteSegment; start: THREE.Vector3; direction: THREE.Vector3 }
type SceneState = {
  renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera; controls: OrbitControls;
  center: THREE.Vector3; span: number; marker: THREE.Mesh;
  roomMeshes: Map<string, THREE.Mesh>; hubMeshes: Map<string, THREE.Mesh>; nodeMeshes: Map<string, THREE.Mesh>;
  cableMeshes: Map<string, THREE.Mesh[]>; trailMeshes: Map<string, CablePiece[]>; tracks: Map<string, RouteTrack>;
  frame: number; observer: ResizeObserver
}

function polygonShape(polygon: Polygon, toPlanar: (point: Point) => THREE.Vector2): THREE.Shape {
  const shape = new THREE.Shape()
  polygon.exterior.forEach((point, index) => {
    const placed = toPlanar(point)
    if (index === 0) shape.moveTo(placed.x, placed.y)
    else shape.lineTo(placed.x, placed.y)
  })
  for (const ring of polygon.holes) {
    const hole = new THREE.Path()
    ring.forEach((point, index) => {
      const placed = toPlanar(point)
      if (index === 0) hole.moveTo(placed.x, placed.y)
      else hole.lineTo(placed.x, placed.y)
    })
    shape.holes.push(hole)
  }
  return shape
}

function makeSolid(polygon: Polygon, toPlanar: (point: Point) => THREE.Vector2, height: number, base: number, material: THREE.Material): THREE.Mesh {
  const geometry = new THREE.ExtrudeGeometry(polygonShape(polygon, toPlanar), { depth: height, bevelEnabled: false, curveSegments: 1 })
  geometry.rotateX(-Math.PI / 2)
  geometry.translate(0, base, 0)
  return new THREE.Mesh(geometry, material)
}

function makeCylinder(from: THREE.Vector3, to: THREE.Vector3, radius: number, material: THREE.Material): THREE.Mesh {
  const direction = to.clone().sub(from)
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, 1, 7), material)
  mesh.position.copy(from).addScaledVector(direction, 0.5)
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize())
  mesh.scale.y = direction.length()
  return mesh
}

function makeRoomLabel(title: string, detail: string): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 128
  const context = canvas.getContext('2d')!
  context.fillStyle = 'rgba(247,241,222,.94)'
  context.fillRect(4, 4, 504, 120)
  context.strokeStyle = '#15140f'
  context.lineWidth = 3
  context.strokeRect(4, 4, 504, 120)
  context.fillStyle = '#15140f'
  context.font = '700 42px Inter, sans-serif'
  context.fillText(title.toUpperCase(), 23, 55)
  context.fillStyle = '#665f51'
  context.font = '500 26px JetBrains Mono, monospace'
  context.fillText(detail, 23, 97)
  const material = new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false, transparent: true })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(2.25, 0.56, 1)
  sprite.renderOrder = 20
  return sprite
}

function setCamera(state: SceneState, mode: 'reset' | 'top') {
  const { camera, controls, center, span, renderer } = state
  const fitDistance = (span / Math.max(0.45, 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))))
    * Math.max(1.25, 1 / Math.min(1, renderer.domElement.clientWidth / Math.max(1, renderer.domElement.clientHeight)))
  camera.up.set(0, mode === 'top' ? 0 : 1, mode === 'top' ? -1 : 0)
  if (mode === 'top') camera.position.set(center.x, Math.max(8, fitDistance * 1.22), center.z)
  else camera.position.set(center.x + span * 0.48, Math.max(6, fitDistance * 0.75), center.z + span * 0.52)
  controls.target.copy(center)
  camera.lookAt(center)
  controls.update()
}

export default function FloorPlan3D(props: ViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null)
  const stateRef = useRef<SceneState | null>(null)
  const callbacksRef = useRef({ onSelectHub: props.onSelectHub, onSelectNode: props.onSelectNode })
  callbacksRef.current = { onSelectHub: props.onSelectHub, onSelectNode: props.onSelectNode }

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    const { plan, solution, architecture } = props
    const scale = plan.drawing_units_per_metre
    const boundary = plan.internal_boundary.exterior
    const minX = Math.min(...boundary.map(point => point.x))
    const minY = Math.min(...boundary.map(point => point.y))
    const maxX = Math.max(...boundary.map(point => point.x))
    const maxY = Math.max(...boundary.map(point => point.y))
    const width = (maxX - minX) / scale
    const depth = (maxY - minY) / scale
    const span = Math.max(width, depth, 5)
    const center = new THREE.Vector3(width / 2, 0, -depth / 2)
    const point3 = (point: Point, height = 0) => new THREE.Vector3((point.x - minX) / scale, height, -(point.y - minY) / scale)
    const planar = (point: Point) => new THREE.Vector2((point.x - minX) / scale, (point.y - minY) / scale)
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#e8e0cb')
    const camera = new THREE.PerspectiveCamera(45, 1, 0.02, Math.max(300, span * 25))
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.domElement.tabIndex = 0
    renderer.domElement.setAttribute('aria-label', '3D floor plan: drag to orbit, scroll to zoom, right-drag to pan; arrow keys pan when focused')
    mount.appendChild(renderer.domElement)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.screenSpacePanning = true
    controls.minDistance = 1.2
    controls.maxDistance = span * 8
    controls.listenToKeyEvents(renderer.domElement)
    scene.add(new THREE.AmbientLight('#ffffff', 2.2))
    const sunlight = new THREE.DirectionalLight('#fff5df', 2.6)
    sunlight.position.set(width * 0.4, span * 1.5, depth * 0.5)
    scene.add(sunlight)
    const grid = new THREE.GridHelper(span * 1.55, Math.max(10, Math.round(span * 1.5)), '#aaa28e', '#c9c0ac')
    grid.position.copy(center).setY(-0.07)
    ;(grid.material as THREE.Material).transparent = true
    ;(grid.material as THREE.Material).opacity = 0.34
    scene.add(grid)

    const assignmentByRoom = new Map(solution.assignments.map(item => [item.room_id, item.hub_id]))
    const hubIndex = new Map(solution.hubs.map((hub, index) => [hub.id, index]))
    const nodeByRoom = new Map(plan.nodes.map(node => [node.room_id, node]))
    const roomMeshes = new Map<string, THREE.Mesh>()
    const hubMeshes = new Map<string, THREE.Mesh>()
    const nodeMeshes = new Map<string, THREE.Mesh>()
    const cableMeshes = new Map<string, THREE.Mesh[]>()
    const trailMeshes = new Map<string, CablePiece[]>()
    const tracks = new Map<string, RouteTrack>()
    const pickables: THREE.Object3D[] = []

    const boundaryGeometry = new THREE.BufferGeometry().setFromPoints(boundary.map(point => point3(point, 0.035)))
    scene.add(new THREE.Line(boundaryGeometry, new THREE.LineBasicMaterial({ color: '#615d4f' })))
    for (const room of plan.rooms) {
      const owner = assignmentByRoom.get(room.id)
      const selectedColor = owner ? hubColor(hubIndex.get(owner) ?? 0) : '#a8a294'
      const floor = makeSolid(room.geometry, planar, room.eligible ? 0.085 : 0.035, -0.045,
        new THREE.MeshStandardMaterial({ color: selectedColor, transparent: true, opacity: room.eligible ? 0.72 : 0.24,
          roughness: 0.95, metalness: 0, side: THREE.DoubleSide }))
      floor.userData = { kind: 'room', id: room.id, nodeId: nodeByRoom.get(room.id)?.id }
      scene.add(floor)
      if (room.eligible) {
        roomMeshes.set(room.id, floor)
        pickables.push(floor)
        const node = nodeByRoom.get(room.id)
        if (node) {
          const label = makeRoomLabel(room.kind, room.source_label)
          label.position.copy(point3(node.point, 0.63))
          scene.add(label)
        }
      }
    }

    for (const wall of architecture.wall_solids) {
      scene.add(makeSolid(wall.geometry, planar, 1.55, 0,
        new THREE.MeshStandardMaterial({ color: '#666b61', transparent: true, opacity: 0.68,
          roughness: 0.9, side: THREE.DoubleSide, depthWrite: false })))
    }
    for (const window of architecture.window_solids) {
      scene.add(makeSolid(window.geometry, planar, 1.1, 0.48,
        new THREE.MeshPhysicalMaterial({ color: '#7dbbc5', transparent: true, opacity: 0.46,
          roughness: 0.15, metalness: 0.1, side: THREE.DoubleSide, depthWrite: false })))
    }
    for (const portal of plan.portals) {
      if (portal.segment.length < 2) continue
      const color = portal.kind === 'door' ? '#ed6f5c' : '#6e7448'
      const from = point3(portal.segment[0], 0.12)
      const to = point3(portal.segment.at(-1)!, 0.12)
      if (from.distanceTo(to) > 0.001) scene.add(makeCylinder(from, to, 0.065, new THREE.MeshBasicMaterial({ color })))
      const label = makeRoomLabel(portal.kind === 'door' ? 'DOOR' : 'OPEN', portal.id.replace('portal:', ''))
      label.scale.set(1.14, 0.28, 1)
      label.position.copy(from.clone().add(to).multiplyScalar(0.5).setY(0.42))
      scene.add(label)
    }

    for (const ring of solution.rings) {
      const track = buildRouteTrack(ring, scale)
      tracks.set(ring.hub_id, track)
      const color = hubColor(hubIndex.get(ring.hub_id) ?? 0)
      const baseMaterial = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55 })
      const trailMaterial = new THREE.MeshBasicMaterial({ color: '#fff5cf', transparent: true, opacity: 0.97 })
      const cables: THREE.Mesh[] = []
      const trails: CablePiece[] = []
      for (const segment of track.segments) {
        const from = point3(segment.from, 0.18)
        const to = point3(segment.to, 0.18)
        const base = makeCylinder(from, to, 0.028, baseMaterial)
        scene.add(base)
        cables.push(base)
        const trail = makeCylinder(from, to, 0.052, trailMaterial)
        trail.visible = false
        scene.add(trail)
        trails.push({ mesh: trail, segment, start: from, direction: to.clone().sub(from).normalize() })
        if (to.distanceTo(from) > 0.42) {
          const direction = to.clone().sub(from).normalize()
          const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.068, 0.17, 7), new THREE.MeshBasicMaterial({ color }))
          arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction)
          arrow.position.copy(from).lerp(to, 0.6).setY(0.245)
          scene.add(arrow)
          cables.push(arrow)
        }
      }
      cableMeshes.set(ring.hub_id, cables)
      trailMeshes.set(ring.hub_id, trails)
    }

    for (const hub of solution.hubs) {
      const color = hubColor(hubIndex.get(hub.id) ?? 0)
      const marker = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.22, 0.3, 10),
        new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.28, roughness: 0.4 }))
      marker.position.copy(point3(hub.point, 0.25))
      marker.userData = { kind: 'hub', id: hub.id }
      scene.add(marker)
      hubMeshes.set(hub.id, marker)
      pickables.push(marker)
      const halo = new THREE.Mesh(new THREE.TorusGeometry(0.31, 0.035, 6, 28), new THREE.MeshBasicMaterial({ color }))
      halo.rotation.x = -Math.PI / 2
      halo.position.copy(point3(hub.point, 0.09))
      scene.add(halo)
    }
    for (const node of plan.nodes) {
      const owner = solution.assignments.find(item => item.node_id === node.id)?.hub_id
      const color = hubColor(hubIndex.get(owner ?? '') ?? 0)
      const marker = new THREE.Mesh(new THREE.SphereGeometry(0.145, 14, 10),
        new THREE.MeshStandardMaterial({ color: '#fff9e7', emissive: color, emissiveIntensity: 0.5, roughness: 0.35 }))
      marker.position.copy(point3(node.point, 0.22))
      marker.userData = { kind: 'node', id: node.id }
      scene.add(marker)
      nodeMeshes.set(node.id, marker)
      pickables.push(marker)
    }
    const marker = new THREE.Mesh(new THREE.SphereGeometry(0.135, 16, 12),
      new THREE.MeshStandardMaterial({ color: '#fff9e7', emissive: '#ed6f5c', emissiveIntensity: 1.8 }))
    marker.visible = false
    scene.add(marker)

    const observer = new ResizeObserver(() => {
      const widthPx = Math.max(mount.clientWidth, 1)
      const heightPx = Math.max(mount.clientHeight, 1)
      camera.aspect = widthPx / heightPx
      camera.updateProjectionMatrix()
      renderer.setSize(widthPx, heightPx, false)
    })
    observer.observe(mount)
    const state: SceneState = { renderer, scene, camera, controls, center, span, marker,
      roomMeshes, hubMeshes, nodeMeshes, cableMeshes, trailMeshes, tracks, frame: 0, observer }
    stateRef.current = state
    setCamera(state, 'reset')
    const animate = () => {
      state.frame = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    let down = { x: 0, y: 0 }
    const pointerDown = (event: PointerEvent) => { down = { x: event.clientX, y: event.clientY } }
    const pointerUp = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) return
      const bounds = renderer.domElement.getBoundingClientRect()
      pointer.set(((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((event.clientY - bounds.top) / bounds.height) * 2 + 1)
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects(pickables, false)[0]?.object
      if (hit?.userData.kind === 'hub') callbacksRef.current.onSelectHub(hit.userData.id as string)
      if (hit?.userData.kind === 'node') callbacksRef.current.onSelectNode(hit.userData.id as string)
      if (hit?.userData.kind === 'room' && hit.userData.nodeId) callbacksRef.current.onSelectNode(hit.userData.nodeId as string)
    }
    renderer.domElement.addEventListener('pointerdown', pointerDown)
    renderer.domElement.addEventListener('pointerup', pointerUp)

    return () => {
      renderer.domElement.removeEventListener('pointerdown', pointerDown)
      renderer.domElement.removeEventListener('pointerup', pointerUp)
      observer.disconnect()
      cancelAnimationFrame(state.frame)
      controls.dispose()
      scene.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Sprite) {
          object.geometry?.dispose()
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          materials.forEach(material => {
            if (material instanceof THREE.SpriteMaterial) material.map?.dispose()
            material.dispose()
          })
        }
      })
      renderer.dispose()
      mount.removeChild(renderer.domElement)
      stateRef.current = null
    }
  }, [props.plan, props.solution, props.architecture])

  useEffect(() => {
    const state = stateRef.current
    if (!state) return
    const ownerByRoom = new Map(props.solution.assignments.map(item => [item.room_id, item.hub_id]))
    for (const [roomId, mesh] of state.roomMeshes) {
      const selected = ownerByRoom.get(roomId) === props.selectedHubId
      ;(mesh.material as THREE.MeshStandardMaterial).opacity = selected ? 0.88 : 0.38
    }
    for (const [hubId, mesh] of state.hubMeshes) mesh.scale.setScalar(hubId === props.selectedHubId ? 1.35 : 1)
    for (const [nodeId, mesh] of state.nodeMeshes) mesh.scale.setScalar(nodeId === props.selectedNodeId ? 1.6 : 1)
    for (const [hubId, cables] of state.cableMeshes) {
      for (const mesh of cables) mesh.visible = hubId === props.selectedHubId
    }
  }, [props.solution, props.selectedHubId, props.selectedNodeId])

  useEffect(() => {
    const state = stateRef.current
    if (!state) return
    const track = state.tracks.get(props.selectedHubId)
    for (const [hubId, pieces] of state.trailMeshes) {
      for (const piece of pieces) {
        const coveredM = hubId === props.selectedHubId
          ? Math.max(0, Math.min(piece.segment.endM, props.progressM) - piece.segment.startM) : 0
        piece.mesh.visible = coveredM > 1e-5
        if (coveredM > 1e-5) {
          const coveredWorld = coveredM
          piece.mesh.scale.y = coveredWorld
          piece.mesh.position.copy(piece.start).addScaledVector(piece.direction, coveredWorld / 2)
        }
      }
    }
    if (track) {
      const currentPosition = routePosition(track, props.progressM)
      const current = currentPosition.point
      const boundary = props.plan.internal_boundary.exterior
      const minX = Math.min(...boundary.map(point => point.x))
      const minY = Math.min(...boundary.map(point => point.y))
      state.marker.position.set((current.x - minX) / props.plan.drawing_units_per_metre, 0.27,
        -(current.y - minY) / props.plan.drawing_units_per_metre)
      state.marker.visible = true
      const returning = props.progressM > 0 && currentPosition.segment.destinationId === props.selectedHubId
      ;(state.marker.material as THREE.MeshStandardMaterial).emissive.set(returning ? '#6e7448' : '#ed6f5c')
      const visited = new Set(reachedStops(track, props.progressM))
      for (const [nodeId, mesh] of state.nodeMeshes) {
        const selected = nodeId === props.selectedNodeId
        mesh.scale.setScalar(selected ? 1.65 : visited.has(nodeId) ? 1.35 : 1)
        ;(mesh.material as THREE.MeshStandardMaterial).emissiveIntensity = visited.has(nodeId) ? 1.45 : 0.5
      }
    } else state.marker.visible = false
  }, [props.plan, props.selectedHubId, props.selectedNodeId, props.progressM])

  useEffect(() => {
    if (stateRef.current) setCamera(stateRef.current, props.cameraCommand.mode)
  }, [props.cameraCommand])

  return <div className="viewer-canvas" ref={mountRef} role="img" aria-label="Interactive 3D floor-plan viewer; drag to orbit, scroll to zoom, right-drag to pan" />
}
