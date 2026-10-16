"""Thread-safe, transient progress snapshots for a streamed plan run."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any


STAGES = (
    ("load_plan", "Load plan"),
    ("normalize_plan", "Normalize local plan"),
    ("prepare_geometry", "Prepare routing geometry"),
    ("search", "Search connected territories and closed rings"),
    ("validate", "Independently check solution"),
    ("render_export", "Render and export results"),
)

_ADDITIVE_COUNTERS = {
    "hub_count_attempts",
    "partition_patterns_examined",
    "connected_partitions_found",
    "candidate_combinations_evaluated",
    "ring_route_attempts",
    "astar_states_expanded",
}


class RunProgress:
    """Publishes throttled complete snapshots, never one event per inner-loop step."""

    def __init__(self, update_interval_s: float = 0.2):
        self._lock = threading.Lock()
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._started = time.perf_counter()
        self._update_interval_s = update_interval_s
        self._last_publish = 0.0
        self._stage_status = {stage_id: "upcoming" for stage_id, _ in STAGES}
        self._active_stage: str | None = None
        self._failed_stage: str | None = None
        self._counters: dict[str, int] = {}
        self._terminal = False

    @property
    def active_stage(self) -> str | None:
        with self._lock:
            return self._active_stage

    def start(self, stage_id: str) -> None:
        with self._lock:
            self._start_locked(stage_id)
            self._publish_locked(force=True)

    def complete(self, stage_id: str) -> None:
        with self._lock:
            if self._stage_status.get(stage_id) == "active":
                self._stage_status[stage_id] = "completed"
            if self._active_stage == stage_id:
                self._active_stage = None
            self._publish_locked(force=True)

    def skip(self, stage_id: str) -> None:
        with self._lock:
            self._stage_status[stage_id] = "skipped"
            self._publish_locked(force=True)

    def skip_if_upcoming(self, stage_id: str) -> None:
        with self._lock:
            if self._stage_status.get(stage_id) == "upcoming":
                self._stage_status[stage_id] = "skipped"
                self._publish_locked(force=True)

    def solver_update(self, stage_id: str, updates: dict[str, int]) -> None:
        with self._lock:
            stage_changed = self._active_stage != stage_id
            if stage_changed:
                self._start_locked(stage_id)
            for name, value in updates.items():
                if name in _ADDITIVE_COUNTERS:
                    self._counters[name] = self._counters.get(name, 0) + value
                else:
                    self._counters[name] = value
            self._publish_locked(force=stage_changed)

    def finish(self, result: dict[str, Any]) -> None:
        with self._lock:
            self._terminal = True
            state = self._state_locked()
            self._events.put({"type": "complete", "state": state, "result": result})

    def fail(self, stage_id: str, error: dict[str, Any]) -> None:
        with self._lock:
            if stage_id in self._stage_status:
                self._stage_status[stage_id] = "failed"
            self._active_stage = stage_id
            self._failed_stage = stage_id
            self._terminal = True
            state = self._state_locked()
            self._events.put({
                "type": "error", "state": state, "stage": stage_id, "error": error,
            })

    def next_event(self, timeout_s: float = 0.25) -> dict[str, Any] | None:
        try:
            return self._events.get(timeout=timeout_s)
        except queue.Empty:
            return None

    @property
    def terminal(self) -> bool:
        with self._lock:
            return self._terminal

    def _start_locked(self, stage_id: str) -> None:
        if stage_id not in self._stage_status:
            raise ValueError(f"Unknown run stage: {stage_id}")
        if self._active_stage and self._active_stage != stage_id:
            self._stage_status[self._active_stage] = "completed"
        self._active_stage = stage_id
        self._stage_status[stage_id] = "active"

    def _state_locked(self) -> dict[str, Any]:
        return {
            "stages": [
                {"id": stage_id, "label": label, "status": self._stage_status[stage_id]}
                for stage_id, label in STAGES
            ],
            "active_stage": self._active_stage,
            "failed_stage": self._failed_stage,
            "counters": dict(self._counters),
            "elapsed_s": round(time.perf_counter() - self._started, 2),
        }

    def _publish_locked(self, *, force: bool) -> None:
        now = time.perf_counter()
        if not force and now - self._last_publish < self._update_interval_s:
            return
        self._last_publish = now
        self._events.put({"type": "progress", **self._state_locked()})
