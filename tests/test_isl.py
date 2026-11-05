"""Tests for ISL connectivity modes on small Walker shells."""

import pytest

from orbitsim.constellation import from_walker, expand_satellites
from orbitsim import isl


def shell(planes=5, spp=4, alt=550e3, inc=53.0):
    # 5 planes × 4 sats avoids the exact t=0 antipodal degeneracy of even shells
    return from_walker(planes, spp, alt, inc)


def test_expand_satellites_walker_counts():
    sats = expand_satellites(shell())
    assert len(sats) == 20
    assert {s["plane"] for s in sats} == {0, 1, 2, 3, 4}
    assert all(0.0 <= s["phase_deg"] < 360.0 for s in sats)


def test_ring_edges_count_and_intra():
    const = shell()
    edges = isl.build_edges(const, {"kind": "ring"})
    # 5 planes × 4 sats → 4 edges per plane ring
    assert len(edges) == 20
    assert all(e["intra_plane"] for e in edges)


def test_ring_degree_two():
    const = shell()
    edges = isl.build_edges(const, {"kind": "ring"})
    s = isl.summarize_edges(const, edges)
    assert s["degree_min"] == 2
    assert s["degree_max"] == 2
    assert s["inter_plane_edges"] == 0


def test_bent_pipe_no_edges():
    const = shell()
    assert isl.build_edges(const, {"kind": "bent_pipe"}) == []


def test_positive_grid_degree_four():
    const = shell()
    edges = isl.build_edges(const, {"kind": "positive_grid"})
    s = isl.summarize_edges(const, edges)
    assert s["degree_min"] == 4
    assert s["degree_max"] == 4


def test_positive_grid_has_two_intra_and_two_inter_plane_edges_per_sat():
    const = shell()
    edges = isl.build_edges(const, {"kind": "positive_grid"})
    # Starlink pattern: every satellite has exactly 2 intra-plane (fore/aft
    # along the orbit) and 2 inter-plane (left/right adjacent plane) edges.
    per_sat_intra: dict[str, int] = {}
    per_sat_inter: dict[str, int] = {}
    for e in edges:
        for sat in (e["a"], e["b"]):
            if e["intra_plane"]:
                per_sat_intra[sat] = per_sat_intra.get(sat, 0) + 1
            else:
                per_sat_inter[sat] = per_sat_inter.get(sat, 0) + 1
    assert set(per_sat_intra.values()) == {2}
    assert set(per_sat_inter.values()) == {2}
    s = isl.summarize_edges(const, edges)
    # 5 planes × 4 sats: 5·4 intra + 5·4 inter = 40 edges (each edge counted once)
    assert s["intra_plane_edges"] == 20
    assert s["inter_plane_edges"] == 20


def test_n_nearest_degree_bounded():
    const = shell()
    edges = isl.build_edges(const, {"kind": "n_nearest", "n": 4})
    s = isl.summarize_edges(const, edges)
    assert s["degree_max"] <= 4
    assert s["degree_mean"] > 0.0


def test_max_range_kills_all_edges():
    const = shell()
    edges = isl.build_edges(const, {"kind": "n_nearest", "n": 4, "max_range_km": 1.0})
    assert edges == []


def test_edge_distances_positive_and_symmetric():
    const = shell(planes=3, spp=3)
    edges = isl.build_edges(const, {"kind": "n_nearest", "n": 2})
    assert all(e["distance_km"] > 0.0 for e in edges)
    assert len({(e["a"], e["b"]) for e in edges}) == len(edges)  # no duplicate undirected edges


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        isl.build_edges(shell(), {"kind": "nope"})
