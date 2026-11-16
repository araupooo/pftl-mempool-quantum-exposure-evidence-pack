# PFTL Mempool and Transaction-Ordering Quantum Exposure Evidence Pack

A public, reproducible assessment of PFTL mempool exposure and
transaction-ordering risks from a quantum-capable adversary. All measured
numbers are **simulated** (deterministic simulator, no live network data).
Simulated results are never presented as live PFTL measurements.

## What this pack contains

- [framework.md](framework.md) — the mempool exposure framework: transaction
  lifecycle (broadcast → queue → open ledger → validation), exposure windows,
  ordering rules (canonical hash order, fee-priority inclusion, sequence
  rules), adversary capabilities (parameterised key-recovery time vs exposure
  window, front-running fee premium, observation scope), mitigations
  (commit-reveal, ordering-rule changes, fee/sequence policies, ML-DSA
  migration), assumptions and limitations. Every substantive claim carries
  exactly one label: [FAKTA], [ESTIMASI], or [ANALISIS].
- [simulator.py](simulator.py) — the simulator (pure Python standard library,
  no network, deterministic with explicit seeds). Models transaction arrival
  (Poisson), queueing under fee-escalation rules modelled on postfiatd's TxQ,
  canonical ordering, and validation at a 3.5 s ledger-close cadence, plus a
  quantum-adversary module with configurable key-recovery time, front-running
  fee premium, and observation scope.
- [scenarios.json](scenarios.json) — scenario configuration: seven scenarios
  (baseline, congested, commit-reveal, fee/sequence policy, ML-DSA migration,
  near-term control, fast adversary) over five seeds.
- [run_drill.py](run_drill.py) — the one-command drill (see below).
- [exposure-table.md](exposure-table.md) — the measured table: median and p95
  exposure time, ordering-manipulation (hijack) success rate, mitigation
  effectiveness, value hijacked, and outcome rates per scenario.
- [claim-to-evidence-index.md](claim-to-evidence-index.md) — every
  substantive claim mapped to its primary source (URL + access date) or its
  unedited log file + line.

## Headline result (simulated)

At normal load (20 tx/s) the mempool is safe at every modelled recovery
tier: hijack rate 0.0000, median exposure 1.7 s. Under congestion (80 tx/s)
the mature-CRQC tier (30 s key recovery) hijacks 54.85% of settled
value-carrying transactions, and the advanced tier (3.5 s) hijacks 94.01%.
All three mitigations — commit-reveal, fee/sequence policy, ML-DSA
migration — reduce the hijack rate to 0.0000 under congestion, each with a
different cost (latency, expiry, or signature size). Full table:
[exposure-table.md](exposure-table.md).

## How to reproduce

One command, from this directory:

```
python3 run_drill.py
```

Requires Python 3.8+ and nothing else (standard library only, no network
access). The drill runs all seven scenarios over seeds 1001-1005, prints the
exposure table and a determinism proof, writes per-transaction event logs for
seed 1001 into `logs/`, and exits 0 only if every check passes. Re-running
it produces byte-identical output.

## Logs

Unedited drill logs (five runs, byte-identical to each other):

- [logs/drill-run-1.log](logs/drill-run-1.log)
- [logs/drill-run-2.log](logs/drill-run-2.log)
- [logs/drill-run-3.log](logs/drill-run-3.log)
- [logs/drill-run-4.log](logs/drill-run-4.log)
- [logs/drill-run-5.log](logs/drill-run-5.log)

All five runs have SHA-256
`e8b657e673bd26137eea1eb9ce3c7378eb2101b35c72f891ccba7e0317a91340` and end
with `RUN_DRILL: ALL GREEN`. The canonical results hash printed by the
drill is
`c83862f93153f6b27065e8dcd03a0c7d769fae4591eef7b58c2942a072557d38`.

Per-transaction event logs for seed 1001 (one line per transaction: txid,
account, sequence, fee level, value, broadcast ledger, outcome, outcome
ledger, exposure seconds, hijacked flag, kind):

- [logs/events-baseline-seed1001.log](logs/events-baseline-seed1001.log)
- [logs/events-congested-seed1001.log](logs/events-congested-seed1001.log)
- [logs/events-congested-commit-reveal-seed1001.log](logs/events-congested-commit-reveal-seed1001.log)
- [logs/events-congested-fee-policy-seed1001.log](logs/events-congested-fee-policy-seed1001.log)
- [logs/events-congested-ml-dsa-seed1001.log](logs/events-congested-ml-dsa-seed1001.log)
- [logs/events-near-term-control-seed1001.log](logs/events-near-term-control-seed1001.log)
- [logs/events-congested-fast-adversary-seed1001.log](logs/events-congested-fast-adversary-seed1001.log)

Fresh-clone rerun log:

- [logs/fresh-clone-rerun.log](logs/fresh-clone-rerun.log)

## Fresh-clone rerun

The documented workflow was validated from a fresh copy: the three code and
config files (`simulator.py`, `run_drill.py`, `scenarios.json`) were copied
to a clean directory, the drill was run there with no other pack files
present, and the unedited stdout was saved as
[logs/fresh-clone-rerun.log](logs/fresh-clone-rerun.log).

```
cp simulator.py run_drill.py scenarios.json ../fresh-clone-cycle4/
cd ../fresh-clone-cycle4 && python3 run_drill.py
```

Result: exit code 0, `RUN_DRILL: ALL GREEN`, output byte-identical to
`logs/drill-run-1.log`, canonical results SHA-256
`c83862f93153f6b27065e8dcd03a0c7d769fae4591eef7b58c2942a072557d38`.

## File integrity

`SHA256SUMS` lists the SHA-256 of every file in this pack except itself (a
file cannot contain its own hash). Verify with:

```
sha256sum -c SHA256SUMS
```

## Primary sources

- XRPL Transaction Cost — https://xrpl.org/docs/concepts/transactions/transaction-cost — accessed 2026-11-17.
- XRPL Transaction Queue — https://xrpl.org/docs/concepts/transactions/transaction-queue — accessed 2026-11-17.
- postfiatd `TxQ.h` / `TxQ.cpp`, commit `0085a1ff` — https://github.com/postfiatorg/postfiatd — accessed 2026-11-17.
- NIST FIPS 203 / 204 / 205, final 2024-08-13 — https://csrc.nist.gov/pubs/fips/204/final — accessed 2026-11-17.
- Gershteyn & Alber, "Quantum Horizon", arXiv 2606.14484 — https://arxiv.org/abs/2606.14484 — accessed 2026-11-17.
- Kelling, Lux Industries, "Quantum Threat Model for Blockchain Infrastructure", revised February 2026 — https://papers.lux.network/pdfs/lux-quantum-threat-blockchain-lux-quantum-threat-blockchain.pdf — accessed 2026-11-17.

Full source list with per-claim mapping:
[claim-to-evidence-index.md](claim-to-evidence-index.md).
