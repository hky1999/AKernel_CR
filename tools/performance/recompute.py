#!/usr/bin/env python3
"""Verify paired estimates; recorded bootstrap intervals are not recomputed."""
import argparse
import json
import math
from pathlib import Path
import statistics

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("samples", type=Path)
args = parser.parse_args()
data = json.loads(args.samples.read_text())
output = {}
for runtime, result in data["statistics"].items():
    pairs = result["pairs"]
    if len(pairs) != 6 or {p["block"] for p in pairs} != set(range(1, 7)):
        raise SystemExit("expected exactly six registered paired samples")
    if any(p["A"] <= 0 or p["B"] <= 0 for p in pairs):
        raise SystemExit("all durations must be positive")
    ratio = math.exp(statistics.mean(math.log(p["B"] / p["A"]) for p in pairs))
    if not math.isclose(ratio, result["R_geometric_mean_ratio"], rel_tol=1e-12):
        raise SystemExit("published geometric ratio does not match raw samples")
    medians = {v: statistics.median(p[v] for p in pairs) for v in ("A", "B")}
    for version, value in medians.items():
        if value != result["version_descriptive"][version]["median"]:
            raise SystemExit("published median does not match raw samples")
    output[runtime] = {
        "old_median_seconds": medians["A"] / 1e9,
        "new_median_seconds": medians["B"] / 1e9,
        "paired_geometric_new_over_old": ratio,
        "registered_bootstrap95_not_recomputed_here": result["bootstrap95_type7"],
        "registered_decision": result["decision"],
    }
print(json.dumps({"status": "paired_point_estimates_verified", "runtimes": output}, indent=2))

