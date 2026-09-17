from __future__ import annotations

from datetime import timezone

from ..contracts import AgentAssessment, Direction, MarketSnapshot


def assess_macro(snapshot: MarketSnapshot) -> AgentAssessment:
    """Read structured macro/event evidence already attached to the snapshot.

    V1 deliberately does not fetch external data or invent macro direction.
    Provider adapters will later normalize DXY/yields/calendar into this context.
    """
    evidence: list[str] = []
    missing: list[str] = []
    directions: list[Direction] = []
    for event in snapshot.scheduled_events:
        name = str(event.get("name") or event.get("title") or "scheduled event")
        impact = str(event.get("impact") or "unknown").upper()
        evidence.append(f"Scheduled macro event: {name} [{impact}]")
    for item in snapshot.news_context:
        if str(item.get("kind") or "").lower() != "macro":
            continue
        text = str(item.get("summary") or item.get("title") or "macro context")
        evidence.append(text)
        raw = str(item.get("direction") or "NEUTRAL").upper()
        if raw in Direction.__members__:
            directions.append(Direction[raw])
    directional = [x for x in directions if x != Direction.NEUTRAL]
    direction = directional[0] if directional and all(x == directional[0] for x in directional) else Direction.NEUTRAL
    if not evidence:
        missing.append("structured_macro_context")
        evidence.append("No structured macro context attached; macro agent remains neutral")
    return AgentAssessment(
        agent_id="nexus-macro-v1", symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id,
        direction=direction, confidence=None, evidence=tuple(evidence),
        invalidations=("refresh macro context before candidate approval",) if missing else (),
        missing_data=tuple(missing), created_at=snapshot.as_of.astimezone(timezone.utc),
    )
