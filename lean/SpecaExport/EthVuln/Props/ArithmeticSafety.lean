import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `arithmetic-safety`

主クラスが `arithmetic-safety` であるインベントリの各エントリに
つき定理を1つずつ用意する（`data/classification.json` を参照）。

算術系の述語は性質の異なる2系統に分離されている（PR #24 レビュー
対応 — 旧 `ArithAgrees` は wrapping 実装が仮定・結論を両方満たして
しまい、オーバーフロー系エントリのバグを排除できなかった）:

- **overflow 検出系** (`CheckedArith` → `AcceptedExact`): 長さ・
  サイズ・カーソル演算のエントリ。仮定は修正が導入した checked
  演算であり、wrapping 実装は仮定を満たせない。結論は下流の上限
  チェックが依存する「受理値の厳密性」。
- **modulo 意味論系** (`AgreesModWidth`): 仕様自体が 2^n を法と
  する演算を定めるエントリ（consensus 仕様の uint64、EVM の
  ガス計算）。仮定は法簡約前の値を全精度で計算する修正内容で
  あり、縮小変換や IEEE-754 経由の実装は結論を満たせない。
- **EVM 仕様の等式系** (`ShiftSaturates` / `SarSaturates` /
  `evmMulMod`): エントリが破った仕様条項そのものを述べ、仕様
  モデル上で証明する。

