from __future__ import annotations

from datetime import timezone

from ..contracts import AgentAssessment, Direction, MarketSnapshot


def assess_news(snapshot: MarketSnapshot) -> AgentAssessment:
    evidence: list[str] = []
    directions: list[Direction] = []
    for item in snapshot.news_context:
        if str(item.get("kind") or "news").lower() == "macro":
            continue
        title = str(item.get("title") or item.get("summary") or "market news")
        impact = str(item.get("impact") or item.get("impact_level") or "unknown").upper()
        evidence.append(f"{title} [{impact}]")
        raw = str(item.get("direction") or "NEUTRAL").upper()
        if raw in Direction.__members__:
            directions.append(Direction[raw])
    directional = [x for x in directions if x != Direction.NEUTRAL]
    direction = directional[0] if directional and all(x == directional[0] for x in directional) else Direction.NEUTRAL
    missing = () if evidence else ("structured_news_context",)
    if not evidence:
        evidence.append("No structured news context attached; news agent remains neutral")
    return AgentAssessment(
        agent_id="nexus-news-v1", symbol=snapshot.symbol, snapshot_id=snapshot.snapshot_id,
        direction=direction, confidence=None, evidence=tuple(evidence), invalidations=(),
        missing_data=missing, created_at=snapshot.as_of.astimezone(timezone.utc),
    )
