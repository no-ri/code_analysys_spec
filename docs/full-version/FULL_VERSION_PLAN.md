# フル版 実装計画（凍結）

**切り出し日**: 2026-08-27
**出典**: `CODE_ANALYSIS_CONCEPT.md`（フル版の構想。2026-08-25 に凍結）
**位置づけ**: **フル版でのみ使う部分**をここへ移した。簡易版の検討では参照しない。

> ## この文書の読み方
>
> **節番号は出典のまま据え置いている。** `[構想] §9.3` のような既存の参照が、
> 番号を変えずにこの文書へ到達できるようにするため（参照の書き換えは、
> それ自体が不整合の原因になる）。
>
> | 節 | 内容 | なぜ簡易版で使わないか |
> |---|---|---|
> | §4.2 〜 §4.6 | 言語別ツールの詳細（libclang / Roslyn / ts-morph / `ast`+Jedi） | **E-2 で軸2 = ゼロを決めた時点で、名前解決を持つツールは全部使えない**（ビルドコンテキスト無しでは機能しない）。簡易版の主力は tree-sitter |
> | §5 | ライセンスと制約 | 上記ツール群のライセンス調査。tree-sitter の実測は `OPEN_DECISIONS.md` E-3 にある |
> | §6 | 深掘りの段階（AST → CFG → データフロー） | 段階5以降。**簡易版の天井は段階1**（E-1） |
> | §9.3 | 必要なインストール | **凍結の理由そのもの**（Python / .NET SDK / Node / clang / cmake）。簡易版は軸1 =「Python 3.10+ ＋ `pip install` 1コマンド」 |
> | §10 | ロードマップ | Phase 1 = C# の計画。簡易版の初期対象は **C と C#**（E-1） |
>
> **`CODE_ANALYSIS_CONCEPT.md` に残したもの**: §4.1（選定基準。**簡易版が放棄した基準そのもの**）、
> §4.7（tree-sitter の位置づけ。**E-2 が覆した記述**）、§9.1 / §9.2（B-3 の根拠と GUI の3つの約束。簡易版でも有効）。
>
> **凍結は「捨てる」ではない。** フル版は「厳密版」として有効であり、再開時はこの文書に戻る。

---

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


---

### 9.3 必要なインストール

**ステータス: 確定**（2026-08-25、実測に基づく訂正版）

Phase ごとに段階的に増える。**入れていないランタイムがあっても、他言語の解析は完走する**（§7.7）。

#### 前提の明示

C/C++（Phase 2）の抽出には、役割の異なる3種類のツールが必要になる。**これらは互いに代替できない**。C# （Phase 1）にはいずれも不要。

| 役割 | ツール | いつ動くか |
|---|---|---|
| ビルド情報の生成 | **cmake**（+ Cコンパイラ） | 解析の**前**。`compile_commands.json` を作る（§4.3） |
| ヘッダの供給 | **clang** / **libc 開発ヘッダ** | パース時に `#include` を解決するため |
| パース本体 | **libclang**（pip） | 解析本体 |

#### 9.3.1 Python のバージョン下限（全 Phase 共通）

実測した要件は以下の通り。

| パッケージ | `Requires-Python` |
|---|---|
| libclang 18.1.1 | **指定なし**（依存パッケージもゼロ） |
| jedi 0.20.0 | **>= 3.10** |

- **Phase 1 のみ**なら libclang 側に制約が無い。実質的な下限は `ast` の `end_lineno`（終了位置。`EXTRACTABLE_DATA_MATRIX.md` §2.7）が入った **3.8**
- **Phase 3 まで見込む**なら jedi の要求で **3.10 以上**

**決定: 3.10 以上に統一する。** 後から上げ直すより最初から揃える方が安い。

#### Phase 1（C#）— 最小構成

| 対象 | 要否 | 備考 |
|---|---|---|
| **.NET SDK 8.0+** | 必須 | Roslyn は .NET ランタイム内でしか動かない。**ランタイムのみでは不可**。§9.3.2 の「SDK の実在確認」を必ず行うこと |
| **Git** | 必須 | `snapshot` 列（§3.4.2） |
| **Python 3.10+** | 必須 | TSV → SQLite のローダー（§9.1）。Windows は python.org 版、Ubuntu は標準同梱 |
| NuGet パッケージ | **自動** | `Microsoft.CodeAnalysis.CSharp.Workspaces` / `Microsoft.Build.Locator`。`dotnet restore` が自動取得する。ただし §9.3.2 の確認が要る |
| ~~clang / gcc / cmake~~ | **不要** | C/C++ 固有の要件。C# には `compile_commands.json` の概念が無い |
| ~~libclang~~ | **不要** | 同上 |

