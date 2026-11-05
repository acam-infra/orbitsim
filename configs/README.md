# Runnable experiments (`exp_*.yaml`)

Each file here is a CLI entry point: `orbitsim configs/exp_*.yaml`.

| file | what it shows |
|------|---------------|
| `exp_dawn_dusk_eclipse_v1.yaml` | 650 km dawn–dusk SSO: 3-season β + annual + per-day umbra |
| `exp_imaging_eclipse_v1.yaml` | 650 km imaging SSO (LTAN 10:30): eclipsed every day of the year |
| `exp_walker_constellation_v1.yaml` | Walker-delta shell constellation-level counts |
| `exp_dawn_dusk_access_suntransit_v1.yaml` | ground access + sun-transit (日凌) window |

An `exp_*` pulls a `base_*` template from `../input/scenarios/` via the
`base:` key, then overrides/extends it. Keep the file name (sans `.yaml`)
equal to the top-level `name:`.
