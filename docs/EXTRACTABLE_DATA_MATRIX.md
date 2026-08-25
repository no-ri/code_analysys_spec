# 言語別 抽出可能データ 比較調査

**作成日**: 2026-08-09
**対象言語**: C/C++、Python、C#、JavaScript、TypeScript
**目的**: 各言語で同じ深さのデータが取れるのかを確認し、データ仕様への影響を把握する
**関連文書**: CODE_ANALYSIS_CONCEPT.md

---

## 0. 調査方法と範囲

### 調査対象ツール（各言語の第一候補）

| 言語 | ツール | 種別 |
|---|---|---|
| C/C++ | **libclang**（Python バインディング） | コンパイラフロントエンドの C API |
| C/C++ | Clang LibTooling（参考） | コンパイラ内部の C++ API |
| C# | **Roslyn**（Microsoft.CodeAnalysis） | コンパイラ本体 |
| TypeScript / JavaScript | **TypeScript Compiler API** / ts-morph | コンパイラ本体 / ラッパー |
| Python | **標準 `ast` + `symtable`** | 標準ライブラリ |
| Python | **Jedi** / scip-python (pyright) | 意味解析の補完 |

### 記号の定義

| 記号 | 意味 |
|---|---|
| **○** | 公式APIで直接取得可能 |
| **△** | 取得可能だが条件付き（自前導出が必要 / 精度が保証されない / バージョン依存） |
| **×** | 取得不可（そのツールでは実現できない） |
| **−** | 言語仕様上その概念が存在しない、または不要 |

> ○×だけでは実態を誤って伝えるため、△を追加しました。△の内容は各表の注記に明記しています。

### 調査の限界（明記）

- 各ツールの公式APIリファレンスおよびソースを参照したが、**全APIを網羅的に列挙したわけではない**
- ツールのバージョンによって可否が変わる項目がある（特に libclang）
- 実際に動かして検証してはいない。**実装前に対象コードで実測すること**

---

## 1. 言語別 詳細

### 1.1 C/C++ — libclang

**アーキテクチャ**: 単一の `Cursor` 木のみ。すべてがこの1つのモデルに集約される。

**主要API**:
```
Cursor: kind, spelling, displayname, get_usr(), mangled_name,
        location, extent, referenced, canonical, get_definition(),
        is_definition(), semantic_parent, lexical_parent,
        type, result_type, get_arguments(), storage_class, linkage,
        access_specifier, is_virtual_method(), is_static_method(),
        is_const_method(), get_overriden_cursors(), is_variadic(),
        raw_comment, brief_comment, availability,
        specialized_template, get_bitfield_width(), enum_value,
        is_anonymous(), has_attrs, exception_specification_kind
Type:   spelling, get_canonical(), get_size(), get_align(),
        get_offset(), get_pointee(), get_array_element_type(),
        argument_types(), is_const_qualified(), is_volatile_qualified(),
        get_declaration(), get_num_template_arguments()
TU:     diagnostics, get_includes(), get_tokens(), cursor
```

**特筆すべき強み**
- **USR**: 翻訳単位を横断して一意なシンボルID。名寄せの基盤として最も信頼できる
- **マングル名**: リンカレベルの一意名も取れる
- **メモリレイアウト**: `get_size()` / `get_align()` / `get_offset()` により構造体の物理配置まで分かる。他言語には存在しない情報
- **Doxygenコメント**: `raw_comment` / `brief_comment` が標準で取れる
- **プリプロセッサ**: マクロ定義、インクルード関係、展開位置

**特筆すべき弱点**
- **リテラルの値が取れない**。整数・浮動小数・文字列・文字・bool の各リテラル値は素の libclang では公開されていない。`clang_tokenize` でトークン列から自力で読むか、Sealang のような非公式フォークを使う必要がある
- **演算子の種類がバージョン依存**。`clang_Cursor_getBinaryOpcode` は 2015年に提案（D10833）されたが、Python バインディングへの反映は 2024年の PR #98489。古い LLVM では利用できない
- **CFG が取れない**。`clang::CFG` は C++ の LibTooling 側にのみ存在
- **読み/書きの区別がない**。`DECL_REF_EXPR` は「参照した」としか言わず、親ノードを自力で判定する必要がある
- AST の一部しか公開していない（`Stmt` のサブクラス詳細など）

