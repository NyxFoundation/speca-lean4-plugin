/-
共有定義モジュール。

`data/classification.json` の9つの不変条件クラスに共通する概念を、
ここでのみ定義する。命題ファイルはこのモジュールをインポートしなけ
ればならず、これらの概念を再定義してはならない(命題ファイル内で
の重複定義は `scripts/check_mapping.py` が検査する違反である)。

これらの概念は意図的に抽象化されている。各命題は、対象となる脆弱
性エントリが持つ実体(client、プロトコルのメッセージ型、EVM
operation、...)によってこれらを具体化し、その脆弱性が破った不変
条件を述べる。具体的な意味論の参照点となるのは、Python の実行可
能仕様である ethereum/execution-specs (mainnet) と
ethereum/consensus-specs だ。

**述語の設計規約** (PR #24 レビュー対応): 各エントリ定理は
「名前付きの仮説(実装が確立すべき義務、exporter の
must-establish)から、名前付き述語1適用の結論(保証される不変
条件)を導く」形に統一する。結論の内側に量化子・ガードを直接
書き込むと、exporter のテレスコープ平坦化によって入力・文脈条件
が must-establish に混入するため、ガードを持つ結論は必ずここで
定義された述語で閉じる。この規約の下では仮説→結論の含意はごく
浅い補題になるので、各定理は `sorry` ではなく実際に証明する。
-/

namespace EthVulnFormalProps

/- 宇宙変数は明示的に宣言する(`autoImplicit := false` の
パッケージ(speca-lean4-plugin の `lean/`)に配置されても
そのまま型検査が通るようにするため)。 -/
universe u v w

/-! ## マシンワードと算術演算 (class: arithmetic-safety)

固定幅のマシン整数は `BitVec` としてモデル化する。算術系の不変
条件は、性質の異なる2系統に**明確に分離**する(PR #24 レビュー
指摘: 旧 `ArithAgrees` は「数学的結果が幅に収まる場合のみ」一致を
要求していたため、通常の wrapping 実装がオーバーフロー安全性の
つもりの仮定・結論を両方満たしてしまっていた):

1. **modulo 意味論** (`AgreesModWidth`) — EVM ワードや consensus
   仕様の uint64 のように、*仕様自体が* 2^n を法とする演算を定めて
   いる場合。wrapping は仕様どおりの挙動であり、排除すべきは
   縮小変換や浮動小数点経由などで法簡約前の値を壊す実装である。
2. **overflow 検出** (`CheckedArith` / `AcceptedExact`) — 長さ・
   サイズ・カーソル演算のように、下流の上限チェックやループ終了
   判定が「真の数学的値」に依存する場合。オーバーフローは黙って
   値を返すのではなく必ず検出されなければならず、wrapping 実装
   はこの述語を満たせない。 -/

/-- `n` ビットの固定幅マシンワード(`toNat` による符号なし解釈、
`toInt` による2の補数の符号付き解釈を持つ)。 -/
abbrev Word (n : Nat) := BitVec n

/-- EVM の 256 ビットワード。 -/
abbrev EvmWord := Word 256

/-- 固定幅演算 `impl` が、全定義域で「無制限の数学的演算 `spec` の
結果を `2^n` を法として簡約したもの」と厳密に一致する。仕様自体が
modulo 意味論を定める演算(EVM ワード演算、consensus 仕様の
uint64)のための述語である。32 ビットへの縮小変換や IEEE-754 経由
の計算のように法簡約前の値そのものを壊す実装は、**`spec` が具体的
に固定されている限り**(この Common の `evmCallGas` や `Nat` の
`+` のように。自由な `spec` パラメータのままでは spec 側を実装に
合わせて選べてしまい排除にならない)、この述語の反例になる。
オーバーフローの*禁止*を述べる述語ではない(それは
`CheckedArith`)。 -/
def AgreesModWidth (n : Nat) (impl : Word n → Word n → Word n)
    (spec : Nat → Nat → Nat) : Prop :=
  ∀ x y : Word n, (impl x y).toNat = spec x.toNat y.toNat % 2 ^ n

/-- overflow を検出する固定幅演算のモデル。`impl` は結果が `n`
ビットに収まるときに限り `some` を返し、その値は無制限の数学的
結果と厳密に一致する。収まらないときは必ず `none`(検出・拒否)
を返す。通常の wrapping 実装はオーバーフロー時にも値を返して
しまうため、この述語を満たせない — 「オーバーフローやラップ
アラウンドによって結果が壊れることはない」を主張するのはこちら
である。 -/
def CheckedArith (n : Nat) (impl : Word n → Word n → Option (Word n))
    (spec : Nat → Nat → Nat) : Prop :=
  (∀ x y z, impl x y = some z → z.toNat = spec x.toNat y.toNat) ∧
  (∀ x y, impl x y = none ↔ 2 ^ n ≤ spec x.toNat y.toNat)

/-- checked 演算から、下流(上限チェック・確保量比較・ループ終了
判定)が実際に依存する射影: 受理された(= `some` が返った)すべて
の結果は真の数学的値である — wrapping によって過小な値が下流に
流れることはない。オーバーフローした加算がラップした値を返す実装
は、この述語の反例である。 -/
def AcceptedExact (n : Nat) (impl : Word n → Word n → Option (Word n))
    (spec : Nat → Nat → Nat) : Prop :=
  ∀ x y z, impl x y = some z → z.toNat = spec x.toNat y.toNat

/-- checked 演算は受理値の厳密性を保証する(`CheckedArith` の
第1射影)。 -/
theorem acceptedExact_of_checked {n : Nat}
    {impl : Word n → Word n → Option (Word n)} {spec : Nat → Nat → Nat}
    (h : CheckedArith n impl spec) : AcceptedExact n impl spec :=
  h.1

/-- execution specs に基づく EVM `MULMOD` の意味論。積は無制限の
自然数上で計算し、`m` を法として剰余を取る。法が 0 の場合は 0
を返す(仕様は本来部分関数である演算を全域化しており、代わりに
トラップする実装は availability を壊す)。 -/
def evmMulMod (a b m : EvmWord) : EvmWord :=
  if m = 0 then 0 else BitVec.ofNat 256 ((a.toNat * b.toNat) % m.toNat)

/-- EVM `SHL`: `shift` ビットだけ左シフトし、256 ビットに切り詰
める。シフト量が 256 以上の場合は 0 を返す。 -/
def evmShl (shift value : EvmWord) : EvmWord :=
  if shift.toNat ≥ 256 then 0 else value <<< shift.toNat

/-- EVM `SHR`: 論理(符号なし)右シフト。シフト量が 256 以上の
場合は 0 を返す。 -/
def evmShr (shift value : EvmWord) : EvmWord :=
  if shift.toNat ≥ 256 then 0 else value >>> shift.toNat

/-- EVM `SAR`: 2の補数による解釈に基づく算術(符号付き)右シフ
ト。シフト量が 256 以上の場合、非負の値には 0 を、負の値には
-1 (全ビットが1)を返す。 -/
def evmSar (shift value : EvmWord) : EvmWord :=
  if shift.toNat ≥ 256 then
    if value.toInt < 0 then BitVec.allOnes 256 else 0
  else
    BitVec.sshiftRight value shift.toNat

/-- EVM シフト演算の飽和条項(EIP-145 / execution specs): シフト
量が 256 以上のすべての値 — 特に、符号付き 32 ビットへの縮小変換
で壊れやすい、ビット 31 が立った値を含む — に対して SHL/SHR は 0
を返す。シフト量を符号付き 32 ビット経由で扱った Besu の実装が
破った条項である。 -/
def ShiftSaturates (shl shr : EvmWord → EvmWord → EvmWord) : Prop :=
  ∀ value shift : EvmWord, 256 ≤ shift.toNat →
    shl shift value = 0 ∧ shr shift value = 0

/-- EVM `SAR` の飽和条項: シフト量が 256 以上の場合、結果は
符号に応じた全ビット拡張(負なら全ビット 1、非負なら 0)である。 -/
def SarSaturates (sar : EvmWord → EvmWord → EvmWord) : Prop :=
  ∀ value shift : EvmWord, 256 ≤ shift.toNat →
    sar shift value = (if value.toInt < 0 then BitVec.allOnes 256 else 0)

/-- execution specs の MULMOD 全域化条項(閉じた命題): モジュラス
が 0 の `MULMOD` は、トラップせず 0 を返す。 -/
def MulModZeroTotal : Prop :=
  ∀ a b : EvmWord, evmMulMod a b 0 = 0

/-- execution specs の EIP-150「63/64 ルール」: CALL 系で呼び出し
先に転送できるガスの上限。呼び出し元は残りガスの 1/64 を保持する
(`max_message_call_gas`)。 -/
def evmMaxCallGas (gasLeft : Nat) : Nat := gasLeft - gasLeft / 64

/-- execution specs の CALL 転送ガス(`calculate_message_call_gas`
の中核): 要求量と EIP-150 上限の小さい方。stipend や extra gas は
このモデルでは要求量・残量に織り込み済みとして抽象化する。CALL 系
のガス計算エントリはこの**固定された**仕様関数に対して
`AgreesModWidth` を述べる — spec 側を自由パラメータにすると、
縮小変換の実装が spec を自分に合わせて選べてしまい、述語が排除
すべきバグを排除できないためである。 -/
def evmCallGas (gasLeft requested : Nat) : Nat :=
  min (evmMaxCallGas gasLeft) requested

/-! ## 信頼できない入力・ハンドラ・結果
(classes: availability-robustness, input-validation) -/

/-- 実装が信頼できない入力を1単位処理した結果。状態が進む
(`ok`)、入力が拒否され明確に定義された状態のまま残る
(`reject`)、あるいは panic・未処理の例外・abort・強制シャット
ダウンといったクラッシュ系の障害が発生する(`crash`)のいずれか
である。 -/
inductive Outcome (σ : Type u) where
  | ok (next : σ)
  | reject (next : σ)
  | crash
  deriving Repr, BEq

/-- ノード状態 `σ` 上で、型 `ι` の信頼できない入力を消費するハ
ンドラ。 -/
def Handler (ι : Type v) (σ : Type u) := σ → ι → Outcome σ

/-- availability robustness(可用性の堅牢性): 到達可能な状態と
どのような信頼できない入力の組み合わせであっても、クラッシュ系
の障害を発生させないこと。 -/
def NeverCrashes {ι σ} (h : Handler ι σ) : Prop :=
  ∀ s i, h s i ≠ Outcome.crash

/-- input validation(入力検証): 妥当性述語に違反する入力は、状
態に一切影響を与えることなく拒否される。 -/
def ValidatedBy {ι σ} (h : Handler ι σ) (valid : ι → Prop) : Prop :=
  ∀ s i, ¬ valid i → h s i = Outcome.reject s

/-- 受理された遷移の事後条件: `ok` で状態が進んだすべてのステップ
は、指定された関係 `post` を満たす。 -/
def OnAccept {ι σ} (h : Handler ι σ) (post : σ → ι → σ → Prop) : Prop :=
  ∀ s i s', h s i = Outcome.ok s' → post s i s'

/-- 受理は妥当性を含意する: ハンドラが `ok` で受理した入力は、
必ず妥当性述語を満たしている(検証の抜け道が存在しない)。
`ValidatedBy` が「不当な入力は拒否される」という*機構*を述べる
のに対し、こちらは下流が依存する*帰結*を述べる。 -/
def AcceptsOnlyValid {ι σ} (h : Handler ι σ) (valid : ι → Prop) : Prop :=
  OnAccept h fun _ i _ => valid i

/-- 検証機構は受理の妥当性を保証する: `ValidatedBy` から
`AcceptsOnlyValid` が従う。 -/
theorem acceptsOnlyValid_of_validatedBy {ι σ}
    {h : Handler ι σ} {valid : ι → Prop}
    (hv : ValidatedBy h valid) : AcceptsOnlyValid h valid := by
  intro s i s' hok
  refine Classical.byContradiction fun hnv => ?_
  rw [hv s i hnv] at hok
  simp at hok

/-! ### 可用性の堅牢性の分解 (class: availability-robustness)

PR #24 レビュー対応: `NeverCrashes` を仮説側でそのまま言い換える
(旧 `hTotal`)のではなく、実装が守るべき具体的な2条件 —
**(1) 整形式でない入力の正常拒否**(malformed input のパース・
検証段階が全域で、拒否時に状態を変えない = ロールバック)と
**(2) 整形式入力の全域処理**(リソース枯渇・内部エラーも定義
された拒否に落ち、拒否時は状態を変えない) — に分解する。
`neverCrashes_of_split` がこの2条件から `NeverCrashes` を導く。
`wellFormed` は対象コンポーネントの入力整形式性(構文・意味検証
を通過すること)の抽象である。 -/

/-- 整形式でない入力は、状態を一切変えずに拒否される(クラッシュ
もしないし、部分的な状態変更も残さない)。malformed 入力に対する
パース・検証段階の全域性とロールバックを表す。 -/
def RejectsMalformed {ι σ} (h : Handler ι σ) (wellFormed : ι → Prop) : Prop :=
  ∀ s i, ¬ wellFormed i → h s i = Outcome.reject s

/-- 整形式の入力の処理は全域である: 受理して状態を進めるか、状態
を変えずに拒否するかのいずれかに必ず到達する。リソース枯渇・内部
エラーといった失敗も、クラッシュではなく定義された拒否(状態
ロールバック付き)に落ちることを含む。 -/
def TotalOnWellFormed {ι σ} (h : Handler ι σ) (wellFormed : ι → Prop) : Prop :=
  ∀ s i, wellFormed i →
    (∃ s', h s i = Outcome.ok s') ∨ h s i = Outcome.reject s

/-- 可用性の分解補題: malformed 入力の正常拒否と整形式入力の全域
処理から、クラッシュしないことが従う。 -/
theorem neverCrashes_of_split {ι σ} {h : Handler ι σ} {wellFormed : ι → Prop}
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) : NeverCrashes h := by
  intro s i
  cases Classical.em (wellFormed i) with
  | inl hwf =>
    cases hTotal s i hwf with
    | inl hok =>
      cases hok with
      | intro s' hs' => simp [hs']
    | inr hrej => simp [hrej]
  | inr hnwf => simp [hMalformed s i hnwf]

/-! ## リソース計量 (class: resource-bounds) -/

/-- リソースモデル。ノード状態上の使用量の尺度と、信頼できない
入力を消費するハンドラの組。`usage` はメモリバイト数、
goroutine の数、CPU ステップ数、格納されたエントリ数、メトリク
スのカーディナリティなどを抽象化したものである。 -/
structure ResourceModel (ι : Type v) (σ : Type u) where
  usage : σ → Nat
  step : Handler ι σ

/-- resource bounds(リソース境界): 上限を下回った状態から始め
れば、受理された入力・拒否された入力のいずれか1つによって使用
量が上限を超えることはない。したがって、攻撃者が制御するどのよ
うな入力列によっても上限を超えることはない。 -/
def BoundedUsage {ι σ} (m : ResourceModel ι σ) (bound : Nat) : Prop :=
  ∀ s i s', m.usage s ≤ bound →
    (m.step s i = Outcome.ok s' ∨ m.step s i = Outcome.reject s') →
    m.usage s' ≤ bound

/-- 割り当ての計上: 受理された各入力の使用量増分は、その入力に
帰属するコスト `cost i` を超えない(帰属されない割り当てが存在
しない)。 -/
def UsageAccounted {ι σ} (m : ResourceModel ι σ) (cost : ι → Nat) : Prop :=
  ∀ s i s', m.step s i = Outcome.ok s' →
    m.usage s' ≤ m.usage s + cost i

/-- 受け入れ制御: コストを加えると上限を超える入力は受理されない
(受理された時点で `usage + cost ≤ bound` が成り立っている)。 -/
def AdmissionControlled {ι σ} (m : ResourceModel ι σ)
    (cost : ι → Nat) (bound : Nat) : Prop :=
  ∀ s i s', m.step s i = Outcome.ok s' →
    m.usage s + cost i ≤ bound

/-- 拒否は使用量を増やさない: 拒否された入力が資源を確保したまま
にすることはない。 -/
def RejectFrees {ι σ} (m : ResourceModel ι σ) : Prop :=
  ∀ s i s', m.step s i = Outcome.reject s' →
    m.usage s' ≤ m.usage s

/-- リソース境界の分解補題: 計上・受け入れ制御・拒否時非増加の
3条件から、使用量の有界性が従う。 -/
theorem boundedUsage_of_admission {ι σ}
    {m : ResourceModel ι σ} {cost : ι → Nat} {bound : Nat}
    (hAccounted : UsageAccounted m cost)
    (hAdmission : AdmissionControlled m cost bound)
    (hRejectFree : RejectFrees m) : BoundedUsage m bound := by
  intro s i s' hstart hstep
  cases hstep with
  | inl hok => exact Nat.le_trans (hAccounted s i s' hok) (hAdmission s i s' hok)
  | inr hrej => exact Nat.le_trans (hRejectFree s i s' hrej) hstart

/-! ## メモリ領域 (class: memory-safety) -/

/-- `size` 個のアドレス指定可能な単位を持つオブジェクトへのイン
デックスが範囲内にあること。巨大な符号なしインデックスを生む符
号関連の誤り、範囲外読み出し、長さメタデータの不整合は、いずれ
かのアクセスに対してこの述語に違反する。 -/
def InBounds (size idx : Nat) : Prop := idx < size

/-- メモリ領域。`size` 個のアドレス指定可能な単位からなり、範囲
内では内容が定義されている。 -/
structure MemRegion where
  size : Nat
  read : Fin size → UInt8

/-- 実装が信頼できない入力から導くすべてのアクセスが範囲内に収
まること。`accesses input` は、その入力に対して実装が触れるイ
ンデックスを列挙したものである。 -/
def AccessesInBounds {ι} (size : Nat) (accesses : ι → List Nat) : Prop :=
  ∀ i idx, idx ∈ accesses i → InBounds size idx

/-- ウィンドウ検証補題: 各入力のアクセスウィンドウ
`[base c, base c + len c)` の全体が `size` に対して検証されて
いれば、ウィンドウ内のすべてのインデックスは境界内に収まる。 -/
theorem accessesInBounds_of_window {ι} {size : Nat} {base len : ι → Nat}
    (hWindow : ∀ c, base c + len c ≤ size) :
    AccessesInBounds size (fun c => (List.range (len c)).map (base c + ·)) := by
  intro c idx hmem
  cases List.mem_map.mp hmem with
  | intro k hk =>
    cases hk with
    | intro hkmem hkeq =>
      have hklt : k < len c := List.mem_range.mp hkmem
      have hw := hWindow c
      subst hkeq
      simp only [InBounds]
      omega

/-- 長さメタデータ整合補題: 申告された長さが割り当てサイズを超え
なければ、申告された長さの範囲内のすべてのインデックスは割り当て
の境界内に収まる。 -/
theorem accessesInBounds_of_claimedLen {size claimedLen : Nat}
    (hConsistent : claimedLen ≤ size) :
    AccessesInBounds size (fun _ : Unit => List.range claimedLen) := by
  intro _ idx hmem
  have := List.mem_range.mp hmem
  simp only [InBounds]
  omega

/-! ## 遷移・仕様との等価性・状態の整合性
(classes: spec-equivalence, state-integrity) -/

/-- 状態 `σ` と入力 `ι` 上の(全域かつ決定的な)状態遷移。状態
遷移関数、block/payload の処理ステップ、fork-choice の更新、あ
るいは RPC 応答の計算を表す抽象的な形である。 -/
def Transition (σ : Type u) (ι : Type v) := σ → ι → σ

/-- 指定された定義域上での仕様との等価性。入力が仕様上妥当であ
る限り、実装側の結果は正典となる仕様側の結果と一致する。
consensus の分岐、誤ったプロトコル定数、仕様に適合しない RPC
応答は、いずれもこの性質への反例である。 -/
def SpecEquivOn {σ ι} (validFor : σ → ι → Prop)
    (specT implT : Transition σ ι) : Prop :=
  ∀ s i, validFor s i → implT s i = specT s i

/-- 無条件の仕様との等価性。 -/
def SpecEquiv {σ ι} (specT implT : Transition σ ι) : Prop :=
  ∀ s i, implT s i = specT s i

/-- クライアント間の合意: 2つの実装が、すべての状態と入力の組に
対して同一の観測可能な結果を返す。正規仕様に個別に準拠する2実装
の interop 性質を述べるための形である。 -/
def Agree {σ : Type u} {ι : Type v} {ρ : Type w} (fA fB : σ → ι → ρ) : Prop :=
  ∀ s i, fA s i = fB s i

/-- 正規の受理の伝播: 仕様上妥当な定義域において、仕様側が受理
する状態に到達する遷移であれば、実装側も受理する状態に到達する。
consensus divergence(脆弱なノードが正規チェーンを拒否する)の
否定を述べる形である。 -/
def AcceptanceCarriesOver {σ ι} (validFor : σ → ι → Prop)
    (specT implT : Transition σ ι) (accepts : σ → Prop) : Prop :=
  ∀ s i, validFor s i → accepts (specT s i) → accepts (implT s i)

/-- 仕様準拠から正規受理の伝播が従う。 -/
theorem acceptanceCarriesOver_of_specEquivOn {σ ι}
    {validFor : σ → ι → Prop} {specT implT : Transition σ ι}
    {accepts : σ → Prop} (hConform : SpecEquivOn validFor specT implT) :
    AcceptanceCarriesOver validFor specT implT accepts := by
  intro s i hv hacc
  rw [hConform s i hv]
  exact hacc

/-- 観測の一致: 仕様上妥当な定義域において、実装の遷移結果の観測
値(状態ルートなどのコミットメント)が仕様の遷移結果の観測値と
一致する。 -/
def AgreeOnObservation {σ ι} {ω : Type w} (validFor : σ → ι → Prop)
    (obs : σ → ω) (specT implT : Transition σ ι) : Prop :=
  ∀ s i, validFor s i → obs (implT s i) = obs (specT s i)

/-- 仕様準拠から観測の一致が従う。 -/
theorem agreeOnObservation_of_specEquivOn {σ ι} {ω : Type w}
    {validFor : σ → ι → Prop} {obs : σ → ω} {specT implT : Transition σ ι}
    (hConform : SpecEquivOn validFor specT implT) :
    AgreeOnObservation validFor obs specT implT := by
  intro s i hv
  rw [hConform s i hv]

/-- 生成物の仕様妥当性: 指定された定義域上で、遷移が生成する状態
は仕様の妥当性述語を満たす。 -/
def ProducesSpecValid {σ ι} (validFor : σ → ι → Prop)
    (produce : Transition σ ι) (valid : σ → Prop) : Prop :=
  ∀ s i, validFor s i → valid (produce s i)

/-- state integrity(状態の整合性): 遷移が状態の妥当性という不
変条件を保存すること。妥当な遷移前状態からは、妥当な遷移後状態
しか生じ得ない(マイナーが生成した不正な block や、破損したデー
タベースはいずれも反例である)。 -/
def PreservesInv {σ ι} (t : Transition σ ι) (Inv : σ → Prop) : Prop :=
  ∀ s i, Inv s → Inv (t s i)

/-- 指定された定義域上での不変条件の保存。 -/
def PreservesInvOn {σ ι} (validFor : σ → ι → Prop)
    (t : Transition σ ι) (Inv : σ → Prop) : Prop :=
  ∀ s i, validFor s i → Inv s → Inv (t s i)

/-- 遷移の任意有限列に沿った不変条件の保存: 妥当な状態から始めれ
ば、入力列をどう畳み込んでも妥当なままである。 -/
def PreservesInvOnTrace {σ ι} (t : Transition σ ι) (Inv : σ → Prop) : Prop :=
  ∀ (s : σ) (l : List ι), Inv s → Inv (l.foldl t s)

/-- 単一遷移の保存から列に沿った保存が従う(リスト帰納法)。 -/
theorem preservesInvOnTrace_of_step {σ ι}
    {t : Transition σ ι} {Inv : σ → Prop}
    (hStep : PreservesInv t Inv) : PreservesInvOnTrace t Inv := by
  intro s l
  induction l generalizing s with
  | nil => exact fun h => h
  | cons x xs ih => exact fun h => ih (t s x) (hStep s x h)

/-! ## 暗号学的検証と認証
(class: crypto-auth-integrity) -/

/-- artifact `a`(signature、certificate、host key、proof)が
key/context `k` のもとで受理可能かどうかを判定する、抽象的な
verifier。 -/
structure Verifier (κ : Type u) (α : Type v) where
  accepts : κ → α → Bool

/-- soundness(健全性): verifier は、暗号学的仕様のもとで妥当な
artifact のみを受理する(不当な artifact を受理してしまうこと
は認証バイパスにほかならない)。 -/
def VerifierSound {κ α} (v : Verifier κ α) (Valid : κ → α → Prop) : Prop :=
  ∀ k a, v.accepts k a = true → Valid k a

/-- 健全性の拒否側の読み: 不当な artifact は決して受理されない。
`VerifierSound` の対偶を、監査項目として直接読める形にしたもの。 -/
def RejectsInvalid {κ α} (v : Verifier κ α) (Valid : κ → α → Prop) : Prop :=
  ∀ k a, ¬ Valid k a → v.accepts k a = false

/-- 健全な verifier は不当な artifact を拒否する。 -/
theorem rejectsInvalid_of_sound {κ α}
    {v : Verifier κ α} {Valid : κ → α → Prop}
    (hSound : VerifierSound v Valid) : RejectsInvalid v Valid := by
  intro k a hnv
  cases hacc : v.accepts k a with
  | false => rfl
  | true => exact absurd (hSound k a hacc) hnv

/-- デフォルトでのバイパスがないこと: 検証すると仕様で定められ
たプロトコルのステップは、実際に verifier に問い合わせなければ
ならない。これは「受理されたすべての実行は、verifier が受理し
た artifact を提示する」としてモデル化される。デフォルトでスキッ
プされる host-key の検査は、この性質への反例である。 -/
def AlwaysVerifies {κ α σ} (v : Verifier κ α)
    (accepted : σ → κ → α → Prop) : Prop :=
  ∀ s k a, accepted s k a → v.accepts k a = true

/-- 固定された context の下で、指定された関係にあるすべての
artifact が verifier に受理されていること。「認可は検証済みの鍵
に対してのみ発行される」のように、セッション上の関係と検証を
結び付けるための形である。 -/
def GrantedOnlyVerified {κ α σ} (v : Verifier κ α) (ctx : κ)
    (granted : σ → α → Prop) : Prop :=
  ∀ s a, granted s a → v.accepts ctx a = true

/-- 確立されたセッションの artifact はすべて暗号学的に妥当である
こと。検証の省略(MITM)の否定を、監査項目として直接読める形に
したもの。 -/
def EstablishedAreValid {κ α σ} (Valid : κ → α → Prop)
    (established : σ → κ → α → Prop) : Prop :=
  ∀ s k a, established s k a → Valid k a

/-! ## シリアライズ (class: serialization-fidelity) -/

/-- `α` の値と wire 表現 `β` との間の encoder/decoder の組。 -/
structure Codec (α : Type u) (β : Type v) where
  enc : α → β
  dec : β → Option α

/-- round-trip fidelity(往復の忠実性): シリアライズ仕様に従っ
てエンコードした結果をデコードすれば、元の値が正確に復元され
る。 -/
def RoundTrips {α β} (c : Codec α β) : Prop :=
  ∀ a, c.dec (c.enc a) = some a

end EthVulnFormalProps
