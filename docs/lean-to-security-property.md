# Lean → security property: proof-frontier design

## Decision

SPECA does not translate a Lean theorem by copying only its final conclusion,
and it does not expose every proof lemma as a separate top-level checklist
item. The unit shown to an auditor is a **root-centred property packet**:

```text
root preconditions
∧ implementation-checkable supporting facts
⇒ root security guarantee
```

The root theorem remains the security guarantee. Local theorem/lemma
conclusions that are stronger than the root conclusion become supporting audit
facts and derived implementation obligations. Definitions, typeclass plumbing,
and routine library/arithmetic normalization are retained as provenance but do
not become checklist controls.

This is the right compromise for an audit in which the auditor reads only
01e: the proof chain is not hidden in Lean, but the checklist is not inflated
to one row per lemma.

## Why root-only is insufficient

Suppose a local lemma proves:

```text
after zeroing and crediting v, the stored balance equals v
```

and the root theorem proves only:

```text
if v != 0, the stored balance is nonzero
```

A property that checks only the root conclusion accepts an implementation that
writes any wrong nonzero value. The exact-equality lemma must therefore appear
as an audit check even though it is not a separate root property.

## 01e shape

Existing core fields (`text`, `assertion`, severity, reachability, and so on)
remain unchanged. Proof-aware generated properties additionally carry:

```json
{
  "audit_packet": {
    "guarantee": "the root security guarantee",
    "preconditions": ["all root must-establish conditions"],
    "supporting_facts": [
      {
        "fact_id": "FACT-1",
        "source_fact_ids": ["ROOT", "L001"],
        "claim": "the strong semantic fact proved by the lemma",
        "check": "what the auditor checks in implementation logic",
        "expected": "the exact expected behaviour",
        "flag_if": "the observable suspicious condition"
      }
    ],
    "derived_obligations": [
      {
        "obligation_id": "OBS-1",
        "check": "one implementation-level check",
        "expected": "expected result",
        "flag_if": "failure signal",
        "supports": ["FACT-1"]
      }
    ],
    "derivation": "how the checks establish the root guarantee",
    "omitted_facts": [
      {"source_fact_id": "L002", "reason": "routine arithmetic normalization"}
    ]
  },
  "x_proof_closure": "exact project-local theorem/lemma closure",
  "x_proof_dependency_stats": "closure counts and unresolved definition/constants"
}
```

`audit_packet` is the auditor-facing content. `x_proof_closure` is the
machine-readable audit trail carried in the same 01e artifact; it lets a
reviewer verify what was available to the generator without reopening Lean.
SPECA 02c still performs the client-specific file/function mapping. This stage
must not invent those locations.

## Generation flow

```text
spec / Lean export
  → root theorem + transitive proof_constants closure
  → retain local theorem/lemma conclusions
  → classify semantic facts vs definitions/library noise
  → synthesize one root-centred audit packet
  → verify source fact IDs and closure coverage
  → fidelity repair against the whole closure
  → dataset-indexed few-shot style cards
  → quality judge/improve of only text/assertion
  → emit 01e
```

The generator prompt receives all root `must-establish` obligations, not an
arbitrary single selected obligation. It receives the proof-DAG theorem
records as numbered `L001`, `L002`, … facts. Every supporting fact must cite
those IDs. A fact may be omitted only with an explicit reason.

The quality loop may sharpen the short top-level text and assertion, but the
packet is the semantic anchor. Fidelity review is closure-aware and can repair
both the prose and the packet.

The ethereum-vuln-dataset enters only at this final wording step. Matching
rows select a small set of defensive weak/strong style cards for the failure
class. Titles, attack paths, clients, and functions are deliberately excluded.
The cards teach the model to name the operation, guard, exact operands or
state, expected result, and flag condition; they cannot add facts to the
Lean-derived packet.

## Fidelity gates

The following are separate gates:

1. **Structural gate** — every source reference is a real root or closure fact;
   every supporting obligation refers to an existing fact.
2. **Coverage gate** — every proof-DAG fact is either represented by a
   supporting fact or explicitly omitted with a reason.
3. **Strength gate** — an exact equality, bound, membership, conservation, or
   ordering fact may not be silently reduced to a weaker boolean consequence.
4. **Derivation gate** — where a formalized packet expression exists, a Lean
   wrapper checks that the selected frontier entails the root conclusion.
5. **Prose gate** — an independent LLM checks actionability, specificity and
   unsupported implementation additions. It is not the semantic verifier.

The CHK-GEN-01 counterexample is the canonical regression: `balance != 0`
alone is rejected because the stronger `balance == v` fact is in the closure.

In the 2026-08-14 EthTotal run, 45 generated packets were produced. Their
closure contains 571 theorem/lemma records in total (the largest single
closure has 56 records); every closure record was either cited or explicitly
omitted, and all 45 packets passed the structural and coverage checks. One
root theorem has no project-local theorem/lemma health record beneath it, so
its packet is correctly root-only rather than fabricating a lemma closure.

## Promotion rule for standalone properties

A lemma becomes its own top-level property only when it is reused by multiple
root guarantees, represents an independent implementation failure mode, or
has a distinct high-impact audit surface. Otherwise it remains a nested
supporting fact in its root packet.

## Current implementation

`src/speca_lean4/frontier.py` computes the transitive health-record closure.
`tools/generate-properties.py` hashes that closure as canonical evidence and
asks the model for the packet. `schema.py` and `mapping.py` preserve the packet
and closure in 01e. `tools/refine-property-fidelity.py` reviews the packet
against the same closure. The existing five-axis improvement loop only mutates
the short `text`/`assertion` surface, so quality iteration cannot erase the
formal audit packet. The reviewed artifact is
`outputs/20260814-ethtotal/01e_PARTIAL_ethtotal.json`; it contains 390 total
properties, including the 45 generated CHK packets. The few-shot improvement
round raised the logged pre-fidelity mean from 3.036 to 3.778. After the final
fidelity repair pass, the packet judge scored 3.467 against the 2.169
reference mean and still met the configured reference bar; the closure-aware
fidelity pass completed for all 45 packets.

For reviewer ergonomics, this path is the single canonical 01e for the track.
Each new run replaces it with the latest validated result; intermediate 01e
emits are kept only in the ignored run workspace, and before/after history is
reviewed through git.

For the existing 345 properties, a conservative non-LLM materializer now
attaches the same root-plus-closure packet shape directly from the Lean export.
Thus the full artifact has 390/390 packets and 1,712 root-closure records in
the 176 distinct theorem roots. The full Cloud Opus run then judged and
improved all 390 properties: the overall mean rose from 2.242 to 3.149 and
the configured reference bar was met. The quality evidence is in
`outputs/20260814-ethtotal/quality/`; it is supplementary to the canonical 01e.
