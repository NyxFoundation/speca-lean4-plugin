import SpecaExport.Basic

/-!
`speca-export` executable entry point.

    lake exe speca-export --targets <file>

`<file>` is a newline-delimited list of fully-qualified theorem names (blank
lines and `#` comments ignored). Emits the proof-health JSON (see
`SpecaExport.render`) to stdout. The Python driver (`src/speca_lean4/`) writes
the targets file from `theorem_map.json`, runs this exe, and maps the health
records onto the `01e` property schema.

The environment is loaded at runtime via `importModules` of both
`GasperBeaconChain.Core.All` (the substantive Theories/Lemmas) and
`GasperBeaconChain.Executable.All` (the decidable checker layer), then
`collectAxioms` runs in `CoreM` over that environment — the same axiom
mechanism gasper-lean4's compile-time `#mr_audit_json` uses.

A7 (verbatim proof source): `classify` records each declaration's source range
(`findDeclarationRanges?`); here, in IO, we locate the module's `.lean` file in
the lake package checkout (`.lake/packages/<pkg>/<Module/Path>.lean`) and slice
the declaration's lines verbatim (term/tactic code and its comments) into
`proof_source`. Best-effort: if the file or range is unavailable the field is
empty and `proof_code` (the pretty-printed proof term) is the fallback.

A7+ (issue #17): `findDeclarationRanges?` starts the range at the declaration
keyword, which excludes the leading doc comment and adjacent
explanatory comments, but per the gasper maintainer the proof and its
documentation are a pair. So the slice is widened upward over the contiguous
leading comment block (line comments and block comments ending directly above
the declaration, stopping at the first blank or code line). Purely textual and
verbatim: nothing is fabricated, the slice is only widened. The docstring also
travels as the structured `doc_string` field (from `findDocString?`, set in
`classify`).
-/

open Lean SpecaExport

/-- Parse a newline-delimited targets file; blank lines and `#` comments dropped. -/
def parseTargets (path : System.FilePath) : IO (List Name) := do
  let content ← IO.FS.readFile path
  let names := (content.splitOn "\n").filterMap fun line =>
    let t := line.trim
    if t.isEmpty || "#".isPrefixOf t then none else some t.toName
  return names

/-- Slice lines `startLine..endLine` (1-based, inclusive) out of `content`. -/
def sliceLines (content : String) (startLine endLine : Nat) : String :=
  if startLine == 0 then ""
  else
    let lines := (content.splitOn "\n").drop (startLine - 1)
    String.intercalate "\n" (lines.take (endLine + 1 - startLine))

/-- Scan upward from `endLine` (1-based; its trimmed text closes a block comment)
for the line whose trimmed text opens that block comment. -/
partial def findBlockCommentStart (lines : Array String) (endLine : Nat) : Option Nat :=
  if endLine == 0 then none
  else
    let t := (lines.getD (endLine - 1) "").trim
    if t.startsWith "/-" then some endLine
    else findBlockCommentStart lines (endLine - 1)

/-- A7+ (issue #17): 1-based line where the contiguous leading comment block
above `startLine` begins. Absorbs line comments and block comments that end
directly above the declaration, stopping
at the first blank or code line. Returns `startLine` unchanged when there is
no leading comment. -/
partial def widenToLeadingComments (lines : Array String) (startLine : Nat) : Nat :=
  if startLine ≤ 1 then startLine
  else
    let above := (lines.getD (startLine - 2) "").trim
    if above.startsWith "--" then
      widenToLeadingComments lines (startLine - 1)
    else if above.endsWith "-/" then
      match findBlockCommentStart lines (startLine - 1) with
      | some j => widenToLeadingComments lines j
      | none   => startLine
    else startLine

/-- Attach the verbatim declaration source (A7) by reading the module's `.lean`
file out of the lake package checkout, widened upward over the contiguous
leading comment block so the docstring travels with the proof (A7+, issue #17).
Best-effort; leaves the record unchanged when the module path or source range
is unknown. -/
def attachProofSource (h : SpecaExport.TheoremHealth) : IO SpecaExport.TheoremHealth := do
  if h.«module».isEmpty || h.declStartLine == 0 then
    return h
  let rel := System.FilePath.mk ((h.«module».replace "." "/") ++ ".lean")
  let pkgsDir : System.FilePath := System.FilePath.mk ".lake" / "packages"
  let mut src := ""
  if ← pkgsDir.isDir then
    for entry in ← pkgsDir.readDir do
      let cand := entry.path / rel
      if src.isEmpty && (← cand.pathExists) then
        let content ← IO.FS.readFile cand
        let lines := (content.splitOn "\n").toArray
        let widenedStart := widenToLeadingComments lines h.declStartLine
        src := sliceLines content widenedStart h.declEndLine
  return { h with proofSource := src }

def usage : String :=
  "usage: speca-export --targets <file>\n" ++
  "Emits proof-health JSON for the listed theorem names to stdout."

unsafe def main (args : List String) : IO Unit := do
  let targetPath ← match args with
    | ["--targets", p] => pure (System.FilePath.mk p)
    | _ => do IO.eprintln usage; IO.Process.exit 2
  let targets ← parseTargets targetPath
  initSearchPath (← findSysroot)
  enableInitializersExecution
  -- Import BOTH layers: the substantive proved theorems live in
  -- `GasperBeaconChain.Core.*` (Theories/Lemmas), and `Executable.All` adds the
  -- decidable checker versions on top. The bare root module reaches only Core.
  let env ← importModules
    #[{ module := `GasperBeaconChain.Core.All },
      { module := `GasperBeaconChain.Executable.All }] Options.empty
  -- pp.proofs so `proof_code` renders the actual proof term rather than `⋯`.
  let ppOpts : Options := Options.empty.setBool `pp.proofs true
  let coreCtx : Core.Context :=
    { fileName := "<speca-export>", fileMap := FileMap.ofString "", options := ppOpts }
  let coreState : Core.State := { env := env }
  let (records, _) ← (SpecaExport.classifyAll env targets).toIO coreCtx coreState
  let records ← records.mapM attachProofSource
  IO.println (SpecaExport.render records).compress
