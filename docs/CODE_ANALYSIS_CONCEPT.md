# ソースコード解析データセット 構想メモ

**作成日**: 2026-08-08
**ステータス**: 構想段階（実装未着手）
**位置づけ**: 設計判断の根拠を残すためのメモ。実装開始時に SPEC.md へ落とし込む。

---

## 0. この文書について

ソースコードから構造化データを抽出し、そのデータを起点に自由な可視化・分析を行う仕組みを作るための構想メモ。

「なぜこの選択をしたのか」を残すことを主目的とする。数か月後に自分が読んで、判断を再現できる状態を保つ。

---

## 1. 目的とスコープ

### 1.1 現時点の目的（確定）

**コード理解（Code Comprehension）**。具体的には以下を知りたい。

- 関数のコール関係（誰が誰を呼んでいるか、呼び元は誰か）
- データの所在（グローバル変数がどこで読まれ、どこで書かれているか）
- （将来）処理の流れそのもの

対象言語は **C/C++ が最優先**。メジャー言語（Python / JavaScript / TypeScript / C#）にも順次対応したい。

### 1.2 将来の可能性（非確定）

コード理解を進めるうちに、**バグ検出**にも手を出したくなる可能性がある。

これは必須要件ではない。ただし「あとから追加できる構造」にしておきたい。逆に、そこに引きずられてコード理解の基盤を壊すことは避けたい。→ 詳細は §7。

### 1.3 やらないこと（スコープガード）

明示的に「やらない」と決めておく。これを書いておかないと際限なく広がる。

- ❌ **パーサの自作**（§2.3 に理由）
- ❌ **一般的なバグ検出エンジンの自作**（Coverity / PVS-Studio と競合しない。既製エンジンの結果を取り込む）
- ❌ **IDE の代替を作ること**（編集機能は持たない。読み取り専用）
- ❌ **リアルタイム解析**（バッチで十分。インクリメンタルは後回し）
- ❌ **正確さより網羅を優先すること**（不明は「不明」と記録する。推測で埋めない）

---

## 2. 基本方針

### 2.1 中間データセット方式

ソースコードから **一度ファクト（事実）を抽出してデータセット化し、可視化・分析はすべてその上で行う**。

これは思いつきではなく、この分野の主流アーキテクチャと一致している。

| ツール | 中間表現 |
|---|---|
| CodeQL | クエリ可能なデータベース |
| Joern | CPG（Code Property Graph） |
| Understand | Entity / Reference の2モデル |
| SCIP / LSIF | シンボルと参照の永続インデックス |

**利点**: 図の作り方を変えたいとき、解析の切り口を変えたいときに、再パースが不要になる。

### 2.2 自作する層／既製に任せる層

```
[ 既製に任せる ]                    [ 自作する ]
┌──────────────┬──────────────┐   ┌───────────┬───────────┐
│ 字句・構文解析 │ 名前解決・型解決 │ → │ ファクト抽出 │ データセット │
│ (AST を作る)  │ (シンボル確定)   │   │ 何を記録するか│ 自分のスキーマ│
└──────────────┴──────────────┘   ├───────────┼───────────┤
                                    │ クエリ・集計 │  可視化    │
                                    └───────────┴───────────┘
```

**重要な認識**: 「既存ツールに縛られる」という懸念は正しいが、**縛ってくるのは「完成品ツール」であって「コンパイラのフロントエンド」ではない**。

- **縛ってくる**: Understand、Sourcetrail、Doxygen → 固定のデータモデル・固定のUI・固定の出力
- **縛ってこない**: libclang、Roslyn、TypeScript Compiler API → 生の構文木とシンボル解決結果を返すだけ

したがって、**抽象化の境界は「パーサの手前」ではなく「自分が所有するスキーマ」に置く**。抽出エンジンを差し替えても下流はそのまま使える。

### 2.3 なぜパーサを自作しないか

文法（BNF）を書くところまでは AI 支援で一気に進む。**しかし本当に大変なのはその先**。

- プリプロセッサ（`#include` 再帰展開、マクロ展開、条件コンパイル）
- 名前解決（名前空間、`using`、ADL）
- オーバーロード解決（暗黙の型変換を含む最適合の選択）
- テンプレート実体化

これは「パーサを書く」ではなく「**コンパイラのフロントエンドを書く**」仕事。Clang が20年かけて到達している場所。

**最大のリスクは「静かな取りこぼし」**。マクロと関数ポインタのせいで呼び出しエッジの8%が欠けていても、生成された図は綺麗に表示される。気づけない。そして「この関数はどこからも呼ばれていないから消せる」と誤判断する。

> **間違った答えが自信を持って出てくるツールは、答えが出ないツールより有害である。**

AI が強いのは「文法規則の生成」「ビジターのボイラープレート」「テストケースの量産」。AI が弱いのは、まさにこの**長い尻尾の言語仕様への対応**。何が漏れているかを教えてくれるのは AI ではなく、実コードにぶつかったときのバグだけ。

---

## 3. データセット設計

### 3.1 テーブル構成（初版）

**ステータス: 確定**（2026-08-25）。§3.1.1〜§3.1.3 の3つの決定を反映済み。

```
symbols.csv
  id              -- 安定シンボルID（§3.2）
  kind            -- function | variable | type | namespace | ...
  name            -- 短い名前
  qualified_name  -- 修飾名
  file, line, col, end_line, end_col
  is_definition   -- 定義か宣言か
  storage_class   -- static | extern | ...
  linkage         -- internal | external
  confidence      -- high | medium | low（§3.1.2）
  lang            -- c | cpp | py | ts | cs
  extractor       -- 抽出器の識別子とバージョン
  snapshot        -- コミットハッシュ等

calls.csv
  caller_id
  callee_id       -- 解決できた場合のみ。できなければ空
  callee_expr     -- 元の式（"fp", "handler->on_event" 等）
  status          -- resolved | unresolved | not_applicable | not_extracted
                  -- （§3.1.1）
  reason          -- status = unresolved のときのみ埋める。
                  -- via_function_pointer | virtual_unresolved
                  -- | macro_expanded | unknown
  confidence      -- high | medium | low（§3.1.2）
  call_kind       -- direct | virtual | implicit
  file, line, col
  lang, extractor, snapshot

var_refs.csv
  func_id
  var_id
  access          -- read | write | readwrite | address_of | unknown
  status          -- resolved | unresolved | not_applicable | not_extracted
  reason          -- status = unresolved のときのみ
  confidence      -- high | medium | low
  file, line, col
  lang, extractor, snapshot
```

#### 3.1.1 `status` と `reason` を分ける理由

当初は `resolution` という1列に「解決できたか」と「なぜできなかったか」を混在させていたが、**この2つは粒度の異なる軸**であり、分離する。

| 列 | 問い | 値 |
|---|---|---|
| `status` | どの状態か（事実） | `resolved` / `unresolved` / `not_applicable` / `not_extracted` |
| `reason` | なぜ解決できなかったか（事実） | `via_function_pointer` / `virtual_unresolved` / `macro_expanded` / `unknown` |

`status` の4値は「**解決できた**」「**取れなかった**」「**そもそもその言語に概念が存在しない**」「**まだ調べていない**」を区別する。この3つ（後者3値）は意味が全く違い、混ぜると解析結果を誤読する（`ANALYSIS_VIEWPOINTS.md` §3.3 ④）。

分けたことで以下が成立する。

- §7.3 のフィルタ原則が `WHERE status = 'resolved'` と素直に書ける
- `reason` に値を追加しても `status` の値域が汚れないため、既存クエリが壊れない
- 「未対応の言語だから空」（`not_extracted`）と「その言語に仮想関数が無いから空」（`not_applicable`）が区別できる

#### 3.1.2 `confidence` を enum にする理由

§7.4-2 が「信頼度列を最初から入れる」を必須としているため列を追加する。値域は **`high` / `medium` / `low` の enum**とし、数値（0.0〜1.0）は採らない。

**理由**: libclang も Jedi も確率値を返さない。数値にすると根拠のない小数を書くことになり、§2.3 の「間違った答えが自信を持って出てくるツールは、答えが出ないツールより有害」に逆行する。enum なら「Python の動的解決だから `low`」のように、**抽出器が根拠を持って言える粒度**に一致する。

`status` / `reason` / `confidence` は役割が重複しない。

| 列 | 種別 |
|---|---|
| `status` | 解決できたか（事実） |
| `reason` | できなかった理由（事実） |
| `confidence` | 解決できたと言っているが、どれだけ信じてよいか（判断） |

Python の `foo()` を Jedi が解決した場合は `status = resolved` かつ `confidence = low` になる。この組み合わせは頻出するはずで、`confidence` が無いと Python と C++ の解決結果が同じ重みで混ざる。

#### 3.1.3 `lang` / `extractor` / `snapshot` を全テーブルに持たせる理由

§7.4-4「抽出器の識別子とバージョンを記録」は再現性のための全体方針であり、`symbols` だけでは満たせない。

