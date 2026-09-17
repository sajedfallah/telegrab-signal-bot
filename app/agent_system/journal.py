from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .contracts import AgentAssessment, MarketSnapshot, RiskDecision, SupervisorDecision


@dataclass(frozen=True)
class JournalRecord:
    snapshot: MarketSnapshot
    assessments: tuple[AgentAssessment, ...]
    supervisor: SupervisorDecision
    risk: RiskDecision | None = None

    def as_dict(self) -> dict:
        return {"recorded_at":datetime.now(timezone.utc).isoformat(),"snapshot":self.snapshot.model_dump(mode="json"),"assessments":[a.model_dump(mode="json") for a in self.assessments],"supervisor":self.supervisor.model_dump(mode="json"),"risk":self.risk.model_dump(mode="json") if self.risk else None}


def append_jsonl(path: str | Path, record: JournalRecord) -> None:
    """Append one replayable shadow decision. Caller controls the isolated path."""
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("a",encoding="utf-8") as handle:
        handle.write(json.dumps(record.as_dict(),ensure_ascii=False,separators=(",",":"))+"\n")
