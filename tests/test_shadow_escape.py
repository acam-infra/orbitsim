"""Closed-form shadow arc must agree with the instantaneous 3-D umbra test."""

import math

from orbitsim import fleet_energy as fe
from orbitsim import orbit_sun as osun
from orbitsim import shadow_escape as se
from orbitsim.constellation import from_walker, expand_satellites
from orbitsim.isl import build_edges


def _walker(planes=6, spp=8, alt=550e3, f=1):
    const = from_walker(planes, spp, alt, osun.sso_inclination_deg(alt), f)
    return const, expand_satellites(const)


def test_state_matches_lit_mask():
    _, sats = _walker()
    for doy in (0.0, 81.0, 172.0, 300.0):
        for k in range(40):
            t = 137.0 * k
            mask = fe.lit_mask(sats, doy, t)
            st = se.fleet_states(sats, doy, t)
            bad = [i for i, (m, s) in enumerate(zip(mask, st)) if m != s["lit"]]
            # only grazing-edge disagreements allowed (float noise at the arc boundary)
            assert len(bad) == 0, (doy, t, bad)


def test_half_width_matches_eclipse_fraction():
    alt = 650e3
    inc = osun.sso_inclination_deg(alt)
    beta, _, half = se.shadow_arc(0.0, inc, alt, 81.0)
    assert abs(half / 180.0 - osun.eclipse_fraction(alt, math.radians(beta))) < 1e-9


def test_dark_left_counts_down():
    _, sats = _walker(1, 1)
    s = sats[0]
    st0 = se.sat_state(s, 81.0, 0.0)
    # walk until shadowed, then 60 s later dark_left must drop by 60 s
    t = 0.0
    while se.sat_state(s, 81.0, t)["lit"]:
        t += 10.0
    a = se.sat_state(s, 81.0, t)
    b = se.sat_state(s, 81.0, t + 60.0)
    assert not b["lit"] and abs((a["dark_left_s"] - b["dark_left_s"]) - 60.0) < 1e-6
    assert st0["dark_total_s"] > 0


def test_escape_hops_and_capacity():
    const, sats = _walker()
    adj = se.adjacency(sats, build_edges(const, {"kind": "positive_grid"}))
    lit = fe.lit_mask(sats, 81.0, 0.0)
    hops = se.escape_hops(adj, lit)
    assert all((h == 0) == ok for h, ok in zip(hops, lit))
    cap = se.capacitated_offload(adj, lit, k=1)
    unc = [h for h, ok in zip(hops, lit) if not ok]
    # capacity can only lengthen paths
    assert sorted(c for c in cap if c is not None)[0] >= min(unc)
    assert sum(c for c in cap if c is not None) >= sum(unc)


def test_kv_transfer():
    # 8k tokens × 128 KiB = 1 GiB ≈ 0.86 s at 10 Gbps, pipelined
    t = se.kv_transfer_s(8192, 131072, 10.0, 3, per_hop_stall_s=0.05)
    assert abs(t - (8192 * 131072 * 8 / 1e10 + 0.15)) < 1e-9
    assert se.kv_transfer_s(8192, 131072, 10.0, 3, store_and_forward=True) > t
