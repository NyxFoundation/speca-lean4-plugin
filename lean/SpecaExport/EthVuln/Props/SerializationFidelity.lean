import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `serialization-fidelity`

主クラスが `serialization-fidelity` であるインベントリの各
エントリにつき定理を1つずつ用意する（`data/classification.json`
を参照）。これらの定理は `EthVulnFormalProps.Common` の
`Codec` / `RoundTrips` をインスタンス化する。証明はスコープ上
`sorry` とする。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_serialization_fidelity`。
-/

namespace EthVulnFormalProps

/-- **エントリ `b89b66ccf953baca`** (High) — two changes getting closer to
interop (Nimbus).

**壊れた不変条件**: ハッシュ値が正しいエンコーディングではなく
生のバイト配列として JSON にシリアライズされており、さらに
attestation ビットフィールドが bootstrap ENR から欠落していた
— エンコーディングが相互運用のシリアライズ規則に従っていな
かった。コーデックは規定されたエンコーディングを厳密に生成
しなければならず、あるエンコーディングをデコードすれば元の値
が復元されなければならない。

**root_cause**: `serialization_bug`。

**クラス**: `serialization-fidelity`。

読み下し: `specEnc` は相互運用規則が規定するエンコーディング
である。修正により実装のエンコーダはそれを生成するようになり
（`hEncConforms`）、デコーダはそれを逆変換するようになった
（`hDecInverts`）。この2つが合わさって、実装コーデックの
ラウンドトリップ忠実性が得られる。 -/
theorem entry_b89b66ccf953baca_serialization_fidelity
    {Val Wire : Type}
    (c : Codec Val Wire) (specEnc : Val → Wire)
    (hEncConforms : ∀ a, c.enc a = specEnc a)
    (hDecInverts : ∀ a, c.dec (specEnc a) = some a) :
    RoundTrips c := sorry

end EthVulnFormalProps
