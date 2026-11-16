"""PFTL mempool and transaction-ordering quantum-exposure simulator.

Models transactions arriving at a PFTL-style (XRPL-derived) node, waiting in
the transaction queue under fee-escalation rules, and being validated at a
fixed ledger-close cadence. A quantum adversary observes each broadcast
transaction's public key and may recover the private key with Shor's
algorithm; if recovery completes before the transaction validates, the
adversary submits a competing transaction (same account, same sequence,
higher fee) that can displace the original.

Pure Python standard library, deterministic: the same (scenario, seed)
always produces the same events. No network access, no timestamps in
output, no absolute paths in output.

Model parameters (all from scenarios.json; defaults below are the values
used when a scenario does not override them):

- ledger_close_s = 3.5            ledger-close cadence in seconds
- target_tx_per_ledger = 256      TxQ targetTxnInLedger (postfiatd TxQ.h)
- base_fee_level = 256             TxQ baseLevel (fee level of a
                                   single-signed reference transaction)
- min_escalation_multiplier = 128000  TxQ minimumEscalationMultiplier
                                   (= baseLevel * 500, postfiatd TxQ.h)
- queue_ledgers = 20               TxQ ledgersInQueue (postfiatd TxQ.h)
- queue_size_min = 2000            TxQ queueSizeMin (postfiatd TxQ.h)
- max_tx_per_account = 10          TxQ maximumTxnPerAccount (postfiatd TxQ.h)
- min_last_ledger_buffer = 2       TxQ minimumLastLedgerBuffer (postfiatd TxQ.h)
- fee_premium = 50.0               adversary competing-tx fee multiplier
                                   (the adversary pays 50x the victim's fee
                                   level; the premium is bounded by the value
                                   at stake and is trivial next to a hijacked
                                   transfer of 10-10,000 XRP)
- recovery_seconds = 30.0          adversary key-recovery time (parameter,
                                   NOT a measurement)
- run_ledgers = 120                simulated ledgers per run

Each transaction is modelled as coming from a distinct account, so the
arrival stream is the same for every scenario at the same seed and the
scenarios are comparable at equal load. The per-account queue cap (10)
is enforced in the queue code but does not bind when every transaction
has its own account; per-account sequence ordering is therefore not a
binding constraint in these scenarios. This is a stated simplification:
the exposure question here is about aggregate queue dynamics, not about
one account's sequence chain.

Exposure is measured from the transaction's broadcast instant. A
transaction broadcast during ledger interval L arrives at a seeded
offset inside that interval; if it resolves at the close of ledger
L', its exposure is (L' - L) * close + (close - offset) seconds, so a
transaction validated in the ledger it was broadcast in is exposed for
up to one full close interval, not zero seconds.

Admission rule (simplified TxQ scaleFeeLevel, postfiatd TxQ.cpp): a
transaction is admitted to the open ledger while its fee level is at
least the required level for the running count. The required level is
base_fee_level while the ledger count is at or below target_tx_per_ledger;
above the target it is multiplier * (count / target) ** 2, where
multiplier is the larger of the previous ledger's median fee level and
min_escalation_multiplier. Candidates are considered in fee-level order
(highest first, ties by transaction ID ascending); transactions from one
account are considered in sequence order. This mirrors the documented
queue ranking (higher relative fee first, ties by hash, same-sender by
Sequence) and the documented fact that queue order does not change the
execution order inside a validated ledger (canonical order).

Exposure of a transaction is the time from broadcast to validation
(validated), to expiry (LastLedgerSequence passed), to being dropped
from a full queue, or to being hijacked. A transaction is hijacked when
the adversary's competing transaction validates in an earlier ledger,
or in the same ledger with a smaller transaction ID under canonical
(hash) order.

Commit-reveal: the commit transaction carries no value and no public
key, so it cannot be hijacked. The reveal carries the value and the
public key, but it is bound to the already-validated commit: a forged
reveal cannot match the commit's content hash, so the reveal is not
targeted by the adversary either. (An adversary could still grief a
reveal by consuming its sequence with a different transaction; that
denies the transfer but does not steal the value, and the model does
not count griefing as a hijack.)
"""

import hashlib
import math
import random

# --- Model constants (postfiatd TxQ.h, commit 0085a1ff, verified live) ---
BASE_FEE_LEVEL = 256
MIN_ESCALATION_MULTIPLIER = 128000  # baseLevel * 500
TARGET_TX_PER_LEDGER = 256
MIN_TX_PER_LEDGER = 32
QUEUE_LEDGERS = 20
QUEUE_SIZE_MIN = 2000
MAX_TX_PER_ACCOUNT = 10
MIN_LAST_LEDGER_BUFFER = 2
LEDGER_CLOSE_S = 3.5

