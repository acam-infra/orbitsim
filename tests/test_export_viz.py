"""export_viz must write scenarios the viewer can replay exactly."""

import json

import numpy as np

from orbitsim import fleet_synth as fs

import export_viz as ev


def test_export_scenario_round_trip(tmp_path):
    sats = fs.sso_plane("A", 3, 550, 10.5) + fs.walker("W", 2, 2, 600, 53.0)
    sats[0]["cluster"] = "簇A"
    path = ev.export_scenario("t1", "测试", sats, links=[["A/s0", "A/s1", "intra"]], doy=172,
                              dst=str(tmp_path))
    sc = json.load(open(path, encoding="utf-8"))
    assert sc["epoch_doy"] == 172 and len(sc["satellites"]) == 7
    assert {s["cluster"] for s in sc["satellites"]} >= {"簇A", "0", "1"}
    # every reference sample is reproduced by fleet_synth itself
    by = {s["name"]: s for s in sats}
    for c in sc["check"]:
        t = np.array([c["t"]])
        p = ev.ecef(fs.positions([by[c["sat"]]], 172.0, t), 172.0, t)[0, 0]
        assert np.linalg.norm(p - np.array(c["ecef"])) < 1e-3
    idx = json.load(open(tmp_path / "index.json", encoding="utf-8"))
    assert [e["name"] for e in idx] == ["t1"]
    # re-exporting the same name replaces its index entry
    ev.export_scenario("t1", "测试2", sats, dst=str(tmp_path))
    idx = json.load(open(tmp_path / "index.json", encoding="utf-8"))
    assert [e["title"] for e in idx] == ["测试2"]
