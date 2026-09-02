from app.autotrade import service


def row(destination):
    return {"destination": destination}


def test_free_and_both_are_visible_to_eligible_clients():
    for dest in ("FREE", "BOTH"):
        assert service.signal_visible_to_auth(row(dest), {"vip_access": False})
        assert service.signal_visible_to_auth(row(dest), {"vip_access": True})


def test_vip_is_hidden_from_non_vip_client_and_visible_to_vip_client():
    assert not service.signal_visible_to_auth(row("VIP"), {"vip_access": False})
    assert service.signal_visible_to_auth(row("VIP"), {"vip_access": True})
