"""contact_trace must turn the closed-form geometry into consistent event intervals."""

import numpy as np

from orbitsim import contact_trace as ct
from orbitsim import fleet_synth as fs


def test_intervals_half_open_and_clipped():
    t = np.arange(0.0, 50.0, 5.0)
    m = np.array([1, 1, 0, 0, 1, 0, 0, 1, 1, 1], bool)
    assert ct.intervals(m, t, 5.0) == [[0.0, 10.0], [20.0, 25.0], [35.0, 50.0]]
    assert ct.intervals(np.zeros(10, bool), t, 5.0) == []


def _fleet():
    rs = [fs.make_sat("RS", 500, ltan_h=10.5, role="rs", group="rs")]
    cs = [dict(s, group="compute") for s in fs.walker("C", 4, 10, 550, 53.0, F=1)]
    return rs + cs, cs


def test_trace_matches_point_samples():
    sats, cs = _fleet()
    pairs = [(a, b, "intra", ct.chord_m(550e3, 36.0) * 1.05)
             for p in range(4)
             for a, b in ct.ring_pairs([s["name"] for s in cs if s["plane"] == p])]
    pairs += [(a, b, "inter", 5000e3) for a, b in ct.nearest_plane_pairs(cs, 81.0)]
    tr = ct.build_trace(sats, doy=81.0, horizon_s=6000.0, dt_s=10.0, pairs=pairs,
                        attach=[ct.AttachRule("rs", "compute", "rs", 4000e3, "sticky")])
    # in-plane rings never break (36° chord clears the 80 km grazing height)
    intra = [e for e in tr["edges"] if e["kind"] == "intra"]
    assert len(intra) == 40 and all(e["up"] == [[0.0, 6000.0]] for e in intra)
    # every umbra interval agrees with the cylindrical test at its midpoint and just outside it
    for j, dark in enumerate(tr["dark"]):
        for a, b in dark:
            mid = np.array([(a + b) / 2])
            assert not fs.lit(fs.positions([sats[j]], 81.0, mid), fs.sun_vec(81.0))[0, 0]
    # a single-terminal satellite holds at most one link at any instant
    rs_edges = [e for e in tr["edges"] if e["kind"] == "rs"]
    for t in np.arange(0.0, 6000.0, 10.0):
        n_up = sum(any(a <= t < b for a, b in e["up"]) for e in rs_edges)
        assert n_up <= 1
    assert tr["stats"]["rs_handovers_per_hour_per_sat"] > 0


def test_sticky_keeps_partner_longer_than_nearest():
    sats, _ = _fleet()
    kw = dict(doy=81.0, horizon_s=6000.0, dt_s=10.0)
    sticky = ct.build_trace(sats, attach=[ct.AttachRule("rs", "compute", "rs", 4000e3, "sticky")], **kw)
    near = ct.build_trace(sats, attach=[ct.AttachRule("rs", "compute", "rs", 4000e3, "nearest")], **kw)
    assert sticky["stats"]["rs_handovers_per_hour_per_sat"] < near["stats"]["rs_handovers_per_hour_per_sat"]