**文の種別は取れる**: `IF_STMT` / `FOR_STMT` / `WHILE_STMT` / `DO_STMT` / `SWITCH_STMT` / `CASE_STMT` / `BREAK_STMT` / `CONTINUE_STMT` / `RETURN_STMT` / `GOTO_STMT` / `LABEL_STMT` / `CXX_TRY_STMT` / `CXX_CATCH_STMT` などは `CursorKind` として公開されている。**簡易CFGの自前構築は可能**。

---

### 1.2 C# — Roslyn

**アーキテクチャ**: **3層構造**。これが他言語との決定的な差。

| 層 | 型 | 役割 |
|---|---|---|
| 構文層 | `SyntaxNode` | ソースの構文木。トリビア（空白・コメント）まで完全保持 |
| 意味層 | `ISymbol` | 解決済みのシンボル |
| 操作層 | **`IOperation`** | 言語非依存に正規化された「操作」の木 |

`ISymbol` はルートインターフェースで、名前空間・型・メソッド・プロパティ・フィールド・パラメータ・ローカル変数まで、C# のあらゆる名前付き要素にシンボルが対応します。

`IOperation` はすべての文と式に対応する表現で、`IInvocationOperation`（`.TargetMethod` に解決済みの `IMethodSymbol`、`.Arguments`、`.Instance`）、`IAssignmentOperation`（`.Target` と `.Value`）、`IBinaryOperation`（`.LeftOperand` / `.RightOperand` / `.OperatorKind`）、`ILocalReferenceOperation` などが用意されています。

**主要API**:
```
ISymbol:          Kind, Name, MetadataName, ContainingType, ContainingNamespace,
                  ContainingAssembly, DeclaredAccessibility, IsStatic, IsVirtual,
                  IsOverride, IsAbstract, IsSealed, IsExtern, IsImplicitlyDeclared,
                  Locations, DeclaringSyntaxReferences, GetAttributes(),
                  GetDocumentationCommentId(), GetDocumentationCommentXml(),
                  ToDisplayString()
IMethodSymbol:    MethodKind, Arity, IsGenericMethod, ReturnType, Parameters,
                  IsAsync, IsExtensionMethod, AssociatedSymbol, OverriddenMethod,
                  ExplicitInterfaceImplementations, TypeArguments,
                  PartialDefinitionPart, PartialImplementationPart
INamedTypeSymbol: BaseType, Interfaces, AllInterfaces, GetMembers(), TypeKind,
                  SpecialType, IsRecord, EnumUnderlyingType
IFieldSymbol:     IsConst, IsReadOnly, ConstantValue, AssociatedSymbol
IPropertySymbol:  GetMethod, SetMethod, IsIndexer
IParameterSymbol: RefKind, Type, HasExplicitDefaultValue, ExplicitDefaultValue
SemanticModel:    GetSymbolInfo(), GetTypeInfo(), GetDeclaredSymbol(),
                  GetOperation(), AnalyzeDataFlow(), AnalyzeControlFlow(),
                  GetDiagnostics()
SymbolFinder:     FindReferencesAsync(), FindCallersAsync(),
                  FindImplementationsAsync(), FindDerivedClassesAsync()
```

**制御フローグラフが公開API**

`Microsoft.CodeAnalysis.FlowAnalysis.ControlFlowGraph` は、実行可能コードブロックに対する CFG 表現です。エントリブロック、0個以上の中間ブロック、出口ブロックからなる `BasicBlock` の集合を持ち、各基本ブロックは 0個以上の `Operations` と、他ブロックへの明示的な `ControlFlowBranch` を持ちます。

`BasicBlock` に入ったら中の全操作は必ず実行され、末尾の `BranchValue` の評価結果に応じて `ConditionalSuccessor` か `FallThroughSuccessor` のどちらかの分岐を取って抜けます。ループ・if-else・条件式などはすべて条件分岐/無条件分岐操作の組に低次化されています。また `ControlFlowRegion` がローカル変数とキャプチャの生存期間（C# のスコープに近い概念）をブロックのグループとして表現します。

