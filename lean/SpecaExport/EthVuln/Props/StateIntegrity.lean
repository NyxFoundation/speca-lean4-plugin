import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `state-integrity`

主クラスが `state-integrity` であるインベントリの各エントリに
対して定理を1つずつ用意する（`data/classification.json` を
参照）。各定理は `EthVulnFormalProps.Common` の `Transition` /
`PreservesInv` をインスタンス化する: 仮説は指定された単一の
遷移による不変条件の保存（修正が回復した内容）であり、結論は
それを任意の入力シーケンスに沿って拡張したもの — 妥当な開始
状態からコンポーネントが生成または保存するすべてのものの妥当
性である。証明はスコープ外であり `sorry` とする。

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

**クラス**: `state-integrity`、副次的に `spec-equivalence`。 -/
theorem entry_d73c7daa388f8462_state_integrity
    {ChainState Block : Type}
    (produce : Transition ChainState Block)
    (ValidState : ChainState → Prop)
    (hPreserves : PreservesInv produce ValidState) :
    ∀ (s : ChainState) (blocks : List Block),
      ValidState s → ValidState (blocks.foldl produce s) := sorry

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
マッピングした。 -/
theorem entry_f81c1c6c4cd53ffb_state_integrity
    {SlasherDb Record : Type}
    (write : Transition SlasherDb Record)
    (Consistent : SlasherDb → Prop)
    (hPreserves : PreservesInv write Consistent) :
    ∀ (db : SlasherDb) (recs : List Record),
      Consistent db → Consistent (recs.foldl write db) := sorry

end EthVulnFormalProps
