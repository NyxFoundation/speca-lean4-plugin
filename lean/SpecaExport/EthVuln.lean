/-
ethereum-vuln-dataset トラック(M2 Track C / c-1)のルートモジュール。

`NyxFoundation/ethereum-vuln-dataset` の `data/ethereum_vulns.csv` に記録
された Critical/High の脆弱性が破る不変条件を、Lean 4 の命題と
して形式化する。証明は現段階ではスコープ外(`sorry` を許容する)であり、
すべての命題は型検査を通らなければならない。

各宣言の完全修飾名は `EthVulnFormalProps.*`(名前空間は移植元の
eth-vuln-formal-props パッケージのまま)。`theorem_map.json` の
`PROP-lean-ethvuln-*` エントリがこの名前で各定理を参照する。
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
