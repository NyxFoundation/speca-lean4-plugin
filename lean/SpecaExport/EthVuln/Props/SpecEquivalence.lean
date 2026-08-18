import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `spec-equivalence`

主クラスが `spec-equivalence` であるインベントリの各エントリに
対して定理を1つずつ用意する（`data/classification.json` を参照）。
これらの定理は `EthVulnFormalProps.Common` の `Transition` /
`SpecEquivOn` / `SpecEquiv`（さらに、そのエントリが状態妥当性
も壊していた場合は `PreservesInvOn`）をインスタンス化する。繰り
返し現れる形は2種類ある。

- *クライアント間の合意*: 正規仕様に準拠する2つのクライアント
  が同一の観測可能な結果を生成する — interop / spec-alignment
  系のエントリが回復する性質。結論は `Agree` の1適用で読む。
- *正規の受理*: spec-valid なドメイン上で仕様に準拠するクライ
  アントは、仕様が受理するものをまさに受理する —
  consensus-divergence 系のエントリが壊した性質（脆弱なノード
  が正規チェーンを拒否した）。結論は `AcceptanceCarriesOver` /
  `AgreeOnObservation` / `SpecEquivOn` の1適用で読む。

いずれの形でも、状態・入力の量化と spec-valid ガードは Common
側の述語の内側に畳み込む（結論に直接書くと exporter の
テレスコープ平坦化で must-establish に混入する）。