さらに roslyn-analyzers リポジトリには、この CFG API の上に構築されたデータフロー解析フレームワークがあります。`DataflowAnalysis` がワークリスト方式で不動点に達するまで抽象値を基本ブロック間に伝播させ、`DataFlowOperationVisitor` が転送関数を定義し、`AnalysisEntity` が追跡対象のエンティティを表します。既知のデータフロー解析がいくつか実装済みで、その結果を消費することも独自解析を書くこともできます。

> **これは §7.2 で「自作は中程度の難易度」とした単調フレームワークが、C# では既製品として存在するということ。**

---

### 1.3 TypeScript / JavaScript — TypeScript Compiler API / ts-morph

**アーキテクチャ**: 構文層（`ts.Node`）と意味層（`ts.Symbol` / `ts.Type`）の2層。`TypeChecker` が両者を橋渡しします。

**主要API（TypeChecker）**:
```
getSymbolAtLocation(node)          -- ノードのシンボル解決
getTypeAtLocation(node)            -- ノードの型
getTypeOfSymbolAtLocation(sym,node)
getDeclaredTypeOfSymbol(symbol)
getSignatureFromDeclaration(node)  -- シグネチャ
getResolvedSignature(callLike)     -- 呼び出しの解決先シグネチャ
getReturnTypeOfSignature(sig)
getPropertiesOfType(type) / getPropertyOfType()
getSignaturesOfType(type)
getBaseTypes(type)
getIndexTypeOfType(type)
getNonNullableType(type)
getSymbolsInScope(node, flags)
getExportSymbolOfSymbol(symbol)    -- ローカル→エクスポートシンボル
typeToString(type)
getDiagnostics()
```

`getResolvedSignature` はエラー時に `unknownSignature` を返し、ノードが不正な場合は `undefined` を返します。`getExportSymbolOfSymbol` はローカルシンボルに対応するエクスポートシンボルを返すためのもので、`export type T = number;` において `getSymbolAtLocation` はエクスポートシンボルを返すが `getSymbolsInScope` はローカルシンボルを返す、という差を吸収します。

**ts-morph（ラッパー）の追加機能**:
```
identifier.findReferences()          -- 参照検索（詳細情報つき）
identifier.findReferencesAsNodes()   -- ノードのみ
identifier.getDefinitions()          -- 定義へジャンプ
identifier.getDefinitionNodes()
identifier.getImplementations()      -- 実装へジャンプ
identifier.getType()
node.getDescendantsOfKind(SyntaxKind.X)
languageService.findReferencesAtPosition()
                getSuggestionDiagnostics()
                getCodeFixesAtPosition()
```

`findReferences()` は参照ごとにソースファイルパス、テキストスパンの開始位置と長さ、親ノードの種別を返します。

**強み**
- 型システムが非常に豊かで、ユニオン型・交差型・ジェネリクスまで解決できる
- `allowJs: true` で **JavaScript も同じ TypeChecker を通せる**。JSDoc からの型推論も効く
- 言語サービス層（`findReferences` / `getImplementations`）が IDE 品質
- **リテラル値が AST に直接ある**（`StringLiteral.text`、`NumericLiteral.text`）

**弱点**
- **CFG の公開APIが存在しない**。内部の binder は型ナローイングのためのフロー解析を持つが、外部には公開されていない
- **データフロー解析APIがない**
- 素の JavaScript（型注釈なし）では名前解決の精度が落ちる
- 安定シンボルIDの標準形式がない（宣言位置ベースで自作するか SCIP を使う）

---

### 1.4 Python — 標準 `ast` + `symtable` + Jedi / scip-python

**アーキテクチャ**: 構文層（`ast`）とスコープ層（`symtable`）は標準ライブラリ。意味層（名前解決・型推論）は**外部ツールに依存**。

#### 標準 `ast`

`ast.expr` と `ast.stmt` のサブクラスは `lineno` / `col_offset` / `end_lineno` / `end_col_offset` を持ちます。`lineno` と `end_lineno` はソーステキスト範囲の最初と最後の行番号（1始まり）、`col_offset` と `end_col_offset` は対応する **UTF-8 バイトオフセット**です（パーサが内部で UTF-8 を使うため）。ただし**終了位置はコンパイラが必要としないためオプショナル**です。

`ast.get_source_segment()` でノードに対応するソース断片が取れますが、位置情報が欠けている場合は `None` を返します。

**Python の決定的な強み**: ASDL 定義に `expr_context = Load | Store | Del` があり、**`Name` ノードが読み/書き/削除のどれなのかを AST が最初から持っています**。

