import SpecaExport.EthVuln.Common

/-!
# 命題 — 不変条件クラス `resource-bounds`

主クラスが `resource-bounds` であるインベントリ項目ごとに定理を
1つ用意する（`data/classification.json` を参照）。各定理は
`EthVulnFormalProps.Common` にある共通の `ResourceModel` /
`BoundedUsage` の概念を、その項目のエンティティで具体化した
ものであり、仮定は修正によって回復された保証（各割り当ての
計上、上限での受け入れ制御、拒否時に増加しないこと）を表現し、
結論はその脆弱性が破っていたリソース上限の不変条件である。
仮説は Common の named 述語（`UsageAccounted` /
`AdmissionControlled` / `RejectFrees`）で述べ、結論
`BoundedUsage` は Common の分解補題
`boundedUsage_of_admission` で証明する（`sorry` なし）。

定理の命名規則:
`entry_<id sanitized: [^A-Za-z0-9] → _>_resource_bounds`。
-/

namespace EthVulnFormalProps

/-- **エントリ `02e19ccf58f8c45a`** (High) — libp2p DoS vulnerability from
lack of resource management.

**壊れた不変条件**: 攻撃者ノードは被害者に対し、OOM killer に
殺されるまで際限なく多数の小さなメモリチャンクを割り当てさせる
ことができた。ピアごとのメモリ消費量は一定の上限内に収まらな
ければならない。

**root_cause**: `resource_exhaustion` — libp2p のリソース
マネージャが攻撃者主導の割り当てを計上・制限していなかった。

**クラス**: `resource-bounds`。

