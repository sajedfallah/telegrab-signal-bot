import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.agent_system.channel_collector import collect_once, last_message_id


class FakeClient:
    def __init__(self,fail=False):
        self.fail=fail
    async def get_entity(self, username):
        if self.fail: raise ValueError("unavailable")
        return username
    async def iter_messages(self, entity, *, limit, min_id, reverse):
        for i in (1,2,3):
            if i>min_id:
                yield SimpleNamespace(id=i,date=datetime(2026,10,14,tzinfo=timezone.utc),
                                      message=f"XAUUSD BUY 4142 SL 4139 TP1 4148")


def test_collector_ingests_once_and_ignores_seen_messages(tmp_path):
    db=str(tmp_path/"audit.db")
    first=asyncio.run(collect_once(FakeClient(),db,channels=("ssfgold",),limit=10))
    assert first["messages_imported"]==3
    assert last_message_id(db,"ssfgold")==3
    second=asyncio.run(collect_once(FakeClient(),db,channels=("ssfgold",),limit=10))
    assert second["messages_imported"]==0


def test_channel_failures_isolated(tmp_path):
    db=str(tmp_path/"audit.db")
    result=asyncio.run(collect_once(FakeClient(fail=True),db,channels=("ssfgold",),limit=10))
    assert result["channels_failed"]==1
    assert result["messages_imported"]==0
    assert result["errors"]["ssfgold"]=="ValueError"
