# Claim-to-evidence index

Every substantive claim in `framework.md` and `exposure-table.md` mapped to
its primary source (URL + access date) or its unedited log file + line.
Line numbers are 1-based and refer to the files as committed in this pack.

## Primary-source claims (framework.md sections 2-3, 5-6)

| # | Claim | Evidence |
|---|---|---|
| C1 | PFTL is XRPL-derived; queue and fee escalation live in postfiatd `TxQ.h` / `TxQ.cpp`, commit `0085a1ff` | postfiatd repo, commit `0085a1ff` (full hash `0085a1ff885d6a446369cf73a4430f75af22be55`), `src/xrpld/app/misc/TxQ.h` and `src/xrpld/app/misc/detail/TxQ.cpp`, accessed 2026-11-17 |
| C2 | Minimum transaction cost 10 drops (0.00001 XRP); reference tx 10 drops = 256 fee levels, double = 512 | https://xrpl.org/docs/concepts/transactions/transaction-cost, accessed 2026-11-17 |
| C3 | Two thresholds: load-based cost (below it the server ignores the tx) and open ledger cost (below it the tx is queued) | https://xrpl.org/docs/concepts/transactions/transaction-cost, accessed 2026-11-17 |
| C4 | Open ledger cost = minimum until the soft limit, then exponential per extra tx; soft limit rises after a busy ledger, falls if consensus takes more than 5 s | https://xrpl.org/docs/concepts/transactions/transaction-cost, accessed 2026-11-17 |
| C5 | `Fee` field is immutable; a queued tx cannot raise its own fee | https://xrpl.org/docs/concepts/transactions/transaction-cost, accessed 2026-11-17 |
| C6 | Queued tx leaves the queue when applied, invalid (e.g. `LastLedgerSequence` expiry), or dropped for higher-fee txs; otherwise it can stay "for a theoretically unlimited amount of time" while others cut in line | https://xrpl.org/docs/concepts/transactions/transaction-queue, accessed 2026-11-17 |
| C7 | TxQ.h constants: baseLevel 256 (line 114); ledgersInQueue 20 (line 145); queueSizeMin 2000 (line 156); retrySequencePercent 25 (line 175); minimumEscalationMultiplier = baseLevel x 500 = 128000 (line 181); minimumTxnInLedger 32 (line 187); targetTxnInLedger 256 (line 199); normalConsensusIncreasePercent 20 (line 242); slowConsensusDecreasePercent 50 (line 268); maximumTxnPerAccount 10 (line 272); minimumLastLedgerBuffer 2 (line 286) | postfiatd `src/xrpld/app/misc/TxQ.h`, commit `0085a1ff`, accessed 2026-11-17 (each constant re-verified live at that commit on 2026-11-17) |
| C8 | Fee escalation is quadratic past the target: `mulDiv(multiplier, current * current, target * target)` | postfiatd `src/xrpld/app/misc/detail/TxQ.cpp`, `scaleFeeLevel`, file lines 343-351, accessed 2026-11-17 |
| C9 | Escalation multiplier is the previous ledger's median fee level, floored at the minimum escalation multiplier | postfiatd `src/xrpld/app/misc/detail/TxQ.cpp`, `FeeMetrics::update`, accessed 2026-11-17 |
| C10 | Queue ranking: higher relative cost first, ties by hash ascending, same-sender by `Sequence`; queue order decides inclusion, not execution order within a validated ledger (canonical order) | https://xrpl.org/docs/concepts/transactions/transaction-queue, accessed 2026-11-17 |
| C11 | Queueing restrictions: max 10 tx per sending address; queued fees total cannot exceed the 1 XRP base reserve; `LastLedgerSequence` must be at least current ledger index + 2; cancel by same-sequence higher-fee tx; fee averaging | https://xrpl.org/docs/concepts/transactions/transaction-queue, accessed 2026-11-17 |
| C12 | postfiatd enforces the `LastLedgerSequence` buffer and per-account cap in `canBeHeld` | postfiatd `src/xrpld/app/misc/detail/TxQ.cpp`, file lines 752-758 and 781-783, accessed 2026-11-17 |
| C13 | CRQC timeline: about one in six by 2035, near 30% by 2040, about 60% by 2050; ~1,200-2,330 logical qubits to break ECC (reported estimates) | Gershteyn & Alber, "Quantum Horizon", arXiv 2606.14484, submitted 12 June 2026, https://arxiv.org/abs/2606.14484, accessed 2026-11-17 |
| C14 | Lux: greater than 50% CRQC probability before 2035 (their assessment); Ed25519 key recovery about 2,310 logical qubits and about 8 hours; mempool key exposure is attack vector #1 (public key visible 2-30 s typical); commit-reveal doubles latency, not backward compatible | Kelling, Lux Industries, "Quantum Threat Model for Blockchain Infrastructure", revised February 2026, https://papers.lux.network/pdfs/lux-quantum-threat-blockchain-lux-quantum-threat-blockchain.pdf, accessed 2026-11-17 |
| C15 | ML-DSA-65: public key 1,952 B, secret key 4,032 B, signature 3,309 B; ML-DSA-44: 1,312 / 2,560 / 2,420 B; ML-DSA-87: 2,592 / 4,896 / 4,627 B | NIST FIPS 204, final 2024-08-13, https://csrc.nist.gov/pubs/fips/204/final, accessed 2026-11-17; sizes cross-checked against liboqs 0.16.0 output, 2026-11-17 |
| C16 | Ed25519: 32-byte public key, 64-byte signature | Verified with openssl, 2026-11-17 |
| C17 | FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA) final 2024-08-13 | https://csrc.nist.gov/pubs/fips/203/final, https://csrc.nist.gov/pubs/fips/204/final, https://csrc.nist.gov/pubs/fips/205/final, accessed 2026-11-17 |

