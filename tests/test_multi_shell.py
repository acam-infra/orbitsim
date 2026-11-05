"""Tests for multi-shell constellations: shells: [...] declaration, per-shell
expansion, and intra/inter-shell ISL topology."""

import pytest

from orbitsim.constellation import (
    load_constellation,
    expand_satellites,
    from_shells,
    from_walker,
)
from orbitsim import isl


# Starlink's actual five shells (altitude/inclination/planes/sats_per_plane),
# scaled down to keep the test fast — geometry is what matters, not the count.
def starlink_like_cfg():
    return {
        "shells": [
            {"name": "sh1", "kind": "walker", "planes": 5, "sats_per_plane": 4,
             "altitude_m": 550e3, "inclination_deg": 53.0},
            {"name": "sh2", "kind": "walker", "planes": 5, "sats_per_plane": 4,
             "altitude_m": 540e3, "inclination_deg": 53.2},
            {"name": "sh3", "kind": "walker", "planes": 3, "sats_per_plane": 4,
             "altitude_m": 570e3, "inclination_deg": 70.0},
            {"name": "sh4", "kind": "walker", "planes": 3, "sats_per_plane": 6,
             "altitude_m": 560e3, "inclination_deg": 97.6},
            {"name": "sh5", "kind": "walker", "planes": 3, "sats_per_plane": 6,
             "altitude_m": 560e3, "inclination_deg": 97.6,
             # Same geometry as sh4. A RAAN-only shift is not enough: (Ω,u)
             # and (Ω+180°,u+180°) are the same point on a circular orbit, so
             # we also shift the in-plane phase by half the satellite spacing
             # (360°/6 / 2 = 30°) to keep t=0 positions distinct.
             "raan_offset_deg": 60.0, "phase_offset_deg": 30.0},
        ]
    }


def test_shells_declaration_parses():
    const = load_constellation(starlink_like_cfg())
    assert const.n_shells == 5
    assert [sh.name for sh in const.shells] == ["sh1", "sh2", "sh3", "sh4", "sh5"]
    assert const.n_sats == 5*4 + 5*4 + 3*4 + 3*6 + 3*6  # = 88


def test_shell_names_must_be_unique():
    cfg = starlink_like_cfg()
    cfg["shells"][1]["name"] = "sh1"
    with pytest.raises(ValueError, match="unique"):
        load_constellation(cfg)


def test_shells_and_kind_are_mutually_exclusive():
    cfg = starlink_like_cfg()
    cfg["kind"] = "walker"
    with pytest.raises(ValueError):
        load_constellation(cfg)


def test_expanded_satellites_carry_shell_prefix_and_field():
    const = load_constellation(starlink_like_cfg())
    sats = expand_satellites(const)
    assert len(sats) == 88
    # every name is prefixed with its shell name
    assert all(s["name"].startswith(s["shell"] + "/") for s in sats)
    # shells partition the satellite set
    by_shell: dict[str, int] = {}
    for s in sats:
        by_shell[s["shell"]] = by_shell.get(s["shell"], 0) + 1
    assert by_shell == {"sh1": 20, "sh2": 20, "sh3": 12, "sh4": 18, "sh5": 18}


def test_single_mode_is_per_shell_only():
    """A flat links: declaration gives intra-shell edges only, even with
    multiple shells."""
    const = load_constellation(starlink_like_cfg())
    edges = isl.build_edges(const, {"kind": "positive_grid"})
    assert edges
    assert all(e["intra_shell"] for e in edges)
    s = isl.summarize_edges(const, edges)
    assert s["inter_shell_edges"] == 0
    # every walker shell contributes planes·spp intra-plane + planes·spp inter-plane
    expected_intra_plane = 5*4 + 5*4 + 3*4 + 3*6 + 3*6
    assert s["intra_plane_edges"] == expected_intra_plane
    assert s["intra_shell_edges"] == 2 * expected_intra_plane


