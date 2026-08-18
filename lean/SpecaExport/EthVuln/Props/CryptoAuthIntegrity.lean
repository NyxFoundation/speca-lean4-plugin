import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `crypto-auth-integrity`

主クラスが `crypto-auth-integrity` であるインベントリの各エントリ
に対して定理を1つずつ用意する（`data/classification.json` を
参照）。各定理は `EthVulnFormalProps.Common` の `Verifier` /
`VerifierSound` / `AlwaysVerifies`（検証経路自体がクラッシュし
得た場合は `Handler` / `RejectsMalformed` / `TotalOnWellFormed`
と `NeverCrashes` も）をインスタンス化する。

結論は Common の名前付き述語1適用に畳み、仮説からの含意は
証明する（`sorry` なし）。セッション・鍵の量化とガードは
`GrantedOnlyVerified` / `EstablishedAreValid` / `RejectsInvalid`
の内側に畳み込む。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_crypto_auth_integrity`。
-/

namespace EthVulnFormalProps

/-- **エントリ `8dc5f046b9907f2a`** (High) — misuse of
`ServerConfig.PublicKeyCallback` may cause authorization bypass in
golang.org/x/crypto.

**壊れた不変条件**: 認可の判断が実際に使われた鍵から切り離されて
しまう可能性があった — 呼び出し元は、認証に使われた鍵ではなく、
その試行シーケンスの中でコールバックが以前に受理した鍵に基づい
てアクセスを許可してしまうことがあった。アクセスは、検証者が
実際に受理した鍵に対してのみ許可されなければならない。

**root_cause**: `missing_input_validation`（データセット）。

**クラス**: `crypto-auth-integrity`。

読み下し: `accepted s k` はセッション `s` でコールバックが鍵
`k` を受理したことを表し、`granted s k` は `k` に対して認可が
発行されたことを表す。修正では認可を受理済みの鍵に結び付ける
ため（`hBoundToKey`）、結論
`GrantedOnlyVerified v ctx granted` の1適用により、認可された
すべての鍵は検証を通過している。 -/
theorem entry_8dc5f046b9907f2a_crypto_auth_integrity
    {Ctx Key SessionState : Type}
    (v : Verifier Ctx Key) (ctx : Ctx)
    (accepted granted : SessionState → Key → Prop)
    (hBoundToKey : ∀ s k, granted s k → accepted s k)
    (hVerified : GrantedOnlyVerified v ctx accepted) :
    GrantedOnlyVerified v ctx granted :=
  fun s k hg => hVerified s k (hBoundToKey s k hg)

/-- **エントリ `c976633ee45dd987`** (High) — improper verification of
cryptographic signature in golang.org/x/crypto.

**壊れた不変条件**: x/crypto/ssh は公開鍵署名の検証中にパニック
していた — 検証経路自体が敵対的な鍵によってクラッシュさせられ
る可能性があった。正しさの前提条件として、検証は全域的でなけれ
ばならない（すべての鍵と署名の組が受理／拒否のいずれかの明確な
結果に到達する）。

**root_cause**: `missing_input_validation`。

**クラス**: `crypto-auth-integrity`、副次的に
`availability-robustness`。

読み下し: `wellFormed` はパース可能な鍵・署名エンコーディング
の抽象。修正が追加したのは malformed な鍵・署名に対する
（パニックではない）正常拒否であり、整形式な組の検証は全域で
ある。この2条件からクラッシュしないことが従う（Common の分解
補題で証明）。 -/
theorem entry_c976633ee45dd987_crypto_auth_integrity
    {PubKey Sig VerifierState : Type}
    (verifyStep : Handler (PubKey × Sig) VerifierState)
    (wellFormed : PubKey × Sig → Prop)
    (hMalformed : RejectsMalformed verifyStep wellFormed)
    (hTotal : TotalOnWellFormed verifyStep wellFormed) :
    NeverCrashes verifyStep :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `d29c5b0777a57b29`** (High) — golang.org/x/crypto/ssh
man-in-the-middle attack.

**壊れた不変条件**: x/crypto/ssh はデフォルトではホスト鍵を検証
していなかった（`HostKeyCallback` が必須でなかった）ため、中間
者攻撃を許してしまう。検証は決して省略されてはならない — 検証
者の健全性と組み合わさることで、確立されたすべてのセッションの
ホスト鍵が暗号学的に妥当であることが保証される。

**root_cause**: `missing_input_validation`。

**クラス**: `crypto-auth-integrity`。

読み下し: `established s h k` は、ホスト `h` が鍵 `k` を提示して
セッションが確立されたことを表す。中間者攻撃は、
`AlwaysVerifies`（修正内容: コールバックが必須になったこと）と
`VerifierSound` が組み合わさって、結論
`EstablishedAreValid Valid established` の1適用 — 確立された
すべてのセッションの鍵が妥当であること — が成り立つときに
正確に排除される。 -/
theorem entry_d29c5b0777a57b29_crypto_auth_integrity
    {Host HostKey ConnState : Type}
    (v : Verifier Host HostKey) (Valid : Host → HostKey → Prop)
    (established : ConnState → Host → HostKey → Prop)
    (hSound : VerifierSound v Valid)
    (hAlways : AlwaysVerifies v established) :
    EstablishedAreValid Valid established :=
  fun s h k he => hSound h k (hAlways s h k he)

/-- **エントリ `f6053ce4214c0e2f`** (High) — Lighthouse versions before
v1.2.0 exposed to a vulnerability in the core cryptography library
(`blst` advisory).

**壊れた不変条件**: 暗号レイヤーは署名方式を正しく実装しなけれ
ばならない — 検証者は暗号仕様の下で妥当なアーティファクトのみ
を受理する。同値な言い方をすれば、無効なアーティファクトが受理
されることは決してない。

**root_cause**: `crypto_misuse`。

**クラス**: `crypto-auth-integrity`。

**抽象化**: クラスレベル — アドバイザリは不具合の仕組みを開示
していない。影響を受けたコアライブラリの暗号学的正しさの不変
条件にマッピングした。

読み下し: 仮説は検証者の健全性 `VerifierSound` であり、結論は
その拒否側の読み `RejectsInvalid v Valid` の1適用である。 -/
theorem entry_f6053ce4214c0e2f_crypto_auth_integrity
    {PubKey Signature : Type}
    (v : Verifier PubKey Signature)
    (Valid : PubKey → Signature → Prop)
    (hSound : VerifierSound v Valid) :
    RejectsInvalid v Valid :=
  rejectsInvalid_of_sound hSound

end EthVulnFormalProps
