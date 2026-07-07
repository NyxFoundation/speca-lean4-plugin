import SpecaExport.Basic

/-!
`speca-export` executable entry point.

    lake exe speca-export --targets <file>

`<file>` is a newline-delimited list of fully-qualified theorem names (blank
lines and `#` comments ignored). Emits the proof-health JSON (see
`SpecaExport.report`) to stdout. The Python driver (`src/speca_lean4/`) writes
the targets file from `theorem_map.json`, runs this exe, and maps the health
records onto the `01e` property schema.

The environment is loaded at runtime via
`importModules #[GasperBeaconChain.Executable.All]`,
then `collectAxioms` runs in `CoreM` over that environment — the same axiom
mechanism gasper-lean4's compile-time `#mr_audit_json` uses.
-/

open Lean SpecaExport

/-- Parse a newline-delimited targets file; blank lines and `#` comments dropped. -/
def parseTargets (path : System.FilePath) : IO (List Name) := do
  let content ← IO.FS.readFile path
  let names := (content.splitOn "\n").filterMap fun line =>
    let t := line.trim
    if t.isEmpty || "#".isPrefixOf t then none else some t.toName
  return names

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
  -- `GasperBeaconChain.Executable.All` (not the bare root module): the root
  -- only reaches `Core.All`, while every target theorem lives in `Executable`.
  let env ← importModules #[{ module := `GasperBeaconChain.Executable.All }] Options.empty
  let coreCtx : Core.Context :=
    { fileName := "<speca-export>", fileMap := FileMap.ofString "" }
  let coreState : Core.State := { env := env }
  let (j, _) ← (SpecaExport.report env targets).toIO coreCtx coreState
  IO.println j.compress
