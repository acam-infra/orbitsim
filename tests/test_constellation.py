"""Tests for constellation declarations and feature analysis."""

import pytest

from orbitsim.constellation import from_sso, from_tle, from_walker, load_constellation
from orbitsim import visibility


def test_sso_expansion():
    c = from_sso(650e3, 6.0)
    assert c.kind == "sso"
    assert c.n_orbits == 1
    assert c.n_sats == 1
    assert c.orbits[0].inclination_deg == pytest.approx(98.0, abs=0.1)


def test_walker_expansion():
    c = from_walker(72, 22, 550e3, 53.0)
    assert c.kind == "walker"
    assert c.n_orbits == 72
    assert c.n_sats == 72 * 22
    assert c.orbits[0].raan_deg == 0.0
    assert c.orbits[1].raan_deg == pytest.approx(5.0)


def test_walker_rejects_bad_counts():
    with pytest.raises(ValueError):
        from_walker(0, 22, 550e3, 53.0)


def test_tle_expansion_starlink_like():
    tles = [{
        "name": "STARLINK-1007",
        "l1": "1 44713U 19074A   20001.00000000  .00000000  00000-0  00000-0 0  9999",
        "l2": "2 44713  53.0000  20.0000 0001000   0.0000  90.0000 15.05000000    10",
    }]
    c = from_tle(tles)
    assert c.kind == "tle"
    assert c.n_orbits == 1
    assert c.orbits[0].inclination_deg == pytest.approx(53.0)
    assert c.orbits[0].altitude_m == pytest.approx(550e3, abs=20e3)


def test_load_constellation_sso():
    c = load_constellation({"kind": "sso", "altitude_m": 650000, "ltan_h": 6.0})
    assert c.kind == "sso"


def test_load_constellation_bad_kind():
    with pytest.raises(ValueError):
        load_constellation({"kind": "nope"})


def test_access_fraction_positive_and_bounded():
    frac = visibility.access_fraction_equatorial(650e3, 10.0)
    assert 0.0 < frac < 0.5


def test_site_poleward_of_inclination_no_access():
    assert visibility.daily_access_minutes(650e3, 10.0, 89.0, 53.0) == 0.0


def test_sun_transit_noon_sso_more_prone_than_dawn_dusk():
    noon = visibility.sun_outage_season_days(12.0, 0.5)
    dawn = visibility.sun_outage_season_days(6.0, 0.5)
    assert noon > dawn