`symbols` から JOIN で引く案は、**未解決の行**（`callee_id` が空）で対応先が無く、抽出器のバージョンだけを上げて再抽出したケースでも破綻する。冗長を承知で全テーブルに持たせる。

§7.6 の L0 中間ファイルでは、この3列をメタ情報行に1回だけ書き、L1 取り込み時に各行へ展開する。**冗長になるのは L1 のみで、手書きする中間ファイル側は冗長にならない。**

### 3.2 シンボルID

言語ごとにネイティブIDの形が違うため、そのまま混ぜるとデータセットが破綻する。

| 言語 | ネイティブID |
|---|---|
| C/C++ | USR（`c:@F@process#I#`） |
| C# | DocumentationCommentId（`M:App.Svc.Process(System.Int32)`） |
| TS/JS | Symbol → 宣言のファイル+位置 |
| Python | `module.Class.method` |

**方針: SCIP のシンボル文字列形式を借用する。**

SCIP は LSIF の後継として Sourcegraph が設計した規格で、不透明なID番号ではなく人間が読めるシンボル文字列を使う。**多言語のシンボルを1つの名前空間に統合するために設計されている**ため、車輪の再発明にならない。

副産物として `scip-python` / `scip-typescript` の出力を直接取り込める。

- 仕様: https://github.com/sourcegraph/scip
- 2026年3月、Uber・Meta・Sourcegraph のエンジニアからなる運営委員会を持つオープンガバナンス体制へ移行済み

#### 3.2.1 マッピング規則（ステータス: 確定 2026-08-25）

SCIP のシンボル文字列は次の構造を持つ。

```
<scheme> <package-manager> <package-name> <version> <descriptor...>
```

**問題**: C/C++ には「パッケージマネージャ」「パッケージ名」「バージョン」に相当する概念が存在しない。npm や pypi のような座標系が無いため、この3欄に入れる値が決まらない。

**決定**: 自リポジトリのコードには **`local` スキーム**を使い、パッケージ座標の位置にリポジトリ識別子とスナップショットを入れる。

```
local  <repo-name>  <snapshot>  <descriptor...>
```

外部ライブラリへの参照は、`scip-python` / `scip-typescript` が生成する本来の座標（`pypi requests 2.31.0` 等）をそのまま受け入れる。両者は同じ名前空間に矛盾なく共存する。

**採用理由**: C/C++ に無理やりパッケージ概念を当てはめない。`requests` を解析した場合、`requests` 自身のコードは `local`、`urllib3` への参照は `pypi` スキームとなり、1つの `symbols` テーブルに自然に並ぶ。

**却下した案**:

| 案 | 却下理由 |
|---|---|
| ネイティブIDに言語プレフィクスを付けるだけ（`cpp:c:@F@process#I#`） | 実装は最も楽だが、§3.2 が否定した「IDの文法が言語ごとにバラバラ」がそのまま残る。SCIP 互換性も失い、`scip-python` の出力を取り込めない |
| SCIP 完全準拠（パッケージ座標を厳密に埋める） | C/C++ で埋める値が存在せず、結局ダミーを入れることになる |

**要実測（Phase 0）**: descriptor 部分を各言語のネイティブIDから機械的に生成できるか。特に C++ のオーバーロード・テンプレートで descriptor が一意になるか。

> **実測メモ（2026-08-25）**: `pip install libclang` で USR の取得を確認済み。`static void helper(void)` は `c:t.c@F@helper`（ファイル名入り）、`void process(int)` は `c:@F@process` となり、**同名の別物が USR レベルで区別される**ことを確認した。descriptor 生成の入力としては十分な情報がある。

### 3.3 「解決できなかった」を記録する ★最重要

**これが自作の最大の価値。既製ツールがやってくれない部分。**

`callee_id` が空でも行を残し、`callee_expr` に元の式を、`status` / `reason` に状態と理由を記録する（§3.1.1）。

これにより、**自分の知識の穴がどこにあるかがデータとして見える**ようになる。§2.3 で挙げた「静かな取りこぼし」という最大のリスクが、可視化できるものに変わる。

```sql
-- 解決率のモニタリング
SELECT status, COUNT(*) FROM calls GROUP BY status;

-- 未解決の理由の内訳（なぜ解けなかったか）
SELECT reason, COUNT(*) FROM calls
WHERE status = 'unresolved' GROUP BY reason ORDER BY 2 DESC;

-- 未解決が集中しているファイル = 要注意領域
-- not_applicable（言語に概念が無い）を混ぜないこと
SELECT file, COUNT(*) FROM calls
WHERE status = 'unresolved' GROUP BY file ORDER BY 2 DESC;

-- 「解決済み」と言っているが信用度が低いもの = 検証優先度が高い
SELECT file, COUNT(*) FROM calls
WHERE status = 'resolved' AND confidence = 'low' GROUP BY file ORDER BY 2 DESC;
```

**原則: 抽出層では絶対に情報を捨てない。** フィルタリングは必ず下流で行う（§7.3）。

### 3.4 ストアと snapshot

**ステータス: 確定**（2026-08-25）

#### 3.4.1 L1 のストアは SQLite

配置は `facts/db.sqlite`（L0 の中間ファイルは `facts/raw/`。§7.6）。

**採用理由**:

- **追加依存がゼロ**。`sqlite3` は Python 本体に同梱されており、インストール不要。B-3 で複数ランタイムをまたぐ構成になるため、依存を増やさないことに価値がある
- 単一ファイルなので解析結果を丸ごとコピー・共有・バックアップできる
- `sqlite3` コマンドや DB Browser for SQLite で中身を直接覗ける
- 規模が足りなくなっても **DuckDB / Parquet への移行が容易**（どちらも SQLite を直接読める）。逆にグラフDBを最初に選ぶと戻れない

**却下した案**:

| 案 | 却下理由 |
|---|---|
| テキストファイル（TSV）のみ | クロスファイル集計のたびに全ファイル走査が必要。§3.3 の「未解決が集中しているファイルは?」に答えるのに全 TSV を読むことになり、T2 ストレステストで破綻する |
| DuckDB | 集計は速いが外部依存。本件のデータ規模（数万〜数十万行）では SQLite との体感差がほぼ無い |
| Parquet | 数千万行規模なら最適だが過剰。**バイナリで人間が中身を見られない**ため、本構想の「素直さ」志向と合わない |
| グラフDB（Neo4j 等） | コールグラフとの相性は理論上良いが、サーバプロセスが要る。§2.2 の「縛ってくるツール」側に近づく |

なお **TSV（L0）と SQLite（L1）の両方を持つ構成**であり、TSV が人間の目と手の入り口、SQLite が機械の集計の入り口という役割分担になっている。

#### 3.4.2 `snapshot` の粒度

`git describe --always --dirty` 相当の値を用いる。

```
8f3ac21          クリーンなワークツリー
8f3ac21-dirty    未コミットの変更あり
nogit-20260825T143052   Git 管理外（ISO 8601 基本形式、秒まで）
```

**`-dirty` を付ける理由**: `snapshot` の目的は差分検出と再現性（§7.4-3）。ハッシュだけを記録すると「そのコミットをチェックアウトすれば同じ結果が再現できる」と読めてしまうが、解析時にワークツリーが編集途中だった場合は再現できない。`-dirty` があれば**そのファクトデータが再現不能であることが一目で分かる**。§2.3「間違った答えが自信を持って出てくるツールは有害」と同じく、不確かさを黙って隠さないための仕掛け。

**ブランチ名は含めない**。同じコミットが複数ブランチに属しうるため、識別子として不安定なため。

---

## 4. 言語別ツール選定

### 4.1 選定基準

1. **意味解析（名前解決）を持っているか** — これがないと呼び出し関係すら正しく出ない
2. **深掘りの天井がどこか** — 構文木止まりか、CFG まで出るか、データフローまで出るか
3. **シンボルIDの安定性** — 翻訳単位・ファイルをまたいで名寄せできるか

### 4.2 一覧

| 言語 | 推奨 | 名前解決 | CFG | データフロー | 安定ID |
|---|---|---|---|---|---|
| C/C++ | **libclang** → 必要に応じ LibTooling | ◎ | △ | ✕ | USR |
| C# | **Roslyn** | ◎ | ◎ | ◎ | DocCommentId |
| TS/JS | **TypeScript Compiler API**（ts-morph） | ◎ | ✕ | ✕ | 宣言位置 |
| Python | **ast** + pyright系（scip-python / Jedi） | ○ | ✕ | ✕ | module.qualname |
| Go | `go/ast` + `go/types` + `go/callgraph` | ◎ | ◎ | ○ | Object |
| Java | Spoon、または JavaParser + SymbolSolver | ◎ | ○ | △ | 修飾名 |

### 4.3 C/C++ → libclang（Python）

**選定理由**: プリプロセッサ・オーバーロード解決・テンプレート実体化を正しく解ける実装が事実上 Clang しか存在しない。tree-sitter、ANTLR自作文法、Cscope はこの時点で脱落。