DEFAULTS = {
    "ledger_close_s": LEDGER_CLOSE_S,
    "target_tx_per_ledger": TARGET_TX_PER_LEDGER,
    "base_fee_level": BASE_FEE_LEVEL,
    "min_escalation_multiplier": MIN_ESCALATION_MULTIPLIER,
    "queue_ledgers": QUEUE_LEDGERS,
    "queue_size_min": QUEUE_SIZE_MIN,
    "max_tx_per_account": MAX_TX_PER_ACCOUNT,
    "min_last_ledger_buffer": MIN_LAST_LEDGER_BUFFER,
    "fee_premium": 50.0,
    "recovery_seconds": 30.0,
    "run_ledgers": 120,
    "arrival_rate_per_s": 20.0,
    "last_ledger_window": 20,
    "min_fee_level": 256,
    "commit_reveal": False,
    "signature_scheme": "ed25519",
}


def _txid(seed, index):
    """Deterministic transaction ID: sha256 of seed and index, hex."""
    return hashlib.sha256(("%d:%d" % (seed, index)).encode()).hexdigest()


class Tx:
    """One modelled transaction."""

    __slots__ = (
        "txid", "account", "seq", "fee_level", "value_xrp", "broadcast_ledger",
        "arrival_offset_s", "last_valid_ledger", "kind", "phase", "commit_id",
    )

    def __init__(self, txid, account, seq, fee_level, value_xrp,
                 broadcast_ledger, arrival_offset_s, last_valid_ledger,
                 kind="payment", phase="single", commit_id=None):
        self.txid = txid
        self.account = account
        self.seq = seq
        self.fee_level = fee_level
        self.value_xrp = value_xrp
        self.broadcast_ledger = broadcast_ledger
        self.arrival_offset_s = arrival_offset_s
        self.last_valid_ledger = last_valid_ledger
        self.kind = kind
        self.phase = phase
        self.commit_id = commit_id


def _fee_level(rng, min_fee_level):
    """Fee level for a fresh transaction.

    Fee levels are multiples of the base level 256. Most transactions pay
    the minimum; a seeded minority pays 2x, 4x or 8x. Returns a fee level
    (int, multiple of 256, at least min_fee_level).
    """
    r = rng.random()
    if r < 0.70:
        mult = 1
    elif r < 0.88:
        mult = 2
    elif r < 0.97:
        mult = 4
    else:
        mult = 8
    return max(min_fee_level, 256 * mult)


def _value_xrp(rng):
    """Transaction value in XRP, log-uniform between 10 and 10,000."""
    return round(10.0 ** rng.uniform(1.0, 4.0), 2)


