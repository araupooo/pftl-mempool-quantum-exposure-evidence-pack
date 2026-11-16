# PFTL Mempool and Transaction-Ordering Quantum Exposure Framework

**Status: simulated assessment.** Every measured number in this document comes
from the deterministic simulator in this pack (`simulator.py`, driven by
`run_drill.py`), not from live PFTL network observations. Simulated results
are labelled as simulated wherever they appear. No live PFTL mempool data was
used, and no claim here should be read as a measurement of the live network.

**Claim labels.** Every substantive claim in this document carries exactly one
label: [FAKTA] (verified fact, with source and access date), [ESTIMASI]
(modelled or reported number, with source), or [ANALISIS] (interpretation).
Labels are never mixed on one claim.

## 1. Scope and method

[FAKTA] PFTL is an XRPL-derived ledger: its transaction queue and fee
escalation are implemented in `postfiatd`, a fork of `rippled`
(`src/xrpld/app/misc/TxQ.h`, `src/xrpld/app/misc/detail/TxQ.cpp`, commit
`0085a1ff`, verified live 2026-11-17). [ANALISIS] The mempool exposure
question is therefore an XRPL-queue question with PFTL's parameters: how long
a signed transaction sits exposed between broadcast and validation, and
whether that window is long enough for a quantum-capable adversary to recover
the signing key and displace the transaction.

[FAKTA] The method is: (a) verify the queue, ordering, fee and expiry rules
against primary sources (xrpl.org documentation and postfiatd source);
(b) build a deterministic simulator of arrival, queueing, ordering and
validation under those rules; (c) run seven scenarios over five seeds and
report the measured table in `exposure-table.md`; (d) map every substantive
claim to a source or a log line in `claim-to-evidence-index.md`.

## 2. Transaction lifecycle: broadcast, queue, open ledger, validation

[FAKTA] A signed transaction is broadcast to the network, where its public
key becomes visible to every observer, including an adversary
(xrpl.org, Transaction Queue, accessed 2026-11-17). [FAKTA] A server that
receives it first checks the local load-based transaction cost: below that
threshold the server ignores the transaction completely
(xrpl.org, Transaction Cost, accessed 2026-11-17). [FAKTA] If the transaction
meets the load cost but not the open ledger cost, the server queues it for a
later ledger version and relays it; the provisional response code is
`terQUEUED` (xrpl.org, Transaction Cost and Transaction Queue, accessed
2026-11-17).

[FAKTA] The open ledger cost equals the minimum transaction cost until the
open ledger reaches a soft limit on the number of transactions; past the soft
limit it increases exponentially per extra transaction. For the next ledger,
the soft limit rises if the current ledger contained more transactions than
the soft limit, and falls if consensus took more than 5 seconds
(xrpl.org, Transaction Cost, accessed 2026-11-17).

[FAKTA] The minimum transaction cost for a standard (reference) transaction
is 10 drops (0.00001 XRP). Fee levels measure the proportional difference
from the minimum: the reference transaction is 10 drops = 256 fee levels,
double cost is 512 fee levels (xrpl.org, Transaction Cost, accessed
2026-11-17). [FAKTA] Every signed transaction's `Fee` field is immutable:
it cannot be changed without invalidating the signature, so a queued
transaction cannot raise its own fee to gain priority
(xrpl.org, Transaction Cost, accessed 2026-11-17).

[FAKTA] A queued transaction leaves the queue when it is applied to a
validated ledger, when it becomes invalid (for example its
`LastLedgerSequence` passes), or when it is dropped for higher-fee
transactions (xrpl.org, Transaction Queue, accessed 2026-11-17).
[FAKTA] If none of those occur, a transaction "can stay in the queue for a
theoretically unlimited amount of time, while other senders can 'cut in
line' by submitting transactions with higher transaction costs"
(xrpl.org, Transaction Queue, accessed 2026-11-17).

[FAKTA] postfiatd's queue parameters, verified live at commit `0085a1ff`
(`src/xrpld/app/misc/TxQ.h`, accessed 2026-11-17): base fee level 256
(file line 114); queue holds 20 ledgers' worth of transactions
(`ledgersInQueue`, line 145) with a minimum of 2,000 (`queueSizeMin`,
line 156); minimum escalation multiplier is base level x 500 = 128,000
(line 181); minimum transactions per ledger 32 (line 187); target
transactions per ledger 256 (`targetTxnInLedger`, line 199); maximum 10
queued transactions per account (`maximumTxnPerAccount`, line 272); minimum
`LastLedgerSequence` buffer 2 ledgers (`minimumLastLedgerBuffer`, line 286);
same-sequence replacement requires a 25% higher fee level
(`retrySequencePercent`, line 175).

