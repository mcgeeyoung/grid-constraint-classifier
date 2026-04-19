from dominion_dispatch.zones import Zone, load_zones, zone_for_pnode, ZoneIndex


def test_load_zones_returns_three_zones():
    idx = load_zones()
    assert len(idx.zones) == 3
    ids = [z.id for z in idx.zones]
    assert ids == ["loudoun-corridor", "fairfax-230", "alexandria"]


def test_zone_for_pnode_maps_each_enrolled_pnode():
    idx = load_zones()
    cases = {
        "1348256193": "loudoun-corridor",
        "83734355": "loudoun-corridor",
        "34886155": "fairfax-230",
        "123900989": "fairfax-230",
        "34886435": "fairfax-230",
        "34886297": "alexandria",
    }
    for pid, zid in cases.items():
        assert zone_for_pnode(idx, pid).id == zid


def test_zone_for_pnode_returns_none_for_unknown():
    idx = load_zones()
    assert zone_for_pnode(idx, "999999") is None


def test_zone_index_has_stable_ordering():
    idx = load_zones()
    assert [z.label for z in idx.zones] == [
        "Loudoun corridor",
        "Fairfax 230 kV",
        "Alexandria",
    ]
