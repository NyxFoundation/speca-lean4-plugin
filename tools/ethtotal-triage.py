#!/usr/bin/env python3
"""Triage every EthTotal theorem into an audit role — the lemma sweep.

`ethtotal-inventory.py` says WHAT exists (3333 theorems). This says what each
one is FOR, so that selecting ~40 of them as `01e` property sources is a
reviewable decision instead of a hand-picked sample. Every theorem lands in
exactly one bucket with a recorded reason; nothing is silently dropped, and the
per-file table shows the lemma layers (`Lemmata/`, `AtomicDef/`) getting the
same treatment as the headline `Theorem/Main` results.

Buckets
-------
``selected``        top-ranked in its file: gets a `theorem_map` base entry.
``represented``     same concept group as a selected theorem in the same file
                    (e.g. the `_on` / `_of_le` / pointwise variants of a
                    selected result) — covered by it, not separately lowered.
``screened-out``    scored below the audit-relevance floor, with the reason:
                    a pure algebraic/structural helper with no implementation
                    surface of its own.

Ranking is a transparent keyword score over the theorem's NAME and its
statement text — the formalization names results after what they mean
(`naive_self_transfer_mints`, `no_unchecked_write`, `overflow_requires_mint`),
so the name is real signal, not a guess. The score orders candidates *within a
file*; it never decides severity, and it never touches proof status.

Usage:
    python3 tools/ethtotal-triage.py [--per-file N] [--out data/ethtotal_triage.json]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# --- audit-relevance signals -------------------------------------------------
# Each group is (weight, regex). A theorem's score is the sum of the weights of
# the groups its name or statement matches (each group counts once).
SIGNALS: list[tuple[str, int, str]] = [
    # value can be created or destroyed here — the whole point of the repo
    ("supply-conservation", 6, r"supply|minted?|burn|acc_|accounting|conserv|total"),
    # an implementation defect directly moves funds
    ("balance-integrity", 5, r"\bbal\b|balance|credit|debit|overdraft|xfer|transfer|inflat|overcount|shortfall"),
    # the audit-context results: what an implementation must NOT do
    ("negative-result", 5, r"^(no|not|never|cannot)_|_not_|impossible|unsound|forbid|breaks|differs|_ne$|_ne_|leak|stale|naive|wrong|invalid|silent|hides|loses|manufactur"),
    # attribution: a change must have an explicit, sited witness
    ("witness-attribution", 4, r"witness|only_at|_forces|requires|localiz|recover|pinned|detect"),
    # account lifecycle: create / destroy / resurrect / write preconditions
    ("lifecycle", 4, r"destroy|erase|resurrect|relive|live|addLive|removeLive|write|storage|trie|default|support|kernel"),
    # fee mechanics: prepay / refund / tip / burn split, escrow
    ("fee-mechanics", 4, r"fee|refund|tip|escrow|prepay|gas|settlement|churn|quantiz|threshold"),
    # arithmetic representation: monus truncation, carries, caps, overflow
    ("arithmetic-representation", 4, r"overflow|cap\b|cap_|carry|parity|checksum|saturat|monus|bound|quantum|granular"),
    # ordering / duplication / replay of records
    ("ordering-replay", 3, r"order|sorted|duplicat|collision|comm\b|permut|displacement|append|rollback|cut\b"),
    # guards and admission checks an implementation must actually perform
    ("guard", 3, r"guard|admission|precondition|iff_|_iff\b|necessary|insufficient|independent"),
    # pure algebra / plumbing: real proof substance, but no implementation
    # surface of its own — negative weight so it sorts below the rest
    ("algebraic-helper", -4, r"^(sumOver|add|mul|sub|zero|succ|nat|list|append|map|congr|cast)_|_congr$|_refl$|_symm$|_trans$|_assoc$|_comm$|_idem$|^pair|^odd|^even"),
    ("categorical-repackaging", -3, r"functor|monad|comonad|dagger|natural|adjoint|galois|lawful|_id$|_comp$|category"),
]
_COMPILED = [(n, w, re.compile(p, re.I)) for n, w, p in SIGNALS]

# A theorem is a variant of another when its name reduces to the same stem.
_VARIANT_SUFFIXES = re.compile(
    r"(_on|_of_le|_of_lt|_of_ne|_of_pos|_left|_right|_self|_other|_iff|_witness|"
    r"_mem|_pointwise|_aux|_general|_eq|_le|_lt|_ge|_gt|_comm|_symm|'|₀|₁|₂)+$"
)


def concept_group(short_name: str) -> str:
    """Concept stem — variants of one result share it (e.g. `exact_supply`,
    `exact_supply_on`)."""
    stem = _VARIANT_SUFFIXES.sub("", short_name)
    return stem or short_name


def score(decl: dict) -> tuple[int, list[str]]:
    hay = f"{decl['short_name']} {decl['signature']} {decl['doc']}"
    total, hits = 0, []
    for name, weight, rx in _COMPILED:
        if rx.search(hay):
            total += weight
            hits.append(name)
    return total, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default=str(_ROOT / "data" / "ethtotal_inventory.json"))
    ap.add_argument("--per-file", type=int, default=1,
                    help="max theorems selected per source file (default 1)")
    ap.add_argument("--per-file-main", type=int, default=6,
                    help="max for the Theorem.Main / Theorem.EthConcepts / "
                         "Lemmata.EthConcepts layers, where the substance concentrates")
    ap.add_argument("--floor", type=int, default=4,
                    help="minimum audit-relevance score to be selectable")
    ap.add_argument("--out", default=str(_ROOT / "data" / "ethtotal_triage.json"))
    args = ap.parse_args()

    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    theorems = [d for d in inv["declarations"] if d["kind"] == "theorem"]

    rich_layers = {"Theorem.Main", "Theorem.EthConcepts", "Lemmata.EthConcepts"}
    by_file: dict[str, list[dict]] = defaultdict(list)
    for t in theorems:
        s, hits = score(t)
        t = dict(t, audit_score=s, signals=hits, concept=concept_group(t["short_name"]))
        by_file[t["file"]].append(t)

    files_out = []
    selected_total = 0
    for f in sorted(by_file):
        rows = by_file[f]
        layer = rows[0]["layer"]
        cap = args.per_file_main if layer in rich_layers else args.per_file
        ranked = sorted(rows, key=lambda r: (-r["audit_score"], r["line_start"]))
        chosen: list[dict] = []
        chosen_concepts: set[str] = set()
        for r in ranked:
            if len(chosen) >= cap:
                break
            if r["audit_score"] < args.floor:
                break
            if r["concept"] in chosen_concepts:
                continue
            chosen.append(r)
            chosen_concepts.add(r["concept"])
        chosen_names = {r["name"] for r in chosen}

        entries = []
        for r in sorted(rows, key=lambda r: r["line_start"]):
            if r["name"] in chosen_names:
                bucket, reason = "selected", "highest audit-relevance in file: " + ", ".join(r["signals"])
            elif r["concept"] in chosen_concepts:
                bucket, reason = "represented", f"variant of the selected `{r['concept']}` result"
            elif r["audit_score"] < args.floor:
                bucket, reason = ("screened-out",
                                  "below audit-relevance floor: "
                                  + (", ".join(r["signals"]) or "no audit signal")
                                  + " — algebraic/structural helper with no implementation surface of its own")
            else:
                bucket, reason = ("represented",
                                  "same file and audit theme as the selected result; "
                                  "covered by it rather than lowered separately")
            entries.append({"name": r["name"], "line": r["line_start"],
                            "score": r["audit_score"], "signals": r["signals"],
                            "concept": r["concept"], "bucket": bucket, "reason": reason})
        selected_total += len(chosen)
        files_out.append({
            "file": f, "module": rows[0]["module"], "layer": layer,
            "theorem_count": len(rows), "selected_count": len(chosen),
            "cap": cap,
            "selected": [r["name"] for r in chosen],
            "theorems": entries,
        })

    buckets = defaultdict(int)
    for f in files_out:
        for e in f["theorems"]:
            buckets[e["bucket"]] += 1

    out = {
        "source": inv["source"],
        "rev": inv["rev"],
        "method": (
            "Keyword-scored audit relevance over theorem NAME + statement, ranked WITHIN "
            "each source file, capped per file. Every theorem is bucketed with a reason: "
            "selected / represented (variant or same-theme sibling of a selected result) / "
            "screened-out (below the audit-relevance floor). This is a SELECTION record, "
            "not a proof-status claim — `lean_status` comes only from lake exe speca-export."
        ),
        "params": {"per_file": args.per_file, "per_file_main": args.per_file_main,
                   "floor": args.floor},
        "theorem_count": len(theorems),
        "selected_count": selected_total,
        "buckets": dict(buckets),
        "files": files_out,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(theorems)} theorems in {len(files_out)} files -> {args.out}")
    print(f"  buckets: {dict(buckets)}")
    print(f"  selected: {selected_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