## Simulated-measurement claims (framework.md sections 4-7, exposure-table.md)

All of the following come from the drill output. Aggregation across the 5
seeds: median/p95 exposure, hijack rate, and value hijacked are means of
the 5 per-seed values; validated/expired/dropped percentages are pooled
across all 5 seeds; `still_queued` is the total across all 5 seeds. The
canonical results hash is in the drill log.

| # | Claim | Evidence |
|---|---|---|
| M1 | Baseline median exposure 1.7 s, p95 3.3 s, hijack rate 0.0000 | `logs/drill-run-1.log`, line 10 |
| M2 | Congested median exposure 30.3 s, p95 33.2 s, hijack rate 0.5485, value hijacked 24,619,160.71 XRP per run | `logs/drill-run-1.log`, line 11 |
| M3 | Commit-reveal under congestion: hijack 0.0000, effectiveness 1.0000; median 3.7 s, p95 31.7 s, 4.27% expired | `logs/drill-run-1.log`, lines 12 and 19 |
| M4 | Fee/sequence policy under congestion: hijack 0.0000, effectiveness 1.0000; median 2.0 s, p95 18.8 s, 7.73% expired | `logs/drill-run-1.log`, lines 13 and 20 |
| M5 | ML-DSA under congestion: hijack 0.0000, effectiveness 1.0000; median 2.0 s, p95 70.9 s, 6.66% expired | `logs/drill-run-1.log`, lines 14 and 21 |
| M6 | Near-term control (8 h recovery): hijack rate 0.0000; effectiveness n/a | `logs/drill-run-1.log`, lines 15 and 22 |
| M7 | Fast adversary (3.5 s recovery) under congestion: hijack rate 0.9401, value hijacked 42,036,017.89 XRP per run | `logs/drill-run-1.log`, line 16 |
| M8 | Canonical results SHA-256 `c83862f93153f6b27065e8dcd03a0c7d769fae4591eef7b58c2942a072557d38` | `logs/drill-run-1.log`, line 32 |
| M9 | Five drill runs byte-identical; drill exits ALL GREEN | `logs/drill-run-1.log` through `logs/drill-run-5.log` (all SHA-256 `e8b657e673bd26137eea1eb9ce3c7378eb2101b35c72f891ccba7e0317a91340`), line 36 of each (`RUN_DRILL: ALL GREEN`) |
| M10 | Single hijacked payment, congested, seed 1001: 2,181.56 XRP, broadcast ledger 0, hijacked ledger 8, exposure 30.0 s | `logs/events-congested-seed1001.log`, line 2059 |
| M11 | Single hijacked payment, fast adversary, seed 1001: 4,855.00 XRP, broadcast ledger 0, hijacked ledger 1, exposure 4.0 s | `logs/events-congested-fast-adversary-seed1001.log`, line 268 |
| M12 | Single validated payment, baseline, seed 1001: 32.25 XRP, broadcast ledger 0, validated ledger 0, exposure 0.9 s | `logs/events-baseline-seed1001.log`, line 3 |
| M13 | Single expired payment, fee-policy, seed 1001: 18.27 XRP, broadcast ledger 0, expired ledger 5, exposure 18.5 s | `logs/events-congested-fee-policy-seed1001.log`, line 1545 |
| M14 | Single expired payment, ML-DSA, seed 1001: 18.27 XRP, broadcast ledger 0, expired ledger 20, exposure 71.0 s | `logs/events-congested-ml-dsa-seed1001.log`, line 5400 |
| M15 | Commit-reveal examples, seed 1001: a commit (0.00 XRP) validated in ledger 0 after 1.9 s of exposure; a reveal (212.65 XRP) validated in ledger 1 after 4.3 s of exposure (separate transfers; the log lines do not link a commit to its reveal) | `logs/events-congested-commit-reveal-seed1001.log`, lines 3 and 137 |
| M16 | Seed-1001 outcome counts: congested 15,409 validated / 15,431 hijacked / 0 expired; fast adversary 2,300 validated / 28,546 hijacked / 1,705 expired; fee-policy 30,840 validated / 2,310 expired; ML-DSA 30,840 validated / 1,966 expired; commit-reveal 30,717 validated (incl. commits) / 1,450 expired (incl. commits) | `logs/events-<scenario>-seed1001.log` (counted from the event lines; see `exposure-table.md`, seed-1001 detail) |
| M17 | Fresh-clone rerun reproduces the drill from a clean copy | `logs/fresh-clone-rerun.log` (see README.md, fresh-clone section) |

## Model-parameter claims (simulator.py, scenarios.json)

| # | Claim | Evidence |
|---|---|---|
| P1 | Ledger close 3.5 s; target 256 tx/ledger; base fee level 256; minimum escalation multiplier 128,000; queue capacity max(2000, 20 x 256) = 5,120; max 10 tx per account; `LastLedgerSequence` buffer 2 ledgers | `scenarios.json` and `simulator.py` (module constants, with the postfiatd `TxQ.h` source cited in C7) |
| P2 | Adversary fee premium 50x; recovery tiers 28,800 s / 30 s / 3.5 s; signature schemes Ed25519 / ML-DSA-65 | `scenarios.json` |
| P3 | Fee distribution 70% base / 18% 2x / 9% 4x / 3% 8x; values log-uniform 10-10,000 XRP; Poisson arrivals; one transaction per distinct account | `simulator.py` (`_fee_level`, `_value_xrp`, `generate`) |
| P4 | Exposure measured from broadcast instant (ledger index + seeded arrival offset) to resolution ledger close | `simulator.py` (`record`) |
| P5 | Commit-reveal: commit carries no value/key; reveal bound to validated commit and not targeted; ML-DSA: recovery never completes | `simulator.py` (`generate`, sections 2 and 4) |
