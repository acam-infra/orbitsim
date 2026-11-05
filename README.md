# orbitsim

Minimal orbit & constellation **feature** analysis: declarative YAML, closed knobs.
Computes the β angle, Earth-umbra (日影) windows, ground access, and sun-transit
(日凌) prone days for circular SSO / Walker-delta / TLE constellations — no
ephemeris, no SimPy, just closed-form astrodynamics.

```bash
uv sync
.venv/bin/orbitsim configs/exp_dawn_dusk_eclipse_v1.yaml
.venv/bin/orbitsim configs/exp_imaging_eclipse_v1.yaml
.venv/bin/orbitsim configs/exp_walker_constellation_v1.yaml
.venv/bin/orbitsim configs/exp_dawn_dusk_access_suntransit_v1.yaml
.venv/bin/pytest
```

## Model

Circular orbit, spherical Earth, **cylindrical umbra** (penumbra ignored — its
half-angle is ~0.27°, ≈10 s per edge at 650 km). The umbra depends only on the
**β angle** between the Sun vector and the orbit plane:

```
sin β = sin i · cos δ · sin Δ + cos i · sin δ,   Δ = (LTAN − 12 h)·15°
no eclipse:  |β| ≥ asin(RE / r)
fraction:    arccos(√(r² − RE²) / (r cos β)) / π   otherwise
```

Headline numbers this reproduces (650 km SSO):

- dawn–dusk (LTAN 06:00): eclipsed **90 of 365** days, season crosses the New
  Year, peak 4.84 h/day at the December solstice; annual sunlight **96.1%**
- imaging (LTAN 10:30): eclipsed **all 365** days, ~34 min/orbit
- dawn–dusk clears the umbra all year only above ≈**1391 km**

## Configuration (`base` / `exp`)

| prefix | dir | role |
|--------|-----|------|
| `base_*` | `input/scenarios/` | reusable scenario template; not a CLI entry |
| `exp_*`  | `configs/`         | runnable experiment; `orbitsim configs/exp_*.yaml` |

An `exp_*` references a `base_*` via `base:`, then declares an `analysis:` list.
File name (sans `.yaml`) must equal the top-level `name:`.

### `constellation:` — closed set of kinds

```yaml
constellation:
  kind: sso          # one sun-synchronous circular orbit
  altitude_m: 650000
  ltan_h: 6.0
```
```yaml
constellation:
  kind: walker       # Walker-delta shell
  planes: 72
  sats_per_plane: 22
  altitude_m: 550000
  inclination_deg: 53.0
```
```yaml
constellation:
  kind: tle          # explicit TLE list
  tles:
    - { name: SAT1, l1: "1 ...", l2: "2 ..." }
```

### `analysis:` — closed set of kinds

| kind | what it reports |
|------|-----------------|
| `constellation` | orbits/sats counts, per-orbit alt/inc/period |
| `orbit_eclipse` | no-eclipse β threshold + 3-season umbra minutes |
| `year_eclipse` | annual umbra hours, days with umbra, sunlight fraction |
| `daily_eclipse` | per-calendar-day umbra summary (peak day, season) |
| `ground_access` | daily access minutes for a `site_lat_deg` / `min_elevation_deg` |
| `sun_transit`   | days of year prone to sun-transit outages (`thresh_deg`) |

## Layout

```
input/scenarios/   base_* templates
configs/           exp_* runnable experiments
src/orbitsim/      orbit_sun.py · constellation.py · visibility.py · report.py
tests/             pytest against known LEO numbers
docs/              notes
```

## Terminology

See `GLOSSARY.md`.
