import SpecaExport.Basic

/-!
`speca-export` driver — the IO half of the exporter, shared by every workspace.

    speca-export --targets <file> [--output <file>] [--src-root <dir>]...

`--targets` is a newline-delimited list of fully-qualified theorem names (blank
lines and `#` comments ignored). Emits the proof-health JSON (see
`SpecaExport.render`) to the `--output` file, or to stdout when `--output` is
omitted. Machine consumers must use `--output`: a cold `lake exe` interleaves
toolchain-download / dependency-fetch / build progress into stdout before this
executable runs, so stdout is a log channel, not a data channel (speca run
29749878252).

This module is project-agnostic. Each workspace has a two-line `Main.lean` that
imports the formalization's root modules (so lake builds them) and calls
`driverMain` with that project's `ProjectConfig` and runtime import list:

* `lean/Main.lean`           — gasper-lean4      (`GasperBeaconChain.*`)
* `lean-ethtotal/Main.lean`  — eth-total-supply-safety (`EthTotal.*`)

The environment is loaded at runtime via `importModules` of the given root
modules, then `collectAxioms` runs in `CoreM` over that environment — the same
axiom mechanism gasper-lean4's compile-time `#mr_audit_json` and
eth-total-supply-safety's `EthTotal/Audit.lean` (`#print axioms`) use.

A7 (verbatim proof source): `classify` records each declaration's source range
(`findDeclarationRanges?`); here, in IO, we locate the module's `.lean` file
and slice the declaration's lines verbatim (term/tactic code and its comments)
into `proof_source`. Sources are looked for under every `--src-root` (a path
dependency such as the `external/` submodule checkout) and under each
`.lake/packages/<pkg>` directory (a git dependency). Best-effort: if the file
or range is unavailable the field is empty and `proof_code` (the
pretty-printed proof term) is the fallback.

A7+ (issue #17): `findDeclarationRanges?` starts the range at the declaration
keyword, which excludes the leading doc comment and adjacent explanatory
comments, but per the gasper maintainer the proof and its documentation are a
pair. So the slice is widened upward over the contiguous leading comment block
(line comments and block comments ending directly above the declaration,
stopping at the first blank or code line). Purely textual and verbatim:
nothing is fabricated, the slice is only widened. The docstring also travels as
the structured `doc_string` field (from `findDocString?`, set in `classify`).
-/

open Lean

namespace SpecaExport

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
directly above the declaration, stopping at the first blank or code line.
Returns `startLine` unchanged when there is no leading comment. -/
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

/-- Directories to look for a dependency's `.lean` sources in: the explicitly
passed `--src-root`s (path dependencies, e.g. the `external/` submodule) first,
then every `.lake/packages/<pkg>` (git dependencies). -/
def sourceRoots (extraRoots : List System.FilePath) : IO (Array System.FilePath) := do
  let mut roots : Array System.FilePath := extraRoots.toArray
  let pkgsDir : System.FilePath := System.FilePath.mk ".lake" / "packages"
  if ← pkgsDir.isDir then
    for entry in ← pkgsDir.readDir do
      roots := roots.push entry.path
  return roots

/-- Attach the verbatim declaration source (A7) by reading the module's `.lean`
file out of one of `roots`, widened upward over the contiguous leading comment
block so the docstring travels with the proof (A7+, issue #17). Best-effort;
leaves the record unchanged when the module path or source range is unknown. -/
def attachProofSource (roots : Array System.FilePath) (h : TheoremHealth) :
    IO TheoremHealth := do
  if h.«module».isEmpty || h.declStartLine == 0 then
    return h
  let rel := System.FilePath.mk ((h.«module».replace "." "/") ++ ".lean")
  let mut src := ""
  for root in roots do
    let cand := root / rel
    if src.isEmpty && (← cand.pathExists) then
      let content ← IO.FS.readFile cand
      let lines := (content.splitOn "\n").toArray
      let widenedStart := widenToLeadingComments lines h.declStartLine
      src := sliceLines content widenedStart h.declEndLine
  return { h with proofSource := src }

def usage : String :=
  "usage: speca-export --targets <file> [--output <file>] [--src-root <dir>]...\n" ++
  "Emits proof-health JSON for the listed theorem names to --output\n" ++
  "(default: stdout). Machine consumers must pass --output: a cold\n" ++
  "`lake exe` prints toolchain/dependency/build progress to stdout before\n" ++
  "this executable runs, so stdout is not a clean JSON channel.\n" ++
  "--src-root points at a path-dependency checkout so the verbatim\n" ++
  "proof source (A7) can be sliced from it; repeatable."

/-- CLI options: the targets file, an optional output file, and any number of
extra source roots. -/
structure Options where
  targets  : System.FilePath
  output?  : Option System.FilePath := none
  srcRoots : List System.FilePath := []

/-- Parse the CLI in any flag order; anything unrecognized prints usage and
exits 2. -/
def parseCli (args : List String) : IO Options := do
  let rec go (as : List String) (targets? : Option System.FilePath)
      (out? : Option System.FilePath) (roots : List System.FilePath) :
      IO Options := do
    match as with
    | [] =>
      match targets? with
      | some t => pure { targets := t, output? := out?, srcRoots := roots.reverse }
      | none   => do IO.eprintln usage; IO.Process.exit 2
    | "--targets"  :: p :: rest => go rest (some (System.FilePath.mk p)) out? roots
    | "--output"   :: p :: rest => go rest targets? (some (System.FilePath.mk p)) roots
    | "--src-root" :: p :: rest => go rest targets? out? (System.FilePath.mk p :: roots)
    | _ => do IO.eprintln usage; IO.Process.exit 2
  go args none none []

/-- The whole exporter run: parse the CLI, import `rootModules` into a fresh
environment, classify every target under `cfg`, attach verbatim sources, and
write the health JSON. -/
unsafe def driverMain (cfg : ProjectConfig) (rootModules : Array Name)
    (args : List String) : IO Unit := do
  let opts ← parseCli args
  let targets ← parseTargets opts.targets
  initSearchPath (← findSysroot)
  enableInitializersExecution
  let env ← importModules (rootModules.map fun m => { module := m }) Options.empty
  -- pp.proofs so `proof_code` renders the actual proof term rather than `⋯`.
  let ppOpts : Lean.Options := Lean.Options.empty.setBool `pp.proofs true
  -- maxHeartbeats := 0 (no ceiling): the exporter pretty-prints and telescopes
  -- every target, and the default interactive budget is calibrated for editing
  -- one declaration, not for a batch over thousands. A theorem that needs more
  -- work than the default allows is not a failed theorem, and timing out on it
  -- would silently degrade its record to `unknown`.
  let coreCtx : Core.Context :=
    { fileName := "<speca-export>", fileMap := FileMap.ofString "", options := ppOpts,
      maxHeartbeats := 0 }
  let coreState : Core.State := { env := env }
  let (records, _) ← (SpecaExport.classifyAll cfg env targets).toIO coreCtx coreState
  let roots ← sourceRoots opts.srcRoots
  let records ← records.mapM (attachProofSource roots)
  let out := (SpecaExport.render cfg records).compress
  match opts.output? with
  | some path => IO.FS.writeFile path (out ++ "\n")
  | none => IO.println out

end SpecaExport
