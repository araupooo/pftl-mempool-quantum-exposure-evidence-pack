"""One-command drill for the PFTL mempool quantum-exposure pack.

Runs every scenario in scenarios.json over 5 seeds, prints the exposure
table and a determinism proof, and writes the per-transaction event logs
for seed 1001 (one file per scenario) under logs/.

Usage:
    python3 run_drill.py

Requires Python 3.8+ and nothing else (standard library only, no network
access). Exit code 0 means every check passed. The output contains no
timestamps and no absolute paths, so repeated invocations are
byte-identical.

Mitigation effectiveness is defined against the matching unmitigated
scenario: the three congested mitigations (commit-reveal, fee-policy,
ML-DSA) are measured against congested; the near-term control is
measured against baseline. Effectiveness = 1 - hijack_rate(mitigation)
/ hijack_rate(reference). When the reference hijack rate is 0, the
effectiveness is reported as n/a (nothing to mitigate at that tier).
"""

import hashlib
import json
import os
import sys

import simulator

HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = [1001, 1002, 1003, 1004, 1005]
REFERENCE = {
    "congested-commit-reveal": "congested",
    "congested-fee-policy": "congested",
    "congested-ml-dsa": "congested",
    "near-term-control": "baseline",
}


def _mean(values):
    return sum(values) / float(len(values)) if values else 0.0