結論は Common の名前付き述語1適用に畳み、仮説からの含意は
証明する（`sorry` なし）。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_spec_equivalence`。
-/

namespace EthVulnFormalProps

/-- **エントリ `475682d10d661b75`** (High) — Ethereum 2.0 networking
specification consolidation.

**壊れた不変条件**: クライアント実装は、ばらばらの独自挙動で
はなく単一の正規ワイヤプロトコル（Req/Resp）に準拠しなければ
ならない — 準拠する2つのクライアントは同一の応答を返す。

**root_cause**: `other`。

**クラス**: `spec-equivalence`。

**抽象化**: クラスレベル — 単一の脆弱性ではなく仕様策定PRで
あるため、プロトコル準拠（クライアントは正規仕様に一致しな
ければならない）にマッピングする。

読み下し: `specT` は正規のワイヤプロトコル、`hA` / `hB` は
各クライアントの準拠義務（must-establish）である。結論は
クライアント間の合意 `Agree implA implB` の1適用であり、
状態とメッセージの量化は述語の内側に畳み込まれている。 -/
theorem entry_475682d10d661b75_spec_equivalence
    {NetState WireMsg : Type}
    (specT implA implB : Transition NetState WireMsg)
    (hA : SpecEquiv specT implA) (hB : SpecEquiv specT implB) :
    Agree implA implB := by
  intro s m
  rw [hA s m, hB s m]

/-- **エントリ `4f09bedbf1707694`** (High) — implement Kintsugi specs (the
Merge November sprint PR).

**壊れた不変条件**: クライアントの状態遷移とエンジンのセマン
ティクスは、spec-valid な入力に対して正規のマージ（Kintsugi）
仕様が定める結果と一致しなければならない — 準拠クライアント
は正規チェーンをそのまま受理する。

**root_cause**: `missing_input_validation`（データセット由来）。

**クラス**: `spec-equivalence`。

**抽象化**: クラスレベル — 単一の脆弱性ではなく仕様実装PRで
あるため、正規のマージ仕様への準拠にマッピングする。

読み下し: 仮説は spec-valid な定義域上での準拠義務であり、
結論は正規の受理の伝播 `AcceptanceCarriesOver` の1適用 —
`validFor` ガードと受理条件は述語の内側にある。 -/
theorem entry_4f09bedbf1707694_spec_equivalence
    {ChainState Block : Type}
    (validFor : ChainState → Block → Prop)
    (specT implT : Transition ChainState Block)
    (accepts : ChainState → Prop)
    (hConform : SpecEquivOn validFor specT implT) :
    AcceptanceCarriesOver validFor specT implT accepts :=
  acceptanceCarriesOver_of_specEquivOn hConform

/-- **エントリ `6c13a1c54cea1ce2`** (High) — Grandine 2.0.5 security
release (epoch processing, `process_registry_updates` reuse).

**壊れた不変条件**: エポック遷移中のレジストリ更新処理は、
コンセンサス仕様の結果と一致しなければならない。

**root_cause**: `other`。

**クラス**: `spec-equivalence`。

**抽象化**: クラスレベル — アドバイザリには脆弱性の詳細が
記載されていないため、このリリースのエポック処理の変更点を
手がかりに、仕様準拠のエポック遷移にマッピングする。

読み下し: `registryView` はエポック遷移後の状態から見える
バリデータレジストリ（activation / exit のキュー処理の結果 —
このリリースが名指しする `process_registry_updates` の出力面）
を抽象化した観測である。must-establish は仕様準拠 `hConform`
であり、結論はそこから従う「spec-valid な定義域上でのレジストリ
観測の一致」— consensus divergence が現れる面そのものである。 -/
theorem entry_6c13a1c54cea1ce2_spec_equivalence
    {BeaconState EpochCtx RegistryView : Type}
    (validFor : BeaconState → EpochCtx → Prop)
    (specEpoch implEpoch : Transition BeaconState EpochCtx)
    (registryView : BeaconState → RegistryView)
    (hConform : SpecEquivOn validFor specEpoch implEpoch) :
    AgreeOnObservation validFor registryView specEpoch implEpoch :=
  agreeOnObservation_of_specEquivOn hConform

/-- **エントリ `7482623489bc990c`** (High) — EIP-8025 optional execution
proofs in Lodestar (3-client interop).

**壊れた不変条件**: EIP の定めるところに従い、証明の取り扱いは
クライアント間で一致しなければならない — その EIP のセマン
ティクスに準拠する2つのクライアントは、同一の証明に対して同一
の結果を生成する。

**root_cause**: `missing_input_validation`（データセット由来）。

**クラス**: `spec-equivalence`。

**抽象化**: クラスレベル — 単一の脆弱性ではなく機能実装PRで
あるため、新しい証明セマンティクスのクライアント間準拠に
マッピングする。

読み下し: 仮説は各クライアントの EIP 準拠義務であり、結論は
クライアント間の合意 `Agree implA implB` の1適用である。 -/
theorem entry_7482623489bc990c_spec_equivalence
    {NodeState ExecutionProof : Type}
    (specT implA implB : Transition NodeState ExecutionProof)
    (hA : SpecEquiv specT implA) (hB : SpecEquiv specT implB) :
    Agree implA implB := by
  intro s p
  rw [hA s p, hB s p]

/-- **エントリ `94e5ca105ce4f0b9`** (High) — Grandine 2.0.4 security
release (fork-choice area, consensus divergence).

**壊れた不変条件**: フォークチョイスの結果はコンセンサス仕様
と一致しなければならない — spec-valid な入力に対して、準拠
するノードのヘッド選択は仕様の結果と一致する。

**root_cause**: `consensus_divergence`。

**クラス**: `spec-equivalence`。

**抽象化**: クラスレベル — アドバイザリは欠陥の内容を明示して
いないため、データセットの `consensus_divergence` という
root_cause とフォークチョイスというラベルを手がかりにマッピン
グする。

読み下し: `headOf` はフォークチョイスストアから計算されるヘッド
選択（`get_head` の結果）の観測である。must-establish は仕様準拠
`hConform` であり、結論はそこから従う「spec-valid な attestation
処理後のヘッド選択の一致」— consensus divergence が観測される面
そのものである。 -/
theorem entry_94e5ca105ce4f0b9_spec_equivalence
    {ForkChoiceStore Attestation Head : Type}
    (validFor : ForkChoiceStore → Attestation → Prop)
    (specFC implFC : Transition ForkChoiceStore Attestation)
    (headOf : ForkChoiceStore → Head)
    (hConform : SpecEquivOn validFor specFC implFC) :
    AgreeOnObservation validFor headOf specFC implFC :=
  agreeOnObservation_of_specEquivOn hConform

/-- **エントリ `a528f483050329a6`** (High) — bump EIP-8025
`MAX_PROOF_SIZE` to 400 KiB.

**壊れた不変条件**: プロトコル定数はクライアント間で仕様レベ
ルの要件と完全に一致しなければならず、そうでなければ妥当な
データが拒否される — 実際に観測された証明は旧来の 300 KiB
という定数を超えていた。仕様のサイズ要件を満たすすべての証明
は、クライアントの定数によって受理されなければならない。

**root_cause**: `consensus_divergence`。

**クラス**: `spec-equivalence`。

読み下し: 仕様が要求する最小サイズ 400 KiB を実装定数が
下回らないこと(旧 300 KiB 定数はこの不等式の反例)。 -/
theorem entry_a528f483050329a6_spec_equivalence
    (implMaxProofSize : Nat)
    (hConst : implMaxProofSize = 400 * 1024) :
    400 * 1024 ≤ implMaxProofSize :=
  Nat.le_of_eq hConst.symm

/-- **エントリ `b1a6e88b2f095f12`** (High) — geth-compatible zero hashes
for non-existent accounts in `eth_getProof`.

**壊れた不変条件**: 同一の状態に対する RPC 応答はクライアント
間で一致しなければならない — 存在しないアカウントに対する
`eth_getProof` は、正規の（geth 互換の）ゼロハッシュ応答を
返さなければならない。

**root_cause**: `missing_input_validation`（データセット由来）。

**クラス**: `spec-equivalence`。

読み下し: `specResp` は正規の応答関数であり、`hA` / `hB` は
それぞれのクライアントがその応答に一致する義務（`Agree` の
1適用）である。結論は2実装のあいだの合意
`Agree implA implB` であり、状態とアドレスの量化は述語の
内側に畳み込まれている。 -/
theorem entry_b1a6e88b2f095f12_spec_equivalence
    {StateDb Address ProofResp : Type}
    (specResp implA implB : StateDb → Address → ProofResp)
    (hA : Agree implA specResp)
    (hB : Agree implB specResp) :
    Agree implA implB := by
  intro db a
  rw [hA db a, hB db a]

/-- **エントリ `dc7e3fa111ce0e2a`** (High) — rename `random` to
`prevRandao` per the Kiln v2 specs.

**壊れた不変条件**: クライアントは仕様のフィールド名／セマン
ティクスを完全に同一に使用しなければならず、そうでなければ
engine-API の相互運用性が壊れる — 準拠する2つのクライアントの
ペイロードフィールド解釈は一致しなければならない。

**root_cause**: `consensus_divergence`。

**クラス**: `spec-equivalence`。

**抽象化**: クラスレベル — 悪用された脆弱性ではなく仕様整合PR
であるため、エンジンのペイロードフィールドにおける正規仕様
への準拠にマッピングする。

読み下し: 仮説は各クライアントのフィールド解釈の準拠義務で
あり、結論はクライアント間の合意 `Agree implA implB` の
1適用である。 -/
theorem entry_dc7e3fa111ce0e2a_spec_equivalence
    {EngineState PayloadField : Type}
    (specT implA implB : Transition EngineState PayloadField)
    (hA : SpecEquiv specT implA) (hB : SpecEquiv specT implB) :
    Agree implA implB := by
  intro s f
  rw [hA s f, hB s f]

/-- **エントリ `f960a5728e79e59b`** (High) — check CL/Reth capability
compatibility.

**壊れた不変条件**: Reth は Fusaka フォークをまたいでも古い
バージョンの CL のまま動作し続け、妥当なブロックを生成できな
くなった。EL/CL のケーパビリティバージョンが有効なフォーク
と互換である場合、ブロック生成は有効なフォークの仕様に準拠し
なければならない — 生成されたブロックは spec の遷移によって
受理される。

**root_cause**: `consensus_divergence`。

**クラス**: `spec-equivalence`。

読み下し: `compatible s` は、この修正が強制するケーパビリ
ティチェックである。そのドメイン上での準拠（`hConform`）と
仕様側の生成物妥当性（`hSpecValid`）から、実装側の生成物
妥当性 `ProducesSpecValid` の1適用が従う。 -/
theorem entry_f960a5728e79e59b_spec_equivalence
    {ChainState Slot : Type}
    (compatible : ChainState → Slot → Prop)
    (specProduce implProduce : Transition ChainState Slot)
    (specValidBlock : ChainState → Prop)
    (hConform : SpecEquivOn compatible specProduce implProduce)
    (hSpecValid : ProducesSpecValid compatible specProduce specValidBlock) :
    ProducesSpecValid compatible implProduce specValidBlock := by
  intro s t hc
  rw [hConform s t hc]
  exact hSpecValid s t hc

/-- **エントリ `geth:ethereum-go-ethereum:GHSA-69v6-xc2j-r2jf`** (High) —
shallow copy in the 0x4 precompile could lead to EVM memory
corruption.

**壊れた不変条件**: Geth の 0x4（`dataCopy`）プリコンパイルは
シャローコピーを行っており、EVM のメモリ破壊とチェーン分裂を
招いていた — 脆弱なノードは正規チェーンを拒否する。プリコン
パイルの観測可能なセマンティクスは仕様の値セマンティックな
コピーと一致しなければならず、それにより準拠ノードは仕様が
受理するものを受理する。

**root_cause**: `improper_state_update`。

**クラス**: `spec-equivalence`、副次的に `memory-safety`
（エイリアシングそのものがメモリ安全性違反であり、コンセン
サスへの影響がここで述べる乖離である）。

読み下し: `hValueSemantics` は値セマンティックなコピーへの
準拠義務であり、結論は正規の受理の伝播
`AcceptanceCarriesOver` の1適用である。 -/
theorem entry_geth_ethereum_go_ethereum_GHSA_69v6_xc2j_r2jf_spec_equivalence
    {EvmState CallInput : Type}
    (validFor : EvmState → CallInput → Prop)
    (specCopy implCopy : Transition EvmState CallInput)
    (accepts : EvmState → Prop)
    (hValueSemantics : SpecEquivOn validFor specCopy implCopy) :
    AcceptanceCarriesOver validFor specCopy implCopy accepts :=
  acceptanceCarriesOver_of_specEquivOn hValueSemantics

/-- **エントリ `geth:ethereum-go-ethereum:GHSA-9856-9gg9-qcmq`** (High) —
RETURNDATA corruption via datacopy.

**壊れた不変条件**: EVM のメモリ破壊バグにより、脆弱なノード
は異なる `stateRoot` を計算してしまい、正規チェーンに対する
コンセンサスエラーを引き起こした。RETURNDATA のセマンティクス
は仕様のものと一致しなければならず、それにより準拠ノードが
計算するステートルートは正規のものと一致する。

**root_cause**: `consensus_divergence`。

**クラス**: `spec-equivalence`、副次的に `memory-safety`。

読み下し: `root` はポスト状態のコミットメントを抽象化したも
のであり、遷移の準拠性はそのコミットメントの一致を強制する。
結論は観測の一致 `AgreeOnObservation` の1適用であり、
spec-valid ガードは述語の内側に畳み込まれている。 -/
theorem entry_geth_ethereum_go_ethereum_GHSA_9856_9gg9_qcmq_spec_equivalence
    {EvmState Tx Root : Type}
    (validFor : EvmState → Tx → Prop)
    (specT implT : Transition EvmState Tx)
    (root : EvmState → Root)
    (hConform : SpecEquivOn validFor specT implT) :
    AgreeOnObservation validFor root specT implT :=
  agreeOnObservation_of_specEquivOn hConform

/-- **エントリ `geth:ethereum-go-ethereum:GHSA-xw37-57qp-9mm4`** (High) —
consensus flaw during block processing.

**壊れた不変条件**: 特定のトランザクション列により、脆弱な
バージョンの Geth は正規チェーンを拒否してしまった — ブロック
処理が仕様の定める状態遷移から乖離した。準拠ノードは仕様が
受理するすべてのチェーンを受理する。

**root_cause**: `consensus_divergence`。

**クラス**: `spec-equivalence`。

読み下し: 仮説はブロック処理の仕様準拠義務であり、結論は
正規の受理の伝播 `AcceptanceCarriesOver` の1適用である。 -/
theorem entry_geth_ethereum_go_ethereum_GHSA_xw37_57qp_9mm4_spec_equivalence
    {ChainState Block : Type}
    (validFor : ChainState → Block → Prop)
    (specT implT : Transition ChainState Block)
    (accepts : ChainState → Prop)
    (hConform : SpecEquivOn validFor specT implT) :
    AcceptanceCarriesOver validFor specT implT accepts :=
  acceptanceCarriesOver_of_specEquivOn hConform

/-- **エントリ `lighthouse:sigp-lighthouse:GHSA-wm9c-xvqq-5c28`** (High)
— incorrect processing of effective balances in Electra epoch
processing.

**壊れた不変条件**: Lighthouse v7.0.0-beta の `process_epoch` は
Electra ネットワーク上で実効残高（effective balance）の扱いを
誤っていた。エポック処理はコンセンサス仕様の遷移と一致しな
ければならず、また仕様の遷移が残高を妥当な状態に保つ以上、
準拠する実装も残高状態を妥当に保たなければならない。

**root_cause**: `missing_input_validation`（データセット由来）。

**クラス**: `spec-equivalence`、副次的に `state-integrity`。

読み下し: `hConform` はエポック処理の仕様準拠義務、
`hSpecPreserves` は仕様側の残高妥当性の保存である。結論は
実装側の保存 `PreservesInvOn` の1適用であり、spec-valid
ガードと事前条件は述語の内側に畳み込まれている。 -/
theorem entry_lighthouse_sigp_lighthouse_GHSA_wm9c_xvqq_5c28_spec_equivalence
    {BeaconState EpochCtx : Type}
    (validFor : BeaconState → EpochCtx → Prop)
    (specEpoch implEpoch : Transition BeaconState EpochCtx)
    (balancesValid : BeaconState → Prop)
    (hConform : SpecEquivOn validFor specEpoch implEpoch)
    (hSpecPreserves : PreservesInvOn validFor specEpoch balancesValid) :
    PreservesInvOn validFor implEpoch balancesValid := by
  intro s e hv hb
  rw [hConform s e hv]
  exact hSpecPreserves s e hv hb

end EthVulnFormalProps