[FAKTA] The fee escalation is quadratic once the open ledger passes the
target: `scaleFeeLevel` returns `multiplier * current^2 / target^2`
(`src/xrpld/app/misc/detail/TxQ.cpp`, file lines 343-351, verified live
2026-11-17). [FAKTA] The escalation multiplier is the previous ledger's
median fee level, floored at the minimum escalation multiplier
(TxQ.cpp `FeeMetrics::update`, verified live 2026-11-17).

## 3. Ordering rules: canonical order, fee-priority inclusion, sequence

[FAKTA] Within the transaction queue, transactions are ranked so that higher
relative transaction cost comes first; transactions paying the same cost are
ranked in ascending order by hash; transactions from the same sender are
sorted by their `Sequence` numbers (xrpl.org, Transaction Queue, accessed
2026-11-17). [FAKTA] The order of transactions in the queue decides which
transactions get added to the next in-progress ledger version when there are
more transactions in the queue than the expected ledger size — but it does
NOT affect the order the transactions are executed within a validated ledger:
in each validated ledger version, the transaction set executes in canonical
order (xrpl.org, Transaction Queue, accessed 2026-11-17).

[ANALISIS] The consequence for ordering risk is sharp: fees buy *inclusion*,
not *execution order*. A validator cannot reorder transactions inside a
validated ledger for profit, and a higher fee cannot move a transaction
earlier within the ledger's execution sequence. What a higher fee buys is
admission to an earlier ledger — and that is exactly what the quantum
adversary in section 5 exploits: the competing transaction does not need to
execute first within a ledger, it needs to validate in an earlier ledger
than the victim (or, in the same ledger, to sort first under canonical
order, which is decided by transaction ID, not by fee).

[FAKTA] Queueing restrictions, verified live (xrpl.org, Transaction Queue,
accessed 2026-11-17): a single sending address can have at most 10
transactions queued at the same time; the total of the queued transactions'
fees cannot exceed the base account reserve (currently 1 XRP); a transaction
with a `LastLedgerSequence` field must have it at least the current ledger
index + 2; a sender can cancel a queued transaction by submitting a new
transaction with the same sequence number and a higher transaction cost;
fee averaging lets a later high-fee transaction from the same sender push
earlier queued transactions into the open ledger.

[FAKTA] postfiatd enforces the same two limits in code: `canBeHeld` returns
`telCAN_NOT_QUEUE` when `LastLedgerSequence` is below the current ledger
index plus `minimumLastLedgerBuffer`, and allows queueing only while the
account holds fewer than `maximumTxnPerAccount` transactions
(`src/xrpld/app/misc/detail/TxQ.cpp`, file lines 752-758 and 781-783,
verified live 2026-11-17).

## 4. Exposure windows

[ANALISIS] Exposure is the time between a transaction's broadcast (when its
public key becomes visible) and its resolution (validation, hijack, expiry,
or drop). Three factors set it: the ledger-close cadence, the queue wait
under load, and the `LastLedgerSequence` window the sender chose.

[ANALISIS] The simulator uses a 3.5 s ledger-close cadence as a model
parameter, consistent with the commonly reported XRPL close time of roughly
3-4 seconds; the exact cadence is a parameter, and slower consensus would
lengthen exposure.
[ESTIMASI] At normal load (20 transactions/s, simulated), median exposure is
1.7 s and p95 is 3.3 s — one ledger close or less
(`logs/drill-run-1.log`, line 10; `logs/events-baseline-seed1001.log`).
[ESTIMASI] Under congestion (80 transactions/s against a ~256-transaction
per-ledger admission capacity, simulated), median exposure rises to 30.3 s
and p95 to 33.2 s (`logs/drill-run-1.log`, line 11). [ANALISIS] Congestion,
not the ledger cadence, is what opens the exposure window: the queue, not
the clock, is the risk.

[ESTIMASI] The simulated exposure distribution under congestion is bimodal:
most transactions validate in one or two ledgers, while low-fee transactions
starve behind higher-fee ones and wait close to the full `LastLedgerSequence`
window. In the ML-DSA scenario (same load, adversary present but recovery never
completes because ML-DSA is quantum-resistant), median exposure is
2.0 s but p95 is 70.9 s (`logs/drill-run-1.log`, line 14) — the long tail is
the queue: without hijacks, low-fee transactions wait out the full
20-ledger `LastLedgerSequence` window (70 s at the 3.5 s close), so expired
transactions resolve at roughly 70-73.5 s of exposure and the p95 lands in
that expired tail.

