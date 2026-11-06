"""Rotating-Earth synthesis must respect LTAN and agree with fleet_energy."""

import numpy as np

from orbitsim import fleet_energy as fe
from orbitsim import fleet_synth as fs


def test_ascending_node_local_time_equals_ltan():
    for ltan in (6.0, 10.5, 13.5):
        sat = fs.make_sat("s", 500, ltan_h=ltan)
        t = np.arange(0.0, 86400.0, 5.0)
        lat, lon = fs.subpoint(fs.positions([sat], 81.0, t), 81.0, t)
        lat = lat[:, 0]
        asc = np.where((lat[:-1] < 0) & (lat[1:] >= 0))[0]
        lst = (t[asc] / 3600.0 + lon[asc, 0] / 15.0) % 24.0
        # J2 drift over one day and the 5 s grid keep this within ~0.1 h
        assert np.all(np.abs(((lst - ltan) + 12) % 24 - 12) < 0.15), (ltan, lst)


def test_lit_matches_fleet_energy():
    sat = fs.make_sat("s", 550, inc_deg=53.0, raan_deg=30.0, u0_deg=10.0)
    t = np.arange(0.0, 6000.0, 60.0)
    a = fs.lit(fs.positions([sat], 172.0, t), fs.sun_vec(172.0))[:, 0]
    rec = [{"raan_deg": 30.0, "inclination_deg": 53.0, "phase_deg": 10.0, "altitude_m": 550e3}]
    # fleet_energy has no J2 drift: over 100 min the 53° plane drifts ~0.35°, allow a couple of edge slots
    b = np.array([fe.lit_mask(rec, 172.0, x)[0] for x in t])
    assert np.sum(a != b) <= 2


def test_elevation_overhead_and_los():
    t = np.array([0.0])
    site = fs.site_eci(0.0, 0.0, 81.0, t)
    above = site * (1 + 500e3 / fs.RE_M)
    assert abs(fs.elevation_deg(above[:, None, :], site)[0, 0] - 90.0) < 1e-6
    opposite = -above
    _, clear = fs.los_range(above[:, None, :], opposite[:, None, :])
    assert not clear[0, 0, 0]