もう1つの重要な理由: **libclang の C API はバージョン間の安定性が保証されている**。LibTooling の C++ API は LLVM のバージョン間で平気で壊れる。長期運用する基盤としては libclang から入るのが正解。

**取れるもの**: `USR`、`CursorKind`、`referenced`、`type` / `result_type`、`semantic_parent`、`storage_class` / `linkage`、`is_virtual_method()`、`get_overriden_cursors()`

**天井**: libclang は Clang の AST の一部しか公開していない。届かないもの:
- 関数内の CFG（`clang::CFG` は C++ API 側にのみ存在）
- `Stmt` の細かいサブクラス情報（`CursorKind` に潰される）
- テンプレート実体化の詳細

**必須の前提**: `compile_commands.json`
- CMake: `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`
- それ以外: `bear -- make`
- Python バインディングは `libclang.so` のバージョンと一致させること

### 4.4 C# → Roslyn（一択、かつ最も贅沢）

**制御フロー解析とデータフロー解析が標準APIとして最初から入っている。**

```csharp
var model = compilation.GetSemanticModel(tree);

var df = model.AnalyzeDataFlow(statement);
// df.ReadInside / WrittenInside / DataFlowsIn / DataFlowsOut
// df.AlwaysAssigned / VariablesDeclared / Captured

var cf = model.AnalyzeControlFlow(block);
// cf.EntryPoints / ExitPoints / EndPointIsReachable

await SymbolFinder.FindCallersAsync(symbol, solution);  // 呼び出し元検索が標準API
```

`ISymbol.GetDocumentationCommentId()` が `M:MyApp.Service.Process(System.Int32,System.String)` を返す。人間が読めて、シグネチャを含み、XMLドキュメントと同じ規格。**IDスキームを設計する必要すらない。**

- パッケージ: `Microsoft.CodeAnalysis.CSharp.Workspaces`
- ソリューション読み込み: `MSBuildWorkspace.OpenSolutionAsync()`

> **戦術メモ**: アーキテクチャ検証を早く回したいなら、最初に C# で試すのも手。数時間でデータフローまで含むデータセットが出るので、スキーマ設計の妥当性を先に確かめられる。

### 4.5 TypeScript / JavaScript → TypeScript Compiler API（ts-morph 経由）

JS にも TS コンパイラを使う。`allowJs: true` で JS も TypeChecker を通せる。JSDoc からの型推論も効く。

SWC / oxc は Rust 製で速いが **TypeChecker を持たない**ため、この用途では失格。

```typescript
const project = new Project({ tsConfigFilePath: "tsconfig.json" });
const fn = project.getSourceFile("a.ts").getFunction("process");
fn.findReferences();
fn.getImplementations();
node.getType();
```

**天井**: CFG もデータフローもない。必要になったら AST から自前で CFG を構築するか、Joern の `jssrc2cpg` に委ねる。

**注意**: 型注釈のない素の JS では名前解決の精度が落ちる。`status` / `confidence` 列（§3.1）がここで効く。

### 4.6 Python → 標準 `ast` + pyright系（2段構え）

**唯一「一択」にならない言語。** 標準 `ast` は構文的には完璧だが、**名前解決を一切しない**。`foo()` がどの `foo` かは分からない。

Mypy / Pyre / Pytype / Pyright / Jedi は本来「型チェック」向けで、注釈済みコードには強いが、**注釈のないコード、リフレクション、動的インポートには苦戦する**。これは受け入れるべき制約。

- **構造の抽出** → 標準 `ast`（+ スコープ解析は標準 `symtable`）。正確でゼロ依存
- **名前解決** → 以下のどちらか

| 選択肢 | 特徴 |
|---|---|
| **scip-python** | pyright ベース。型チェックと意味解析をフル活用。依存パッケージが利用可能な環境で実行すれば依存先への安定参照も生成。SCIP形式で直接出力。**巨大リポジトリでCPUを食い続けて止まらなくなる報告あり**（Mozilla） |
| **Jedi** | MIT。軽量。`Script.goto()` / `get_references()` / `infer()`。Pythonプロセス内から直接呼べる |

**判断基準**: 型注釈をよく付けているコードなら scip-python、そうでなく Python プロセスに組み込みたいなら Jedi。どちらにせよ Python は best effort と割り切り、信頼度をデータに残す。

### 4.7 tree-sitter の位置づけ

**主力にはしない。「まだ抽出器を書いていない言語」の暫定対応として持つ。**

1つの抽出器アーキテクチャで多言語を薄くカバーでき、関数一覧やファイル内呼び出し程度なら実用になる。主力の抽出器ができた言語から順次置き換える。

**注意**: tree-sitter は CST 寄りで、括弧やセミコロンもノードとして持つ。またプリプロセッサを解決しないので、C/C++ では `#ifdef` の中身も外も両方 AST 化される。

---

## 5. ライセンスと制約

### 5.1 一覧（2026-08 時点で確認）

| ツール | ライセンス | 商用 | クローズドソース製品への組み込み |
|---|---|---|---|
| libclang / Clang / LLVM | Apache-2.0 with LLVM Exception | ○ | ○ |
| tree-sitter 本体 | MIT | ○ | ○ |
| tree-sitter 各文法 | 主要言語はMIT（§5.4） | ○ | ○ |
| Roslyn | MIT | ○ | ○ |
| TypeScript Compiler API | Apache-2.0 | ○ | ○ |
| ts-morph | MIT | ○ | ○ |
| Python `ast` | PSF License | ○ | ○ |
| Jedi | MIT | ○ | ○ |
| go/ast | BSD-3-Clause | ○ | ○ |
| Joern | Apache-2.0 | ○ | ○ |
| Clang Static Analyzer | Apache-2.0 with LLVM Exception | ○ | ○ |
| **CodeQL CLI** | **GitHub CodeQL Terms**（§5.2） | **✕** | ✕ |
| CodeCompass | **GPLv3** | △（§5.3） | ✕ |
| Sourcetrail / フォーク | **GPLv3** | △（§5.3） | ✕ |
| cppcheck | GPLv3 | △ | ✕ |
| Doxygen | GPL | △ | ✕ |
| SciTools Understand | プロプライエタリ商用 | 要購入 | — |

**結論: 主力構成（libclang + tree-sitter + Roslyn + TypeScript API + 自作コード）は Apache-2.0 と MIT のみで構成され、商用利用・社内配布・クローズドソース保持・製品化のすべてが可能。** 義務は著作権表示とライセンス文の同梱程度（Apache-2.0 では変更点の明示も必要）。

### 5.2 ⚠️ CodeQL の制限（業務では使えない）

構造が二重になっているのが誤解の元。

- `github/codeql`（標準ライブラリとクエリ）= **MIT**
- **CodeQL CLI（エンジン本体）= 別リポジトリ・別ライセンス（プロプライエタリ）**

CLI の利用規約が明示的に禁じているもの:

> - その他いかなる文脈においても、自動解析・CI・CD のために CodeQL データベースを生成すること。通常のエンジニアリングプロセスの一部かどうかを問わない
> - その他いかなる文脈においても、オープンソースコードベースでないコードベース（例：GitHub のプライベートリポジトリのコード）に対して本ソフトウェアを使用すること

許可されているのは学術研究、デモ、OSI承認ライセンスで公開したクエリのテスト等の限定用途のみ。有償の GitHub Advanced Security ライセンス下ではこれらの制限は適用されない。

**→ 会社のプロプライエタリな C/C++ コードを CodeQL で解析することは、GHAS なしでは規約違反。**

**代替**: データフロー解析が必要なら **Joern**（Apache-2.0）が正しい選択肢。

- 原文: https://github.com/github/codeql-cli-binaries/blob/main/LICENSE.md

### 5.3 GPL系の扱い

CodeCompass の LICENSE.txt を直接確認 → GPLv3 本文に `Copyright (C) 2012 Ericsson`。

GPL で問題になるのは**配布（convey）した場合**。GPLv3 第2条:

> あなたは、配布しない限り、あなたのライセンスが有効であり続ける限りにおいて、条件なしに covered work を作成・実行・伝播してよい

したがって:

- ✅ **社内で立てて自分たちのコードを解析する** → 配布に当たらない。義務は生じない
- ⚠️ **組み込んだ製品を社外に出す** → GPLv3 の義務が発生

GPLツールを**別プロセスとして起動し出力ファイルを受け取るだけ**の連携なら、自作側が GPL に感染するという解釈は一般的ではない。ただしこの境界は法的に議論のある領域。

### 5.4 うっかり踏みやすい落とし穴

1. **tree-sitter の文法ライセンス** — 本体は MIT だが、**文法は言語ごとに別リポジトリで別ライセンス**。公式 tree-sitter 組織のもの（cpp、c-sharp、python、javascript、java、go、html、css）は MIT。**マイナー言語を追加するときは都度 LICENSE を確認すること**（コピーレフトの文法も存在する）