> これは libclang にはない利点です。C/C++ では親ノードを自力で判定する必要がある「read / write の区別」が、Python では**無条件で正確に取れます**。単純な優劣ではないことの好例。

さらに演算子も列挙型として直接持ちます:
```
operator = Add | Sub | Mult | MatMult | Div | Mod | Pow | LShift
         | RShift | BitOr | BitXor | BitAnd | FloorDiv
unaryop  = Invert | Not | UAdd | USub
cmpop    = Eq | NotEq | Lt | LtE | Gt | GtE | Is | IsNot | In | NotIn
boolop   = And | Or
```
リテラル値も `ast.Constant.value` で直接取得できます。**libclang が苦労する部分が Python では自明**です。

#### 標準 `symtable`

スコープ解析を提供します。`is_global()` / `is_local()` / `is_free()` / `is_parameter()` / `is_imported()` / `is_assigned()` / `is_namespace()` などで、名前がどのスコープに属するかを判定できます。名前解決そのものではありませんが、ローカル変数とグローバル変数の区別には十分です。

#### Jedi

```
Script:   goto(), infer(), get_references(), get_names(),
          get_syntax_errors(), get_signatures(), search(), complete()
BaseName: name, type, module_name, module_path, line, column,
          description, full_name, docstring(), get_signatures(),
          get_type_hint(), is_stub(), is_side_effect(),
          in_builtin_module(), parent(), defined_names()
```

`type` は `'module' | 'class' | 'instance' | 'function' | 'param' | 'path' | 'keyword' | 'property' | 'statement'` のいずれかを返します。`full_name` は `<module>[.<submodule>...][.<object>]` 形式で、`os.path.join` のように返ります（実体が `posixpath.join` であっても実用性を優先してこの形になります）。

`goto()` と `infer()` の違いは、**`goto()` が import と文を追わないのに対し `infer()` は追う**点です。Python は動的言語なので、どちらも**複数の結果が返る可能性があります**。

**重大な制約**: `get_references()` のドキュメントには、これが Jedi にとってかなり難しい処理であり、**複雑すぎる場合は探索を打ち切る**と明記されています。つまり参照検索の網羅性は保証されません。

#### 総合的な弱点

- **名前解決が best effort**。動的インポート、`getattr`、メタクラス、モンキーパッチは原理的に追えない
- **CFG も データフローも標準にない**
- 標準 `ast` 単体では `foo()` がどの `foo` か分からない

---

## 2. 横並び比較マトリクス

### 2.1 ファイル・プロジェクト層

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| ファイルパス・行数 | ○ | ○ | ○ | ○ | ○ |
| インクルード / import 関係 | ○ | ○ | ○ | ○ | ○ |
| import のエイリアス（`as`） | − | ○ | ○ | ○ | ○ |
| 名前空間 / モジュール境界 | ○ | ○ | ○ | ○ | ○ |
| **翻訳単位（TU）の概念** | ○ | − | − | − | − |
| **コンパイルフラグ** | ○ | − | ○ | △ | ○ |
| **プリプロセッサ条件（`#ifdef`）** | ○ | − | ○ | − | − |
| ビルド構成による分岐 | ○ | − | ○ | − | − |

注:
- Python / JS / TS には翻訳単位もプリプロセッサも存在しない → `−`
- **C# には `#if` がある**。C/C++ ほど多用されないが、条件コンパイルの問題は同様に発生する
- JS の `△` は tsconfig 相当が任意のため

### 2.2 関数・メソッド

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| 名前 / 修飾名 | ○ | ○ | ○ | ○ | ○ |
| **安定シンボルID** | ○ USR | △ full_name | ○ DocCommentId | △ | △ |
| マングル名 / メタデータ名 | ○ | − | ○ | − | − |
| 戻り値型 | ○ | △ | ○ | △ | ○ |
| 引数（名前・型・順序） | ○ | ○ | ○ | ○ | ○ |
| 引数のデフォルト値 | △ | ○ | ○ | ○ | ○ |
| 可変長引数 | ○ | ○ | ○ | ○ | ○ |
| **宣言と定義の区別** | ○ | − | △ partial | − | ○ .d.ts |
| リンケージ / storage class | ○ | − | ○ | − | − |
| アクセス修飾子 | ○ | △ 慣習 | ○ | △ `#` | ○ |
| static / const / virtual | ○ | △ | ○ | △ | △ |
| **オーバーライド元** | ○ | × | ○ | × | △ |
| オーバーロード | ○ | − | ○ | − | ○ 宣言のみ |
| async / generator | − | ○ | ○ | ○ | ○ |
| 例外仕様 | ○ | − | − | − | − |
| 属性 / デコレータ / アノテーション | ○ | ○ | ○ | △ | ○ |
| **ドキュメントコメント** | ○ Doxygen | ○ docstring | ○ XMLDoc | ○ JSDoc | ○ JSDoc |