**C# だけなら、これだけで Phase 1 を始められる。** C/C++ で必要だったビルド情報の生成（cmake）とヘッダの供給（clang / libc）が丸ごと不要になる。

##### 9.3.2 .NET SDK の実在確認と NuGet の取得可否

**先に確認すべき落とし穴: `dotnet` コマンドがあっても SDK があるとは限らない。**

`dotnet.exe` はランタイム単体のインストールや Visual Studio 同梱の共有ホストでも配置される。コマンドの存在確認だけでは不十分で、次のように SDK の実体を見る。

```
dotnet --list-sdks
```

1行も出なければ SDK は入っていない（`dotnet nuget` 等の SDK コマンドは `No .NET SDKs were found` で失敗する）。

**紛らわしい別物**:

| 名称 | 実体 | この用途で使えるか |
|---|---|---|
| **.NET SDK**（8.0 / 9.0 など） | かつての .NET Core SDK。`dotnet build` / `dotnet restore` を提供 | **これが必要** |
| .NET Framework 4.x SDK / Targeting Pack | Windows 専用の旧フレームワーク向け開発資材 | **代わりにならない**。インストール済みアプリ一覧に「4.5.1」等と出ていても SDK 要件は満たさない |
| .NET Runtime / ASP.NET Core Runtime | 実行専用 | 不可。`dotnet.exe` は入るがビルド・復元ができない |

導入は https://dotnet.microsoft.com/download から .NET SDK 8.0（LTS）。**既存の .NET Framework とはサイドバイサイドで共存**し、既存アプリに影響しない。

###### NuGet が取得できるかの確認

**「`dotnet` が入っている」ことと「NuGet パッケージを取得できる」ことは別**である。社内プロキシ、ファイアウォール、プライベートフィード設定などで復元だけが失敗するケースがある。

**段階1: 設定されているフィードを見る**

```
dotnet nuget list source
```

`nuget.org [Enabled]` が出ていれば設定上は取得可能。社内フィードのみが登録されている場合は、そのフィードに Roslyn パッケージがあるかを確認する。

**段階2: 実際に復元してみる（これが決定的）**

設定を見るだけでは疎通は分からない。小さなプロジェクトで実際に試す。

```
dotnet new classlib -o nugetcheck
cd nugetcheck
dotnet add package Microsoft.CodeAnalysis.CSharp.Workspaces
dotnet restore
```

成功すれば Phase 1 に必要な NuGet 取得は確実に動く。`tools/check-env.ps1 -NuGet` はこの手順を自動で実行する（数十秒かかるためオプション扱い）。

**失敗した場合**:

| 症状 | 対処 |
|---|---|
| タイムアウト・接続エラー | プロキシ設定。`HTTP_PROXY` / `HTTPS_PROXY` 環境変数、または `%APPDATA%\NuGet\NuGet.Config` の `<config>` セクション |
| 401 / 403 | プライベートフィードの認証。`dotnet nuget update source` で資格情報を設定 |
| パッケージが見つからない | 社内フィードのみが有効で nuget.org が無効化されている。`dotnet nuget add source https://api.nuget.org/v3/index.json -n nuget.org` |

オフライン環境では、疎通のある端末で `dotnet restore --packages ./localpkgs` を実行してパッケージをコピーし、`--source` で参照する。

##### 9.3.3 解析対象の C# が Windows / WSL どちらで扱えるか

**インストールとは別に、解析対象側の条件がある。**

```
（対象プロジェクトで）
grep -r "TargetFramework" --include=*.csproj -h . | sort -u
```

| `TargetFramework` の値 | WSL | Windows |
|---|:--:|:--:|
| `net8.0` / `net6.0` などクロスプラットフォーム | ○ | ○ |
| `net8.0-windows`（WPF / WinForms） | ✕ | ○ |
| `net48` など .NET Framework 4.x | ✕ | ○ |

Linux 版 .NET SDK は .NET Framework をターゲットにしたプロジェクトを復元・ロードできないため、`MSBuildWorkspace.OpenSolutionAsync()` が失敗する。

**さらに、解析の前に対象プロジェクト側で `dotnet restore` を通しておく必要がある。** 参照が解決できないと Roslyn のシンボル解決が不完全になる。

**ロードできない場合のフォールバック**: プロジェクトが開けなくても、`CSharpSyntaxTree.ParseText()` で個別の `.cs` ファイルを構文レベルでパースできる。`symbols` は取れるが `calls` の解決精度は落ちる。この状況こそ §3.1.2 の `confidence` 列が想定するもので、**「プロジェクトをロードできた = `high`」「構文パースのみ = `low`」**と記録する。