結論は Common の名前付き述語（または仕様関数の等式）で閉じ、
含意はすべて証明する（`sorry` なし）。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_arithmetic_safety`。
-/

namespace EthVulnFormalProps

/-- **エントリ `271695669fe1a228`** (High) — integer overflow in
github.com/gorilla/websocket.

**壊れた不変条件**: フレーム長の演算がオーバーフローし、細工した
フレームによって長さの計算をすり抜けて DoS を引き起こせた。下流
の上限チェックが見る総長は、真の数学的な和でなければならない —
ラップした値が下流に流れてはならない。

**root_cause**: `integer_overflow_underflow` — 長さの演算が
ラップアラウンドし、そこから導かれるリソース上限が破綻した。

**クラス**: `arithmetic-safety`、副次的に `resource-bounds`。

読み下し: `implLen` は修正後の overflow 検出付き総長計算である。
仮定 `CheckedArith` は「和が 64 ビットに収まるときに限り厳密値を
返し、あふれるときは必ず検出（`none`）する」ことを述べる —
脆弱だった wrapping 実装は常に値を返すためこの仮定を満たせない。
結論 `AcceptedExact` は、受理された総長がすべて真の和であること
（上限チェックの健全性の根拠）である。 -/
theorem entry_271695669fe1a228_arithmetic_safety
    (implLen : Word 64 → Word 64 → Option (Word 64))
    (hChecked : CheckedArith 64 implLen (· + ·)) :
    AcceptedExact 64 implLen (· + ·) :=
  acceptedExact_of_checked hChecked

/-- **エントリ `2b3def4a540f08df`** (High) — CVE-2021-41272: Besu
SHL/SHR/SAR signed type-coercion error.

**壊れた不変条件**: Besu のシフト再実装は256ビットのシフト量を
符号付き32ビット型経由で変換していたため、最上位ビットが立った
シフト値に対して結果が EVM 仕様から逸脱した。仕様上、シフト量が
256以上（特にビット31が立った値、すなわち 2^31 ≥ 256 のもの）
であれば SHL/SHR は0を返さなければならない。

**root_cause**: `consensus_divergence` — 大きな入力に対して
シフトの結果が EVM 仕様から逸脱した。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し: 結論 `ShiftSaturates evmShl evmShr` は、脆弱な型変換が
破っていた仕様の飽和条項そのもの（シフト量 256 以上の全域。ビット
31 が立った値はその部分域で、まさに 32 ビット縮小が壊した箇所）で
あり、仕様モデル上で証明済みである。実装はこの条項（map の
assertion）を満たす義務を負う。 -/
theorem entry_2b3def4a540f08df_arithmetic_safety :
    ShiftSaturates evmShl evmShr := by
  intro value shift h
  exact ⟨by unfold evmShl; rw [if_pos h],
         by unfold evmShr; rw [if_pos h]⟩

/-- **エントリ `ba1acd77a48c7f43`** (High) — go-ethereum DoS via malicious
p2p message (integer overflow).

**壊れた不変条件**: 細工した p2p メッセージが整数オーバーフローを
突き、ノードが非常に大量のメモリを消費した — 長さ／サイズ演算の
オーバーフローが確保量の上限チェックをすり抜けた。確保量チェック
が見るサイズは真の数学的な和でなければならない。

**root_cause**: `integer_overflow_underflow`。

**クラス**: `arithmetic-safety`、副次的に `resource-bounds`。

読み下し: `implSize` は修正後の checked 確保量サイズ計算である。
wrapping 実装は `CheckedArith` を満たせず、受理値の厳密性
（`AcceptedExact`）が確保量上限チェックを健全にする。 -/
theorem entry_ba1acd77a48c7f43_arithmetic_safety
    (implSize : Word 64 → Word 64 → Option (Word 64))
    (hChecked : CheckedArith 64 implSize (· + ·)) :
    AcceptedExact 64 implSize (· + ·) :=
  acceptedExact_of_checked hChecked

/-- **エントリ `bc36f78358adeec5`** (High) — Lodestar AttesterSlashing
number overflow.

**壊れた不変条件**: Lodestar は `uint64` の値を JavaScript の
数値（IEEE-754 の倍精度浮動小数点数、2^53 未満でのみ厳密）として
表現していたため、細工した AttesterSlashing／ProposerSlashing の
値がオーバーフローし、コンセンサスの分岐を引き起こしかねなかった。
コンセンサス仕様の64ビット演算は、64ビットの定義域全体で厳密に
実装されなければならない — ここでは仕様自体が modulo 意味論を
定めるため、これは `AgreesModWidth`（全定義域での mod-2^64 厳密
一致）である。

**root_cause**: `integer_overflow_underflow` — 仕様で定められた
64ビット演算が厳密に実装されていなかった。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し: `implAdd` は修正後の64ビット加算（例えば BigInt を
用いたもの）である。仮定は「全精度で和を計算してから 2^64 に
簡約する」という修正の機構を述べ、結論はそこから従う全定義域の
厳密一致である。IEEE-754 経由の脆弱な実装は 2^53 超で法簡約前の
値を壊すため、仮定・結論のいずれも満たせない。 -/
theorem entry_bc36f78358adeec5_arithmetic_safety
    (implAdd : Word 64 → Word 64 → Word 64)
    (hFullPrecision : ∀ x y : Word 64,
      implAdd x y = BitVec.ofNat 64 (x.toNat + y.toNat)) :
    AgreesModWidth 64 implAdd (· + ·) := by
  intro x y
  rw [hFullPrecision x y]
  simp [BitVec.toNat_ofNat]

/-- **エントリ `besu:ghsa-advisory:GHSA-4456-w38r-m53x`** (Critical) —
CVE-2022-36025: gas allocation error in CALL operations in Besu EVM.

**壊れた不変条件**: Besu は CALL に割り当て可能なガスを32ビットの
符号あり／符号なし変換を経て計算していたため、呼び出し先の
コントラクトに誤ったガスを渡し、実行が EVM 仕様から逸脱した。
利用可能ガスの計算は、全定義域で仕様上の数学的な値（ガスワード
の modulo 意味論のもとで）と一致しなければならない。

**root_cause**: `integer_overflow_underflow` — 縮小変換によって
ガス値が破損した。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し: `implCallGas` は残りガスと要求ガスから呼び出し先へ
転送するガスを計算する、修正後の計算である。要求ガスは CALL の
スタック引数（256 ビットワード、攻撃者が任意の値を積める。ここ
では 64 ビットのガスワードに抽象化）に由来し、32 ビット表現に
収まらない値がまさに縮小変換の壊れた定義域だった。仕様側は
Common の**固定された** `evmCallGas`（EIP-150 の 63/64 ルール +
min）であり、自由パラメータではない — spec を自由にすると縮小
実装が spec を自分に合わせて選べてしまうためである。仮定は
「32ビットへ縮小せず全幅で仕様関数を計算する」という修正の機構
を述べ、結論は固定仕様との全定義域厳密一致（`AgreesModWidth`）。
縮小経由の脆弱な実装は 2^31 以上の要求ガスで `evmCallGas` と
食い違うため、仮定・結論のいずれも満たせない。 -/
theorem entry_besu_ghsa_advisory_GHSA_4456_w38r_m53x_arithmetic_safety
    (implCallGas : Word 64 → Word 64 → Word 64)
    (hFullWidth : ∀ g r : Word 64,
      implCallGas g r = BitVec.ofNat 64 (evmCallGas g.toNat r.toNat)) :
    AgreesModWidth 64 implCallGas evmCallGas := by
  intro g r
  rw [hFullWidth g r]
  simp [BitVec.toNat_ofNat]

/-- **エントリ `besu:hyperledger-besu:GHSA-7pg2-p5vj-xp5h`** (High) —
Besu SHL/SHR/SAR trigger native exception at key values.

**壊れた不変条件**: Besu の符号付き32ビットへのシフト量変換は、
32ビット像が負になる値に対してネイティブ例外と誤ったシフト
意味論を引き起こした。EVM 仕様では、あらゆるシフト量が
（例外なく）定義されており、256以上のシフト量 — 特に 2^31 以上
の値 — は SHL/SHR に対して0を、SAR に対して符号拡張ワードを
返す。

**root_cause**: `missing_input_validation`（データセット記載） —
変換後のシフト量が検査なしに使われた。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し: 結論は脆弱な実装が破っていた仕様の飽和条項
（`ShiftSaturates` と `SarSaturates`）であり、仕様モデル上で
証明済みである。 -/
theorem entry_besu_hyperledger_besu_GHSA_7pg2_p5vj_xp5h_arithmetic_safety :
    ShiftSaturates evmShl evmShr ∧ SarSaturates evmSar := by
  constructor
  · intro value shift h
    exact ⟨by unfold evmShl; rw [if_pos h],
           by unfold evmShr; rw [if_pos h]⟩
  · intro value shift h
    unfold evmSar
    rw [if_pos h]

/-- **エントリ `e9e9bc9f0e5c5042`** (High) — CVE-2022-36025 record of the
Besu CALL available-gas 32-bit conversion error.

**壊れた不変条件**: 誤った数値変換（64ビットのガス値を32ビット
へ縮小）によって、コントラクトに渡すガスが EVM 仕様と食い違った。
転送ガスの計算は、全定義域で仕様上の値と一致しなければならない。

**root_cause**: `integer_overflow_underflow` — 誤った数値変換。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し:
`entry_besu_ghsa_advisory_GHSA_4456_w38r_m53x_arithmetic_safety`
と同じ CVE（データセット上は別エントリ）を、ここでは呼び出し先
から見えるガスワードとして捉え直したもの。仕様側は同じく固定の
`evmCallGas`。要求ガスは攻撃者がスタック経由で任意に積める値で
あり、32 ビットに収まらない定義域が縮小変換の壊れた箇所である。
仮定は縮小変換をしない全幅計算という修正の機構、結論は固定仕様
との全定義域厳密一致である。 -/
theorem entry_e9e9bc9f0e5c5042_arithmetic_safety
    (implForwardedGas : Word 64 → Word 64 → Word 64)
    (hNoNarrowing : ∀ g r : Word 64,
      implForwardedGas g r =
        BitVec.ofNat 64 (evmCallGas g.toNat r.toNat)) :
    AgreesModWidth 64 implForwardedGas evmCallGas := by
  intro g r
  rw [hNoNarrowing g r]
  simp [BitVec.toNat_ofNat]

/-- **エントリ `ea812e5ad2a3da8e`** (High) — CVE-2025-29072: Nethermind
Juno integer overflow in Sierra bytecode decompression.

**壊れた不変条件**: 展開処理のインデックス演算での整数
オーバーフローにより、悪意ある入力が無限ループと高い CPU
使用率を引き起こせた — 演算のオーバーフローがループ終了と
コスト上限の保証をすり抜けた。ループの進行尺度が見るカーソル
値は真の数学的な和でなければならない。

**root_cause**: `integer_overflow_underflow`。

**クラス**: `arithmetic-safety`、副次的に `resource-bounds`。

読み下し: `implAdvance` は修正後の checked 32ビットカーソル
前進処理である。wrapping 実装は `CheckedArith` を満たせず、
受理値の厳密性（`AcceptedExact`）が展開ループの終了保証を
成り立たせる。 -/
theorem entry_ea812e5ad2a3da8e_arithmetic_safety
    (implAdvance : Word 32 → Word 32 → Option (Word 32))
    (hChecked : CheckedArith 32 implAdvance (· + ·)) :
    AcceptedExact 32 implAdvance (· + ·) :=
  acceptedExact_of_checked hChecked

/-- **エントリ `geth:ethereum-go-ethereum:GHSA-jm5c-rv3w-w83m`** (High) —
denial of service via `MULMOD`.

**壊れた不変条件**: `mulmod(a, b, 0)` はブロック処理中に Geth を
パニックさせた。EVM 仕様は部分的な剰余演算を全域化しており —
モジュラスが0の `MULMOD` は0を返すと定義されており、クラッシュ
することは決してない。

**root_cause**: `integer_overflow_underflow`（データセット記載） —
仕様が全域的な結果を定めている箇所で、実装の部分的な演算が
クラッシュした。

**クラス**: `arithmetic-safety`、副次的に `availability-robustness`。

読み下し: 結論は、脆弱な実装が破っていた仕様の全域化条項
`MulModZeroTotal`（`evmMulMod` は `Common` にある仕様準拠の定義）
である。仕様モデル上で証明済みであり、実装はこの等式を満たす
義務を負う。 -/
theorem entry_geth_ethereum_go_ethereum_GHSA_jm5c_rv3w_w83m_arithmetic_safety :
    MulModZeroTotal := by
  intro a b
  unfold evmMulMod
  rw [if_pos rfl]

end EthVulnFormalProps