def _median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _p95(values):
    s = sorted(values)
    if not s:
        return 0.0
    idx = int(-(-95 * len(s) // 100)) - 1
    return float(s[max(0, idx)])


def main():
    with open(os.path.join(HERE, "scenarios.json")) as f:
        config = json.load(f)
    scenarios = config["scenarios"]
    run_ledgers = config.get("run_ledgers", 120)
    for sc in scenarios:
        sc.setdefault("params", {})
        sc["params"]["run_ledgers"] = run_ledgers

    print("=== PFTL MEMPOOL QUANTUM EXPOSURE DRILL ===")
    print("scenarios: %s" % ", ".join(s["name"] for s in scenarios))
    print("seeds: %s" % ",".join(str(s) for s in SEEDS))
    print("ledgers per run: %d  ledger close: %.1f s  target tx/ledger: %d"
          % (run_ledgers, simulator.LEDGER_CLOSE_S,
             config.get("target_tx_per_ledger", 256)))

    results = {}
    all_events_seed1001 = {}
    failures = []
    for sc in scenarios:
        name = sc["name"]
        per_seed = []
        for seed in SEEDS:
            events, stats = simulator.generate(sc, seed)
            per_seed.append((events, stats))
            if seed == 1001:
                all_events_seed1001[name] = events
        medians = [s["median_exposure_s"] for _, s in per_seed]
        p95s = [s["p95_exposure_s"] for _, s in per_seed]
        hijacks = [s["hijack_rate"] for _, s in per_seed]
        values = [s["value_hijacked_xrp"] for _, s in per_seed]
        validated = [s["validated_value"] for _, s in per_seed]
        expired = [s["expired_value"] for _, s in per_seed]
        dropped = [s["dropped_value"] for _, s in per_seed]
        broadcast = [s["value_broadcast"] for _, s in per_seed]
        results[name] = {
            "median_exposure_s": round(_mean(medians), 1),
            "p95_exposure_s": round(_mean(p95s), 1),
            "hijack_rate": round(_mean(hijacks), 4),
            "value_hijacked_xrp": round(_mean(values), 2),
            "validated_pct": round(
                100.0 * sum(validated) / float(sum(broadcast)), 2),
            "expired_pct": round(
                100.0 * sum(expired) / float(sum(broadcast)), 2),
            "dropped_pct": round(
                100.0 * sum(dropped) / float(sum(broadcast)), 2),
            "broadcast_total": sum(broadcast),
            "hijacked_total": sum(s["hijacked"] for _, s in per_seed),
            "still_queued": sum(s["still_queued"] for _, s in per_seed),
        }

    print("")
    print("--- exposure table (5 seeds) ---")
    print("# median/p95/hijack/value are means of the 5 per-seed values; "
          "validated/expired/dropped % are pooled across all 5 seeds; "
          "still_queued is the 5-seed total.")
    print("# hijack rate = hijacked / (validated value txs + hijacked).")
    print("scenario                  median_s  p95_s   hijack  value_hijacked_xrp  validated%  hijacked%  expired%  dropped%  still_queued")
    for sc in scenarios:
        r = results[sc["name"]]
        print("%-25s %7.1f %7.1f  %6.4f  %18.2f  %10.2f  %9.2f  %8.2f  %8.2f  %12d"
              % (sc["name"], r["median_exposure_s"], r["p95_exposure_s"],
                 r["hijack_rate"], r["value_hijacked_xrp"],
                 r["validated_pct"],
                 100.0 * r["hijacked_total"] / float(r["broadcast_total"]),
                 r["expired_pct"], r["dropped_pct"], r["still_queued"]))

    print("")
    print("--- mitigation effectiveness (vs reference scenario) ---")
    for name, ref in REFERENCE.items():
        r = results[name]
        ref_rate = results[ref]["hijack_rate"]
        if ref_rate > 0:
            eff = 1.0 - r["hijack_rate"] / ref_rate
            print("%s vs %s: hijack %.4f -> %.4f, effectiveness %.4f"
                  % (name, ref, ref_rate, r["hijack_rate"], eff))
        else:
            print("%s vs %s: reference hijack rate 0, "
                  "effectiveness n/a" % (name, ref))

    # --- determinism: re-run seed 1001 for every scenario and require
    # byte-identical event streams and identical stats. ---
    print("")
    print("--- determinism ---")
    deterministic = True
    for sc in scenarios:
        events1, stats1 = simulator.generate(sc, 1001)
        events2, stats2 = simulator.generate(sc, 1001)
        same_events = events1 == events2
        same_stats = stats1 == stats2
        if not (same_events and same_stats):
            deterministic = False
        print("%s: same-seed events identical: %s, stats identical: %s"
              % (sc["name"], same_events, same_stats))
    canonical = json.dumps(results, sort_keys=True).encode()
    canonical_sha = hashlib.sha256(canonical).hexdigest()
    print("canonical results sha256: %s" % canonical_sha)

    # --- write per-transaction event logs for seed 1001 ---
    logs_dir = os.path.join(HERE, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    for name, events in all_events_seed1001.items():
        path = os.path.join(logs_dir, "events-%s-seed1001.log" % name)
        with open(path, "w") as f:
            f.write("# per-transaction events, scenario=%s seed=1001\n" % name)
            f.write("# txid account seq fee_level value_xrp "
                    "broadcast_ledger outcome outcome_ledger exposure_s "
                    "hijacked kind\n")
            for e in events:
                f.write("%s %s %d %d %.2f %d %s %d %.1f %d %s\n" % (
                    e["txid"], e["account"], e["seq"], e["fee_level"],
                    e["value_xrp"], e["broadcast_ledger"], e["outcome"],
                    e["outcome_ledger"], e["exposure_s"], e["hijacked"],
                    e["kind"]))
    print("event logs written: %d files" % len(all_events_seed1001))

    # --- checks ---
    # 1. Baseline exposure must be short (no queueing at normal load).
    if results["baseline"]["median_exposure_s"] > 10.5:
        failures.append("baseline median exposure unexpectedly high: %.1f s"
                        % results["baseline"]["median_exposure_s"])
    # 2. Congestion must stretch exposure past the 30 s recovery time.
    if results["congested"]["p95_exposure_s"] <= 30.0:
        failures.append("congested p95 exposure does not exceed the 30 s "
                        "recovery time: %.1f s"
                        % results["congested"]["p95_exposure_s"])
    # 3. Congested hijack rate must be positive at the 30 s tier.
    if results["congested"]["hijack_rate"] <= 0:
        failures.append("congested hijack rate is 0 at the 30 s tier")
    # 4. Mitigations must not make hijacking worse than the reference.
    for name, ref in REFERENCE.items():
        if results[name]["hijack_rate"] > results[ref]["hijack_rate"]:
            failures.append("%s hijack rate exceeds its reference %s"
                            % (name, ref))
    # 5. Commit-reveal and ML-DSA must have zero hijacks by construction.
    for name in ("congested-commit-reveal", "congested-ml-dsa"):
        if results[name]["hijack_rate"] != 0:
            failures.append("%s hijack rate is not 0: %.4f"
                            % (name, results[name]["hijack_rate"]))
    # 6. Near-term control (8 h recovery) must have zero hijacks.
    if results["near-term-control"]["hijack_rate"] != 0:
        failures.append("near-term-control hijack rate is not 0: %.4f"
                        % results["near-term-control"]["hijack_rate"])
    # 7. Determinism must hold.
    if not deterministic:
        failures.append("determinism check failed")
    # 8. Fast adversary (3.5 s recovery) must hijack more than the
    #    30 s tier on the same load.
    if results["congested-fast-adversary"]["hijack_rate"] <= \
            results["congested"]["hijack_rate"]:
        failures.append("fast-adversary hijack rate does not exceed "
                        "the 30 s tier")

    print("")
    if failures:
        print("failures: %d %s" % (len(failures), failures))
        print("RUN_DRILL: FAIL")
        return 1
    print("failures: 0 []")
    print("RUN_DRILL: ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
