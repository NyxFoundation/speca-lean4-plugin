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
-/

namespace EthVulnFormalProps

/- 宇宙変数は明示的に宣言する(`autoImplicit := false` の
パッケージ(speca-lean4-plugin の `lean/`)に配置されても
そのまま型検査が通るようにするため)。 -/
universe u v

/-! ## マシンワードと算術演算 (class: arithmetic-safety)

固定幅のマシン整数は `BitVec` としてモデル化する。この不変条件群
が主張するのは、固定幅ワードに対する実装側の算術演算は、仕様が定
義する範囲では無制限の数学的結果と一致し、かつ部分関数である演算
は仕様が定める通りに全域化される、ということである(例えば EVM
における 0 による剰余演算は 0 を返す)。 -/

/-- `n` ビットの固定幅マシンワード(`toNat` による符号なし解釈、
`toInt` による2の補数の符号付き解釈を持つ)。 -/
abbrev Word (n : Nat) := BitVec n

/-- EVM の 256 ビットワード。 -/
abbrev EvmWord := Word 256

/-- 二項の固定幅演算 `impl` が、その数学的結果が `n` ビットに収ま
るすべての入力対について、数学的な演算 `spec` と一致するという
形。すなわち「オーバーフローやラップアラウンドによって結果が壊
れることはない」という性質を表す。 -/
def ArithAgrees (n : Nat) (impl : Word n → Word n → Word n)
    (spec : Nat → Nat → Nat) : Prop :=
  ∀ x y : Word n, spec x.toNat y.toNat < 2 ^ n →
    (impl x y).toNat = spec x.toNat y.toNat

/-- 二項の固定幅演算 `impl` が、2の補数による符号付き解釈のもと
で、その数学的結果が表現可能であるすべての入力について、数学的な
演算 `spec` と一致するという形。すなわち「符号変換の誤りによっ
て結果が壊れることはない」という性質を表す。 -/
def SignedArithAgrees (n : Nat) (impl : Word n → Word n → Word n)
    (spec : Int → Int → Int) : Prop :=
  ∀ x y : Word n,
    -(2 ^ (n - 1) : Int) ≤ spec x.toInt y.toInt →
    spec x.toInt y.toInt < (2 ^ (n - 1) : Int) →
    (impl x y).toInt = spec x.toInt y.toInt

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

/-- state integrity(状態の整合性): 遷移が状態の妥当性という不
変条件を保存すること。妥当な遷移前状態からは、妥当な遷移後状態
しか生じ得ない(マイナーが生成した不正な block や、破損したデー
タベースはいずれも反例である)。 -/
def PreservesInv {σ ι} (t : Transition σ ι) (Inv : σ → Prop) : Prop :=
  ∀ s i, Inv s → Inv (t s i)

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

/-- デフォルトでのバイパスがないこと: 検証すると仕様で定められ
たプロトコルのステップは、実際に verifier に問い合わせなければ
ならない。これは「受理されたすべての実行は、verifier が受理し
た artifact を提示する」としてモデル化される。デフォルトでスキッ
プされる host-key の検査は、この性質への反例である。 -/
def AlwaysVerifies {κ α σ} (v : Verifier κ α)
    (accepted : σ → κ → α → Prop) : Prop :=
  ∀ s k a, accepted s k a → v.accepts k a = true

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
