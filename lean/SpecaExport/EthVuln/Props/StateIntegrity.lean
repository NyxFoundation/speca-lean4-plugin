import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `state-integrity`

主クラスが `state-integrity` であるインベントリの各エントリに
対して定理を1つずつ用意する（`data/classification.json` を
参照）。各定理は `EthVulnFormalProps.Common` の `Transition` /
`PreservesInv` をインスタンス化する: 仮説は指定された単一の
遷移による不変条件の保存（修正が回復した内容）であり、結論は
それを任意の入力シーケンスに沿って拡張した `PreservesInvOnTrace`
— 妥当な開始状態からコンポーネントが生成または保存するすべて
のものの妥当性である。

結論は Common の名前付き述語1適用に畳み、仮説からの含意は
証明する（`sorry` なし）。状態と入力列の量化は述語の内側に
畳み込み、リスト帰納法は Common の補題
`preservesInvOnTrace_of_step` に委ねる。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_state_integrity`。
-/

namespace EthVulnFormalProps

/-- **エントリ `d73c7daa388f8462`** (High) — Geth v1.9.5 security-critical
release fixing a v1.9.4 regression where the miner created blocks with
invalid state.

**壊れた不変条件**: 生成されるブロックは状態遷移関数の下で妥当
でなければならない — 妥当なチェーン状態からマイニングを行う
場合、無効な状態をコミットしてはならない。修正により、各生成
ステップは状態の妥当性を保存するため、妥当な状態から生成される
ブロックのどのシーケンスも妥当なままである。

**root_cause**: `consensus_divergence`（データセット）。

**クラス**: `state-integrity`、副次的に `spec-equivalence`。

読み下し: 仮説は単一の生成ステップによる妥当性の保存であり、
結論は「任意の入力列に沿った保存」を named 述語
`PreservesInvOnTrace` で述べる（リスト帰納法は Common の
補題）。 -/
theorem entry_d73c7daa388f8462_state_integrity
    {ChainState Block : Type}
    (produce : Transition ChainState Block)
    (ValidState : ChainState → Prop)
    (hPreserves : PreservesInv produce ValidState) :
    PreservesInvOnTrace produce ValidState :=
  preservesInvOnTrace_of_step hPreserves

/-- **エントリ `f81c1c6c4cd53ffb`** (High) — Lighthouse v1.0.6: the slasher
database became invalid (and `--beacon-node` was ignored).

**壊れた不変条件**: 保存されたslasherレコードが妥当性を失って
いた — 永続状態は、コンポーネントが行うすべての書き込みの下で
内部的に一貫していなければならない。修正により、各書き込みは
データベースの一貫性を保存するため、一貫したデータベースから
の書き込みシーケンスはどれも一貫したままである。

**root_cause**: `missing_input_validation`（データセット）。

**クラス**: `state-integrity`。

**抽象化**: クラスレベル — このリリース自体、これらは悪用され
たセキュリティ上の欠陥ではなく運用上のバグであったと記して
いる。slasher DBの修正が回復する永続状態の妥当性の不変条件に
マッピングした。

読み下し: 仮説は単一の書き込みによる一貫性の保存であり、結論
は「任意の入力列に沿った保存」を named 述語
`PreservesInvOnTrace` で述べる（リスト帰納法は Common の
補題）。 -/
theorem entry_f81c1c6c4cd53ffb_state_integrity
    {SlasherDb Record : Type}
    (write : Transition SlasherDb Record)
    (Consistent : SlasherDb → Prop)
    (hPreserves : PreservesInv write Consistent) :
    PreservesInvOnTrace write Consistent :=
  preservesInvOnTrace_of_step hPreserves

end EthVulnFormalProps
