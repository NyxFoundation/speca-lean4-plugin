/-
ethereum-vuln-dataset トラック(M2 Track C / c-1)のルートモジュール。

`NyxFoundation/ethereum-vuln-dataset` の `data/ethereum_vulns.csv` に記録
された Critical/High の脆弱性が破る不変条件を、Lean 4 の定理として
形式化する。各定理は「名前付きの実装義務(must-establish 仮説)⇒
名前付き述語の結論(保証される不変条件)」の形で、その含意は証明
済みである(`sorry` なし。PR #24 レビュー対応)。

各宣言の完全修飾名は `EthVulnFormalProps.*`(名前空間は移植元の
eth-vuln-formal-props パッケージのまま)。`theorem_map_ethvuln.json` の
`PROP-lean-ethvuln-*` エントリがこの名前で各定理を参照し、exporter は
`lake exe speca-export-ethvuln`(`MainEthVuln.lean`)で本モジュールを
runtime に読み込んで解決する(gasper 用 `speca-export` は読み込まない)。
-/
import SpecaExport.EthVuln.Common
import SpecaExport.EthVuln.Props.ArithmeticSafety
import SpecaExport.EthVuln.Props.AvailabilityRobustness
import SpecaExport.EthVuln.Props.CryptoAuthIntegrity
import SpecaExport.EthVuln.Props.InputValidation
import SpecaExport.EthVuln.Props.MemorySafety
import SpecaExport.EthVuln.Props.ResourceBounds
import SpecaExport.EthVuln.Props.SerializationFidelity
import SpecaExport.EthVuln.Props.SpecEquivalence
import SpecaExport.EthVuln.Props.StateIntegrity
