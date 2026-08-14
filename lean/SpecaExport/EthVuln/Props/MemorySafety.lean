import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `memory-safety`

主クラスが `memory-safety` であるインベントリの各エントリに
対して定理を1つずつ用意する（`data/classification.json` を
参照）。各定理は `EthVulnFormalProps.Common` の `InBounds` /
`MemRegion` / `AccessesInBounds` をインスタンス化する: 仮説は
修正が導入した検証（範囲チェック、符号チェック、長さメタデータ
の整合性）を表し、結論は脆弱性が破っていた境界内アクセスの
不変条件を表す。証明はスコープ外であり `sorry` とする。

定理の命名規則: `entry_<id sanitized: [^A-Za-z0-9] → _>_memory_safety`。
-/

namespace EthVulnFormalProps

/-- **エントリ `228c807be670b220`** (High) — Go Ethereum denial of service
(cmd/evm SEGV on crafted bytecode).

**壊れた不変条件**: 細工されたバイトコードに対して `cmd/evm` が
セグメンテーション違反を起こしていた — 信頼できないバイトコード
から到達可能な範囲外アクセスがプロセスをクラッシュさせていた。
インタプリタがバイトコードから導出するすべてのメモリアクセス
は、アドレス指定されたオブジェクトの範囲内に収まらなければな
らない。

**root_cause**: `missing_bounds_check` — バイトコードから計算
されたアクセスウィンドウが、オブジェクトサイズに対して検証
されないまま参照外しされていた。

**クラス**: `memory-safety`、副次的に `availability-robustness`。

読み下し: バイトコード `c` ごとに、インタプリタはウィンドウ
`[base c, base c + len c)` にアクセスする。修正はどの参照外し
の前にもウィンドウ全体を `size` に対して検証するため、アクセス
されるすべてのインデックスは境界内に収まる。 -/
theorem entry_228c807be670b220_memory_safety
    {Bytecode : Type}
    (size : Nat) (base len : Bytecode → Nat)
    (hWindowChecked : ∀ c, base c + len c ≤ size) :
    ∀ c k, k < len c → InBounds size (base c + k) := sorry

/-- **エントリ `74709c65793547a0`** (High) — Go Ethereum LES protocol
implementation vulnerable to denial of service.

**壊れた不変条件**: LESの `GetBlockHeadersMsg` ハンドラは、攻撃
者が影響を与えられる*符号付き*配列インデックスを使用しており、
アクセス違反を引き起こしていた。信頼できないメッセージから
導出されるインデックスは、符号を含めて、使用前に検証されなけ
ればならない。

**root_cause**: `missing_bounds_check` — 信頼できない入力に
対する境界・符号の検証が欠落していた。

**クラス**: `memory-safety`、副次的に `input-validation`。

読み下し: `idx q` はハンドラがクエリ `q` から計算する符号付き
インデックスである。修正後は下限（非負性）と上限の両方が
チェックされるため、アクセスに使われるインデックスは境界内
に収まる。 -/
theorem entry_74709c65793547a0_memory_safety
    {HeadersQuery : Type}
    (size : Nat) (idx : HeadersQuery → Int)
    (hNonNeg : ∀ q, 0 ≤ idx q)
    (hUpper : ∀ q, idx q < (size : Int)) :
    ∀ q, InBounds size (idx q).toNat := sorry

/-- **エントリ `a35bfa6a16c0e362`** (High) — CVE-2018-20421 (Geth 1.8.19
dynamic-array length rewrite).

**壊れた不変条件**: EVMメモリ上で動的配列の長さワードを書き換え
た上で要素を1つ書き込むと、巨大なメモリ消費を強制することが
できた — 長さメタデータと実際の割り当てが乖離していた。申告
された長さによって正当化されるアクセスは、その申告された長さ
が割り当てられたサイズを決して超えない場合にのみ安全である。

**root_cause**: `missing_bounds_check` — 長さメタデータが、
実際の割り当てに対して検証されないまま信頼されていた。

**クラス**: `memory-safety`、副次的に `resource-bounds`。

読み下し: `r` は割り当て済みの領域、`claimedLen` はメタデータ
が申告する長さである。修正はメタデータを割り当てと整合させる
（`hConsistent`）ため、申告された長さより小さいすべての
インデックスは実際の割り当ての境界内に収まる。 -/
theorem entry_a35bfa6a16c0e362_memory_safety
    (r : MemRegion) (claimedLen : Nat)
    (hConsistent : claimedLen ≤ r.size) :
    ∀ i, i < claimedLen → InBounds r.size i := sorry

/-- **エントリ `eff1234250453226`** (High) — jsonparser bump 1.1.1 → 1.1.2
addressing CVE-2026-32285 (out-of-bounds read), in Erigon.

**壊れた不変条件**: パース処理が入力バッファの境界を超えて読み
取ってしまうことがあった。パーサが信頼できないJSON入力から
導出するすべての読み取り位置は、バッファ内に収まらなければ
ならない。

**root_cause**: `missing_bounds_check` — パーサのカーソルが
バッファサイズに対して検証されていなかった。

**クラス**: `memory-safety`。

読み下し: `cursor inp` は、修正済みのパーサが入力 `inp` に
対して読み取るバイト位置を列挙する。各位置は読み取りの前に
バッファに対して検証される。 -/
theorem entry_eff1234250453226_memory_safety
    {JsonInput : Type}
    (buf : MemRegion) (cursor : JsonInput → List Nat)
    (hChecked : ∀ inp p, p ∈ cursor inp → p < buf.size) :
    AccessesInBounds buf.size cursor := sorry

end EthVulnFormalProps