#### Phase 2（C/C++）

| 対象 | 要否 | 備考 |
|---|---|---|
| **Python** | 必須 | 下限は §9.3.1 参照 |
| **`pip install libclang`** | 必須 | 依存パッケージゼロ、`Requires-Python` 指定なし（実測）。ネイティブ `libclang.so` を同梱（v18.1.1、約62MB） |
| **clang** | **必須** | **Clang 組み込みヘッダ（`stddef.h` 等）の供給元**。§9.3.4 参照 |
| **gcc + libc 開発ヘッダ** | 必須 | `stdio.h` 等のシステムヘッダの供給元。cmake の configure にも必要 |
| **cmake** | 必須 | 解析対象の `compile_commands.json` 生成用（§8） |
| **Git** | 必須 | `snapshot` 列（§3.4.2） |
| ~~SQLite~~ | **不要** | **Python 本体に同梱**（実測）。`sqlite3` コマンドは中身を手で覗きたいときだけの任意ツール |
| bear | 不要 | Makefile プロジェクト用。T1 に chibicc / wren を選んでいないため（§8.5） |

##### 9.3.4 clang が必須である理由（実測）

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

**Phase 1 を C# に変更した**（2026-08-25）。理由は §10.1。

### 10.1 なぜ C# を先にするか

当初は C/C++ を Phase 1 に置いていたが、以下の理由で C# を先行させる。

1. **§4.4 の戦術メモが元々これを推奨していた** — 「アーキテクチャ検証を早く回したいなら、最初に C# で試すのも手。数時間でデータフローまで含むデータセットが出るので、スキーマ設計の妥当性を先に確かめられる」
2. **C# だけが CFG とデータフローを公式APIとして持つ**（`EXTRACTABLE_DATA_MATRIX.md` §2.6）。将来の拡張に耐えるスキーマかを**最初に**検証できる
3. **前提条件が圧倒的に少ない** — `compile_commands.json` が不要（§4.3）、libclang のヘッダ問題（§9.3.4）が無関係、シンボルIDは `GetDocumentationCommentId()` が既製（§3.2）
4. **実コードで使用感を得られる** — 手元に解析したい C# コードがある

**C/C++ が最優先という §1.1 の方針は変えない。** 順序を入れ替えるだけで、最終的な目標は同じ。C/C++ は前提条件（ビルド情報の取得）の準備に時間がかかるため、その間にスキーマを固める。

### Phase 0: 検証（数日）

- [ ] 解析対象の `.csproj` の `TargetFramework` を確認（§9.3.3 の判定）
- [ ] 対象プロジェクトで `dotnet restore` が通ることを確認
- [ ] `MSBuildWorkspace.OpenSolutionAsync()` で対象の `.sln` が開けることを確認
- [ ] `ISymbol.GetDocumentationCommentId()` が取れることを1メソッドで確認
- [ ] （任意）Understand の無料トライアルで「理想の画面」を確定させる

### Phase 1: 最小データセット ＋ スキーマ検証（C#）

**当初の Phase 1（最小データセット）と Phase 2（スキーマ検証）を統合する。** C# は CFG・データフローまで一度に出せるため、分ける意味が薄い。

- [ ] `symbols` / `calls` / `var_refs` を Roslyn で生成（§3.1）
- [ ] §7.6 の TSV としてファイル単位に出力
- [ ] Python ローダーで SQLite に投入（§3.4.1）
- [ ] `status` / `reason` / `confidence` 列の分布を確認 → 解決率をモニタリング（§3.3）
- [ ] `AnalyzeDataFlow` の結果を追加列として入れてもスキーマが壊れないか検証
  - → **ここで将来のデータフロー拡張に耐えるか分かる**
- [ ] `file` 列での delete+insert による増分取り込みを試す（§7.6）
- [ ] Mermaid または自作 HTML でコールグラフを出力
- [ ] SCIP マッピング規則（§3.2.1）が C# の DocumentationCommentId から機械的に作れるか確認

**検証対象**: 手元の実コード ＋ FluentValidation（§8.3）

### Phase 2: C/C++（libclang）

- [ ] 対象コードで `compile_commands.json` が出せるか確認
- [ ] libclang（Python）で 1 ファイルの AST を歩き、USR が取れることを確認
- [ ] **clang の resource-dir 引き渡し**が効いているか自己診断（§9.3.4）
- [ ] Phase 1 で固めたスキーマにそのまま落とせるか確認
- [ ] `reason` の各値（`via_function_pointer` / `macro_expanded` 等）が実際に出るか（§8.3 の cJSON / cmark / tinyxml2）
- [ ] clangd の Call Hierarchy を触ってベースラインを把握

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

