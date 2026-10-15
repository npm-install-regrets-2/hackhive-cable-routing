# Closed-Ring Cable Planning

This context describes the domain language for assigning eligible rooms in a residential floor plan to hubs and routing one legal closed cable ring per hub.

## Floor-plan model

**Plan**:
A single-floor residential layout containing an internal boundary, architectural obstacles, passages, and semantically labelled room polygons.
_Avoid_: Image, map

**Drawing unit**:
The native coordinate unit used by ResPlan geometry. It is converted per plan into metres using the plan's declared floor area.
_Avoid_: Pixel, metre

**Internal boundary**:
The region inside the building's outer walls within which every hub, node, and cable route must remain.
_Avoid_: Land, footprint

**Eligible room**:
One living, bedroom, kitchen, or storage polygon that requires exactly one fixed node and assignment to exactly one hub.
_Avoid_: Supported room, device room

**Excluded room**:
A bathroom, balcony, stair, garden, pool, parking, or land polygon that receives neither a node nor a hub.
_Avoid_: Invalid room

**Obstacle**:
A wall, window, or external area that cable geometry may not cross.

**Portal**:
A verified door or open passage through which cable may legally cross a room boundary.
_Avoid_: Adjacency, gap

**Traversability graph**:
A graph whose vertices are spaces and whose edges are verified portals. Generic ResPlan adjacency is not sufficient evidence of traversability.
_Avoid_: Room adjacency graph

## Assignment model

**Node**:
The fixed required visit point inside an eligible-room polygon, located at least 0.5 metres from walls.
_Avoid_: Device, sensor, endpoint

**Hub**:
The selected start and end point of one cable ring and the owner of an assigned room territory.
_Avoid_: Control panel, panel, depot

**Territory**:
The eligible rooms assigned to one hub, connected through verified portals and subject to that hub's capacity limits.
_Avoid_: Cluster, zone

**Assignment**:
The exclusive relationship placing one eligible room and its node in exactly one hub territory.

**Hub capacity**:
The simultaneous limit of at most 100 square metres of assigned eligible-room area and at most five assigned nodes.

## Routing model

**Ring**:
One closed, non-branching, axis-aligned cable sequence that starts at a hub, visits each node assigned to that hub exactly once, and returns to the same hub.
_Avoid_: Route, open path, Ring-Star

**Leg**:
The routed polyline between consecutive ring stops, including the hub-to-first-node and last-node-to-hub legs.

**Retrace**:
Repeated traversal of the same cable line, permitted when necessary and counted again in cable length and overlap.

**Crossing**:
A point where cable legs meet away from a node or hub, whether within one ring or between rings.

**Overlap**:
Length over which multiple cable legs occupy the same geometric line; parallel runs on distinct lines are not overlap.

**Bend**:
A direction change along a ring, including a 90-degree turn or a reversal at an ordinary vertex, node, or hub.

## Evaluation model

**Feasible solution**:
A complete set of assignments, hubs, rings, and polylines satisfying every capacity, connectivity, visit, closure, and geometry rule.

**Hub count**:
The primary optimization objective; every solution with fewer hubs ranks ahead of every solution with more hubs.

**Route cost**:
The secondary score `J = L + 5X + O + 0.5B`, evaluated only between solutions with equal hub count.

**Area gap**:
The imbalance in assigned eligible-room area between hubs, used only to break a tie in both hub count and route cost.