2. **CodeQL を「無料で強力」と誤認すること** — §5.2

3. **Understand の Python API** — 開発者ライセンスでは `und` によるコマンドライン自動化、API アクセス、依存関係・グラフ・メトリクスのエクスポートが使えない。自動化には上位ライセンスが必要

4. **Roslyn の NuGet パッケージ内の `ThirdPartyNotices.rtf`** — Apache 2.0 の記載が残っているが、正しくは MIT（PR #41112 で変更済み）

5. **社内利用と製品化の境界** — 今は社内利用でも、将来ツールを外部に出す可能性があるなら、最初から GPL 系を組み込まないほうが安全

> **注記**: これは法的助言ではない。会社での正式採用時は、各リポジトリの LICENSE ファイルと GitHub CodeQL Terms and Conditions を法務部門に提示して判断を仰ぐこと。GPL の「配布」の解釈は会社の方針によって保守的に運用されている場合がある。

---

## 6. 深掘りの段階

### 6.1 AST → CFG → データフロー

| 表現 | 答えられる質問 |
|---|---|
| **AST** | そのコードが**どう書かれているか**。必ず木。親は1つ、循環しない |
| **CFG** | そのコードが実行時に**どの順に進みうるか**。グラフ。合流で親が複数になり、ループで閉路ができる |
| **データフロー** | 変数の値が**どこからどこへ流れるか**。CFG の上に構築される |

| 知りたいこと | AST | CFG |
|---|---|---|
| 関数の一覧、行番号 | ○ | — |
| 誰が誰を呼んでいるか | ○ | — |
| グローバル変数の参照箇所 | ○ | — |
| 型、継承、シグネチャ | ○ | — |
| 循環的複雑度 | △ | ○ |
| 到達不能コード | ✕ | ○ |
| 初期化前の変数使用 | ✕ | ○ |
| ループの検出と入れ子の深さ | △ | ○ |
| 「この行に来たとき変数はどうなっているか」 | ✕ | ○ |

**現時点の目的（コール関係、グローバル変数の所在）は全部 AST だけで足りる。** CFG は深掘り段階の入口。

### 6.2 C/C++ で CFG に届く4つの道

**LibTooling は C++ 専用 API。Python からは操作できない**（公式・実用的な非公式バインディングとも存在しない）。libclang が C API として設計されているのに対し、LibTooling は Clang の生の C++ クラス階層を公開しているため、C API に落とすことが原理的に困難。

ただし「Python を捨てて C++ に移行する」ではなく **分業** になる。

```
[C++ 200行程度]  clang-cfg-extract    ← LibTooling。CFGだけをCSVに吐く
                       ↓ cfg_blocks.csv / cfg_edges.csv
[Python 本体]    抽出パイプライン      ← 既存のまま。subprocess で叩くだけ
```

副次的利点: LibTooling の API 破壊がこの1ファイルに閉じ込められる。

| 手段 | C++ 必要 | 得られるもの | 注意 |
|---|---|---|---|
| ① `clang -Xclang -ast-dump=json` | 不要 | libclang より細かい AST | **CFG は出ない**。JSON スキーマがバージョン間で変わる |
| ② LLVM IR + `dot-cfg` | 不要 | 基本ブロックと分岐（DOT形式） | ソース構造との対応が崩れる（下記） |
| ③ **LibTooling** | 必要（200行程度） | ソース行と厳密に対応した CFG | API がバージョン間で壊れる |
| ④ Joern | 不要 | そこそこの CFG + データフロー | Clang より精度は劣る |

**② の詳細**:
```bash
clang -S -emit-llvm -O0 -g foo.c -o foo.ll
opt -disable-output -passes=dot-cfg foo.ll        # 新パスマネージャ
# または
opt -dot-cfg -disable-output -enable-new-pm=0 foo.ll   # 旧パスマネージャ
```
出力された `.dot` は Python の `pydot` / `networkx` でパース可能。`-cfg-func-name=<部分文字列>` で対象関数を絞れる。LLVM のバージョンによってどちらの書式が通るか変わるので手元で要確認。

**② の重大な注意**: LLVM IR は低レベルに変換された後の姿。`-O0` でも `for` はループ用ブロックに分解され、変数名は `%1`, `%2` になる（`-g` で部分的に復元可）。C++ のテンプレートやインライン展開が絡むとソース行との対応がさらに怪しくなる。

**③ の負担軽減**: LibTooling には **ASTMatchers** という宣言的マッチャDSLがあり、訪問者パターンの手書きが不要。さらに **`clang-query`** で**コンパイルせずにマッチャを試せる**。C++ を書く時間の大半をここで潰せる。

```
$ clang-query foo.cpp --
clang-query> match callExpr(callee(functionDecl().bind("callee")))
```

---

## 7. バグ検出への拡張（将来構想）

### 7.1 静的解析の5段階

| 段階 | 必要なもの | 検出例 | 自作難易度 |
|---|---|---|---|
| **L1** 構文パターン検査 | AST | 命名規則違反、goto使用、ネスト深度 | 易 |
| **L2** 関数内フロー解析 | CFG + データフロー | 未初期化変数、到達不能コード、無駄な代入 | 中 |
| **L3** 手続き間解析 | コールグラフ + 関数サマリ | 引数経由の null 伝播、テイント追跡 | 難 |
| **L4** パス感度・記号実行 | 経路条件 + SMTソルバ | 相関する条件が絡むバグ | 非常に難 |
| **L5** 抽象解釈による証明 | 抽象領域 + 健全性 | バグが存在しないことの証明 | 研究レベル |

MISRA / AUTOSAR ルールの大半は L1。SonarQube の指摘の多くは L1〜L2。Coverity が売り物にしているのが L4。Astrée / Polyspace が L5。

**認識**: いま作ろうとしているデータセット自体が、すでに静的解析の一種（L1 の基盤）。

### 7.2 自作で現実的に届く範囲

**L1〜L2 は自作が十分に現実的。** L2 の実装は恐れられているほど大変ではない。古典的なデータフロー解析は「**単調フレームワーク（monotone framework）**」という統一された型に収まる。

1. 格子（lattice）を定義する — 「未初期化 / 初期化済み / 不明」など
2. 転送関数を定義する — 各文が状態をどう変えるか
3. CFG 上で不動点まで反復する — 変化がなくなるまで回す

到達定義解析、活性変数解析、利用可能式解析は全部この枠に嵌る。骨格は Python 200行程度。

- 参考書: Dragon Book（コンパイラ第2版）第9章、Nielson et al. *Principles of Program Analysis*

**L3 も原理的には可能**だが、再帰と関数ポインタで泥沼になる。

**L4 が壁になる理由**:
1. **経路爆発** — 分岐 n 個で経路は最大 2ⁿ。ループがあれば無限。L4 ツールは必ずどこかで打ち切っており、**「どこで打ち切るか」の設計が製品の本体**。実コードで殴られた経験値の産物であって、アルゴリズムの知識ではない
2. **決定不能性** — ライスの定理により、プログラムの非自明な意味的性質は一般に決定不能。すべての静的解析ツールは「健全だが偽陽性が出る」か「不完全だが静か」のどちらかを選ばざるを得ない。**両方を満たすツールは原理的に存在しない**
3. **偽陽性チューニングが仕事の9割** — 誤検知率30%のツールは誰も使わない。ここを削る作業に終わりはない

### 7.3 ★ コード理解を壊さないための境界設計

**これが今回いちばん重要な整理。**

#### 汚染のメカニズム

コード理解とバグ検出は、**精度要件が正反対**。

| | 重視するもの | 「疑わしい」ときの振る舞い |
|---|---|---|
| **コード理解** | 再現率（取りこぼさない） | **記録する**（人間が見て判断できる） |
| **バグ検出** | 適合率（誤検知を出さない） | **黙る**（誤検知は信頼を失う） |

同じコードベースで両方を最適化しようとすると、**閾値の取り合いになる**。

**最悪の失敗モード**:
> 「誤検知が多いから」という理由で、**抽出器側**で怪しいエッジを捨て始める
> → コード理解のデータが痩せる
> → 気づいたときには元に戻せない

これが「コード理解のソースコードまで壊してしまう」の具体的な姿。

#### 防ぐための層分離ルール

```
L0  抽出層 (extractors/)     事実のみを出す。判断しない。捨てない。
                             ↓ 追記のみ
L1  ファクト層 (facts/)      スキーマ固定。信頼度つき。不変。
                             ↓ 派生（再生成可能）
L2  派生層 (derived/)        CFG、到達可能性、推移閉包など
                    ┌────────┴────────┐
L3a 理解層 (views/)          L3b 検出層 (rules/)
    図、レポート、検索            ルール評価 → findings
```

**絶対に守る3つのルール**:

1. **L0 に判断ロジックを一切入れない**
   「このパターンは怪しい」という知識は必ず L3b に置く。抽出器は「見たものを記録する」だけ。