注:
- Python の戻り値型 `△`: 型注釈があれば `ast` から確実に取れる。無ければ Jedi の推論に依存
- C/C++ の引数デフォルト値 `△`: 子ノードには存在するが、リテラル値は要トークン化
- Python のアクセス修飾子 `△`: `_name` / `__name` は言語機能ではなく慣習（name mangling はあるが強制力なし）
- Python のオーバーライド `×`: 動的なため静的に確定できない。基底クラスの同名メソッドを推測することは可能だが保証されない
- JS の `#private` は ES2022 以降。それ以前は慣習のみ
- C# の宣言/定義 `△`: `partial` メソッドで `PartialDefinitionPart` / `PartialImplementationPart` として区別される

### 2.3 変数・フィールド

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| 名前・位置 | ○ | ○ | ○ | ○ | ○ |
| 型 | ○ | △ | ○ | △ | ○ |
| **スコープ種別** | ○ | ○ symtable | ○ | ○ | ○ |
| グローバル変数の識別 | ○ | ○ | △ static | ○ | ○ |
| const / readonly / final | ○ | △ Final | ○ | ○ | ○ |
| 初期化子の有無 | ○ | ○ | ○ | ○ | ○ |
| **初期化子の値（リテラル）** | × | ○ | ○ | ○ | ○ |
| storage duration | ○ | − | △ | − | − |
| **構造体内オフセット** | ○ | − | × | − | − |
| **サイズ / アライメント** | ○ | − | △ | − | − |
| ビットフィールド幅 | ○ | − | − | − | − |

注:
- **libclang のリテラル値 `×` が最も意外な結果**。Python / C# / TS / JS はすべて AST から直接取れる
- C# にグローバル変数はない（`static` フィールドが最も近い）→ `△`
- Python の `const` `△`: `typing.Final` は型チェッカへのヒントであり実行時の強制力なし
- サイズ/オフセットは C/C++ 固有。C# は `Marshal.SizeOf` 相当で部分的に可能だがコンパイル時ではない

### 2.4 型・クラス

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| クラス / 構造体の定義 | ○ | ○ | ○ | ○ | ○ |
| **基底クラス / インターフェース** | ○ | ○ | ○ | ○ | ○ |
| 多重継承 | ○ | ○ | − | − | − |
| 仮想継承 | ○ | − | − | − | − |
| メンバ一覧 | ○ | ○ | ○ | △ | ○ |
| 列挙型と定数値 | ○ | ○ Enum | ○ | − | ○ |
| typedef / エイリアス | ○ | ○ | ○ | − | ○ |
| ジェネリクス / テンプレート | ○ | ○ | ○ | − | ○ |
| **テンプレート実体化の追跡** | ○ | − | ○ | − | △ |
| 共用体 | ○ | − | − | − | △ union型 |
| 構造的型付け | − | − | − | − | ○ |
| ユニオン型 / 交差型 | − | ○ | − | − | ○ |

注:
- JS のメンバ一覧 `△`: 動的にプロパティが追加されるため静的には不完全
- C++ の `union` と TypeScript の union 型は**全く別の概念**（前者はメモリ共有、後者は型の和）

