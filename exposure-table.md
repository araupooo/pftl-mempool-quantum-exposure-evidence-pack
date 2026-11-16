# Measured exposure and mitigation table

**All numbers are simulated** (deterministic simulator, `simulator.py` driven
by `run_drill.py`), not live PFTL measurements. Aggregation across the 5
seeds (1001-1005): median/p95 exposure, hijack rate, and value hijacked are
means of the 5 per-seed values; validated/expired/dropped percentages are
pooled across all 5 seeds; `still_queued` is the total across all 5 seeds.
The full unedited drill output is `logs/drill-run-1.log` (byte-identical to
`logs/drill-run-2.log` through `logs/drill-run-5.log`; SHA-256
`e8b657e673bd26137eea1eb9ce3c7378eb2101b35c72f891ccba7e0317a91340`).

## Definitions

- **median_s / p95_s**: median and 95th percentile exposure time in seconds
  across all resolved transactions in the run (validated, hijacked, expired,
  dropped). Exposure is measured from the broadcast instant to resolution.
- **hijack**: hijack rate = hijacked / (validated value-carrying transactions
  + hijacked). A hijack means the adversary's competing transaction (same
  account, same sequence, 50x fee premium) validated in an earlier ledger
  than the victim, or in the same ledger with a smaller transaction ID under
  canonical (hash) order.
- **value_hijacked_xrp**: mean simulated XRP value hijacked per run.
  Transaction values are log-uniform between 10 and 10,000 XRP (a modelling
  choice); the totals scale with that choice.
- **validated% / hijacked% / expired% / dropped%**: share of broadcast
  value-carrying transactions (payments and reveals; commits excluded) with
  that outcome. The four percentages plus the still-queued share sum to
  100%.
- **still_queued**: value-carrying transactions still in the queue when the
  120-ledger run ends (unresolved, not counted in any outcome percentage).

## Table (5 seeds; aggregation as noted above)

| scenario | median_s | p95_s | hijack | value_hijacked_xrp | validated% | hijacked% | expired% | dropped% | still_queued |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 1.7 | 3.3 | 0.0000 | 0.00 | 100.00 | 0.00 | 0.00 | 0.00 | 0 |
| congested | 30.3 | 33.2 | 0.5485 | 24619160.71 | 41.50 | 50.42 | 0.33 | 0.00 | 13005 |
| congested-commit-reveal | 3.7 | 31.7 | 0.0000 | 0.00 | 93.91 | 0.00 | 4.27 | 0.00 | 2281 |
| congested-fee-policy | 2.0 | 18.8 | 0.0000 | 0.00 | 91.91 | 0.00 | 7.73 | 0.00 | 607 |
| congested-ml-dsa | 2.0 | 70.9 | 0.0000 | 0.00 | 91.91 | 0.00 | 6.66 | 0.00 | 2405 |
| near-term-control | 1.7 | 3.3 | 0.0000 | 0.00 | 100.00 | 0.00 | 0.00 | 0.00 | 0 |
| congested-fast-adversary | 5.3 | 70.6 | 0.9401 | 42036017.89 | 5.51 | 86.44 | 5.85 | 0.00 | 3696 |

Source: `logs/drill-run-1.log`, lines 10-16 (table) and lines 18-22
(mitigation effectiveness). Canonical results SHA-256 (line 32):
`c83862f93153f6b27065e8dcd03a0c7d769fae4591eef7b58c2942a072557d38`.

## Reading the table: why the ML-DSA p95 is 70.9 s

ML-DSA removes the hijack vector but not the queue: without hijacks,
low-fee transactions sit in the queue until their `LastLedgerSequence`
window ends. The window is 20 ledgers (70 s at the 3.5 s close), so expired
transactions resolve at roughly 70-73.5 s of exposure (median 71.7 s in the
seed-1001 ML-DSA event log), and with 6.66% of transactions expiring, the
p95 lands in that expired tail. In the congested scenario the p95 is lower
(33.2 s) because hijacked transactions resolve earlier, at about the 30 s
recovery time, instead of waiting out the full window. The fee-policy p95
(18.8 s) is lower still because its 5-ledger window caps exposure at 17.5 s
plus arrival offset.