2. **フィルタリングは下流でのみ行う**
   バグ検出ルールが誤検知を減らしたければ、`WHERE status = 'resolved' AND confidence = 'high'` のように**クエリ側で絞る**。抽出器で絞らない。

3. **findings は別テーブル・別ライフサイクル**
   `findings.csv` は L1 のテーブルと混ぜない。ルールを消せば findings も消える、という関係を保つ。L1 は L3b の存在を知らない。

**テストの分け方も分離する**:
- 理解層 → ゴールデンデータセットとの比較（「この関数のコール先は正確に7つ」）
- 検出層 → 真陽性コーパス／偽陽性コーパス（「このコードは検出すべき」「このコードは検出すべきでない」）

この2つを同じテストスイートに混ぜると、片方を通すためにもう片方を壊す改変が起きる。

#### 別リポジトリにすべきか

**不要。同一リポジトリでモジュール分離すれば十分。** ただし **ルールはプラグイン形式**（1ルール1ファイル、動的ロード）にしておくと、ルールの追加削除が L1 に触れずに済む。

### 7.4 今のうちにやっておくべき5つのこと

バグ検出の可能性を潰さないために、**初版のスキーマに入れておくべきもの**。あとから追加するとデータの作り直しになる。

1. **位置情報は範囲で持つ** — `(file, line, col, end_line, end_col)`
   行番号だけでは、ルールの指摘箇所をエディタでハイライトできない。SARIF も範囲を要求する。

2. **`status` / `reason` / `confidence` 列を最初から入れる**（§3.1.1、§3.1.2）
   バグ検出ルールが「解決済みのエッジだけを使う」というフィルタを掛けられるようにする。

3. **`snapshot`（コミットハッシュ）列を入れる**
   差分検出、「新規に入ったバグ」の識別に必須。これがないと「前回からの増分」が出せない。

4. **抽出器の識別子とバージョンを記録**
   結果の再現性。「この行は古い抽出器が出したものだ」が分かる。

5. **findings の出力形式を SARIF に想定しておく**
   既製ツール（Clang Static Analyzer、cppcheck）と同じ土俵に乗る。CI 統合、VS Code 表示、GitHub 連携が全部タダで付いてくる。

### 7.5 現実的なゴール設定

**3層に分けておけば、「静的解析ツールを作る」という際限のないスコープに飲み込まれずに済む。**

| 層 | 内容 | 自作するか |
|---|---|---|
| ① **コード理解のためのデータセット** | 本命。AST 層で完結 | **自作**（今すぐ着手可能） |
| ② **プロジェクト固有ルールのチェック** | L1〜L2。CFG 取得後に少し足すだけ | **自作**（ここに最大の価値） |
| ③ **一般的なバグ検出** | 既製エンジンの結果を取り込むだけ | **自作しない** |

**②に価値がある理由**: 以下のようなルールは、どんな商用ツールにも入っていない。
- 「この社内APIは必ずペアで呼ばれること」
- 「この構造体のこのメンバは初期化関数を経由せずに触ってはいけない」
- 「モジュールAからモジュールBを直接呼んではいけない」

**③を自作しない理由**: Coverity や PVS-Studio は何十年もチューニングを積んでいる。正面から競うのは筋が悪い。

```bash
# ③の取り込み例
clang --analyze -Xanalyzer -analyzer-output=sarif foo.c
# または scan-build でビルド全体に対して一括実行
```

```
symbols.csv    ← 自作（libclang）
calls.csv      ← 自作（libclang）
var_refs.csv   ← 自作（libclang）
cfg_*.csv      ← 自作（LibTooling / LLVM IR）
findings.csv   ← 既製エンジンの SARIF を取り込み  ★
```

自作の強みと既製品の強みが、同じテーブル空間で合流する。

### 7.6 L0 の出力形式とインクリメンタル取り込み

**課題**: L1(SQLite等)を単一のテーブルにすると、「1ファイル変更するたびに全体を作り直す必要があるのでは」という懸念が出る。

**結論**: L0(抽出器の出力)はソースファイル単位の小さな中間ファイルにしてよい。L1への取り込みを `file` 列でのdelete+insertにすれば、変更されたファイルの分だけ再生成・再取り込みすれば済み、フルリビルドは不要。

#### 形式の比較

「中間ファイルなので複雑な作り込みをせず、人間が見てその場で直せる素直さ」を優先基準にすると、候補は以下の通り。

| 形式 | 手編集のしやすさ | コメント | ネスト構造 | L1(CSV系)との親和性 | 備考 |
|---|---|---|---|---|---|
| **TSV**(推奨) | ◎ 1行1レコード。壊れにくい | △ 先頭を`#`始まりの行に決め打ちすれば可 | × | ◎ 列がそのまま対応 | 値にコンマが混ざっても引用符が要らない |
| CSV | ○ | △ 同上 | × | ◎ | `qualified_name`にコンマを含む言語(C++テンプレート引数 `std::pair<int, int>` 等)では毎回引用符が要り、手編集が地味に面倒 |
| JSON | △ 括弧・カンマの対応が崩れやすい | × 標準では不可 | ○ | △ 変換ロジックが要る | 型を持てるのは利点だが、今回はどのテーブルもフラットなので過剰装備 |
| JSON Lines(NDJSON) | ○ 1行1レコード | × | ○ | △ | 将来CFGエッジ等の可変長・入れ子データが増えたときの避難先として温存 |
| YAML | △ インデント崩れに弱く、手編集事故が起きやすい | ◎ | ○ | △ | 人間可読ではあるが「うっかり壊す」リスクが今回の用途には合わない |
| TOML | ○ `[[table]]`で配列表現可 | ◎ | ○ | △ | 設定ファイル文化のフォーマットで、大量行の列挙にはやや冗長 |

現状の3テーブル(`symbols` / `calls` / `var_refs`)はすべてフラットな構造なので、ネスト表現力は不要。**TSVを標準とし、将来ネストが必要なテーブルが増えたときだけJSON Linesを個別採用する**方針とする。

#### ファイル配置

ソースツリーをミラーし、テーブル種別ごとに拡張子で分ける(1ソースファイルにつき複数の小さなTSV)。

```
facts/raw/
  src/foo/bar.c.symbols.tsv
  src/foo/bar.c.calls.tsv
  src/foo/bar.c.var_refs.tsv
```

#### ファイル内フォーマット

1行目は`#`で始まるメタ情報行。そのファイル内の全レコードで共通する値(`snapshot` / `extractor` / `lang`)はここに1回だけ書き、各データ行では繰り返さない。`file`列も持たない(ファイル名自体が経路を表すため冗長)。2行目はヘッダ(列名)、3行目以降がデータ。

`bar.c.symbols.tsv`:

```
# snapshot=8f3ac21 extractor=libclang-18.1.0 lang=c
id	kind	name	qualified_name	line	col	end_line	end_col	is_definition	storage_class	linkage	confidence
c:@F@process#I#	function	process	process	10	1	25	1	true	external	external	high
```

`bar.c.calls.tsv`（`status` が `resolved` の行では `reason` を空にする）:

```
# snapshot=8f3ac21 extractor=libclang-18.1.0 lang=c
caller_id	callee_id	callee_expr	status	reason	confidence	call_kind	line	col
c:@F@process#I#	c:@F@helper#	helper	resolved		high	direct	14	5
c:@F@process#I#		hooks->on_event	unresolved	via_function_pointer	high	direct	19	5
```

手で直すときはテキストエディタでタブ区切りの1行を編集するだけでよい。整形して見たい場合は `column -t -s $'\t' bar.c.symbols.tsv` 等で確認できる。

**空値の扱い**: 該当しない列は空文字（タブが連続する）で表す。`status = resolved` の行の `reason` がこれにあたる。「空」と `not_applicable` は別物であることに注意（前者は列が不要、後者は「その言語に概念が無い」という積極的な記録）。

#### L0 → L1 取り込み(増分ロード)

```
for each changed source file X:
    facts/raw/.../X.*.tsv を読む
    1行目のメタ情報行から snapshot / extractor / lang を取り出す
    2行目のヘッダから列名を取り出す
    each table T in {symbols, calls, var_refs}:
        DELETE FROM T WHERE file = X            -- 旧世代の行を消す
        INSERT INTO T (file, snapshot, extractor, <TSVの列...>)
               VALUES (X, snapshot, extractor, ...)   -- 新世代の行を入れる
```

コストは変更されたファイル数に比例する。ファイル横断のクロス集計(§3.3の未解決率モニタリング等)は、取り込み後のL1(SQLite)に対してのみ行う。

**注意点(§3.3との関係)**: `foo.c`のシンボルを変更しても、`bar.c`から`foo.c`を呼んでいる`calls`行の`status` / `reason`は`bar.c`自体を再抽出しない限り古いままになりうる。これは保存形式(TSVかJSONか)を変えても消えない、依存関係追跡の問題であり、L0の出力形式とは別に、後日「変更されたシンボルを参照しているファイル一覧」を求める仕組み(依存グラフ)を検討する必要がある。現時点では対象外とする(§1「非スコープ」のインクリメンタル解析の一部)。