### 2.5 呼び出し・参照関係

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| **直接呼び出しの解決** | ○ | △ | ○ | △ | ○ |
| 仮想呼び出しの識別 | ○ | × | ○ | × | △ |
| 関数ポインタ経由 | △ 未解決 | △ | △ delegate | △ | △ |
| **参照検索（全参照）** | △ 自前 | △ Jedi | ○ SymbolFinder | ○ | ○ |
| **呼び出し元検索** | △ 自前 | △ | ○ FindCallers | ○ | ○ |
| 実装検索（interface→impl） | △ | × | ○ | × | ○ |
| **変数の read / write 区別** | △ 自前判定 | **○ ctx** | ○ IOperation | ○ | ○ |
| アドレス取得 / 関数参照 | ○ | ○ | ○ | ○ | ○ |
| メンバアクセス | ○ | ○ | ○ | ○ | ○ |
| throw / catch | ○ | ○ | ○ | ○ | ○ |

注:
- **read/write の区別が最も逆転する項目**。Python は `expr_context = Load | Store | Del` で AST が最初から持つ。C/C++ は親ノードの自前判定が必要
- C/C++ の参照検索 `△`: libclang には `SymbolFinder` 相当がない。全 TU を走査して USR で突き合わせる自前実装が必要
- Python / JS の直接呼び出し `△`: 動的言語のため確実性が保証されない

### 2.6 制御フロー・データフロー

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| 文の種別（if/for/while等） | ○ | ○ | ○ | ○ | ○ |
| **CFG（公式API）** | × libclang<br>○ LibTooling | × | **○** | × | × |
| 基本ブロック | × / ○ | × | ○ | × | × |
| 分岐条件式 | ○ | ○ | ○ | ○ | ○ |
| ループ検出 | △ 導出 | △ 導出 | ○ | △ | △ |
| スコープ / 生存期間の領域 | △ | ○ symtable | ○ Region | △ | △ |
| **データフロー解析（公式）** | × | × | **○** | × | × |
| 到達定義 / 活性変数 | × | × | ○ FW | × | × |
| ポインタ / エイリアス解析 | × | − | △ | − | − |
| 例外エッジ | × / ○ | × | ○ | × | × |

**この表が本調査で最も重要です。**

- **C# だけが CFG とデータフロー解析を公式APIとして持っています**
- C/C++ は LibTooling（C++）に降りれば取れますが、libclang からは取れません
- **Python / JS / TS は公式APIが一切存在しません**。自前構築するしかありません

### 2.7 位置・テキスト情報

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| 開始位置（行・列） | ○ | ○ | ○ | ○ | ○ |
| **終了位置（行・列）** | ○ | △ 3.8+任意 | ○ | ○ | ○ |
| バイトオフセット | ○ | ○ UTF-8 | ○ | ○ | ○ |
| **マクロ綴り位置 vs 展開位置** | ○ | − | − | − | − |
| トークン列 | ○ | ○ tokenize | ○ | ○ | ○ |
| コメント本文 | ○ | ○ | ○ Trivia | ○ | ○ |
| 空白・整形情報 | △ | △ | **○ Trivia** | △ | △ |
| **リテラルの値** | **×** | ○ | ○ | ○ | ○ |
| 演算子の種類 | △ 版依存 | ○ | ○ | ○ | ○ |

注:
- Python の終了位置 `△`: 3.8 以降で利用可能だが、ドキュメント上オプショナル扱い。欠けている場合は `None`
- Roslyn の Trivia は空白・改行・コメントまで完全にラウンドトリップ可能な形で保持する。**C# が唯一「完全な CST」を持つ**

### 2.8 診断・メトリクス

| 項目 | C/C++ | Python | C# | JS | TS |
|---|:--:|:--:|:--:|:--:|:--:|
| **コンパイラ診断（warning/error）** | ○ | △ 構文のみ | ○ | ○ | ○ |
| 構文エラー | ○ | ○ | ○ | ○ | ○ |
| 型エラー | ○ | × 標準 | ○ | △ | ○ |
| 提案診断（suggestion） | × | × | ○ | ○ | ○ |
| 循環的複雑度 | △ 導出 | △ 導出 | △ 導出 | △ | △ |

注: Python の型エラーは標準 `ast` では取れない。pyright / mypy / ty など外部ツールが必要。

---

## 3. 結論：同じ深さで抽出できるか

**No。言語間で明確な段差があります。**

### 3.1 深さのランキング