読み下し: `m` は修正後の libp2p 受信パス（usage = 割り当て
バイト数）をモデル化する。受理されたチャンクがすべて計上され
（`hAccounted`）、受け入れ制御が上限を超える割り当てを拒否し
（`hAdmission`）、拒否によって usage が増加しない
（`hRejectFree`）ならば、どの入力列もメモリ上限を超えることは
できない。 -/
theorem entry_02e19ccf58f8c45a_resource_bounds
    {Chunk NodeState : Type}
    (m : ResourceModel Chunk NodeState) (memBound : Nat)
    (allocSize : Chunk → Nat)
    (hAccounted : UsageAccounted m allocSize)
    (hAdmission : AdmissionControlled m allocSize memBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m memBound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `11641305ff48c094`** (High) — libp2p DoS vulnerability from
lack of resource management (consensus-layer p2p surface).

**壊れた不変条件**: 同じ libp2p リソース管理の欠陥が、
コンセンサス層の p2p インターフェースを通じて表面化した
もの — 攻撃者主導の割り当てが上限なく増加する。

**root_cause**: `resource_exhaustion` — CL の p2p パスで
割り当てが計上されていなかった。

**クラス**: `resource-bounds`。 -/
theorem entry_11641305ff48c094_resource_bounds
    {PeerMsg BeaconNodeState : Type}
    (m : ResourceModel PeerMsg BeaconNodeState) (memBound : Nat)
    (allocSize : PeerMsg → Nat)
    (hAccounted : UsageAccounted m allocSize)
    (hAdmission : AdmissionControlled m allocSize memBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m memBound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `18c4c57dddc34f3e`** (High) — Geth v1.4.13 hotfix release
during the 2016 network DoS attacks.

**壊れた不変条件**: 価格が過小に設定された EVM 操作により、
攻撃者は支払ったガスに見合わないほど状態サイズと処理コストを
膨張させることができた。ブロックあたりのリソース増加量は、
ガススケジュールが強制する上限内に収まらなければならない。

**root_cause**: `resource_exhaustion` — 操作のガス価格が
真のリソースコストを賄っていなかった。

**クラス**: `resource-bounds`。

**抽象化**: クラスレベル — リリースノート由来の項目。具体的に
どの上限が破られたか（価格が過小な状態増大操作）は、この
リリースが参照する、よく知られた2016年の Shanghai DoS の
文脈から推測した。`gasCharged` は送信者がその操作に対して
支払ったガスであり、`rate` は改定後のスケジュールが保証する
ガスあたりのリソース上限である。 -/
theorem entry_18c4c57dddc34f3e_resource_bounds
    {Op ChainState : Type}
    (m : ResourceModel Op ChainState) (stateBound : Nat)
    (gasCharged : Op → Nat) (rate : Nat)
    (hPriced : UsageAccounted m (fun op => rate * gasCharged op))
    (hAdmission : AdmissionControlled m
      (fun op => rate * gasCharged op) stateBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m stateBound :=
  boundedUsage_of_admission hPriced hAdmission hRejectFree

/-- **エントリ `4bb523e194701da7`** (High) — Go-Ethereum vulnerable to
denial of service via malicious p2p message.

**壊れた不変条件**: Geth の p2p ハンドラは細工されたメッセージ
ごとに goroutine を生成しており、攻撃者はこれを利用して
メモリ消費を際限なく増大させることができた。ピアごとに存在
する goroutine の数（およびそれが固定するメモリ）は上限内に
収まらなければならない。

**root_cause**: `resource_exhaustion` — メッセージごとの
goroutine 生成に上限がなかった。

**クラス**: `resource-bounds`。

読み下し: usage は存在する goroutine の数を数える。
`spawned` は、修正後にあるメッセージが開始してよい
goroutine の数である。 -/
theorem entry_4bb523e194701da7_resource_bounds
    {P2pMsg NodeState : Type}
    (m : ResourceModel P2pMsg NodeState) (goroutineBound : Nat)
    (spawned : P2pMsg → Nat)
    (hAccounted : UsageAccounted m spawned)
    (hAdmission : AdmissionControlled m spawned goroutineBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m goroutineBound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `6746c31d67430ea7`** (High) — Teku: Netty upgrade fixing
CVE-2021-37136 / CVE-2021-37137 (DoS).

**壊れた不変条件**: Netty の Bzip2/Snappy デコーダは、細工
された圧縮入力を過大なサイズに展開することを許していた。
1つの入力フレームがデコードして出力できるサイズは上限内に
収まらなければならない。

**root_cause**: `resource_exhaustion` — デコーダの出力
サイズが制限されていなかった。

**クラス**: `resource-bounds`。

読み下し: usage はデコーダが保持するバイト数を測る。
`decodedSize` は、修正後のデコーダが1フレームあたりに
許容するサイズである。 -/
theorem entry_6746c31d67430ea7_resource_bounds
    {Frame DecoderState : Type}
    (m : ResourceModel Frame DecoderState) (outputBound : Nat)
    (decodedSize : Frame → Nat)
    (hAccounted : UsageAccounted m decodedSize)
    (hAdmission : AdmissionControlled m decodedSize outputBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m outputBound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `762246407b6270cf`** (High) — Denial of Service in
Go-Ethereum (txpool purge).

**壊れた不変条件**: 高ガス価格の future トランザクションを
5120件含む1つのメッセージが、Geth の txpool から保留中の
トランザクションをすべてパージしてしまった — 安価な攻撃者
入力は、攻撃者自身に許された分を超えて共有プールから追い出し
てはならない。

**root_cause**: `resource_exhaustion` — 受け入れ・追い出しの
設計により、1つの送信者がプール全体を追い出せてしまった。

**クラス**: `resource-bounds`。

読み下し: `pending` はプール内のトランザクション数を数える。
ガードは `OnAccept` 述語の内側に畳まれ、結論は「受理された
1メッセージが引き起こす追い出しは送信者上限まで」を事後条件
として述べる。 -/
theorem entry_762246407b6270cf_resource_bounds
    {TxBatch PoolState : Type}
    (pool : Handler TxBatch PoolState)
    (pending : PoolState → Nat) (senderLimit : Nat)
    (hDisplacement : OnAccept pool
      (fun s _ s' => pending s ≤ pending s' + senderLimit)) :
    OnAccept pool (fun s _ s' => pending s - senderLimit ≤ pending s') := by
  intro s txs s' hok
  have h := hDisplacement s txs s' hok
  omega

/-- **エントリ `7a01ac34bb8f8f97`** (High) — go-ethereum high CPU usage
leading to DoS via malicious p2p message.

**壊れた不変条件**: 特別に細工された p2p メッセージが高い
CPU 使用率を引き起こした。1つのメッセージの処理コストは
上限内に収まらなければならない。

**root_cause**: `resource_exhaustion` — メッセージごとの
処理コストに上限がなかった。

**クラス**: `resource-bounds`。

読み下し: usage は集計ウィンドウごとの累積 CPU 処理量である。
`cpuCost` は、修正後のハンドラが許容するメッセージごとの
コストである。 -/
theorem entry_7a01ac34bb8f8f97_resource_bounds
    {P2pMsg NodeState : Type}
    (m : ResourceModel P2pMsg NodeState) (cpuBudget : Nat)
    (cpuCost : P2pMsg → Nat)
    (hAccounted : UsageAccounted m cpuCost)
    (hAdmission : AdmissionControlled m cpuCost cpuBudget)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m cpuBudget :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `93a34a4a3b58f64f`** (High) — golang.org/x/crypto DoS via
slow or incomplete key exchange.

**壊れた不変条件**: SSH サーバは、クライアントが鍵交換を
遅延させたり未完了のままにしたりしている間、保留中の
コンテンツを上限なくバッファリングしていた。コネクションごと
のバッファバイト数は上限内に収まらなければならない。

**root_cause**: `resource_exhaustion` — 鍵交換（KEX）中の
バッファリングに上限がなかった。

**クラス**: `resource-bounds`。 -/
theorem entry_93a34a4a3b58f64f_resource_bounds
    {KexChunk ConnState : Type}
    (m : ResourceModel KexChunk ConnState) (bufferBound : Nat)
    (chunkSize : KexChunk → Nat)
    (hAccounted : UsageAccounted m chunkSize)
    (hAdmission : AdmissionControlled m chunkSize bufferBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m bufferBound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `9497bc683371db42`** (High) — libp2p DoS vulnerability from
lack of resource management.

**壊れた不変条件**: 同じ libp2p リソース管理の欠陥 — 攻撃者
主導の小さな割り当てが被害者のメモリを OOM kill まで増大させる。
ピアごとのメモリは上限内に収まらなければならない。

**root_cause**: `resource_exhaustion`。

**クラス**: `resource-bounds`。 -/
theorem entry_9497bc683371db42_resource_bounds
    {Chunk NodeState : Type}
    (m : ResourceModel Chunk NodeState) (memBound : Nat)
    (allocSize : Chunk → Nat)
    (hAccounted : UsageAccounted m allocSize)
    (hAdmission : AdmissionControlled m allocSize memBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m memBound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `a0de2557672715e7`** (High) — Lighthouse v8.1.2
high-priority security patch release.

**壊れた不変条件**: p2p サーフェスにおけるピア主導のリソース
消費が許容上限を超えていた（同じパッチ系列で公開された
姉妹版 v8.1.3 のアドバイザリによる）。

**root_cause**: `other`（系列としての root_cause はリソース
枯渇）。

**クラス**: `resource-bounds`、副次的に
`availability-robustness`。

**抽象化**: クラスレベル — アドバイザリに詳細は開示されて
いない。クラスは同じパッチ系列の姉妹版 v8.1.3 アドバイザリの
resource-exhaustion という root_cause から推測した。したがって
このモデルは、ビーコンノードの p2p 入力に対する汎用的な
クラス不変条件であり、計上・受け入れ制御・拒否時非増加という
3条件への分解も標準的なリソース管理の形に基づくモデリング選択
であって、dataset が個別に記載する事実ではない。 -/
theorem entry_a0de2557672715e7_resource_bounds
    {PeerInput BeaconNodeState : Type}
    (m : ResourceModel PeerInput BeaconNodeState) (bound : Nat)
    (cost : PeerInput → Nat)
    (hAccounted : UsageAccounted m cost)
    (hAdmission : AdmissionControlled m cost bound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m bound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `b7463c929025ca0a`** (High) — high-severity security issue
fixup on the RPC surface.

**壊れた不変条件**: RPC リクエストを処理するコストが許容
上限を超えていた。リクエストごとのコストは上限内に収まら
なければならない。

**root_cause**: `resource_exhaustion` — RPC リクエストの
コストが制限されていなかった。

**クラス**: `resource-bounds`。

**抽象化**: クラスレベル — 変更履歴に詳細はない。データセット
上の RPC サーフェスに対する `resource_exhaustion` という
root_cause から対応付けた。 -/
theorem entry_b7463c929025ca0a_resource_bounds
    {RpcRequest ServerState : Type}
    (m : ResourceModel RpcRequest ServerState) (requestBudget : Nat)
    (cost : RpcRequest → Nat)
    (hAccounted : UsageAccounted m cost)
    (hAdmission : AdmissionControlled m cost requestBudget)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m requestBudget :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `d5796321d9ebf1ae`** (High) — go-ethereum DoS via crafted
GraphQL query.

**壊れた不変条件**: `geth --http --graphql` に対する細工
された GraphQL クエリが、上限のないメモリ消費とデーモンの
ハングを引き起こした。1つのクエリの評価コストは上限内に
収まらなければならない。

**root_cause**: `resource_exhaustion` — クエリのコストが
上限を持っていなかった。

**クラス**: `resource-bounds`。 -/
theorem entry_d5796321d9ebf1ae_resource_bounds
    {GraphQLQuery ServerState : Type}
    (m : ResourceModel GraphQLQuery ServerState) (queryBudget : Nat)
    (evalCost : GraphQLQuery → Nat)
    (hAccounted : UsageAccounted m evalCost)
    (hAdmission : AdmissionControlled m evalCost queryBudget)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m queryBudget :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `ded5a1dd6fea6e65`** (High) — Lighthouse v8.1.3
high-priority security patch release.

**壊れた不変条件**: p2p インターフェースにおけるピア主導の
リソース消費が上限を超えていた。

**root_cause**: p2p インターフェースにおける
`resource_exhaustion`。

**クラス**: `resource-bounds`。 -/
theorem entry_ded5a1dd6fea6e65_resource_bounds
    {PeerInput BeaconNodeState : Type}
    (m : ResourceModel PeerInput BeaconNodeState) (bound : Nat)
    (cost : PeerInput → Nat)
    (hAccounted : UsageAccounted m cost)
    (hAdmission : AdmissionControlled m cost bound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m bound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

/-- **エントリ `ece24a10f23119be`** (High) — Lighthouse validator monitor
with high validator counts (#3728).

**壊れた不変条件**: バリデータモニタはバリデータごとの
メトリクスを出力していたが、そのカーディナリティはバリデータ数
が数千に達すると Prometheus を停止させてしまうほどだった。
監視出力のカーディナリティは、監視対象のバリデータ数によらず
上限内に収まらなければならない。

**root_cause**: `missing_input_validation`（データセット
記載）— 未検証のバリデータ数に起因する、上限のない
メトリクスカーディナリティ。

**クラス**: `resource-bounds`。

読み下し: usage はエクスポートされる個別のメトリクス系列数を
数える。修正後（バリデータ数の閾値を超えるとメトリクスを
集約する）、各イベントが導入できる系列数はたかだか
`newSeries e` であり、受け入れ制御は監視対象のバリデータ数
とは独立に選ばれた上限の下に合計を保つ。 -/
theorem entry_ece24a10f23119be_resource_bounds
    {MonitorEvent MonitorState : Type}
    (m : ResourceModel MonitorEvent MonitorState)
    (cardinalityBound : Nat)
    (newSeries : MonitorEvent → Nat)
    (hAccounted : UsageAccounted m newSeries)
    (hAdmission : AdmissionControlled m newSeries cardinalityBound)
    (hRejectFree : RejectFrees m) :
    BoundedUsage m cardinalityBound :=
  boundedUsage_of_admission hAccounted hAdmission hRejectFree

end EthVulnFormalProps