def test_paired_declaration_adds_inter_shell_edges():
    """intra_shell: +Grid, inter_shell: n_nearest(n=2) — the Starlink pattern."""
    const = load_constellation(starlink_like_cfg())
    edges = isl.build_edges(const, {
        "intra_shell": {"kind": "positive_grid"},
        "inter_shell": {"kind": "n_nearest", "n": 2},
    })
    s = isl.summarize_edges(const, edges)
    assert s["inter_shell_edges"] > 0
    assert s["intra_shell_edges"] > 0
    # every inter-shell edge connects two different shells
    inter = [e for e in edges if not e["intra_shell"]]
    assert inter
    for e in inter:
        shell_a, shell_b = e["a"].split("/")[0], e["b"].split("/")[0]
        assert shell_a != shell_b


def test_inter_shell_respects_max_range():
    """A tiny max_range_km on inter_shell kills all cross-shell edges but
    leaves intra-shell edges intact."""
    const = load_constellation(starlink_like_cfg())
    edges = isl.build_edges(const, {
        "intra_shell": {"kind": "positive_grid"},
        "inter_shell": {"kind": "n_nearest", "n": 2, "max_range_km": 1.0},
    })
    s = isl.summarize_edges(const, edges)
    assert s["inter_shell_edges"] == 0
    assert s["intra_shell_edges"] > 0


def test_inter_shell_rejects_topological_modes():
    """positive_grid / ring have no meaning across shells."""
    const = load_constellation(starlink_like_cfg())
    for bad in ("positive_grid", "ring"):
        with pytest.raises(ValueError, match="inter_shell.kind"):
            isl.build_edges(const, {"inter_shell": {"kind": bad}})


def test_positive_grid_rejects_non_walker_shell():
    """A mixed-shell constellation (one sso + one walker) cannot use +Grid
    as its intra-shell mode — the sso shell has no planes."""
    cfg = {
        "shells": [
            {"name": "walk", "kind": "walker", "planes": 5, "sats_per_plane": 4,
             "altitude_m": 550e3, "inclination_deg": 53.0},
            {"name": "sso1", "kind": "sso", "altitude_m": 650e3, "ltan_h": 6.0},
        ]
    }
    const = load_constellation(cfg)
    with pytest.raises(ValueError, match="walker"):
        isl.build_edges(const, {"intra_shell": {"kind": "positive_grid"}})


def test_mixed_shell_n_nearest_works():
    """n_nearest is shell-agnostic — it works on any mix of shell kinds."""
    cfg = {
        "shells": [
            {"name": "walk", "kind": "walker", "planes": 5, "sats_per_plane": 4,
             "altitude_m": 550e3, "inclination_deg": 53.0},
            {"name": "sso1", "kind": "sso", "altitude_m": 650e3, "ltan_h": 6.0},
        ]
    }
    const = load_constellation(cfg)
    edges = isl.build_edges(const, {"kind": "n_nearest", "n": 3})
    s = isl.summarize_edges(const, edges)
    assert s["n_shells"] == 2
    assert s["n_sats"] == 21
    assert s["n_edges"] > 0


def test_backward_compat_single_walker_shell():
    """A flat walker declaration still parses and behaves as one shell."""
    const = load_constellation({
        "kind": "walker", "planes": 5, "sats_per_plane": 4,
        "altitude_m": 550e3, "inclination_deg": 53.0,
    })
    assert const.n_shells == 1
    assert const.shells[0].name == "sh0"
    assert const.n_sats == 20
    sats = expand_satellites(const)
    assert all(s["shell"] == "sh0" for s in sats)
    assert {s["name"] for s in sats} == {f"sh0/p{p}s{k}" for p in range(5) for k in range(4)}


def test_backward_compat_from_walker_helper():
    const = from_walker(5, 4, 550e3, 53.0)
    assert const.n_shells == 1
    edges = isl.build_edges(const, {"kind": "positive_grid"})
    assert len(edges) == 40  # 20 intra-plane + 20 inter-plane