```
深い ┌─────────────────────────────────────────┐
     │ C#（Roslyn）                             │  構文 + 意味 + 操作 + CFG + データフロー
     │   3層モデル、CFG公式API、データフロー公式FW  │  すべて公式・単一パッケージ
     ├─────────────────────────────────────────┤
     │ C/C++（libclang → LibTooling）           │  意味解析は最強だが API 公開が限定的
     │   USR・メモリレイアウトは唯一無二          │  CFG は C++ に降りる必要あり
     │   リテラル値が取れないという意外な穴        │
     ├─────────────────────────────────────────┤
     │ TypeScript                               │  型システムは豊かだが CFG なし
     │   IDE品質の参照検索                       │
     ├─────────────────────────────────────────┤
     │ JavaScript                               │  TS と同じ基盤だが型情報が薄い
     ├─────────────────────────────────────────┤
     │ Python                                   │  構文層は優秀（ctx / リテラル / 演算子）
     │   意味層が best effort、CFG なし          │  意味層が最も弱い
浅い └─────────────────────────────────────────┘
```

### 3.2 ただし単純な優劣ではない（重要）

ランキングは総合的な深さであって、**項目ごとに逆転します**。

| 項目 | 最も強い言語 | 最も弱い言語 |
|---|---|---|
| 意味解析の正確さ | C/C++、C# | Python、JS |
| CFG / データフロー | **C#**（圧倒的） | Python / JS / TS（皆無） |
| **read / write の区別** | **Python**（AST標準） | C/C++（自前判定） |
| **リテラル値** | Python / C# / TS / JS | **C/C++**（取れない） |
| メモリレイアウト | **C/C++**（唯一） | 他全部 |
| 参照検索の完全性 | C#、TS | C/C++（自前実装） |
| 空白・整形の保持 | **C#**（Trivia） | 他全部 |

**特に注意すべき逆転**:
- 「read / write の区別」は Python が最強、C/C++ が最弱
- 「リテラル値」は C/C++ だけが取れない
- 「参照検索」は C/C++ に標準APIがなく、自前で全TU走査が必要

---

## 4. データ仕様への影響

### 4.1 共通スキーマに入れてよい項目（全言語 ○ または軽い △）

```
symbols:   id, kind, name, qualified_name, file,
           line, col, end_line, end_col, is_definition,
           confidence, lang, extractor, snapshot
calls:     caller_id, callee_id, callee_expr,
           status, reason, confidence, call_kind,
           file, line, col, lang, extractor, snapshot
var_refs:  func_id, var_id, access,
           status, reason, confidence,
           file, line, col, lang, extractor, snapshot
imports:   from_file, to_module, alias, file, line
```

> **正はこれではない。** テーブル定義の正本は CODE_ANALYSIS_CONCEPT.md §3.1。本節は「調査結果としてこの形に落ちる」ことを示すための再掲であり、差異が出た場合は §3.1 に従うこと。`imports` は §3.1 の初版テーブルには含まれていない（未決事項。OPEN_DECISIONS.md 参照）。

`access`（read / write / readwrite）は全言語で表現可能だが、**導出方法と信頼度が言語ごとに異なる**ため、後述の `confidence` 列とセットで扱う。

### 4.2 言語固有テーブルに分離すべき項目

共通テーブルに入れると 4/5 の言語で NULL になるもの:

| テーブル | 対象 | 理由 |
|---|---|---|
| `cpp_layout` | サイズ・アライメント・オフセット・ビットフィールド | C/C++ のみ |
| `cpp_preproc` | マクロ定義・展開位置・`#ifdef` 条件 | C/C++（+ C# の `#if` は別扱い） |
| `cpp_linkage` | storage class・linkage・翻訳単位 | C/C++ のみ |
| `cfg_blocks` / `cfg_edges` | 基本ブロック・エッジ | 実質 C# のみ（C/C++ は LibTooling 導入後） |
| `dataflow_*` | 到達定義・活性変数 | 実質 C# のみ |

### 4.3 スキーマに必須の追加列

調査結果から、以下は**初版から必要**と判断:

いずれも **確定済み**（CODE_ANALYSIS_CONCEPT.md §3.1、2026-08-25）。

| 列 | 理由 |
|---|---|
| **`status` / `reason`** | 「解決できたか」と「なぜできなかったか」を分けて記録する（§3.1.1）。Python / JS で特に重要 |
| **`confidence`** | 同じ `access = 'write'` でも、Python は AST 由来（確実）、C/C++ は自前判定（推定）。信頼度が違うことをデータに残す（§3.1.2） |
| **`extractor`** | 同じ言語でも Jedi 由来と scip-python 由来で精度が違う |
| **`config`** | C/C++ と C# の条件コンパイル対応。**C# にも `#if` がある点に注意** |

