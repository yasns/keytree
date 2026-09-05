from app.db.models import Node
from app.routers.subsystems import _build_tree


def _node(id: int, subsystem_id: int, name: str) -> Node:
    return Node(id=id, subsystem_id=subsystem_id, name=name, category=None)


def test_build_tree_roots_aliases_and_subsystem_boundary():
    # Subsystem 1: conf -> tcds -> [alias]x2 -> tcds subsystem's conf.
    # rs is a separate root reaching the same foreign node under two aliases.
    conf = _node(10, 1, "conf")
    rs = _node(11, 1, "rs")
    tcds = _node(12, 1, "tcds")
    foreign_conf = _node(20, 2, "conf")
    foreign_hw = _node(21, 2, "hw")
    foreign_rs = _node(31, 3, "rs")

    edges = [
        (10, "tcds", tcds),
        (12, "ugt", foreign_conf),
        (12, "ugmt", foreign_conf),
        (10, "ugt_conf", foreign_conf),
        (11, "ugt_rs", foreign_rs),
        (11, "spare_ugt_rs", foreign_rs),
        # Not reachable from subsystem 1's roots. Proves recursion stops at the subsystem boundary
        (20, "hw", foreign_hw),
    ]

    roots = _build_tree(1, [conf, rs, tcds], edges)

    assert [r.alias for r in roots] == ["conf", "rs"]

    conf_out = next(r for r in roots if r.alias == "conf")
    assert [c.alias for c in conf_out.children] == ["tcds", "ugt_conf"]

    tcds_out = conf_out.children[0]
    assert tcds_out.name == "tcds"
    # Same foreign node reached under two aliases from one parent.
    assert [c.alias for c in tcds_out.children] == ["ugmt", "ugt"]
    assert all(c.id == 20 and c.subsystem_id == 2 and c.children == [] for c in tcds_out.children)

    ugt_conf_out = conf_out.children[1]
    assert ugt_conf_out.id == 20
    assert ugt_conf_out.subsystem_id == 2
    # Boundary crossed. No recursion even though children_by_parent has an entry for id 20.
    assert ugt_conf_out.children == []

    rs_out = next(r for r in roots if r.alias == "rs")
    assert [c.alias for c in rs_out.children] == ["spare_ugt_rs", "ugt_rs"]
    assert all(c.id == 31 and c.subsystem_id == 3 and c.children == [] for c in rs_out.children)


def test_build_tree_stops_on_cycle():
    # a -> b -> c -> b, all in the same subsystem.
    a = _node(1, 1, "a")
    b = _node(2, 1, "b")
    c = _node(3, 1, "c")

    edges = [
        (1, "b", b),
        (2, "c", c),
        (3, "b", b),
    ]

    roots = _build_tree(1, [a, b, c], edges)

    assert [r.alias for r in roots] == ["a"]
    b_out = roots[0].children[0]
    assert b_out.alias == "b"
    c_out = b_out.children[0]
    assert c_out.alias == "c"
    # b reappears as an ancestor: recursion stops, it renders as a leaf.
    repeated_b = c_out.children[0]
    assert repeated_b.alias == "b" and repeated_b.id == 2
    assert repeated_b.children == []
