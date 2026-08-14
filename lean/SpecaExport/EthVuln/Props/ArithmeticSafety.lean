import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `arithmetic-safety`

主クラスが `arithmetic-safety` であるインベントリの各エントリに
つき定理を1つずつ用意する（`data/classification.json` を参照）。
これらの定理は `EthVulnFormalProps.Common` の `Word` /
`ArithAgrees`、および仕様上全域化された EVM 演算
（`evmMulMod`、`evmShl`、`evmShr`、`evmSar`）をインスタンス化する。
エントリが固定幅のオーバーフロー／型変換バグの場合、仮定は
実装が全幅で計算すること（修正内容）を述べ、結論は指定した
定義域上での非有界な数学的結果との一致となる。エントリが
EVM 仕様の具体的な等式を破った場合は、その等式自体を述べる。
証明はスコープ上 `sorry` とする。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_arithmetic_safety`。
-/

namespace EthVulnFormalProps

/-- **エントリ `271695669fe1a228`** (High) — integer overflow in
github.com/gorilla/websocket.

**壊れた不変条件**: フレーム長の演算がオーバーフローし、細工した
フレームによって長さの計算をすり抜けて DoS を引き起こせた。固定幅
ワードでの総長計算は、その和が表現可能な限り数学的な和と一致し
なければならない。

**root_cause**: `integer_overflow_underflow` — 長さの演算が
ラップアラウンドし、そこから導かれるリソース上限が破綻した。

**クラス**: `arithmetic-safety`、副次的に `resource-bounds`。

読み下し: `implLen` は修正後の64ビット総長計算である。全幅で和を
計算するため、真の和が64ビットに収まるすべての組に対して
`(· + ·)` と一致する — ラップアラウンドによってフレーム長を
過小評価することはない。 -/
theorem entry_271695669fe1a228_arithmetic_safety
    (implLen : Word 64 → Word 64 → Word 64)
    (hFullWidth : ∀ x y : Word 64,
      (implLen x y).toNat = (x.toNat + y.toNat) % 2 ^ 64) :
    ArithAgrees 64 implLen (· + ·) := sorry

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

読み下し: ここで述べる等式は、脆弱な型変換が破っていた仕様の
挙動そのものである。 -/
theorem entry_2b3def4a540f08df_arithmetic_safety :
    ∀ value shift : EvmWord, 2 ^ 31 ≤ shift.toNat →
      evmShl shift value = 0 ∧ evmShr shift value = 0 := sorry

/-- **エントリ `ba1acd77a48c7f43`** (High) — go-ethereum DoS via malicious
p2p message (integer overflow).

**壊れた不変条件**: 細工した p2p メッセージが整数オーバーフローを
突き、ノードが非常に大量のメモリを消費した — 長さ／サイズ演算の
オーバーフローが確保量の上限チェックをすり抜けた。サイズ計算は
表現可能な限り数学的な和と一致しなければならず、それにより確保量
チェックが真のサイズを見ることになる。

**root_cause**: `integer_overflow_underflow`。

**クラス**: `arithmetic-safety`、副次的に `resource-bounds`。

読み下し: `implSize` は修正後の64ビット確保量サイズ計算である
（全幅で、検査付き）。表現可能な定義域上で数学的な和と一致する
ことが、後段の確保量上限チェックを健全にする。 -/
theorem entry_ba1acd77a48c7f43_arithmetic_safety
    (implSize : Word 64 → Word 64 → Word 64)
    (hFullWidth : ∀ x y : Word 64,
      (implSize x y).toNat = (x.toNat + y.toNat) % 2 ^ 64) :
    ArithAgrees 64 implSize (· + ·) := sorry

/-- **エントリ `bc36f78358adeec5`** (High) — Lodestar AttesterSlashing
number overflow.

**壊れた不変条件**: Lodestar は `uint64` の値を JavaScript の
数値（IEEE-754 の倍精度浮動小数点数、2^53 未満でのみ厳密）として
表現していたため、細工した AttesterSlashing／ProposerSlashing の
値がオーバーフローし、コンセンサスの分岐を引き起こしかねなかった。
コンセンサス仕様の64ビット演算は、64ビットの定義域全体で厳密に
実装されなければならない。

**root_cause**: `integer_overflow_underflow` — 仕様で定められた
64ビット演算が厳密に実装されていなかった。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し: `implAdd` は修正後の64ビット加算（例えば BigInt を
用いたもの）である。全精度で 2^64 の剰余を計算することにより、
仕様の非有界な和が64ビットに収まる限り、それとの厳密な一致が
回復される。 -/
theorem entry_bc36f78358adeec5_arithmetic_safety
    (implAdd : Word 64 → Word 64 → Word 64)
    (hExact : ∀ x y : Word 64,
      (implAdd x y).toNat = (x.toNat + y.toNat) % 2 ^ 64) :
    ArithAgrees 64 implAdd (· + ·) := sorry

/-- **エントリ `besu:ghsa-advisory:GHSA-4456-w38r-m53x`** (Critical) —
CVE-2022-36025: gas allocation error in CALL operations in Besu EVM.

**壊れた不変条件**: Besu は CALL に割り当て可能なガスを32ビットの
符号あり／符号なし変換を経て計算していたため、呼び出し先の
コントラクトに誤ったガスを渡し、実行が EVM 仕様から逸脱した。
利用可能ガスの計算は、ガスワードで表現可能な限り仕様上の
数学的な値と一致しなければならない。

**root_cause**: `integer_overflow_underflow` — 縮小変換によって
ガス値が破損した。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し: `implCallGas` は残りガスと要求ガスから呼び出し先へ
転送するガスを計算する、修正後の計算である。全幅の64ビットで
計算する（32ビットへの縮小をしない）ことで、仕様関数
`specCallGas` との一致が回復される。 -/
theorem entry_besu_ghsa_advisory_GHSA_4456_w38r_m53x_arithmetic_safety
    (specCallGas : Nat → Nat → Nat)
    (implCallGas : Word 64 → Word 64 → Word 64)
    (hFullWidth : ∀ g r : Word 64,
      (implCallGas g r).toNat = specCallGas g.toNat r.toNat % 2 ^ 64) :
    ArithAgrees 64 implCallGas specCallGas := sorry

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

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。 -/
theorem entry_besu_hyperledger_besu_GHSA_7pg2_p5vj_xp5h_arithmetic_safety :
    ∀ value shift : EvmWord, 2 ^ 31 ≤ shift.toNat →
      evmShl shift value = 0 ∧ evmShr shift value = 0 ∧
      evmSar shift value =
        (if value.toInt < 0 then BitVec.allOnes 256 else 0) := sorry

/-- **エントリ `e9e9bc9f0e5c5042`** (High) — CVE-2022-36025 record of the
Besu CALL available-gas 32-bit conversion error.

**壊れた不変条件**: 誤った数値変換（64ビットのガス値を32ビット
へ縮小）によって、コントラクトに渡すガスが EVM 仕様と食い違った。
転送ガスの計算は、表現可能な限り仕様上の値と一致しなければ
ならない。

**root_cause**: `integer_overflow_underflow` — 誤った数値変換。

**クラス**: `arithmetic-safety`、副次的に `spec-equivalence`。

読み下し:
`entry_besu_ghsa_advisory_GHSA_4456_w38r_m53x_arithmetic_safety`
と同じ CVE（データセット上は別エントリ）を、ここでは呼び出し先
から見えるガスワードとして捉え直したもの。全幅での計算により
仕様との一致が回復される。 -/
theorem entry_e9e9bc9f0e5c5042_arithmetic_safety
    (specForwardedGas : Nat → Nat → Nat)
    (implForwardedGas : Word 64 → Word 64 → Word 64)
    (hNoNarrowing : ∀ g r : Word 64,
      (implForwardedGas g r).toNat =
        specForwardedGas g.toNat r.toNat % 2 ^ 64) :
    ArithAgrees 64 implForwardedGas specForwardedGas := sorry

/-- **エントリ `ea812e5ad2a3da8e`** (High) — CVE-2025-29072: Nethermind
Juno integer overflow in Sierra bytecode decompression.

**壊れた不変条件**: 展開処理のインデックス演算での整数
オーバーフローにより、悪意ある入力が無限ループと高い CPU
使用率を引き起こせた — 演算のオーバーフローがループ終了と
コスト上限の保証をすり抜けた。カーソル／カウントの演算は、
表現可能な限り数学的な和と一致しなければならず、それにより
ループの進行尺度が健全になる。

**root_cause**: `integer_overflow_underflow`。

**クラス**: `arithmetic-safety`、副次的に `resource-bounds`。

読み下し: `implAdvance` は修正後の32ビットカーソル前進処理で
ある。表現可能な定義域上での厳密な一致が、展開ループの終了
保証を成り立たせる。 -/
theorem entry_ea812e5ad2a3da8e_arithmetic_safety
    (implAdvance : Word 32 → Word 32 → Word 32)
    (hExact : ∀ x y : Word 32,
      (implAdvance x y).toNat = (x.toNat + y.toNat) % 2 ^ 32) :
    ArithAgrees 32 implAdvance (· + ·) := sorry

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

読み下し: ここで述べる等式は、脆弱な実装が破っていた仕様の
全域化条項である（`evmMulMod` は `Common` にある仕様準拠の
定義）。 -/
theorem entry_geth_ethereum_go_ethereum_GHSA_jm5c_rv3w_w83m_arithmetic_safety :
    ∀ a b : EvmWord, evmMulMod a b 0 = 0 := sorry

end EthVulnFormalProps