[ESTIMASI] A single simulated hijacked transaction, quoted from the event
log: `f383fbf4cbc0c98a65511b2156748ae0074795e8ecca87040deeb43bbec36087 249 1
256 2181.56 0 hijacked 8 30.0 1 payment`
(`logs/events-congested-seed1001.log`, line 2059) — a 2,181.56 XRP payment,
broadcast at ledger 0, hijacked at ledger 8 after 30.0 s of exposure.

## 5. The quantum adversary

**Capabilities (model parameters, not measurements).** [ANALISIS] The
adversary observes every broadcast public key; recovers the private key with
Shor's algorithm in a configurable time; and submits a competing transaction
(same account, same sequence, higher fee) that can displace the original.
The recovery time is a parameter of the model, not a measured quantity: this
pack measures what happens *if* recovery completes inside the exposure
window, not *when* a cryptographically relevant quantum computer will exist.

[ESTIMASI] The CRQC timeline figures used to choose the parameter tiers are
reported estimates, not facts: a Monte-Carlo forecast (Gershteyn & Alber,
arXiv 2606.14484 "Quantum Horizon", submitted 12 June 2026, accessed
2026-11-17) puts the chance of a cryptographically relevant quantum computer
at about one in six by 2035, near 30% by 2040, and about 60% by 2050, with
roughly 1,200-2,330 logical qubits needed to break elliptic-curve
signatures. [ESTIMASI] An industry threat model (Kelling, Lux Industries,
"Quantum Threat Model for Blockchain Infrastructure", revised February 2026,
accessed 2026-11-17) is more aggressive, assessing a greater than 50%
probability before 2035, and estimates Ed25519 key recovery at about 2,310
logical qubits and about 8 hours (1 microsecond T-gate time).

[ESTIMASI] The same threat model identifies mempool key exposure as attack
vector #1: the public key is visible between broadcast and confirmation
(typically 2-30 seconds on modern chains); the adversary observes the key,
computes the private key via Shor, and broadcasts a competing draining
transaction with higher gas; it requires completing Shor within the block
time; current estimates suggest this is infeasible with near-term quantum
computers (hours per key recovery), but may become feasible (Lux, revised
February 2026, accessed 2026-11-17).

**Parameter tiers used in this pack (simulated).** [ANALISIS] Three recovery
tiers are modelled: near-term, 28,800 s (8 h, the Lux Table 1 estimate for
Ed25519); mature-CRQC, 30 s (recovery completes inside a congested exposure
window); advanced-CRQC, 3.5 s (recovery completes inside a single ledger
close). The adversary's competing transaction pays a 50x fee premium over
the victim's fee level — trivial next to a hijacked transfer of 10-10,000
XRP, and small enough that the premium itself is not the binding constraint.

**Measured effect (simulated).** [ESTIMASI] At the near-term tier (8 h
recovery), the hijack rate is 0.0000 at normal load: no recovery can complete
inside any mempool exposure window (`logs/drill-run-1.log`, line 15).
[ESTIMASI] At the mature tier (30 s) under congestion, the hijack rate is
0.5485 — 54.85% of settled value-carrying transactions are hijacked — with
24,619,160.71 XRP of simulated value hijacked per run on average
(`logs/drill-run-1.log`, line 11). [ESTIMASI] At the advanced tier (3.5 s)
under congestion, the hijack rate is 0.9401, with 42,036,017.89 XRP of
simulated value hijacked per run (`logs/drill-run-1.log`, line 16).
[ANALISIS] The hijack rate is therefore a step function of the recovery time
against the exposure distribution: harmless while recovery exceeds the
longest exposure, catastrophic once it falls inside the typical exposure.

[ESTIMASI] A single simulated hijack at the advanced tier, quoted from the
event log: `fca7580f64e4a580166485e13a9f8ca5b043ebca5e928aee99910226f28878f8
174 1 256 4855.00 0 hijacked 1 4.0 1 payment`
(`logs/events-congested-fast-adversary-seed1001.log`, line 268) — a 4,855.00
XRP payment hijacked one ledger after broadcast, after 4.0 s of exposure.

## 6. Mitigations

### 6.1 Commit-reveal

