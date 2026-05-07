from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from ...utils.enums import CallFinalState


@dataclass
class ToolMetric:
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    handoff_calls: int = 0
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict:
        avg_ms = self.total_duration_ms / self.total_calls if self.total_calls else 0.0
        return {
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "handoff_calls": self.handoff_calls,
            "avg_duration_ms": round(avg_ms, 2),
        }


class InMemoryMetrics:
    def __init__(self):
        self._lock = Lock()
        self._by_tool: dict[str, ToolMetric] = defaultdict(ToolMetric)
        self._counters: dict[str, int] = defaultdict(int)

    def record(self, tool_name: str, ok: bool, final_state: CallFinalState, duration_ms: float) -> None:
        with self._lock:
            metric = self._by_tool[tool_name]
            metric.total_calls += 1
            metric.total_duration_ms += max(0.0, duration_ms)
            if ok:
                metric.success_calls += 1
            else:
                metric.failed_calls += 1
            if final_state == CallFinalState.TRANSFERIDA_HUMANO:
                metric.handoff_calls += 1

    def snapshot(self) -> dict:
        with self._lock:
            per_tool = {tool_name: metric.to_dict() for tool_name, metric in self._by_tool.items()}
            counters = dict(self._counters)
        totals = {
            "total_calls": sum(item["total_calls"] for item in per_tool.values()),
            "success_calls": sum(item["success_calls"] for item in per_tool.values()),
            "failed_calls": sum(item["failed_calls"] for item in per_tool.values()),
            "handoff_calls": sum(item["handoff_calls"] for item in per_tool.values()),
        }
        return {"totals": totals, "per_tool": per_tool, "ops": counters}

    def increment_counter(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def reset(self) -> None:
        with self._lock:
            self._by_tool.clear()
            self._counters.clear()


metrics_store = InMemoryMetrics()
