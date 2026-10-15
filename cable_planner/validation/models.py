"""Validation models and diagnostic representations."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cable_planner.metrics.models import RecomputedMetrics


@dataclass
class Diagnostic:
    """Diagnostic entry for hard-rule violations or advisories."""
    code: str
    message: str
    entity_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "entity_ids": list(self.entity_ids),
        }


@dataclass
class ValidationReport:
    """Complete independent validation report for a plan and solution."""
    plan_id: str
    is_valid: bool
    violations: List[Diagnostic] = field(default_factory=list)
    warnings: List[Diagnostic] = field(default_factory=list)
    recomputed_metrics: Optional[RecomputedMetrics] = None
    optimizer_metrics_match: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "is_valid": self.is_valid,
            "violation_count": len(self.violations),
            "warning_count": len(self.warnings),
            "violations": [v.to_dict() for v in self.violations],
            "warnings": [w.to_dict() for w in self.warnings],
            "recomputed_metrics": self.recomputed_metrics.to_dict() if self.recomputed_metrics else None,
            "optimizer_metrics_match": self.optimizer_metrics_match,
        }

    def summary(self) -> str:
        lines = [
            f"Validation Report for Plan: {self.plan_id}",
            f"Overall Status: {'PASSED' if self.is_valid else 'FAILED'}",
            f"Violations: {len(self.violations)}",
            f"Warnings: {len(self.warnings)}"
        ]
        if self.violations:
            lines.append("Violations:")
            for v in self.violations:
                entity_str = f" [entities: {', '.join(v.entity_ids)}]" if v.entity_ids else ""
                lines.append(f"  - [{v.code}] {v.message}{entity_str}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                entity_str = f" [entities: {', '.join(w.entity_ids)}]" if w.entity_ids else ""
                lines.append(f"  - [{w.code}] {w.message}{entity_str}")
        if self.recomputed_metrics:
            m = self.recomputed_metrics
            lines.append("Recomputed Metrics:")
            lines.append(f"  - Hub count H: {m.hub_count}")
            lines.append(f"  - Total length L: {m.length_m:.4f} m")
            lines.append(f"  - Crossings X: {m.crossings}")
            lines.append(f"  - Collinear overlap O: {m.overlap_m:.4f} m")
            lines.append(f"  - Bends B: {m.bends}")
            lines.append(f"  - Objective J: {m.route_cost:.4f}")
            lines.append(f"  - Area gap: {m.area_gap_m2:.4f} m2")
        return "\n".join(lines)
