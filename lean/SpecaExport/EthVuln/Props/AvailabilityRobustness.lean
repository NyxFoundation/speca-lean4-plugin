import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `availability-robustness`

主クラスが `availability-robustness` であるインベントリの各エントリ
に対して定理を1つずつ用意する（`data/classification.json` を参照)。

PR #24 レビュー対応: 旧形式の仮定 `hTotal`（すべての入力が ok か
reject に落ちる）は `NeverCrashes` の言い換えそのものであり、01e に
定義の再掲しか出せなかった。本版では実装が守るべき具体的な2条件 —

1. **`RejectsMalformed`**: 整形式でない入力は、状態を一切変えずに
   正常拒否される（malformed 入力に対するパース・検証段階の全域性
   とロールバック）。
2. **`TotalOnWellFormed`**: 整形式の入力の処理は全域である。リソース
   枯渇・内部エラーといった失敗も、クラッシュではなく状態を変えない
   定義された拒否に落ちる。

— に分解し、結論 `NeverCrashes` は Common の分解補題
`neverCrashes_of_split` で証明する（`sorry` なし）。`wellFormed` は
各エントリの入力整形式性（構文・意味検証を通過すること）の抽象で
ある。詳細非公開のエントリでは、この段階分解は標準的なクラッシュ
ベクタ（malformed input / resource exhaustion / state rollback）に
基づくモデリング選択であり、dataset が個別に記載する事実ではない —
その旨を各 docstring に明記する。

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
記載されておらず、コンセンサスクライアントのセキュリティリリース
が保護する可用性の不変条件に対応付けた。`wellFormed` による
段階分解（malformed の正常拒否／整形式入力の全域処理）は標準的な
クラッシュベクタに基づくモデリング選択であり、dataset の記載
事実ではない。 -/
theorem entry_26333a99f530c12b_availability_robustness
    {UntrustedInput BeaconNodeState : Type}
    (h : Handler UntrustedInput BeaconNodeState)
    (wellFormed : UntrustedInput → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

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
reorg イベントに基づいてモデル化した)。`wellFormed` は reorg
イベントの整形式性（チェーン上に実在する分岐点への到達可能性など）
の抽象であり、段階分解はモデリング選択である。 -/
theorem entry_42783aef3977582f_availability_robustness
    {ReorgEvent NodeState : Type}
    (h : Handler ReorgEvent NodeState)
    (wellFormed : ReorgEvent → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `4773ad178a1b0415`** (High) — パニックまたは不正な
状態につながりうる、ライブ同期中の重大なバグ (#6821)。

**壊れた不変条件**: ライブ同期中に到達しうるある条件がノードを
パニックさせる（あるいは不正な状態を残す — セカンダリクラスを
参照）可能性があった。すべての同期メッセージは定義済みの結果へと
処理されなければならない。

**root_cause**: `missing_input_validation` — 同期中の未処理の
条件。

**クラス**: `availability-robustness`、セカンダリとして
`state-integrity`（同じ修正が状態の一貫性も保護している —
`RejectsMalformed` / `TotalOnWellFormed` の拒否は状態を変えない
（ロールバック）ため、失敗経路が不正な状態を残さないという
状態面も同じ2条件が担う)。 -/
theorem entry_4773ad178a1b0415_availability_robustness
    {SyncMsg NodeState : Type}
    (h : Handler SyncMsg NodeState)
    (wellFormed : SyncMsg → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `498f88c549b37c7c`** (High) — `--history:prune` 指定時に
Nimbus が起動時にクラッシュする問題
("backfill block must have a summary")。

**壊れた不変条件**: 正当でサポートされている構成から到達可能な
アサーションが、起動時にノードを異常終了させた。起動はどの構成
に対してもクラッシュしてはならない — サポート外の構成は正常に
拒否され（グレースフルな起動失敗）、サポートされている構成での
起動は必ず定義済みの結果に到達する。

**root_cause**: `missing_input_validation`。

**クラス**: `availability-robustness`。

読み下し: `supported` を整形式性として段階分解する。脆弱だった
アサーションは「サポートされている構成での起動の全域性」
（`TotalOnWellFormed`）に違反していた。旧版の結論は
`supported cfg` 上に限定されていたが、サポート外構成の正常拒否も
実装義務に含めたため、結論は無条件の `NeverCrashes` に強まって
いる。 -/
theorem entry_498f88c549b37c7c_availability_robustness
    {Config NodeState : Type}
    (startup : Handler Config NodeState) (supported : Config → Prop)
    (hUnsupportedRejected : RejectsMalformed startup supported)
    (hSupportedTotal : TotalOnWellFormed startup supported) :
    NeverCrashes startup :=
  neverCrashes_of_split hUnsupportedRejected hSupportedTotal

/-- **エントリ `71a24007e8915533`** (High) — 外部 RPC デーモンと
Milestones を併用した際に Erigon Polygon が起動時にパニックする
問題。

**壊れた不変条件**: サポートされている構成（Milestones ＋外部
RPC デーモン）で到達可能なパニックが起動時にノードを異常終了
させた。起動はどの構成に対してもクラッシュしてはならない —
サポート外の構成は正常拒否、サポートされている構成は全域処理。

**root_cause**: `other`。

**クラス**: `availability-robustness`。

読み下し: `entry_498f88c549b37c7c` と同じ段階分解（`supported` を
整形式性とする）。脆弱だったパニックは `TotalOnWellFormed` への
違反である。 -/
theorem entry_71a24007e8915533_availability_robustness
    {Config NodeState : Type}
    (startup : Handler Config NodeState) (supported : Config → Prop)
    (hUnsupportedRejected : RejectsMalformed startup supported)
    (hSupportedTotal : TotalOnWellFormed startup supported) :
    NeverCrashes startup :=
  neverCrashes_of_split hUnsupportedRejected hSupportedTotal

/-- **エントリ `82bd894e6ef4c96a`** (High) — 細工された `Signer` に
よる golang.org/x/crypto/ssh のサービス拒否。

**壊れた不変条件**: 細工された `Signer` を渡した `AddHostKey` が
サーバーをクラッシュさせうる — 暗号処理経路上の想定外の値が
プロセスを異常終了させた。どれほど敵対的であっても、あらゆる
Signer の値は定義済みの結果へと処理されなければならない。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`。

読み下し: `wellFormed` は Signer 値の契約適合性（アルゴリズム名と
鍵素材の整合など）の抽象。修正が追加したのは、契約に反する
Signer の正常拒否（`RejectsMalformed`）である — 脆弱版はそこで
パニックしていた。 -/
theorem entry_82bd894e6ef4c96a_availability_robustness
    {Signer ServerState : Type}
    (addHostKey : Handler Signer ServerState)
    (wellFormed : Signer → Prop)
    (hMalformed : RejectsMalformed addHostKey wellFormed)
    (hTotal : TotalOnWellFormed addHostKey wellFormed) :
    NeverCrashes addHostKey :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `97363609784b4bd5`** (High) — メインネット利用者向け
の Grandine 2.0.3 高優先度セキュリティリリース。

**壊れた不変条件**: メインネットのコンセンサスノードは敵対的な
入力の下でも動作を継続しなければならない。

**root_cause**: `other` — 内容は非公開。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — 具体的な脆弱性は開示されておらず、
メインネットのセキュリティリリースが保護する可用性の不変条件に
対応付けた。段階分解（malformed の正常拒否／整形式入力の全域
処理）は標準的なクラッシュベクタに基づくモデリング選択であり、
dataset の記載事実ではない。 -/
theorem entry_97363609784b4bd5_availability_robustness
    {UntrustedInput BeaconNodeState : Type}
    (h : Handler UntrustedInput BeaconNodeState)
    (wellFormed : UntrustedInput → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `9a16fbc5d8f36a00`** (High) — Grandine 2.0.2 高優先度
セキュリティリリース（execution-payload 領域）。

**壊れた不変条件**: execution-payload の処理は、信頼できない
入力に対してクラッシュ系の障害を露呈してはならない。

**root_cause**: `other` — 内容は非公開。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — 具体的な脆弱性は開示されておらず、
リリースが名指しする領域（execution-payload の処理）における
可用性の不変条件に対応付けた。`wellFormed` はペイロードの
整形式性（SSZ デコード＋consensus 仕様の妥当性検査）の抽象で
あり、段階分解はモデリング選択である。 -/
theorem entry_9a16fbc5d8f36a00_availability_robustness
    {ExecutionPayload BeaconNodeState : Type}
    (h : Handler ExecutionPayload BeaconNodeState)
    (wellFormed : ExecutionPayload → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `a4feb077db6061c1`** (High) — 悪意ある p2p メッセージ
により脆弱なノードに影響する go-ethereum の DoS。

**壊れた不変条件**: 細工された p2p メッセージがノードを強制的に
シャットダウンまたはクラッシュさせた (CWE-248、捕捉されない例外)。
すべての p2p メッセージは定義済みの結果へと処理されなければ
ならない。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`。

読み下し: CWE-248（捕捉されない例外）はまさに
`RejectsMalformed` への違反 — 細工された（整形式でない）
メッセージが正常拒否ではなく例外経路に到達していた。 -/
theorem entry_a4feb077db6061c1_availability_robustness
    {P2pMsg NodeState : Type}
    (h : Handler P2pMsg NodeState)
    (wellFormed : P2pMsg → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `a81de2d1facebe2f`** (High) — Go Ethereum チームが
発見した非公開の高深刻度修正を含む Erigon のリリース。

**壊れた不変条件**: 実行クライアントは敵対的な入力の下でも動作
を継続しなければならない。

**root_cause**: `other`。

**クラス**: `availability-robustness`。

**抽象化**: クラスレベル — 脆弱性の詳細はなく、緊急のクライア
ントセキュリティ修正が保護する可用性の不変条件に対応付けた。
段階分解はモデリング選択であり、dataset の記載事実ではない。 -/
theorem entry_a81de2d1facebe2f_availability_robustness
    {UntrustedInput NodeState : Type}
    (h : Handler UntrustedInput NodeState)
    (wellFormed : UntrustedInput → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `c3970363b1e95aa8`** (High) — 不正な形式のパケットに
よる x/crypto/ssh のパニック。

**壊れた不変条件**: AES-GCM / ChaCha20Poly1305 の下で平文が空の
不正な形式のパケットが、拒否ではなくパニックに到達していた。
不正な形式のワイヤー入力は、プロセスをクラッシュさせることなく
正常に拒否されなければならない。

**root_cause**: `missing_input_validation`。

**クラス**: `availability-robustness`、セカンダリとして
`input-validation`（`hMalformedRejected` は、まさに修正で追加
された不足していた検証そのものである)。

読み下し: このエントリは分解の2条件が dataset の記載と直接対応
する具体例である — 脆弱性は「平文が空の malformed パケット」が
`RejectsMalformed` に違反してパニックに到達したこと。拒否が状態
を変えない（ロールバック）ことまで実装義務に含む。 -/
theorem entry_c3970363b1e95aa8_availability_robustness
    {Packet ConnState : Type}
    (h : Handler Packet ConnState) (wellFormed : Packet → Prop)
    (hMalformedRejected : RejectsMalformed h wellFormed)
    (hWellFormedTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformedRejected hWellFormedTotal

/-- **エントリ `d77e6d7be5ad3831`** (High) — 不正な形式の X.509
証明書による Go crypto パッケージのパニック (Helm 経由)。

**壊れた不変条件**: 不正な形式の X.509 証明書のパースが、パー
スエラーを返す代わりにパニックしていた。信頼できない不正な形式
の証明書は正常に拒否されなければならない。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`、セカンダリとして
`input-validation`。

読み下し: `entry_c3970363b1e95aa8` と同様、dataset の記載が
`RejectsMalformed`（malformed 証明書のパースエラーによる正常
拒否）に直接対応するエントリである。 -/
theorem entry_d77e6d7be5ad3831_availability_robustness
    {X509Cert ParserState : Type}
    (parse : Handler X509Cert ParserState)
    (wellFormed : X509Cert → Prop)
    (hMalformedRejected : RejectsMalformed parse wellFormed)
    (hWellFormedTotal : TotalOnWellFormed parse wellFormed) :
    NeverCrashes parse :=
  neverCrashes_of_split hMalformedRejected hWellFormedTotal

/-- **エントリ `dfc686972ac72690`** (High) — golang.org/x/crypto/ssh の
NULL ポインタデリファレンス。

**壊れた不変条件**: 細工された認証リクエストが nil デリファレン
スに到達し、サーバーをクラッシュさせた。認証リクエストの未検証
のフィールドがデリファレンスまで伝播してはならない — すべての
リクエストは定義済みの結果へと処理される。

**root_cause**: `unhandled_error_or_nil`。

**クラス**: `availability-robustness`、セカンダリとして
`input-validation`。

読み下し: nil デリファレンスは「未検証フィールドを持つ
（整形式でない）リクエストの正常拒否」（`RejectsMalformed`）へ
の違反である — 修正はまさにこの検証を追加した。 -/
theorem entry_dfc686972ac72690_availability_robustness
    {AuthRequest ServerState : Type}
    (h : Handler AuthRequest ServerState)
    (wellFormed : AuthRequest → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `geth:ethereum-go-ethereum:GHSA-2gjw-fg97-vg3r`** (High) —
悪意ある p2p メッセージによる DoS (Geth v1.16.9 / v1.17.0 で修正)。

**壊れた不変条件**: 細工された p2p メッセージが Geth ノードを
強制的にシャットダウンまたはクラッシュさせうる。すべての p2p
メッセージは定義済みの結果へと処理されなければならない。

**root_cause**: `resource_exhaustion` (dataset) — 細工された
メッセージがノードを致命的な状態に追い込んだ。

**クラス**: `availability-robustness`。

読み下し: dataset の root_cause はリソース枯渇である —
`TotalOnWellFormed` は「リソース枯渇も、クラッシュではなく状態を
変えない定義された拒否（バックプレッシャ）に落ちる」ことを実装
義務として含む。 -/
theorem entry_geth_ethereum_go_ethereum_GHSA_2gjw_fg97_vg3r_availability_robustness
    {P2pMsg NodeState : Type}
    (h : Handler P2pMsg NodeState)
    (wellFormed : P2pMsg → Prop)
    (hMalformed : RejectsMalformed h wellFormed)
    (hTotal : TotalOnWellFormed h wellFormed) :
    NeverCrashes h :=
  neverCrashes_of_split hMalformed hTotal

/-- **エントリ `geth:ghsa-advisory:GHSA-m6gx-rhvj-fh52`** (Critical) —
Go の CVE-2020-28362 (math/big パニック) に起因する DoS。

**壊れた不変条件**: 脆弱な Go バージョンでビルドされた Geth は、
暗号処理経路上の信頼できない入力から到達可能な `math/big` の
パニックを引き継いでいた。敵対的なオペランドに対する多倍長整数
演算は、決してノードをクラッシュさせてはならない。

**root_cause**: `resource_exhaustion` (dataset; mechanism: divide
panic in `math/big`)。

**クラス**: `availability-robustness`。

読み下し: `math/big` の除算パニックは「整形式（仕様上有効）な
オペランドの全域処理」（`TotalOnWellFormed`）への違反である —
仕様が結果を定めている入力で、実装の演算がパニックした。 -/
theorem entry_geth_ghsa_advisory_GHSA_m6gx_rhvj_fh52_availability_robustness
    {BigIntOperands NodeState : Type}
    (compute : Handler BigIntOperands NodeState)
    (wellFormed : BigIntOperands → Prop)
    (hMalformed : RejectsMalformed compute wellFormed)
    (hTotal : TotalOnWellFormed compute wellFormed) :
    NeverCrashes compute :=
  neverCrashes_of_split hMalformed hTotal

end EthVulnFormalProps