### 7.7 多言語混在リポジトリでの挙動（想定）

> **本節は設計上の想定であり、実測はしていない。実装時に実動作を確認すること。**

複数言語のツール群を1つのリポジトリとしてまとめて投入した場合の想定挙動を整理する。

#### 抽出器の起動単位はファイルではなくビルドコンテキスト

拡張子だけでは抽出器を起動できない。各言語の入口は以下の通り（§4）。

| 言語 | 抽出器の起動に必要なもの |
|---|---|
| C/C++ | `compile_commands.json`（§4.3で必須の前提と明記） |
| C# | `.sln` / `.csproj`（`MSBuildWorkspace.OpenSolutionAsync()`） |
| TS/JS | `tsconfig.json`（`new Project({ tsConfigFilePath })`） |
| Python | 不要（1ファイル＝1AST）。名前解決を効かせる場合は依存パッケージが入った実行環境 |

したがって実際の流れは「拡張子でファイルを仕分ける」ではなく、**リポジトリを走査して各言語のプロジェクト定義ファイルを見つけ、見つかった言語の抽出器をそれぞれ起動する**。拡張子は `lang` 列（§3.1）の判定と、プロジェクト定義に含まれないファイルの検出に使う。

#### 言語ごとに独立して完走する

抽出器は言語ごとに別プロセス・別ランタイム（libclang は Python、Roslyn は .NET、ts-morph は Node）で、互いの存在を知らない。

- **成功も失敗も言語単位で閉じる**。`tsconfig.json` が無く TS 抽出器が失敗しても、C/C++ と C# の抽出は完走し中間ファイルも出る。「全部揃わないと何も出ない」にはならない
- 中間ファイルは §7.6 の通りソースツリーをミラーするため、`facts/raw/src/core/foo.c.symbols.tsv` と `facts/raw/src/ui/App.tsx.symbols.tsv` が自然に並ぶ。ファイル名が衝突しないので混在の特別扱いが不要
- L1 に取り込むと `lang` 列で区別された単一の `symbols` テーブルになる。シンボルIDは SCIP 形式で統一する方針（§3.2）のため名前空間も衝突しない

**中間ファイルの生成までは、言語が混在していても問題なくできる想定。**

#### 言語をまたぐ呼び出しは「切れた線」として記録される

言語境界を越えた呼び出し関係の解決は行わない（FFI マッチング等の追加機構は現時点で非スコープ）。エラーにも異常終了にもならず、**到達可能性が途切れた箇所がデータとして残る**。

例：C# から `[DllImport]` で C の関数を呼ぶ場合

- Roslyn から見て `[DllImport]` メソッドは単なる extern 宣言のシンボル。C# 側の呼び出し行は `calls` に記録され、`callee_id` はその extern 宣言を指す
- その extern 宣言は `symbols` に存在するが、定義を持たない（`is_definition = false`）行き止まりになる
- C 側の実体は libclang が別途 `symbols` に入れるが、両者を結ぶ `calls` 行は生成されない

これは §3.3「解決できなかったことを記録する」の思想通りの挙動で、`ANALYSIS_VIEWPOINTS.md` の B-04（到達可能性）／B-13（静的に解決できなかった呼び出し）を実行すると、この境界が答えの出せない箇所として素直に列挙される。誤った線を勝手に引かないため §2.3 の原則にも沿う。

#### 抽出器を持たない言語

Ruby / Go / シェルスクリプト等、抽出器を用意していない言語のファイルは**何も出力されずスキップされる**。必要になれば §4.7 の tree-sitter を暫定対応として当て、関数一覧程度の薄い中間ファイルを出す。

#### 実装時に確認すること

- [ ] 各抽出器がプロジェクト定義ファイルを見つけられなかった場合に、他言語の抽出を巻き込まずに失敗するか
- [ ] 同一リポジトリ内で複数言語の中間ファイルがファイル名衝突なく生成されるか
- [ ] SCIP 形式のシンボルIDが言語をまたいで衝突しないか
- [ ] 言語境界の呼び出しが、エラーではなく「定義を持たないシンボルで途切れた状態」として記録されるか


## 8. テスト対象プロジェクトの選定

**ステータス: 確定**（2026-08）。実装着手時はこのセットで始める。変更する場合は §8.1 の基準に照らして判断すること。

### 8.1 選定基準

抽出器の検証には「適度な規模」だけでなく「**解決できない呼び出しが一定量含まれること**」が要る。§3.3 の `status` / `reason` 列の分布を見るのが検証の本体であり、すべてが `resolved` になるコードでは何も測れないため。

1. **規模** — 5千〜2万行。数千行では未解決ケースが数個しか出ず統計にならない。10万行超は1回の試行が重くなり反復が止まる
2. **`compile_commands.json` が出せるか**（C/C++）— §4.3 の必須前提。CMake 採用プロジェクトが圧倒的に楽
3. **未解決を生む構造を含むか** — 関数ポインタ、関数形式マクロ、仮想関数、`#ifdef`
4. **ライセンスが明確** — 解析結果をリポジトリに置く可能性があるため
5. **ビルドが単純** — 依存パッケージの解決に時間を取られない

### 8.2 実測データ（2026-08 時点、shallow clone で計測）

テスト・サンプルを除いたソース行数。「間接呼び出し」は `x->f(` / `x.f(` 形式の出現数（メンバアクセスも拾う粗い値）。

| プロジェクト | 言語 | 行数 | ファイル数 | ビルド | 関数形式マクロ | 仮想関数 | `#if` | 間接呼び出し |
|---|---|---:|---:|---|---:|---:|---:|---:|
| **cJSON** | C | 5,388 | 7 | CMake ○ | 17 | 0 | 42 | 26 |
| **tinyxml2** | C++ | 5,521 | 3 | CMake ○ | 5 | 88 | 24 | 0 |
| chibicc | C | 9,154 | 17 | Makefile（要 bear） | 37 | 0 | 8 | - |
| wren | C | 12,544 | 25 | Makefile（要 bear） | 68 | 2 | 51 | 4 |
| **cmark** | C | 17,930 | 34 | CMake ○ | 62 | 1 | 54 | 61 |
| **requests** | Python | 6,874 | 22 | - | - | - | - | - |
| click | Python | 13,030 | 31 | - | - | - | - | - |
| **commander.js** | JS | 6,503 | 43 | - | - | - | - | - |
| zod | TS | 45,093 | 251 | - | - | - | - | - |
| **FluentValidation** | C# | 13,028 | 140 | .sln ○ | - | - | - | - |
| serilog | C# | 14,087 | 113 | .sln ○ | - | - | - | - |
| Newtonsoft.Json | C# | 68,994 | 239 | .sln ○ | - | - | - | - |

`cmake -S <dir> -B <build> -DCMAKE_EXPORT_COMPILE_COMMANDS=ON` を無設定で実行し、cJSON（23エントリ）/ cmark（23エントリ）/ tinyxml2（2エントリ）とも `compile_commands.json` の生成に成功することを確認済み。

### 8.3 推奨セット

**3段階に分ける。**「毎回回すもの」と「たまに回すもの」を分けないと、テストに時間を食われて反復が止まる。

| 段 | 用途 | プロジェクト | 理由 |
|---|---|---|---|
| **T0 スモーク** | 毎回。数秒で終わること | **cJSON**（C, 5.4k） | CMake が無設定で通る。関数ポインタ（`malloc_fn` / `free_fn`）が `CJSON_CDECL` マクロ経由で宣言されており、**マクロと関数ポインタが絡む最小ケース**として理想的 |
| **T1 本命** | 機能追加のたび | **cmark**（C, 17.9k） | 規模・構造とも中庸。関数形式マクロ 62、`#if` 54、間接呼び出し 61 と、`reason` の各値が一通り出る見込み。CMake ○、C言語のみで依存が薄い |
| | | **tinyxml2**（C++, 5.5k） | 仮想関数 88 個に対し間接呼び出し 0。**仮想ディスパッチの解決だけを切り出して検証できる**。cmark と役割が重複しない |
| **T2 ストレス** | Phase 完了時など随時 | SQLite / Lua / Redis 等 | 性能と「静かな取りこぼし」（§2.3）の確認用。日常のテストには使わない |

**多言語展開（Phase 3）用**:

| 言語 | プロジェクト | 選定理由 |
|---|---|---|
| Python | **requests**（6.9k） | 型注釈が薄い実コード。`status` / `confidence` が Python でどこまで機能するかの現実的な試金石 |
| JS | **commander.js**（6.5k） | 素の JS。§4.5 の「型注釈のない JS で精度が落ちる」を実測できる |
| C# | **FluentValidation**（13.0k） | `.sln` があり `MSBuildWorkspace` でそのまま開ける。ジェネリクスとラムダを多用しており `IOperation` の検証に向く |