| scenario | arrival rate | recovery time | signature | mitigation |
|---|---|---|---|---|
| baseline | 20 tx/s | 30 s | Ed25519 | none |
| congested | 80 tx/s | 30 s | Ed25519 | none |
| congested-commit-reveal | 40 value-tx/s (80 tx/s on-chain) | 30 s | Ed25519 | commit-reveal |
| congested-fee-policy | 80 tx/s | 30 s | Ed25519 | LastLedgerSequence window 5 ledgers, minimum fee level 512 |
| congested-ml-dsa | 80 tx/s | 30 s | ML-DSA-65 | quantum-resistant signatures |
| near-term-control | 20 tx/s | 28,800 s (8 h) | Ed25519 | none (control) |
| congested-fast-adversary | 80 tx/s | 3.5 s | Ed25519 | none (sensitivity case) |

Full parameters in `scenarios.json`. All scenarios share the TxQ model
constants from postfiatd `TxQ.h` at commit `0085a1ff` (base fee level 256,
target 256 tx/ledger, minimum escalation multiplier 128,000, queue capacity
max(2000, 20 x 256) = 5,120, max 10 queued transactions per account,
`LastLedgerSequence` buffer 2 ledgers) and a 50x adversary fee premium.

## Mitigation effectiveness (vs reference scenario)

| mitigation | reference | hijack before | hijack after | effectiveness |
|---|---|---|---|---|
| congested-commit-reveal | congested | 0.5485 | 0.0000 | 1.0000 |
| congested-fee-policy | congested | 0.5485 | 0.0000 | 1.0000 |
| congested-ml-dsa | congested | 0.5485 | 0.0000 | 1.0000 |
| near-term-control | baseline | 0.0000 | 0.0000 | n/a (nothing to mitigate at that tier) |

Effectiveness = 1 - hijack_rate(mitigation) / hijack_rate(reference).
Source: `logs/drill-run-1.log`, lines 19-22.

## Seed-1001 detail (the per-event logs)

Per-transaction event logs for seed 1001 are in `logs/events-<scenario>-seed1001.log`.
Seed-1001 aggregates (from the event logs themselves):

| scenario | events | validated | hijacked | expired | dropped | still queued* |
|---|---|---|---|---|---|---|
| baseline | 8,364 | 8,364 | 0 | 0 | 0 | 0 |
| congested | 30,840 | 15,409 | 15,431 | 0 | 0 | 2,452 |
| congested-commit-reveal | 32,167 | 30,717 | 0 | 1,450 | 0 | 396 |
| congested-fee-policy | 33,150 | 30,840 | 0 | 2,310 | 0 | 142 |
| congested-ml-dsa | 32,806 | 30,840 | 0 | 1,966 | 0 | 486 |
| near-term-control | 8,364 | 8,364 | 0 | 0 | 0 | 0 |
| congested-fast-adversary | 32,551 | 2,300 | 28,546 | 1,705 | 0 | 741 |

\* Still-queued counts are all transactions still in the queue at run end
(including commit transactions in the commit-reveal scenario, which carry
no value). In the commit-reveal scenario the "validated" and "expired"
counts include commit transactions (value 0), which is why they exceed the
value-transaction counts in the 5-seed table above.

## How to reproduce

```
python3 run_drill.py
```

The drill runs all seven scenarios over seeds 1001-1005, prints this table,
asserts determinism (same-seed re-runs produce identical events and stats),
and exits 0 only if all checks pass. Re-running it produces byte-identical
output; see `logs/drill-run-1.log` through `logs/drill-run-5.log` and the
fresh-clone rerun log `logs/fresh-clone-rerun.log`.
