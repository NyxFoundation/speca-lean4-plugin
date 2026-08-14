import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `input-validation`

主クラスが `input-validation` であるインベントリの各エントリに
対して定理を1つずつ用意する（`data/classification.json` を
参照）。各定理は `EthVulnFormalProps.Common` の `Handler` /
`ValidatedBy` をインスタンス化する: 仮説は修正が導入した検証を
表し、結論は脆弱性が否定していた帰結を表す — 仕様上妥当な入力
にのみ作用が行われる。証明はスコープ外であり `sorry` とする。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_input_validation`。
-/

namespace EthVulnFormalProps

/-- **エントリ `3f495d3767bd5a5f`** (High) — run sim single-node test with
Geth catalyst to finality (merge interop).

**壊れた不変条件**: catalystモードの実際のGethに対してマージの
execution-payloadフローを相互運用テストしたところ、ペイロード
処理の検証・ハンドリングに不備があることが判明した。エンジン
ペイロードはそれに作用が行われる前に仕様に照らして検証されて
いなければならず、その結果、受理されたペイロードは常に仕様上
妥当である。

**root_cause**: `missing_input_validation`。

**クラス**: `input-validation`、副次的に `spec-equivalence`。

**抽象化**: クラスレベル — このエントリは単一の脆弱性ではなく、
複数の修正を集約したクロスクライアントのテストPRである。それが
検証していたエンジンペイロード経路の検証・仕様適合性にマッピ
ングした。 -/
theorem entry_3f495d3767bd5a5f_input_validation
    {Payload EngineState : Type}
    (engine : Handler Payload EngineState) (specValid : Payload → Prop)
    (hValidated : ValidatedBy engine specValid) :
    ∀ s p s', engine s p = .ok s' → specValid p := sorry

/-- **エントリ `d6a02420f6ae46dd`** (High) — Go Ethereum improper input
validation (TraceChain).

**壊れた不変条件**: `TraceChain` は終了ブロックが開始ブロックより
後であることを検証していなかった — RPCパラメータの事前条件が
チェックされないままだった。トレースリクエストは、その範囲が
正しく順序付けられている場合にのみ実行されなければならない。

**root_cause**: `missing_input_validation`。

**クラス**: `input-validation`。

読み下し: リクエストは (startBlock, endBlock) の組である。修正
後はハンドラが `start < end` を検証するため、実行されるどの
リクエストもこの事前条件を満たす。 -/
theorem entry_d6a02420f6ae46dd_input_validation
    {NodeState : Type}
    (traceChain : Handler (Nat × Nat) NodeState)
    (hValidated : ValidatedBy traceChain (fun r => r.1 < r.2)) :
    ∀ s r s', traceChain s r = .ok s' → r.1 < r.2 := sorry

/-- **エントリ `e667b69b60df12fe`** (High) — Teku 21.12.1 critical
security update (log4j window).

**壊れた不変条件**: 信頼できないデータは、ロギングパイプライン
によって実行可能なディレクティブとして解釈されてはならない —
攻撃者が制御できる文字列がロガーに到達しても、無害なテキスト
として扱われなければならない。

**root_cause**: `other`（関連する修正: log4j CVE-2021-44228）。

**クラス**: `input-validation`。

**抽象化**: クラスレベル — リリースノートはCVEを明記していない。
log4jの修正との関連は、リリース日とTekuの同時期のアドバイザリ
（GHSA-mwfw-vm54-g3p7）から推測した。

読み下し: `isDirective m` は、脆弱なパイプラインであれば実行
可能なルックアップとして解釈していたであろうメッセージを示す。
修正済みのパイプラインはそのようなメッセージを無害化するため、
それが作用するどのメッセージも無害である。 -/
theorem entry_e667b69b60df12fe_input_validation
    {LogMsg LoggerState : Type}
    (logStep : Handler LogMsg LoggerState)
    (isDirective : LogMsg → Prop)
    (hNeutralized : ∀ s m, isDirective m → logStep s m = .reject s) :
    ∀ s m s', logStep s m = .ok s' → ¬ isDirective m := sorry

/-- **エントリ `teku:ghsa-advisory:GHSA-mwfw-vm54-g3p7`** (Critical) —
potential remote code exploit in log4j dependency (CVE-2021-44228).

**壊れた不変条件**: 攻撃者が制御できる文字列がロガーに到達する
とリモートコード実行を引き起こしかねなかった — 信頼できない
データが無害なテキストではなく実行可能なルックアップディレク
ティブとして解釈されていた。ロギングパイプラインは、記録され
るデータに埋め込まれたディレクティブに対して決して作用しては
ならない。

**root_cause**: `missing_input_validation`。

**クラス**: `input-validation`。 -/
theorem entry_teku_ghsa_advisory_GHSA_mwfw_vm54_g3p7_input_validation
    {LogMsg LoggerState : Type}
    (logStep : Handler LogMsg LoggerState)
    (isLookupDirective : LogMsg → Prop)
    (hNeutralized : ∀ s m, isLookupDirective m → logStep s m = .reject s) :
    ∀ s m s', logStep s m = .ok s' → ¬ isLookupDirective m := sorry

end EthVulnFormalProps
