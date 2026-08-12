#!/usr/bin/env python3
"""Enumerate EVERY declaration in the eth-total-supply-safety submodule.

Why a source scan when the Lean exporter exists: the exporter answers "is this
named theorem proved, and what does it say" for a *target list*. Something has
to produce that target list first, and for a 33k-line formalization with 3000+
theorems that has to be exhaustive rather than a hand-picked sample — in
particular the lemma layer (`Lemmata/`), which is where most of the proved
substance lives and which a headline-theorem-only target list silently drops.

So this walks the submodule's `.lean` sources and records every `theorem`,
`def`, `structure`, `inductive`, `abbrev` and `instance` with its
fully-qualified name (namespace stack tracked), source range, verbatim
signature, docstring, and layer. Output feeds:

  1. the exporter target list (`lean-ethtotal/targets.txt`), and
  2. `tools/ethtotal-triage.py`, which selects the theorem_map targets from it.

It is a *lexical* scan: it never claims anything about proof status. Anything
that matters for the audit verdict (`lean_status`, hypotheses, axioms) comes
from `lake exe speca-export`, not from here.

Usage:
    python3 tools/ethtotal-inventory.py \
        [--src external/eth-total-supply-safety] \
        [--out data/ethtotal_inventory.json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

# A declaration starts at column 0 (the formalization never indents them),
# optionally behind modifiers/attributes.
DECL_RE = re.compile(
    r"^(?P<mods>(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+|unsafe\s+|partial\s+)*)"
    r"(?P<kind>theorem|lemma|def|abbrev|instance|structure|inductive|class|axiom|opaque|example)\s+"
    r"(?P<name>[^\s:({\[⦃⟨]+)"
)
NAMESPACE_RE = re.compile(r"^namespace\s+(\S+)")
END_RE = re.compile(r"^end(?:\s+(\S+))?\s*$")
SECTION_RE = re.compile(r"^section(?:\s+(\S+))?\s*$")

LAYERS = [
    ("EthTotal/AtomicDef/", "AtomicDef"),
    ("EthTotal/Lemmata/Derives/", "Lemmata.Derives"),
    ("EthTotal/Lemmata/EthConcepts/", "Lemmata.EthConcepts"),
    ("EthTotal/Theorem/Main/Category/", "Theorem.Main.Category"),
    ("EthTotal/Theorem/Main/", "Theorem.Main"),
    ("EthTotal/Theorem/EthConcepts/", "Theorem.EthConcepts"),
    ("EthTotal/Theorem/Derives/", "Theorem.Derives"),
    ("EthTotal/Extentions/", "Extentions"),
]


def layer_of(rel: str) -> str:
    for prefix, layer in LAYERS:
        if rel.startswith(prefix):
            return layer
    if rel.endswith("Audit.lean"):
        return "Audit"
    return "Root"


def module_of(rel: str) -> str:
    return rel[: -len(".lean")].replace("/", ".")


def scan_file(path: Path, rel: str) -> list[dict]:
    """Every declaration in one file, with its namespace-qualified name."""
    lines = path.read_text(encoding="utf-8").split("\n")
    ns: list[str] = []
    # `section` also consumes an `end`, so the stack records what each `end` closes.
    scopes: list[tuple[str, str | None]] = []  # (kind, name) kind in {namespace, section}
    decls: list[dict] = []
    doc_open = False
    doc_buf: list[str] = []
    pending_doc = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # docstring blocks (/-- ... -/) attach to the next declaration
        if doc_open:
            doc_buf.append(stripped)
            if stripped.endswith("-/"):
                doc_open = False
                pending_doc = "\n".join(doc_buf).removeprefix("/--").removesuffix("-/").strip()
                doc_buf = []
            i += 1
            continue
        if stripped.startswith("/--"):
            if stripped.endswith("-/") and len(stripped) > 5:
                pending_doc = stripped[3:-2].strip()
            else:
                doc_open = True
                doc_buf = [stripped]
            i += 1
            continue

        m = NAMESPACE_RE.match(line)
        if m:
            ns.append(m.group(1))
            scopes.append(("namespace", m.group(1)))
            i += 1
            continue
        m = SECTION_RE.match(line)
        if m:
            scopes.append(("section", m.group(1)))
            i += 1
            continue
        m = END_RE.match(line)
        if m:
            if scopes:
                kind, _ = scopes.pop()
                if kind == "namespace" and ns:
                    ns.pop()
            i += 1
            continue

        m = DECL_RE.match(line)
        if m and not line.startswith(" "):
            kind = m.group("kind")
            # `theorem foo.{v} ...` — a universe binder directly after the name
            # leaves a trailing dot on the captured token; it is not part of the
            # declaration name and Lean would parse it as an anonymous name.
            name = m.group("name").rstrip(".")
            start = i + 1  # 1-based
            # the declaration runs until the next column-0 declaration/namespace
            # boundary or a blank-line-separated top-level command
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt and not nxt.startswith((" ", "\t")):
                    if (
                        DECL_RE.match(nxt)
                        or NAMESPACE_RE.match(nxt)
                        or END_RE.match(nxt)
                        or SECTION_RE.match(nxt)
                        or nxt.startswith(("/--", "/-!", "#", "variable", "universe", "open", "import", "attribute", "@["))
                    ):
                        break
                j += 1
            body = "\n".join(lines[i:j]).rstrip()
            # signature = text up to the top-level `:=` (term-mode) — the part
            # that states WHAT is proved, without the proof term
            sig = body
            depth = 0
            for k, ch in enumerate(body):
                if ch in "([{⟨":
                    depth += 1
                elif ch in ")]}⟩":
                    depth -= 1
                elif ch == ":" and depth == 0 and body[k : k + 2] == ":=":
                    sig = body[:k].rstrip()
                    break
            decls.append(
                {
                    "name": ".".join(ns + [name]) if ns else name,
                    "short_name": name,
                    "kind": "theorem" if kind == "lemma" else kind,
                    "module": module_of(rel),
                    "file": rel,
                    "layer": layer_of(rel),
                    "line_start": start,
                    "line_end": j,
                    "signature": sig,
                    "doc": pending_doc,
                    "private": "private" in m.group("mods"),
                }
            )
            pending_doc = ""
            i = j
            continue

        if stripped:
            pending_doc = ""
        i += 1
    return decls


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="external/eth-total-supply-safety")
    ap.add_argument("--out", default="data/ethtotal_inventory.json")
    args = ap.parse_args()

    src = Path(args.src)
    files = sorted(p for p in src.rglob("*.lean") if ".lake" not in p.parts)
    decls: list[dict] = []
    for p in files:
        rel = str(p.relative_to(src))
        if rel in {"lakefile.lean", "Main.lean"}:
            continue
        decls.extend(scan_file(p, rel))

    try:
        rev = subprocess.run(
            ["git", "-C", str(src), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        rev = "unknown"

    by_layer: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for d in decls:
        if d["kind"] == "theorem":
            by_layer[d["layer"]] = by_layer.get(d["layer"], 0) + 1
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1

    out = {
        "source": "NyxFoundation/eth-total-supply-safety",
        "rev": rev,
        "extracted_by": "tools/ethtotal-inventory.py (lexical scan; proof status comes from lake exe speca-export, never from here)",
        "file_count": len(files),
        "declaration_count": len(decls),
        "theorems_by_layer": dict(sorted(by_layer.items())),
        "declarations_by_kind": dict(sorted(by_kind.items())),
        "declarations": decls,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(decls)} declarations from {len(files)} files -> {args.out}")
    print(f"  by kind:  {out['declarations_by_kind']}")
    print(f"  theorems: {out['theorems_by_layer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
