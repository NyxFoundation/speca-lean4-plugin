# `@[speca_spec]` — spec annotations in gasper-lean4 (proposal)

Status: **proposal only** (issue #5, items C1/C2). The attribute must live in
gasper-lean4's Audit module, which needs write access to
`NyxFoundation/gasper-lean4` and maintainer coordination (issue #9, G2).
Nothing here is implemented in gasper-lean4 yet; this document is the concrete
convention we propose to its maintainers. Until it lands, spec anchoring in
this plugin is label-derived via `data/anchor_map.json` (C3/C4/C5).

## Goal

Anchor each exported theorem to the consensus-specs section it formalizes *at
the declaration site*, in Lean, so the anchor travels with the proof instead of
living only in this plugin's mapping tables. The exporter then reads the
annotation mechanically and the plugin derives `spec_reference`/`covers` from
it — no prose judgment, and a divergence between the Lean-side annotation and
the label-derived anchor becomes machine-checkable.

## C1 — the attribute

Proposed addition to gasper-lean4's Audit module (where `#mr_audit_json`
already lives), so the main theory files gain no new imports:

```lean
/-- `@[speca_spec ref]` anchors a declaration to a consensus-specs section.
`ref` is `"consensus-specs:<doc-path>#<pyspec-symbol>"`, e.g.
`"consensus-specs:specs/phase0/beacon-chain.md#process_justification_and_finalization"`. -/
syntax (name := specaSpec) "speca_spec" str : attr

initialize specaSpecExt :
    SimplePersistentEnvExtension (Name × String) (NameMap String) ← ...

initialize registerBuiltinAttribute {
  name := `specaSpec
  descr := "consensus-specs anchor for SPECA export"
  add := fun decl stx _ => do
    let ref := ... -- parse the string literal
    modifyEnv (specaSpecExt.addEntry · (decl, ref))
}
```

Design points:

- **Value format** is exactly the `spec_reference` string this plugin already
  emits: `consensus-specs:<doc>#<symbol>`. One vocabulary end to end; the
  symbol part must be a pyspec section name (`process_*` etc.) from the
  ethereum-vuln-dataset label vocabulary (`docs/label_design.md`), so
  annotations stay inside the controlled vocabulary.
- **Repeatable**: a theorem touching two sections may carry the attribute
  twice; the first is the primary anchor.
- **Persistent env extension**, so the exporter (a downstream lake package)
  can read annotations from the imported environment without re-elaborating
  gasper-lean4 sources.
- **Docstring fallback** for declarations where an attribute is awkward
  (e.g. `instance`s): a line `speca-spec: consensus-specs:...` inside the
  declaration docstring, parsed by the exporter with the same precedence.

## C2 — pilot annotations

The 25 current target theorems, with the anchors already derived in
`data/anchor_map.json` (`defs` rows). Example:

```lean
@[speca_spec "consensus-specs:specs/phase0/beacon-chain.md#process_justification_and_finalization"]
theorem k_safety' ... := ...

@[speca_spec "consensus-specs:specs/phase0/beacon-chain.md#process_slashings"]
theorem two_justified_same_height_slashed ... := ...
```

The full proposed assignment is mechanical: for every row in
`data/anchor_map.json` `defs`, annotate `lean_def` with `spec_reference`.

## Exporter and plugin consumption (this repo, once C1/C2 land)

1. `lake exe speca-export` reads `specaSpecExt` for each target and adds a
   `spec_annotations: [string]` field to the health record (empty list when
   unannotated — never invented).
2. `mapping.py` precedence for `spec_reference` becomes:
   declaration annotation > anchor table (`data/anchor_map.json`) > inline
   fallback. `covers` fallback uses the symbol part the same way.
3. **Honesty gate**: if a theorem carries an annotation that disagrees with
   its label-derived anchor, the emitter flags it (like the B5
   type-consistency gate) instead of silently preferring either side; CI
   fails until the label or the annotation is fixed.

## Why not annotate from this repo today

- The Audit module is in `NyxFoundation/gasper-lean4`; we do not push there
  without maintainer coordination (issue #9 G2 tracks that conversation).
- Vendoring a copy of the attribute in this plugin would fork the audit
  surface and the annotations would not travel with the proofs.
