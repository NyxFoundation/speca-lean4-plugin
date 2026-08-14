import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `availability-robustness`

主クラスが `availability-robustness` であるインベントリの各エントリ
に対して定理を1つずつ用意する（`data/classification.json` を参照)。
これらの定理は `EthVulnFormalProps.Common` の `Handler` /
`Outcome` / `NeverCrashes` をインスタンス化する。仮定はパッチ済み
コンポーネントがすべての（関連する）入力を受理または正常な拒否と
いう定義済みの結果へと処理することを述べ、結論はクラッシュしない
こと、すなわち当該脆弱性が破っていた不変条件である。証明は対象外
のため `sorry` とする。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_availability_robustness`。
-/

namespace EthVulnFormalProps

/-- **エントリ `26333a99f530c12b`** (High) — Lighthouse v8.2.0 の、
複数のセキュリティ脆弱性を修正した高優先度リリース。

**壊れた不変条件**: ビーコンノードは敵対的な入力の下でも動作を
継続しなければならない — 信頼できないデータからクラッシュ系の
障害に到達してはならない。

**root_cause**: `other` — 詳細はアドバイザリにより非公開。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — リリースノートには脆弱性の詳細が
記載されておらず、後日の開示を待ちながら、コンセンサスクライアント
のセキュリティリリースが保護する可用性の不変条件に対応付けた。 -/
theorem entry_26333a99f530c12b_availability_robustness
    {UntrustedInput BeaconNodeState : Type}
    (h : Handler UntrustedInput BeaconNodeState)
    (hTotal : ∀ s i, ∃ s', h s i = .ok s' ∨ h s i = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `42783aef3977582f`** (High) — Reth 1.0 リリース:
0.2.0-beta.6 以降、reorg 関連のエッジケースを含めクラッシュ報告
なし。

**壊れた不変条件**: それ以前のバージョンは reorg 関連のエッジ
ケースで時折クラッシュしていた。高稼働率が求められる運用では、
到達可能な reorg イベントによってノードがクラッシュしないことが
必要である。

**root_cause**: `other`。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — 具体的な脆弱性を伴わないリリース
ノートのエントリであり、リリースが主張するクラッシュしないという
可用性の不変条件に対応付けた（リリースが名指しする障害領域である
reorg イベントに基づいてモデル化した)。 -/
theorem entry_42783aef3977582f_availability_robustness
    {ReorgEvent NodeState : Type}
    (h : Handler ReorgEvent NodeState)
    (hTotal : ∀ s e, ∃ s', h s e = .ok s' ∨ h s e = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `4773ad178a1b0415`** (High) — パニックまたは不正な
状態につながりうる、ライブ同期中の重大なバグ (#6821)。

**壊れた不変条件**: ライブ同期中に到達しうるある条件がノードを
パニックさせる（あるいは不正な状態を残す — セカンダリクラスを
参照）可能性があった。すべての同期メッセージは定義済みの結果へと
処理されなければならない。

**root_cause**: `missing_input_validation` — 同期中の未処理の
条件。

**クラス**: `availability-robustness`、セカンダリとして
`state-integrity`（同じ修正が状態の一貫性も保護しており、その
状態面は `hTotal` の `ok` 分岐を `PreservesInv` として読んだもの
に相当する)。 -/
theorem entry_4773ad178a1b0415_availability_robustness
    {SyncMsg NodeState : Type}
    (h : Handler SyncMsg NodeState)
    (hTotal : ∀ s i, ∃ s', h s i = .ok s' ∨ h s i = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `498f88c549b37c7c`** (High) — `--history:prune` 指定時に
Nimbus が起動時にクラッシュする問題
("backfill block must have a summary")。

**壊れた不変条件**: 正当でサポートされている構成から到達可能な
アサーションが、起動時にノードを異常終了させた。サポートされて
いるどの構成での起動も、クラッシュではなく定義済みの結果に到達
しなければならない。

**root_cause**: `missing_input_validation`。

**クラス**: `availability-robustness`。

読み下し: クラッシュしないことは、サポートされている構成の
定義域 (`supported cfg`) 上で主張されており、脆弱だったアサー
ションはこれに違反していた。 -/
theorem entry_498f88c549b37c7c_availability_robustness
    {Config NodeState : Type}
    (startup : Handler Config NodeState) (supported : Config → Prop)
    (hTotal : ∀ s cfg, supported cfg →
      ∃ s', startup s cfg = .ok s' ∨ startup s cfg = .reject s') :
    ∀ s cfg, supported cfg → startup s cfg ≠ .crash := sorry

/-- **エントリ `71a24007e8915533`** (High) — 外部 RPC デーモンと
Milestones を併用した際に Erigon Polygon が起動時にパニックする
問題。

**壊れた不変条件**: サポートされている構成（Milestones ＋外部
RPC デーモン）で到達可能なパニックが起動時にノードを異常終了
させた。サポートされている構成での起動はクラッシュしてはならない。

**root_cause**: `other`。

**クラス**: `availability-robustness`。 -/
theorem entry_71a24007e8915533_availability_robustness
    {Config NodeState : Type}
    (startup : Handler Config NodeState) (supported : Config → Prop)
    (hTotal : ∀ s cfg, supported cfg →
      ∃ s', startup s cfg = .ok s' ∨ startup s cfg = .reject s') :
    ∀ s cfg, supported cfg → startup s cfg ≠ .crash := sorry

/-- **エントリ `82bd894e6ef4c96a`** (High) — 細工された `Signer` に
よる golang.org/x/crypto/ssh のサービス拒否。

**壊れた不変条件**: 細工された `Signer` を渡した `AddHostKey` が
サーバーをクラッシュさせうる — 暗号処理経路上の想定外の値が
プロセスを異常終了させた。どれほど敵対的であっても、あらゆる
Signer の値は定義済みの結果へと処理されなければならない。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`。 -/
theorem entry_82bd894e6ef4c96a_availability_robustness
    {Signer ServerState : Type}
    (addHostKey : Handler Signer ServerState)
    (hTotal : ∀ s sig, ∃ s',
      addHostKey s sig = .ok s' ∨ addHostKey s sig = .reject s') :
    NeverCrashes addHostKey := sorry