def _poisson(rng, lam):
    """Knuth's algorithm for Poisson sampling (stdlib only)."""
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _median(values):
    if not values:
        return 0.0
    n = len(values)
    if n % 2 == 1:
        return float(values[n // 2])
    return (values[n // 2 - 1] + values[n // 2]) / 2.0


def _percentile(values, q):
    if not values:
        return 0.0
    idx = int(math.ceil(q * len(values))) - 1
    return float(values[max(0, idx)])


def generate(scenario, seed):
    """Run one seeded simulation. Returns (events, stats).

    events: list of dicts, one per transaction, with keys
      txid, scenario, seed, account, seq, fee_level, value_xrp,
      broadcast_ledger, outcome ("validated", "hijacked", "expired",
      "dropped"), outcome_ledger, exposure_s, hijacked (0/1),
      recovery_s, kind.
    Commit transactions have kind "commit" and value 0; their reveal
    carries the value and kind "reveal". Adversary transactions are
    never recorded as events (they are the attacker's tool, not a
    victim outcome).
    stats: dict of aggregate counters for the run. Percentages in the
    exposure table are computed over value-carrying transactions
    (payments and reveals); commits are counted separately.
    """
    cfg = dict(DEFAULTS)
    cfg.update(scenario.get("params", {}))
    rng = random.Random(seed)
    close = cfg["ledger_close_s"]
    target = cfg["target_tx_per_ledger"]
    base_level = cfg["base_fee_level"]
    min_mult = cfg["min_escalation_multiplier"]
    run_ledgers = cfg["run_ledgers"]
    arrival_rate = cfg["arrival_rate_per_s"]
    lls_window = cfg["last_ledger_window"]
    min_fee = cfg["min_fee_level"]
    commit_reveal = cfg["commit_reveal"]
    sig_scheme = cfg["signature_scheme"]
    recovery_s = cfg["recovery_seconds"]
    fee_premium = cfg["fee_premium"]

    queue_max = max(cfg["queue_size_min"],
                    cfg["queue_ledgers"] * target)

    # Live state.
    queue = []                  # Tx objects waiting for admission
    active = {}                 # txid -> Tx, unresolved value txs
    adversary_pending = []      # (victim_txid, Tx) competing txs
    pending_victims = set()     # victim txids with a competing tx pending
    queued_per_account = {}     # account -> queued tx count (cap check)
    events = []                 # one dict per resolved transaction
    # Median fee level of the previous ledger (starts at base level).
    prev_median_fee = base_level
    tx_counter = 0
    stats = {
        "broadcast": 0, "validated": 0, "hijacked": 0, "expired": 0,
        "dropped": 0, "adversary_attempts": 0, "adversary_tx_validated": 0,
        "value_hijacked_xrp": 0.0, "value_broadcast": 0,
        "validated_value": 0, "expired_value": 0, "dropped_value": 0,
        "commits_validated": 0,
    }

    def record(tx, outcome, outcome_ledger, hijacked=False):
        """Resolve one transaction, append its event line, update stats.

        Exposure is measured from the broadcast instant (ledger index
        plus the seeded arrival offset inside that ledger interval) to
        the close of the outcome ledger.
        """
        active.pop(tx.txid, None)
        exposure = (outcome_ledger - tx.broadcast_ledger) * close + \
            (close - tx.arrival_offset_s)
        events.append({
            "txid": tx.txid,
            "scenario": scenario["name"],
            "seed": seed,
            "account": tx.account,
            "seq": tx.seq,
            "fee_level": tx.fee_level,
            "value_xrp": tx.value_xrp,
            "broadcast_ledger": tx.broadcast_ledger,
            "outcome": outcome,
            "outcome_ledger": outcome_ledger,
            "exposure_s": round(exposure, 1),
            "hijacked": 1 if hijacked else 0,
            "recovery_s": recovery_s,
            "kind": tx.kind,
        })
        stats[outcome] += 1
        if tx.kind in ("payment", "reveal"):
            if outcome == "validated":
                stats["validated_value"] += 1
            elif outcome == "expired":
                stats["expired_value"] += 1
            elif outcome == "dropped":
                stats["dropped_value"] += 1
        if tx.kind == "commit" and outcome == "validated":
            stats["commits_validated"] += 1
        if hijacked:
            stats["value_hijacked_xrp"] = round(
                stats["value_hijacked_xrp"] + tx.value_xrp, 2)

    def required_fee_level(count, multiplier):
        if count <= target:
            return base_level
        return multiplier * (count * count) / float(target * target)

    for ledger in range(run_ledgers):
        # ---- 1. New arrivals during this ledger interval ----
        # Poisson arrivals: expected count = rate * close seconds.
        # Each transaction comes from a distinct account (account =
        # tx_counter, sequence 1), so the arrival stream is identical
        # for every scenario at the same seed.
        expected = arrival_rate * close
        n_arrivals = _poisson(rng, expected)
        for _ in range(n_arrivals):
            tx_counter += 1
            account = tx_counter
            fee = _fee_level(rng, min_fee)
            last_valid = ledger + max(lls_window,
                                      cfg["min_last_ledger_buffer"])
            offset = rng.random() * close
            if commit_reveal:
                # Phase 1: commit transaction. Carries no value and no
                # public key: the adversary cannot hijack it (the
                # commit binds the transaction content by hash).
                commit = Tx(_txid(seed, tx_counter), account, 1, fee,
                            0.0, ledger, offset, last_valid,
                            kind="commit", phase="commit")
                active[commit.txid] = commit
                queue.append(commit)
                queued_per_account[account] = \
                    queued_per_account.get(account, 0) + 1
                stats["broadcast"] += 1
            else:
                tx = Tx(_txid(seed, tx_counter), account, 1, fee,
                        _value_xrp(rng), ledger, offset, last_valid,
                        kind="payment")
                active[tx.txid] = tx
                queue.append(tx)
                queued_per_account[account] = \
                    queued_per_account.get(account, 0) + 1
                stats["broadcast"] += 1
                stats["value_broadcast"] += 1
            # Enforce the per-account queue cap (TxQ maximumTxnPerAccount).
            # Non-binding here (one transaction per account), kept for
            # fidelity of the queue implementation.
            if queued_per_account[account] > cfg["max_tx_per_account"]:
                victim = queue.pop()
                queued_per_account[account] -= 1
                record(victim, "dropped", ledger)

        # ---- 2. Adversary: schedule competing transactions ----
        # A competing transaction is submitted once key recovery
        # completes, for every still-unresolved payment transaction
        # whose public key the adversary observed at broadcast. The
        # ready ledger is computed from the broadcast instant (ledger
        # index plus arrival offset) plus the recovery time. ML-DSA
        # signatures are quantum-resistant: recovery never completes.
        # Reveal transactions are not targeted: a forged reveal cannot
        # match the already-validated commit's content hash.
        if sig_scheme != "ml-dsa-65":
            for tx in list(active.values()):
                if tx.kind != "payment":
                    continue
                if tx.txid in pending_victims:
                    continue
                broadcast_time = tx.broadcast_ledger * close + \
                    tx.arrival_offset_s
                ready_ledger = int((broadcast_time + recovery_s) // close)
                if ledger >= ready_ledger:
                    stats["adversary_attempts"] += 1
                    adv_fee = int(tx.fee_level * fee_premium)
                    adv = Tx(_txid(seed, 10 ** 9 + tx_counter +
                                   len(adversary_pending)),
                             tx.account, tx.seq, adv_fee, tx.value_xrp,
                             ledger, 0.0, tx.last_valid_ledger,
                             kind="adversary", phase="competing")
                    adversary_pending.append((tx.txid, adv))
                    pending_victims.add(tx.txid)

        # ---- 3. Build the open ledger from the queue ----
        # Candidates: queued transactions plus pending adversary
        # transactions, in fee-level order (highest first, ties by
        # transaction ID ascending), same-account by sequence.
        candidates = sorted(
            queue + [a for _, a in adversary_pending],
            key=lambda t: (-t.fee_level, t.txid, t.seq))
        multiplier = max(prev_median_fee, min_mult)
        admitted = []
        admitted_fee_levels = []
        count = 0
        admitted_ids = set()
        for cand in candidates:
            if cand.fee_level < required_fee_level(count, multiplier):
                continue
            admitted.append(cand)
            admitted_ids.add(cand.txid)
            admitted_fee_levels.append(cand.fee_level)
            count += 1
        # Remove admitted transactions from the queue.
        new_queue = []
        for tx in queue:
            if tx.txid not in admitted_ids:
                new_queue.append(tx)
        queue = new_queue
        queued_per_account = {}
        for tx in queue:
            queued_per_account[tx.account] = \
                queued_per_account.get(tx.account, 0) + 1
        # Queue capacity: drop the lowest-fee transactions when full.
        if len(queue) > queue_max:
            # Drop lowest fee level first (documented FeeEscalation
            # behaviour: the queue drops the lowest-fee transactions).
            queue.sort(key=lambda t: (t.fee_level, t.txid))
            overflow = queue[:len(queue) - queue_max]
            queue = queue[len(queue) - queue_max:]
            for tx in overflow:
                record(tx, "dropped", ledger)
            queued_per_account = {}
            for tx in queue:
                queued_per_account[tx.account] = \
                    queued_per_account.get(tx.account, 0) + 1

        # ---- 4. Resolve admitted transactions ----
        # Adversary transactions first: if an adversary transaction is
        # admitted, its victim is hijacked (same account, same
        # sequence). A victim admitted in the same ledger loses only
        # if the adversary transaction ID sorts first under canonical
        # (hash) order; otherwise the victim validates and the
        # adversary transaction is discarded.
        adv_by_victim = {v: a for v, a in adversary_pending}
        still_pending = []
        for vtxid, adv in adversary_pending:
            if adv.txid not in admitted_ids and vtxid in active:
                # Still waiting: not admitted yet, victim still alive.
                still_pending.append((vtxid, adv))
            else:
                # Admitted (resolved this ledger) or victim already
                # resolved (validated, expired, or hijacked): the
                # competing transaction is stale, drop it.
                pending_victims.discard(vtxid)
        adversary_pending = still_pending
        # Victims hijacked by an admitted adversary transaction.
        hijacked_ids = set()
        for vtxid, adv in adv_by_victim.items():
            if adv.txid in admitted_ids:
                victim = active.get(vtxid)
                if victim is not None:
                    stats["adversary_tx_validated"] += 1
                    if victim.txid in admitted_ids:
                        # Same ledger: canonical order decides.
                        if adv.txid < victim.txid:
                            hijacked_ids.add(vtxid)
                    else:
                        hijacked_ids.add(vtxid)
        # A victim whose competing transaction validated is hijacked
        # now, even though the victim itself was not admitted: the
        # competing transaction (same account, same sequence) consumes
        # the sequence, so the victim can never validate. Remove such
        # victims from the queue and record the hijack. Victims
        # admitted in this same ledger are decided by canonical order
        # in the resolution loop below.
        hijacked_now = set()
        # Sort: iterating a set of strings is hash-order dependent
        # (PYTHONHASHSEED), so an unsorted iteration would make the
        # event-log line order differ between processes for the same
        # seed. Sorting by txid keeps the log byte-reproducible.
        for vtxid in sorted(hijacked_ids):
            victim = active.get(vtxid)
            if victim is not None and victim.txid not in admitted_ids:
                hijacked_now.add(vtxid)
                record(victim, "hijacked", ledger, hijacked=True)
        if hijacked_now:
            queue = [tx for tx in queue if tx.txid not in hijacked_now]
        for cand in admitted:
            if cand.kind == "adversary":
                continue
            if cand.txid in hijacked_ids:
                record(cand, "hijacked", ledger, hijacked=True)
                continue
            if cand.kind == "commit":
                # The commit validated. The reveal is now broadcast:
                # it carries the value and the public key, but it is
                # bound to the validated commit, so a forged reveal
                # cannot match it.
                record(cand, "validated", ledger)
                tx_counter += 1
                fee = _fee_level(rng, min_fee)
                reveal = Tx(_txid(seed, tx_counter), cand.account, 1,
                            fee, _value_xrp(rng), ledger,
                            rng.random() * close,
                            ledger + max(lls_window,
                                         cfg["min_last_ledger_buffer"]),
                            kind="reveal", phase="reveal",
                            commit_id=cand.txid)
                active[reveal.txid] = reveal
                queue.append(reveal)
                queued_per_account[cand.account] = \
                    queued_per_account.get(cand.account, 0) + 1
                stats["broadcast"] += 1
                stats["value_broadcast"] += 1
                continue
            record(cand, "validated", ledger)

        # Remove admitted adversary transactions from the pending list
        # (they have resolved: either they hijacked, or they lost the
        # same-ledger ordering and are discarded).
        remaining = []
        for v, a in adversary_pending:
            if a.txid not in admitted_ids:
                remaining.append((v, a))
            else:
                pending_victims.discard(v)
        adversary_pending = remaining

        # ---- 5. Expiry: LastLedgerSequence passed ----
        kept = []
        for tx in queue:
            if ledger >= tx.last_valid_ledger:
                record(tx, "expired", ledger)
            else:
                kept.append(tx)
        queue = kept
        queued_per_account = {}
        for tx in queue:
            queued_per_account[tx.account] = \
                queued_per_account.get(tx.account, 0) + 1

        # ---- 6. Update the escalation multiplier ----
        if admitted_fee_levels:
            ordered = sorted(admitted_fee_levels)
            n = len(ordered)
            prev_median_fee = (ordered[n // 2] +
                               ordered[(n - 1) // 2]) / 2.0

    # ---- End of run: everything still queued is unresolved ----
    # Unresolved transactions are not counted in the exposure table;
    # they are reported separately as still-queued at run end.
    stats["still_queued"] = len(queue)
    stats["still_queued_value_xrp"] = round(
        sum(t.value_xrp for t in queue), 2)

    exposures = [e["exposure_s"] for e in events]
    exposures.sort()
    stats["median_exposure_s"] = _median(exposures)
    stats["p95_exposure_s"] = _percentile(exposures, 0.95)
    stats["validated_count"] = len(exposures)
    n_settled_value = stats["validated_value"] + stats["hijacked"]
    stats["hijack_rate"] = round(
        stats["hijacked"] / float(n_settled_value), 4) \
        if n_settled_value else 0.0
    stats["total_broadcast"] = stats["broadcast"]
    return events, stats


if __name__ == "__main__":
    import json
    import sys
    scenario = json.loads(sys.argv[1]) if len(sys.argv) > 1 else \
        {"name": "baseline", "params": {}}
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1001
    events, stats = generate(scenario, seed)
    print("scenario=%s seed=%d events=%d" %
          (scenario["name"], seed, len(events)))
    for key in ("validated", "hijacked", "expired", "dropped",
                "hijack_rate", "median_exposure_s", "p95_exposure_s",
                "value_hijacked_xrp"):
        print("%s=%s" % (key, stats[key]))
    for e in events[:10]:
        print("tx=%s %s ledger=%d outcome=%s exposure_s=%.1f" %
              (e["txid"][:12], e["kind"], e["broadcast_ledger"],
               e["outcome"], e["exposure_s"]))