**§7.7（多言語混在）の検証**は、上記を1つのディレクトリに並べた合成リポジトリで行う。実際の混在プロジェクトを探すより、各言語の挙動が既知である方が差分を切り分けやすい。

### 8.4 取得元とライセンス

すべて shallow clone で取得できる。ライセンスは clone した LICENSE / COPYING の本文を確認済み（2026-08）。

| プロジェクト | 取得元 | ライセンス |
|---|---|---|
| cJSON | `https://github.com/DaveGamble/cJSON` | MIT |
| tinyxml2 | `https://github.com/leethomason/tinyxml2` | zlib License |
| cmark | `https://github.com/commonmark/cmark` | BSD-2-Clause（同梱コンポーネントに ISC / MIT、仕様・テストデータに CC-BY-SA 4.0 を含む） |
| requests | `https://github.com/psf/requests` | Apache-2.0 |
| commander.js | `https://github.com/tj/commander.js` | MIT |
| FluentValidation | `https://github.com/FluentValidation/FluentValidation` | Apache-2.0 |
| （参考）chibicc | `https://github.com/rui314/chibicc` | MIT |
| （参考）wren | `https://github.com/wren-lang/wren` | MIT |

いずれも商用利用・改変が可能な許容的ライセンス。**ただし解析対象のソースそのものを自リポジトリに取り込むことはしない**（サブモジュールか、テスト時に clone するスクリプトで対応する）。取り込むと各プロジェクトのライセンス告知義務が自リポジトリに及ぶため。

cmark のテストデータが CC-BY-SA 4.0 である点は、**解析結果（ファクトデータ）を公開する場合に確認が要る**。ソースコードの解析には影響しない。

### 8.5 注意点

- 行数・構造の計測値は clone 時点のもの。**選定の目安であり、厳密な再現性は期待しない**
- chibicc / wren は Makefile ビルドのため `compile_commands.json` の生成に `bear` が要る。T1 に入れなかったのはこの一手間のみが理由で、コード自体（特に chibicc は C コンパイラの実装で構造が濃い）は良い題材
- **ゴールデンデータセット**（§7.3「理解層のテスト」）は T0 の cJSON に対してのみ人手で作る。T1 以上で正解を人手管理するのは破綻する


## 9. 実装構成と実行環境

**ステータス: 確定**（2026-08-25）

### 9.1 抽出器は「API 呼び出し」ではなく「別プロセス」

Roslyn は .NET ランタイム内、ts-morph は Node ランタイム内でしか動作しない。**Python から関数として呼び出すことは原理的にできない**ため、各抽出器は独立プロセスとして起動する。

```
python -m core.cli analyze --project ./target
   │
   ├─ subprocess: python  extractors/cpp/main.py      ...
   ├─ subprocess: dotnet  extractors/csharp/*.dll     ...
   ├─ subprocess: node    extractors/ts/index.js      ...
   ├─ subprocess: python  extractors/python/main.py   ...
   │
   └─ 各プロセスが facts/raw/**/*.tsv を書く（§7.6）
        ↓
      loader が TSV → facts/db.sqlite に増分ロード（§3.4.1）
```

**抽出器どうしの唯一の接点は TSV ファイル**である。これは弱点ではなく、§7.7 の「言語ごとに独立して成功・失敗する」を成立させている根拠でもある。

**インターフェース規約**:

| 項目 | 規約 |
|---|---|
| 起動 | `<extractor> --project <dir> --out facts/raw --snapshot <値>` |
| 出力 | §7.6 の TSV。標準出力には進捗のみ |
| 終了コード | `0` 成功 / `1` 対象ファイルなし（正常） / `2` ビルドコンテキスト不足 / `3` 異常 |

**`1`（対象なし）を正常系として分けることが重要**。オーケストレータは `2` と `3` のみをログに残し、他言語の抽出は続行する。これが §7.7 の挙動そのものになる。

### 9.2 GUI を後付けするための3つの約束

将来 GUI（フォルダ指定などの設定画面＋実行ボタン）が欲しくなることは想定される。**GUI 自体は初版で作らない**が、後付けを安くする3点は初版から守る。いずれもコストはほぼゼロで、逆に守らないと GUI 化時に書き直しになる。

**① ロジックは `core/` に置き、CLI は薄いラッパーにする**

```
core/
  orchestrator.py    run_analysis(config) -> Result   ← 実処理はすべてここ
cli/main.py          argparse で config を組み立てて core を呼ぶだけ（数十行）
gui/                 将来。同じ core.run_analysis(config) を呼ぶだけ
```

CLI の中に処理を書くと GUI 化のときに全部書き直しになる。この分離さえ守れば、GUI は「設定を組み立てて `run_analysis()` を呼ぶ画面」で済む。

**② 設定をジョブ設定ファイルで表現できるようにする**

```toml
# analysis.toml
target    = "/path/to/project"
out       = "facts/"
languages = ["c", "cpp", "cs"]
```

CLI は個別引数でもこのファイルでも受け付ける。こうすると **GUI は実質「この TOML を編集するフォーム＋実行ボタン」**になり、設計が自明になる。

**③ 進捗を構造化して出力する**

```
{"event":"start","lang":"c","files":34}
{"event":"progress","lang":"c","done":12,"total":34}
{"event":"done","lang":"c","status":"ok"}
```

CLI では人間向けに整形して表示し、GUI ではこれをパースしてプログレスバーにする。**後付けが最もつらいのがこれ**で、処理の奥深くに進捗通知を差し込む改修になる。最初から通知の口だけ空けておく。

**GUI の実装形式（将来）**: ローカル Web UI を想定する。§7.3 の L3a（可視化層）がどのみち HTML になるため、**設定画面と可視化画面が同じ土俵に乗り**、「実行してその場で結果のグラフを見る」が自然につながる。→ C-2（可視化層の実現手段）と合わせて決める。

### 9.3 必要なインストール

**ステータス: 確定**（2026-08-25、実測に基づく訂正版）

Phase ごとに段階的に増える。**入れていないランタイムがあっても、他言語の解析は完走する**（§7.7）。

#### 前提の明示

C/C++ の抽出には、役割の異なる3種類のツールが必要になる。**これらは互いに代替できない**。

| 役割 | ツール | いつ動くか |
|---|---|---|
| ビルド情報の生成 | **cmake**（+ Cコンパイラ） | 解析の**前**。`compile_commands.json` を作る（§4.3） |
| ヘッダの供給 | **clang** / **libc 開発ヘッダ** | パース時に `#include` を解決するため |
| パース本体 | **libclang**（pip） | 解析本体 |

#### Phase 0〜1（C/C++）

| 対象 | 要否 | 備考 |
|---|---|---|
| **Python** | 必須 | 下限は §9.3.1 参照 |
| **`pip install libclang`** | 必須 | 依存パッケージゼロ、`Requires-Python` 指定なし（実測）。ネイティブ `libclang.so` を同梱（v18.1.1、約62MB） |
| **clang** | **必須** | **Clang 組み込みヘッダ（`stddef.h` 等）の供給元**。§9.3.2 参照 |
| **gcc + libc 開発ヘッダ** | 必須 | `stdio.h` 等のシステムヘッダの供給元。cmake の configure にも必要 |
| **cmake** | 必須 | 解析対象の `compile_commands.json` 生成用（§8） |
| **Git** | 必須 | `snapshot` 列（§3.4.2） |
| ~~SQLite~~ | **不要** | **Python 本体に同梱**（実測）。`sqlite3` コマンドは中身を手で覗きたいときだけの任意ツール |
| bear | 不要 | Makefile プロジェクト用。T1 に chibicc / wren を選んでいないため（§8.5） |

##### 9.3.1 Python のバージョン下限

実測した要件は以下の通り。

| パッケージ | `Requires-Python` |
|---|---|
| libclang 18.1.1 | **指定なし**（依存パッケージもゼロ） |
| jedi 0.20.0 | **>= 3.10** |

- **Phase 1 のみ**なら libclang 側に制約が無い。実質的な下限は `ast` の `end_lineno`（終了位置。`EXTRACTABLE_DATA_MATRIX.md` §2.7）が入った **3.8**
- **Phase 3 まで見込む**なら jedi の要求で **3.10 以上**

**決定: 3.10 以上に統一する。** 後から上げ直すより最初から揃える方が安い。

##### 9.3.2 clang が必須である理由（実測）

`pip install libclang` が同梱するのは **`libclang.so` のみ**で、**Clang の組み込みヘッダは含まれない**。パッケージ内を検索しても `stddef.h` は存在しなかった。

このため `#include` を含む実在の C コードはそのままではパースできない。

```
#include <stdio.h> を含むファイルを pip 版 libclang でパース
→ 致命的エラー: 'stddef.h' file not found
```

**回避策**（実測で解決を確認）: システム clang のリソースディレクトリを渡す。