/-- **エントリ `97363609784b4bd5`** (High) — メインネット利用者向け
の Grandine 2.0.3 高優先度セキュリティリリース。

**壊れた不変条件**: メインネットのコンセンサスノードは敵対的な
入力の下でも動作を継続しなければならない。

**root_cause**: `other` — 内容は非公開。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — 具体的な脆弱性は開示されておらず、
メインネットのセキュリティリリースが保護する可用性の不変条件に
対応付けた。 -/
theorem entry_97363609784b4bd5_availability_robustness
    {UntrustedInput BeaconNodeState : Type}
    (h : Handler UntrustedInput BeaconNodeState)
    (hTotal : ∀ s i, ∃ s', h s i = .ok s' ∨ h s i = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `9a16fbc5d8f36a00`** (High) — Grandine 2.0.2 高優先度
セキュリティリリース（execution-payload 領域）。

**壊れた不変条件**: execution-payload の処理は、信頼できない
入力に対してクラッシュ系の障害を露呈してはならない。

**root_cause**: `other` — 内容は非公開。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — 具体的な脆弱性は開示されておらず、
リリースが名指しする領域（execution-payload の処理）における
可用性の不変条件に対応付けた。 -/
theorem entry_9a16fbc5d8f36a00_availability_robustness
    {ExecutionPayload BeaconNodeState : Type}
    (h : Handler ExecutionPayload BeaconNodeState)
    (hTotal : ∀ s p, ∃ s', h s p = .ok s' ∨ h s p = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `a4feb077db6061c1`** (High) — 悪意ある p2p メッセージ
により脆弱なノードに影響する go-ethereum の DoS。

**壊れた不変条件**: 細工された p2p メッセージがノードを強制的に
シャットダウンまたはクラッシュさせた (CWE-248、捕捉されない例外)。
すべての p2p メッセージは定義済みの結果へと処理されなければ
ならない。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`。 -/
theorem entry_a4feb077db6061c1_availability_robustness
    {P2pMsg NodeState : Type}
    (h : Handler P2pMsg NodeState)
    (hTotal : ∀ s i, ∃ s', h s i = .ok s' ∨ h s i = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `a81de2d1facebe2f`** (High) — Go Ethereum チームが
発見した非公開の高深刻度修正を含む Erigon のリリース。

**壊れた不変条件**: 実行クライアントは敵対的な入力の下でも動作
を継続しなければならない。

**root_cause**: `other`。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — 脆弱性の詳細はなく、緊急のクライア
ントセキュリティ修正が保護する可用性の不変条件に対応付けた。 -/
theorem entry_a81de2d1facebe2f_availability_robustness
    {UntrustedInput NodeState : Type}
    (h : Handler UntrustedInput NodeState)
    (hTotal : ∀ s i, ∃ s', h s i = .ok s' ∨ h s i = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `c3970363b1e95aa8`** (High) — 不正な形式のパケットに
よる x/crypto/ssh のパニック。

**壊れた不変条件**: AES-GCM / ChaCha20Poly1305 の下で平文が空の
不正な形式のパケットが、拒否ではなくパニックに到達していた。
不正な形式のワイヤー入力は、プロセスをクラッシュさせることなく
正常に拒否されなければならない。

**root_cause**: `missing_input_validation`。

**クラス**: `availability-robustness`、セカンダリとして
`input-validation`（`hMalformedRejected` は、まさに修正で追加
された不足していた検証そのものである)。 -/
theorem entry_c3970363b1e95aa8_availability_robustness
    {Packet ConnState : Type}
    (h : Handler Packet ConnState) (wellFormed : Packet → Prop)
    (hMalformedRejected : ∀ s p, ¬ wellFormed p → h s p = .reject s)
    (hWellFormedTotal : ∀ s p, wellFormed p →
      ∃ s', h s p = .ok s' ∨ h s p = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `d77e6d7be5ad3831`** (High) — 不正な形式の X.509
証明書による Go crypto パッケージのパニック (Helm 経由)。

**壊れた不変条件**: 不正な形式の X.509 証明書のパースが、パー
スエラーを返す代わりにパニックしていた。信頼できない不正な形式
の証明書は正常に拒否されなければならない。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`、セカンダリとして
`input-validation`。 -/
theorem entry_d77e6d7be5ad3831_availability_robustness
    {X509Cert ParserState : Type}
    (parse : Handler X509Cert ParserState)
    (wellFormed : X509Cert → Prop)
    (hMalformedRejected : ∀ s c, ¬ wellFormed c → parse s c = .reject s)
    (hWellFormedTotal : ∀ s c, wellFormed c →
      ∃ s', parse s c = .ok s' ∨ parse s c = .reject s') :
    NeverCrashes parse := sorry

/-- **エントリ `dfc686972ac72690`** (High) — golang.org/x/crypto/ssh の
NULL ポインタデリファレンス。

**壊れた不変条件**: 細工された認証リクエストが nil デリファレン
スに到達し、サーバーをクラッシュさせた。認証リクエストの未検証
のフィールドがデリファレンスまで伝播してはならない — すべての
リクエストは定義済みの結果へと処理される。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`、セカンダリとして
`input-validation`。 -/
theorem entry_dfc686972ac72690_availability_robustness
    {AuthRequest ServerState : Type}
    (h : Handler AuthRequest ServerState)
    (hTotal : ∀ s r, ∃ s', h s r = .ok s' ∨ h s r = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `geth:ethereum-go-ethereum:GHSA-2gjw-fg97-vg3r`** (High) —
悪意ある p2p メッセージによる DoS (Geth v1.16.9 / v1.17.0 で修正)。

**壊れた不変条件**: 細工された p2p メッセージが Geth ノードを
強制的にシャットダウンまたはクラッシュさせうる。すべての p2p
メッセージは定義済みの結果へと処理されなければならない。

**root_cause**: `resource_exhaustion` (dataset) — 細工された
メッセージがノードを致命的な状態に追い込んだ。

**クラス**: `availability-robustness`。 -/
theorem entry_geth_ethereum_go_ethereum_GHSA_2gjw_fg97_vg3r_availability_robustness
    {P2pMsg NodeState : Type}
    (h : Handler P2pMsg NodeState)
    (hTotal : ∀ s i, ∃ s', h s i = .ok s' ∨ h s i = .reject s') :
    NeverCrashes h := sorry

/-- **エントリ `geth:ghsa-advisory:GHSA-m6gx-rhvj-fh52`** (Critical) —
Go の CVE-2020-28362 (math/big パニック) に起因する DoS。

**壊れた不変条件**: 脆弱な Go バージョンでビルドされた Geth は、
暗号処理経路上の信頼できない入力から到達可能な `math/big` の
パニックを引き継いでいた。敵対的なオペランドに対する多倍長整数
演算は、決してノードをクラッシュさせてはならない。

**root_cause**: `resource_exhaustion` (dataset; mechanism: divide
panic in `math/big`)。

**クラス**: `availability-robustness`。 -/
theorem entry_geth_ghsa_advisory_GHSA_m6gx_rhvj_fh52_availability_robustness
    {BigIntOperands NodeState : Type}
    (compute : Handler BigIntOperands NodeState)
    (hTotal : ∀ s ops, ∃ s',
      compute s ops = .ok s' ∨ compute s ops = .reject s') :
    NeverCrashes compute := sorry

end EthVulnFormalProps