[ANALISIS] Commit-reveal removes the key-exposure window from the value
transfer: the commit transaction carries only a hash of the transaction
content (no value, no public key), and the reveal — which carries the value
and the public key — is bound to the already-validated commit. A forged
reveal cannot match the commit's content hash, so the adversary cannot steal
the value even after recovering the key from the reveal.

[ESTIMASI] Measured (simulated): under congestion, commit-reveal reduces the
hijack rate from 0.5485 to 0.0000, an effectiveness of 1.0000
(`logs/drill-run-1.log`, lines 19-22). [ESTIMASI] The cost is visible in the
same table: a transfer now takes two transactions, so at 40 value-transfers
per second (80 transactions per second on-chain, the same on-chain load as
the congested scenario) median exposure rises to 3.7 s and p95 to 31.7 s,
and 4.27% of value transfers expire (`logs/drill-run-1.log`, line 12).
[ESTIMASI] The Lux threat model notes the same trade-off in general terms:
commit-reveal doubles latency and is not backward compatible (Lux, revised
February 2026, accessed 2026-11-17). [ANALISIS] A residual risk the model
does not count as a hijack: an adversary who recovers the key from the
reveal can grief the transfer by consuming its sequence with a different
transaction — the value is not stolen, but the transfer fails.

### 6.2 Fee and sequence policy

[ANALISIS] The exposure window can be capped from the sender side without
any protocol change: set a short `LastLedgerSequence` window and a higher
minimum fee. A transaction that cannot be admitted within the window expires
harmlessly instead of sitting exposed.

[ESTIMASI] Measured (simulated): with a 5-ledger `LastLedgerSequence`
window (17.5 s maximum exposure) and a minimum fee level of 512, the hijack
rate under congestion falls from 0.5485 to 0.0000, effectiveness 1.0000
(`logs/drill-run-1.log`, lines 19-22). [ESTIMASI] The cost is 7.73% of value
transfers expiring instead of validating, and p95 exposure of 18.8 s
(`logs/drill-run-1.log`, line 13). [ESTIMASI] A single simulated expiry,
quoted: `f63a06cd4a01fe31fad9c6a408b107abe189d08b983e89d7c553959608e6b4f1 39
1 512 18.27 0 expired 5 18.5 0 payment`
(`logs/events-congested-fee-policy-seed1001.log`, line 1545).

### 6.3 ML-DSA migration

[FAKTA] ML-DSA (FIPS 204, final 2024-08-13) is a quantum-resistant signature
scheme. [FAKTA] ML-DSA-65 has a 1,952-byte public key, a 4,032-byte secret
key, and a 3,309-byte signature; ML-DSA-44 is 1,312 / 2,560 / 2,420 bytes
and ML-DSA-87 is 2,592 / 4,896 / 4,627 bytes (FIPS 204, final 2024-08-13;
sizes cross-checked against liboqs 0.16.0 output on 2026-11-17).
[FAKTA] Ed25519, by contrast, has a 32-byte public key and a 64-byte
signature (verified with openssl on 2026-11-17). [ANALISIS] Migration to
ML-DSA therefore multiplies signature size by roughly 50x (ML-DSA-65 vs
Ed25519), which raises transaction sizes and fees, and requires a protocol
change to accept the new signature scheme — it is not a drop-in replacement.

[ESTIMASI] Measured (simulated): under congestion, ML-DSA-65 signatures
reduce the hijack rate from 0.5485 to 0.0000, effectiveness 1.0000, because
key recovery never completes (`logs/drill-run-1.log`, lines 19-22).
[ESTIMASI] ML-DSA does nothing about queue latency: median exposure is 2.0 s
but p95 is 70.9 s, and 6.66% of value transfers expire
(`logs/drill-run-1.log`, line 14). [ANALISIS] ML-DSA removes the quantum
vector; it does not remove the congestion that creates the exposure window
in the first place.

### 6.4 Ordering-rule changes

[ANALISIS] No ordering-rule change available inside the XRPL model removes
the exposure: canonical execution order already prevents in-ledger
reordering for profit, and fee-priority inclusion is what lets the
adversary's competing transaction into an earlier ledger. Hiding the public
key until validation (commit-reveal, section 6.1) or removing the
recoverable signature (ML-DSA, section 6.3) are the two structural fixes;
the fee/sequence policy (section 6.2) is the operational fix available
today.

## 7. Measured results summary

