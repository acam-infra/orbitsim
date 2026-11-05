"""Tests for the β/umbra analytic model against known LEO numbers."""

import math

import pytest

from orbitsim import orbit_sun


def test_sso_inclination_650km():
    assert orbit_sun.sso_inclination_deg(650e3) == pytest.approx(98.0, abs=0.1)


def test_sso_inclination_1400km():
    assert orbit_sun.sso_inclination_deg(1400e3) == pytest.approx(101.4, abs=0.1)


def test_eclipse_threshold_650km():
    assert orbit_sun.eclipse_threshold_deg(650e3) == pytest.approx(65.16, abs=0.05)


def test_eclipse_threshold_470km():
    assert orbit_sun.eclipse_threshold_deg(470e3) == pytest.approx(68.63, abs=0.05)


def test_dawn_dusk_beta_equinox_is_high():
    inc = orbit_sun.sso_inclination_deg(650e3)
    beta = orbit_sun.beta_angle_rad(inc, 0.0, 6.0)
    assert abs(math.degrees(beta)) == pytest.approx(82.0, abs=0.5)


def test_dawn_dusk_eclipse_free_at_equinox():
    inc = orbit_sun.sso_inclination_deg(650e3)
    beta = orbit_sun.beta_angle_rad(inc, 0.0, 6.0)
    assert orbit_sun.eclipse_fraction(650e3, beta) == 0.0


def test_dawn_dusk_solstice_still_eclipsed():
    inc = orbit_sun.sso_inclination_deg(650e3)
    beta = orbit_sun.beta_angle_rad(inc, -orbit_sun.OBLIQUITY_DEG, 6.0)
    emin = orbit_sun.eclipse_minutes(650e3, beta)
    assert emin == pytest.approx(19.7, abs=1.0)


def test_imaging_sso_eclipsed_all_year():
    inc = orbit_sun.sso_inclination_deg(650e3)
    for dec in (0.0, orbit_sun.OBLIQUITY_DEG, -orbit_sun.OBLIQUITY_DEG):
        beta = orbit_sun.beta_angle_rad(inc, dec, 10.5)
        assert orbit_sun.eclipse_minutes(650e3, beta) == pytest.approx(34.2, abs=1.0)


def test_dawn_dusk_clear_altitude():
    h = orbit_sun.dawn_dusk_clear_altitude_m()
    assert h == pytest.approx(1391e3, abs=5e3)


def test_daily_umbra_650km_dawn_dusk_counts():
    rows = orbit_sun.daily_umbra_table(650e3, 6.0)
    s = orbit_sun.summarize_daily_umbra(rows, 650e3, 6.0)
    assert s["days_in_umbra"] == pytest.approx(90, abs=2)
    assert s["days_sunlit"] == pytest.approx(275, abs=2)
    assert s["annual_sunlight_frac"] == pytest.approx(0.9605, abs=0.001)