```python
res = subprocess.check_output(['clang', '-print-resource-dir'], text=True).strip()
tu = index.parse(path, args=['-I' + res + '/include'])
# → 致命的エラー 0 件。printf が USR c:@F@printf として解決される
```

したがって **clang のインストールは必須**であり、抽出器はこの `-print-resource-dir` の引き渡しを標準で行う必要がある。

> **注意**: この処理を忘れると、エラーにはならず**解析結果が静かに痩せる**（一部の型やマクロが解決されない）。§2.3 の「静かな取りこぼし」そのものなので、抽出器は起動時に `stddef.h` が解決できるかを自己診断すべきである。

#### Phase 2（C#）

| 対象 | 要否 | 備考 |
|---|---|---|
| **.NET SDK 8.0+** | 必須 | Roslyn は .NET ランタイム内でしか動かない。**ランタイムのみ（`dotnet-runtime`）では不可**。`restore` / `build` に SDK が要る |
| NuGet パッケージ | **自動** | `Microsoft.CodeAnalysis.CSharp.Workspaces` / `Microsoft.Build.Locator`。`dotnet restore` が nuget.org から自動取得するため手動インストールは不要 |

**条件**: NuGet の自動取得には**ネットワーク接続が必要**。オフライン環境では事前にキャッシュを用意するかローカルフィードを立てる。

**要実測（Phase 2）**: `MSBuildWorkspace.OpenSolutionAsync()`（§4.4）で解析対象の `.sln` を開く際、**解析対象側の依存復元**も必要になる場合がある。参照が解決できないと Roslyn のシンボル解決が不完全になり `confidence` が下がる。

#### Phase 3（Python、TypeScript / JavaScript）

**Python 解析**

| 対象 | 要否 | 備考 |
|---|---|---|
| `ast` / `symtable` | 標準 | **追加インストール不要**。構造の抽出（`symbols`）はこれだけで完結する（実測: 関数定義・呼び出し位置・スコープを取得できた） |
| **`pip install jedi`** | 必須 | 名前解決用。これが無いと `calls` の `callee_id` が埋まらない（実測: `full_name` と参照検索の取得を確認） |
| Node.js | **不要** | jedi は純 Python。**scip-python を選んだ場合のみ** Node が要る（pyright ベースのため） |

jedi の依存は `parso` の1つのみ（実測）。

**TypeScript / JavaScript 解析**

| 対象 | 要否 | 備考 |
|---|---|---|
| **Node.js 18+** | 必須 | ts-morph は Node ランタイム内でしか動かない |
| npm パッケージ | 自動 | `ts-morph`。`npm install` で取得 |

#### Phase 4（深掘り・必要になったら）

| 対象 | 用途 |
|---|---|
| LLVM ツールチェイン（`opt` / `llvm-as`） | LLVM IR 経由の CFG 取得（§6） |
| LLVM 開発ヘッダ + C++ コンパイラ | LibTooling で `clang-cfg-extract` を書く場合（§6）。**ここだけは本格的な LLVM 開発環境が要る** |

#### Phase 5（バグ検出）

| 対象 | 用途 |
|---|---|
| Clang Static Analyzer | clang に同梱。SARIF 出力（§7.5） |
| cppcheck（任意） | 別エンジンの結果も取り込む場合 |

#### まとめ

フル構成では **Python / .NET / Node の3ランタイム**が必要になる。§4 のツール選定（各言語のコンパイラ本体を使う）から必然的に導かれる帰結であり、回避手段は無い。ただし段階的に導入でき、未導入のランタイムがあっても他言語の解析は止まらない。

環境の確認には `tools/check-env.sh`（Linux / WSL）および `tools/check-env.ps1`（Windows）を用いる。


---

## 10. ロードマップ

### Phase 0: 検証（数日）
- [ ] 対象コードで `compile_commands.json` が出せるか確認
- [ ] libclang（Python）で 1 ファイルの AST を歩き、USR が取れることを確認
- [ ] clangd の Call Hierarchy を触ってベースラインを把握
- [ ] （任意）Understand の無料トライアルで「理想の画面」を確定させる

### Phase 1: 最小データセット（C/C++）
- [ ] `symbols.csv` / `calls.csv` / `var_refs.csv` を libclang で生成
- [ ] SQLite に投入
- [ ] `status` / `reason` / `confidence` 列の分布を確認 → 解決率をモニタリング
- [ ] Mermaid または自作 HTML でコールグラフを出力
- [ ] （§7.6）L0出力をファイル単位のTSVに分割し、`file`列でのdelete+insertによる増分取り込みを試す

### Phase 2: スキーマ検証（C#）
- [ ] Roslyn で同じスキーマに落とせるか確認
- [ ] `AnalyzeDataFlow` の結果を追加列として入れてもスキーマが壊れないか検証
  - → **ここで将来のデータフロー拡張に耐えるか分かる**

### Phase 3: 多言語展開
- [ ] TypeScript（ts-morph）— 型注釈の薄い言語で ID と `status` / `confidence` が機能するか
- [ ] Python（ast + Jedi / scip-python）— 最難関。ここが通ればスキーマは十分に汎用
- [ ] （§7.7）多言語混在リポジトリに投入し、想定挙動と実動作の差を確認する

### Phase 4: 深掘り（必要になったら）
- [ ] `clang -ast-dump=json` で AST 情報を拡充
- [ ] LLVM IR + `dot-cfg` で CFG を試す（C++ 不要）
- [ ] 足りなければ LibTooling で `clang-cfg-extract` を書く

### Phase 5: バグ検出（未確定）
- [ ] Clang Static Analyzer の SARIF を `findings.csv` に取り込む（③）
- [ ] プロジェクト固有ルールを 1〜2個 書いてみる（②）
- [ ] §7.3 の層分離ルールを守れているか自己点検

---

## 11. 用語集

| 用語 | 意味 |
|---|---|
| **AST** | Abstract Syntax Tree。コードの構造を表す木。`{}` や `;` など意味に寄与しない記号を捨てている |
| **CST / Parse Tree** | 具象構文木。記号も全部残したもの。tree-sitter はこちら寄り |
| **CFG** | Control Flow Graph。実行がどの順に進みうるかを表す有向グラフ。ノードは基本ブロック |
| **基本ブロック** | 分岐なしに一直線に実行される命令の並び。CFG のノード単位 |
| **PDG** | Program Dependence Graph。制御依存とデータ依存を表すグラフ |
| **CPG** | Code Property Graph。AST + CFG + PDG を単一グラフに統合したもの。Joern の中核 |
| **USR** | Unified Symbol Resolution。Clang が付ける、翻訳単位をまたいで一意なシンボルID |
| **SCIP** | Sourcegraph の code intelligence protocol。LSIF の後継。人間が読めるシンボル文字列を使う |
| **LSP** | Language Server Protocol。エディタと言語サーバの通信規約 |
| **SARIF** | Static Analysis Results Interchange Format。静的解析結果の標準交換形式（OASIS標準） |
| **テイント解析** | 外部入力（汚染源）が危険な箇所（シンク）に届くかを追う手法 |
| **単調フレームワーク** | 古典的データフロー解析の統一枠組み。格子 + 転送関数 + 不動点反復 |
| **健全（sound）** | 見逃しがないこと。代償として偽陽性が増える |
| **ライスの定理** | プログラムの非自明な意味的性質は一般に決定不能、という定理 |

---

## 付録: 参照リンク

**パーサ / フロントエンド**
- libclang Python bindings: https://libclang.readthedocs.io/
- Clang LibTooling: https://clang.llvm.org/docs/LibTooling.html
- clang-query / ASTMatchers: https://clang.llvm.org/docs/LibASTMatchersReference.html
- Roslyn: https://github.com/dotnet/roslyn
- ts-morph: https://ts-morph.com/
- tree-sitter: https://tree-sitter.github.io/tree-sitter/
- Jedi: https://jedi.readthedocs.io/
- scip-python: https://github.com/sourcegraph/scip-python

**解析プラットフォーム**
- Joern: https://joern.io/ / https://docs.joern.io/
- Clang Static Analyzer: https://clang-analyzer.llvm.org/
- CodeCompass: https://github.com/Ericsson/CodeCompass

**規格**
- SCIP: https://github.com/sourcegraph/scip
- SARIF: https://sarifweb.azurewebsites.net/

**ライセンス原文**
- LLVM: https://llvm.org/LICENSE.txt
- LLVM Exception (SPDX): https://spdx.org/licenses/LLVM-exception.html
- GitHub CodeQL Terms: https://github.com/github/codeql-cli-binaries/blob/main/LICENSE.md
- CodeCompass LICENSE: https://github.com/Ericsson/CodeCompass/blob/master/LICENSE.txt

**参考ツール（比較用）**
- SciTools Understand: https://scitools.com/features
- Sourcetrail フォーク（petermost）: https://github.com/petermost/Sourcetrail
- NumbatUI（Quarkslab）: https://github.com/quarkslab/NumbatUI