[ESTIMASI] Full table in `exposure-table.md`; all numbers are simulated.
Aggregation across the 5 seeds: median/p95 exposure, hijack rate, and value
hijacked are means of the 5 per-seed values; validated/expired/dropped
percentages are pooled across all 5 seeds; `still_queued` is the total
across all 5 seeds. Headline: at normal load the mempool is
safe at every modelled recovery tier (hijack rate 0.0000); under congestion
at 80 transactions per second, the mature-CRQC tier (30 s recovery) hijacks
54.85% of settled value transfers, and the advanced tier (3.5 s) hijacks
94.01%. All three mitigations — commit-reveal, fee/sequence policy, ML-DSA
migration — reduce the hijack rate to 0.0000 under congestion, each with a
different cost (latency, expiry, or signature size).

## 8. Assumptions and limitations

- [ANALISIS] All measured numbers are simulated, from a synthetic model of
  the mempool. They are not live PFTL measurements, and PFTL's live queue
  parameters may differ from postfiatd's defaults (the model uses the
  defaults in `TxQ.h`).
- [ANALISIS] The ledger-close cadence is a fixed 3.5 s parameter; real
  ledgers vary around 3-4 s, and consensus delays would lengthen exposure.
- [ANALISIS] Each simulated transaction comes from a distinct account, so
  the per-account queue cap (10) and per-account sequence ordering do not
  bind in these scenarios. The exposure question here is about aggregate
  queue dynamics, not about one account's sequence chain.
- [ANALISIS] The adversary's key-recovery times (8 h, 30 s, 3.5 s) are
  parameters, not measurements. The 8 h tier comes from the Lux Table 1
  estimate; the 30 s and 3.5 s tiers are sensitivity cases, not forecasts.
- [ANALISIS] The adversary targets every exposed payment transaction and
  pays a 50x fee premium. A real adversary would prioritise high-value
  victims and face capital and relay constraints the model does not impose.
- [ANALISIS] Transaction values are log-uniform between 10 and 10,000 XRP,
  a modelling choice, not an observed distribution; the "value hijacked"
  totals scale with that choice.
- [ANALISIS] The model does not simulate consensus, validator behaviour,
  network propagation delay, or the fee-voting mechanism. It models one
  node's queue and open ledger.
- [ANALISIS] Commit-reveal griefing (section 6.1) is documented but not
  counted as a hijack in the table.
- [ANALISIS] The simulator's fee distribution (70% at base fee, 18% at 2x,
  9% at 4x, 3% at 8x) is a modelling choice; real fee distributions differ
  and would change the queue dynamics.

## 9. Primary sources

- XRPL Transaction Cost — https://xrpl.org/docs/concepts/transactions/transaction-cost — accessed 2026-11-17.
- XRPL Transaction Queue — https://xrpl.org/docs/concepts/transactions/transaction-queue — accessed 2026-11-17.
- postfiatd `src/xrpld/app/misc/TxQ.h`, commit `0085a1ff` (full hash `0085a1ff885d6a446369cf73a4430f75af22be55`) — https://github.com/postfiatorg/postfiatd/blob/0085a1ff885d6a446369cf73a4430f75af22be55/src/xrpld/app/misc/TxQ.h — accessed 2026-11-17.
- postfiatd `src/xrpld/app/misc/detail/TxQ.cpp`, commit `0085a1ff` — https://github.com/postfiatorg/postfiatd/blob/0085a1ff885d6a446369cf73a4430f75af22be55/src/xrpld/app/misc/detail/TxQ.cpp — accessed 2026-11-17.
- NIST FIPS 204, Module-Lattice-Based Digital Signature Standard (ML-DSA), final 2024-08-13 — https://csrc.nist.gov/pubs/fips/204/final — accessed 2026-11-17 (sizes cross-checked against liboqs 0.16.0 output, 2026-11-17).
- NIST FIPS 203 (ML-KEM) and FIPS 205 (SLH-DSA), final 2024-08-13 — https://csrc.nist.gov/pubs/fips/203/final and https://csrc.nist.gov/pubs/fips/205/final — accessed 2026-11-17.
- Gershteyn & Alber, "Quantum Horizon", arXiv 2606.14484, submitted 12 June 2026 — https://arxiv.org/abs/2606.14484 — accessed 2026-11-17.
- Kelling, Lux Industries, "Quantum Threat Model for Blockchain Infrastructure", revised February 2026 — https://papers.lux.network/pdfs/lux-quantum-threat-blockchain-lux-quantum-threat-blockchain.pdf — accessed 2026-11-17.