### 4.4 覚悟しておくべき非対称性

1. **CFG テーブルは長期間 C# のみ埋まる**
   → 「言語によって空のテーブルがある」ことを前提に設計する。全言語で埋まるまで待つ設計にしない

2. **リテラル値テーブルは C/C++ だけ空になる**
   → マジックナンバー検出を全言語でやりたいなら、C/C++ 用にトークン化処理を別途書く必要がある

3. **参照検索の実装コストが C/C++ だけ突出する**
   → C# / TS は API 一発、C/C++ は全 TU 走査 + USR 突合の自前実装

4. **Python / JS の呼び出しエッジは常に不完全**
   → `status` の分布をモニタリングし、「解決率 60%」のような数字を可視化に出す設計にしておく

5. **「宣言が複数ある」問題は全言語で起きるが原因が違う**

   | 言語 | 原因 |
   |---|---|
   | C/C++ | 宣言 / 定義の分離、ヘッダの多重インクルード |
   | C# | `partial` クラス / メソッド |
   | TS | 宣言マージ、`.d.ts` |
   | Python | 再定義、条件付き定義 |

   → 「正規シンボル1行 + 宣言箇所の別テーブル」構造は全言語で必要

### 4.5 推奨する着手順の再確認

> **更新（2026-08-25）**: 当初は「Phase 1 = C/C++、Phase 2 = C#」としていたが、**順序を入れ替えて C# を Phase 1 とした**。理由は CODE_ANALYSIS_CONCEPT.md §10.1。本節の分析はその判断を支持する内容だったため、結論だけを差し替える。

**C# が最も多くの情報を出せるため、スキーマの穴を最も早く発見できます。** C/C++ だけでスキーマを固めると、CFG・データフロー・リテラル値・参照検索という4方向で後から作り直しが発生します。**この理由により C# を先行させます。**

一方で **C/C++ が本命**（CODE_ANALYSIS_CONCEPT.md §1.1）である点は変わりません。C/C++ 固有の現実的な制約（`compile_commands.json`、リテラル値の欠如、参照検索の自前実装）は Phase 2 で体感することになります。**順序を変えただけで、最終的な目標は変わっていません。**

---

## 5. 参照

**C/C++**
- libclang Python bindings: https://libclang.readthedocs.io/
- `clang_Cursor_getBinaryOpcode` 提案: https://reviews.llvm.org/D10833
- Python バインディングへの反映 PR #98489（2024年）
- Sealang（リテラル値・演算子を追加するフォーク）: https://github.com/ptrstr/sealang
- Clang LibTooling: https://clang.llvm.org/docs/LibTooling.html

**C#**
- ISymbol: https://github.com/dotnet/roslyn/blob/main/src/Compilers/Core/Portable/Symbols/ISymbol.cs
- IMethodSymbol: https://learn.microsoft.com/en-us/dotnet/api/microsoft.codeanalysis.imethodsymbol
- ControlFlowGraph: https://learn.microsoft.com/en-us/dotnet/api/microsoft.codeanalysis.flowanalysis.controlflowgraph
- BasicBlock: https://learn.microsoft.com/en-us/dotnet/api/microsoft.codeanalysis.flowanalysis.basicblock
- データフロー解析FW: https://github.com/dotnet/roslyn-analyzers/blob/main/docs/Writing%20dataflow%20analysis%20based%20analyzers.md
- CFG API 設計議論: https://github.com/dotnet/roslyn/issues/24104

**TypeScript / JavaScript**
- TypeChecker: https://typestrong.org/typedoc-auto-docs/typedoc/interfaces/TypeScript.TypeChecker.html
- ts-morph 参照検索: https://ts-morph.com/navigation/finding-references
- ts-morph 識別子: https://ts-morph.com/details/identifiers

**Python**
- `ast`: https://docs.python.org/3/library/ast.html
- Jedi API: https://jedi.readthedocs.io/en/latest/docs/api.html
- Jedi 戻り値クラス: https://jedi.readthedocs.io/en/latest/docs/api-classes.html
- scip-python: https://github.com/sourcegraph/scip-python
