"""Fleet illumination must reduce to the single-orbit closed form.

The instant-by-instant cylindrical-umbra test in ``fleet_energy`` is the same
model ``orbit_sun.eclipse_fraction`` integrates analytically — so the fraction
of a day one satellite spends shadowed must match the closed form, and a
dawn-dusk plane must stay lit at the equinoxes.
"""

import math

from orbitsim import fleet_energy as fe
from orbitsim import orbit_sun as osun
from orbitsim.constellation import from_walker, expand_satellites


def _one_sat(alt_m, inc_deg, raan_deg, phase_deg=0.0):
    return [{"name": "s", "shell": "sh", "plane": 0, "index_in_plane": 0,
             "altitude_m": alt_m, "inclination_deg": inc_deg,
             "raan_deg": raan_deg, "phase_deg": phase_deg}]


def test_shadowed_fraction_matches_closed_form():
    # A noon-ish plane at the equinox: β ≈ 0, deepest eclipse.
    alt = 650e3
    inc = osun.sso_inclination_deg(alt)
    doy = 81.0  # equinox, sun RA = 0
    # Plane whose ascending node points at the Sun (Δ = 0 ⇒ LTAN 12).
    sats = _one_sat(alt, inc, raan_deg=0.0)
    n = 2000
    shadowed = sum(1 for k in range(n)
                   if not fe.lit_mask(sats, doy, 86400.0 * k / n)[0])
    frac_sim = shadowed / n
    beta = osun.beta_angle_rad(inc, 0.0, 12.0)
    frac_closed = osun.eclipse_fraction(alt, beta)
    assert abs(frac_sim - frac_closed) < 0.01  # one day ≈ 14.7 orbits, slot noise small


def test_dawn_dusk_plane_lit_at_equinox():
    # Dawn-dusk plane (LTAN 6 ⇒ Δ = −90° ⇒ Ω = α_sun − 90°) at the equinox:
    # |β| = 90° − (i − 90°) ≈ 82° at 650 km, far above the 65° threshold.
    alt = 650e3
    inc = osun.sso_inclination_deg(alt)
    sats = _one_sat(alt, inc, raan_deg=-90.0)
    assert all(fe.lit_mask(sats, 81.0, 86400.0 * k / 96)[0] for k in range(96))


def test_instantaneous_matches_beta_geometry():
    # Spot-check one geometry: satellite at u pointing at the Sun must be lit,
    # at u + 180° it is the deepest candidate for shadow.
    alt = 650e3
    pos_toward = fe.sat_position(0.0, 0.0, 0.0, alt)   # on the +x axis
    sun = (1.0, 0.0, 0.0)
    assert not fe.in_umbra(pos_toward, sun)
    pos_away = fe.sat_position(0.0, 0.0, 180.0, alt)   # on the −x axis
    assert fe.in_umbra(pos_away, sun)


def test_walker_fleet_never_all_shadowed():
    # A 4×6 Walker at 550 km: the RAAN grid decorrelates planes, so even at
    # the solstices a healthy fraction stays lit at every instant.
    const = from_walker(planes=4, sats_per_plane=6, altitude_m=550e3,
                        inclination_deg=osun.sso_inclination_deg(550e3))
    sats = expand_satellites(const)
    for doy in (0.0, 81.0, 172.0, 355.0):
        prof = fe.daily_profile(sats, doy, n_slots=48)
        assert min(prof) >= len(sats) // 2


def test_equivalent_ltan_recovers_design_value():
    # Plane with Ω = α_sun − 90° must read LTAN ≈ 6 h on the equinox.
    assert abs(fe.equivalent_ltan_h(-90.0, 81.0) - 6.0) < 1e-6
