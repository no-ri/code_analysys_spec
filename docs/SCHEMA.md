# スキーマ定義（L1）— **正本**

**作成日**: 2026-08-27
**ステータス**: **確定**。L1 の列定義はこの文書が唯一の正本
**対象**: **L1 のみ**（K-3）。L0 の中間ファイル形式は [構想] §7.6、L2 の派生は §8 に一覧のみ

> ## この文書の位置づけ
>
> **列定義の正本はここ1箇所。** 他の文書は再掲せず参照する（F-1 決定5）。
> [構想] §3.1 ／ `OPEN_DECISIONS.md` の E-1・F-1 ／ [現実] §4.1 の列一覧は**すべて過去の記録**であり、
> 食い違った場合は本文書が正。
>
> **なぜ1箇所に集めるか**: 再掲が3箇所あった結果、追随漏れが構造的に起きた（F-8 が実例。
> 追随改訂6件のうち §7.6 だけが「現状の3テーブル」のまま取り残された）。
>
> **決定の根拠は本文書に書かない。** 「なぜそう決めたか」は `OPEN_DECISIONS.md` の決定事項にあり、
> 列ごとの追跡は `SCHEMA_INDEX.md` にある。本文書は**現在の姿**だけを書く。
>
> **このスキーマは実行して検証されている** → §9

---

## 1. 全体像

```
L0  抽出層   facts/raw/**.tsv ＋ facts/raw/run.tsv     事実のみ。判断しない。捨てない
              ↓ 取り込み（§7）
L1  ファクト層 facts/db.sqlite                          ★ 本文書の対象
              ↓ 派生（再生成可能）
L2  派生層   derived/db.sqlite                          §8 に一覧のみ
              ↓
L3a 理解層（図・レポート）        L3b 検出層（findings）
```

| テーブル | 役割 | 対象範囲 |
|---|---|---|
| `analysis_run` | 実行の設定と結果（縦持ち） | (言語, 実行) ごと |
| `files` | ファイルの計測値 | **解析対象ツリーのみ** |
| `symbols` | 名前を持つもの | 解析対象ツリー ＋ **追加ソースツリー** |
| `refs` | 参照関係（呼び出し・import・変数参照） | **解析対象ツリーのみ** |
| `comments` | 人が書いた説明 | **解析対象ツリーのみ** |

**`symbols` だけが追加ソースツリーの行を持つ**（閉世界の境界レベル1）。そのため `symbols` にのみ `root` 列がある。

---

## 2. 全テーブル共通の規約

### 2.1 `NOT NULL`

**主キーを構成する列はすべて `NOT NULL` を明示する。**
SQLite は `INTEGER PRIMARY KEY` 以外の主キー列に NULL を許し、**NULL 同士を重複と見なさない**。
明示しないと「衝突をエラーにする」（§7.3）が静かに無効化される。

### 2.2 位置

| 項目 | 規約 |
|---|---|
| 列名 | `start_line` / `start_col` / `end_line` / `end_col` |
| 起点 | **1 起点**（tree-sitter は 0 起点なので +1） |
| `end` | **排他**（最後の文字の次を指す。libclang は包含なので +1） |
| `col` の単位 | **文字数（Unicode コードポイント）**。tree-sitter の column は**行内のバイトオフセット**なので変換が要る |

| テーブル | 範囲が指すもの |
|---|---|
| `symbols` | **宣言・定義全体**（修飾子・属性を含む先頭から本体の閉じ括弧まで） |
| `refs` | **参照式全体**（`p->f(a,b)` 全体、`#include "x.h"` の行全体） |
| `comments` | コメント（または docstring リテラル）全体 |

**名前トークンだけの位置は持たない。**

### 2.3 空値の3種類

| 表現 | 意味 | 例 |
|---|---|---|
| **空文字** | **その行に該当しない** | `status='resolved'` の行の `reason`、`kind≠'call'` の行の `dispatch` |
| **`not_applicable`** | **その言語に概念が無い** | C# の `storage_class`、Python の `guard` |
| **`NULL`**（整数列） | **測っていない** | 抽出しなかったファイルの `comment_lines` |

`NULL = 未測定` を持つ整数列: `files.bytes` / `lines` / `comment_lines` / `blank_lines` / `parse_errors` /
`missing_nodes` / `error_lines` / `git_commits` / `git_authors`、`symbols.branch_count`。
**`refs.lambda_depth` は対象外**（常に整数。「ラムダの外」は測った結果の 0）。

### 2.4 集計クエリの規約

**すべての集計クエリは `extractor` で絞る。** `ATTACH` でフル版の DB を結合したとき、
絞らないと同じ呼び出しが2回数えられる。

```sql
-- ✗ 二重計上する
SELECT status, COUNT(*) FROM refs GROUP BY status;
-- ○
SELECT status, COUNT(*) FROM refs WHERE extractor = ? GROUP BY status;
```

**`confidence` 単独でフィルタしない。** `unresolved` の行にも `high` が付く（§6）。
必ず `WHERE status='resolved' AND confidence='high'` と組にする。

### 2.5 `id` での結合

`symbols.id` は**1シンボル N 行**にマッチする（宣言と定義、`#ifdef` の両枝、`partial`、名前空間）。
素朴に JOIN すると件数が倍になるため、参照の性質ごとに書き方を変える。

| 参照 | 行の特定方法 |
|---|---|
| `refs.src_id` / `symbols.container_id` | **位置の包含**（`s.file = r.file` かつ範囲が包含）。どちらも「囲むもの」なので一意に決まる |
| `refs.dst_id` | 集計は `refs` 側だけで行う。名前が要るときは `COUNT(DISTINCT 位置)` か L2 の `symbol_canonical` |
| `comments.attached_id` | **`attached_line` と組にする**。コメントは対象の**前**にあり「囲む」関係ではないので位置包含が使えない |

### 2.6 シンボルID

```
local  <repo-name>  <version欄>  <descriptor...>
例: local  cJSON  .  cJSON_Delete(cJSON*).
```

- **`snapshot` を含めない。** 含めると同じ関数が snapshot ごとに別IDになり、2時点比較が「全件消滅＋全件新規」になる
- **descriptor にパラメータの型名リストを含める（必須）。** 名前だけだとオーバーロードが衝突して消える（C# で 17.7%）
- 型注釈が無い言語は**アリティ**でフォールバック。**出現順の連番は採らない**（編集で変わる）
- ファイルシンボルは末尾 `/`（`local cJSON . src/a.c/`）
- 外部ライブラリは本来の座標を5欄で受け入れる（`stdlib c libc c99 printf().`）

> **要確認（実装時）**: `<version欄>` の固定値（`.` を想定）は **SCIP 仕様を確認する**。未検証。

---

## 3. DDL

**この DDL は `tools/schema-check/verify_schema.py` で実行して検証されている**（§9）。

```sql
CREATE TABLE analysis_run(
  extractor  TEXT NOT NULL,
  snapshot   TEXT NOT NULL,
  key        TEXT NOT NULL,
  value      TEXT,
  seq        INT  NOT NULL,
  PRIMARY KEY (extractor, snapshot, key, seq));

CREATE TABLE files(
  file              TEXT NOT NULL,
  lang              TEXT,
  extract_status    TEXT,
  bytes             INT,
  lines             INT,
  comment_lines     INT,
  blank_lines       INT,
  parse_errors      INT,
  missing_nodes     INT,
  error_lines       INT,
  content_hash      TEXT,
  git_commits       INT,
  git_authors       INT,
  git_last_modified TEXT,
  confidence        TEXT,
  extractor         TEXT NOT NULL,
  snapshot          TEXT NOT NULL,
  PRIMARY KEY (file, extractor, snapshot));

CREATE TABLE symbols(
  id                TEXT NOT NULL,
  root              TEXT NOT NULL,
  kind              TEXT,
  name              TEXT,
  qualified_name    TEXT,
  container_id      TEXT,
  file              TEXT NOT NULL,
  start_line        INT  NOT NULL,
  start_col         INT,
  end_line          INT,
  end_col           INT,
  is_definition     INT,
  visibility        TEXT,
  visibility_source TEXT,
  storage_class     TEXT,
  branch_count      INT,
  guard             TEXT,
  confidence        TEXT,
  lang              TEXT,
  extractor         TEXT NOT NULL,
  snapshot          TEXT NOT NULL,
  PRIMARY KEY (id, file, start_line, extractor, snapshot));

CREATE TABLE refs(
  src_id       TEXT,
  dst_id       TEXT,
  dst_expr     TEXT,
  kind         TEXT NOT NULL,
  dispatch     TEXT,
  guard        TEXT,
  lambda_depth INT,
  file         TEXT NOT NULL,
  start_line   INT  NOT NULL,
  start_col    INT  NOT NULL,
  end_line     INT  NOT NULL,
  end_col      INT  NOT NULL,
  status       TEXT,
  reason       TEXT,
  confidence   TEXT,
  lang         TEXT,
  extractor    TEXT NOT NULL,
  snapshot     TEXT NOT NULL,
  PRIMARY KEY (file, start_line, start_col, end_line, end_col, kind, extractor, snapshot));

CREATE TABLE comments(
  file          TEXT NOT NULL,
  start_line    INT  NOT NULL,
  start_col     INT  NOT NULL,
  end_line      INT,
  end_col       INT,
  kind          TEXT,
  source_kind   TEXT,
  attached_id   TEXT,
  attached_line INT,
  marker        TEXT,
  text          TEXT,
  guard         TEXT,
  confidence    TEXT,
  lang          TEXT,
  extractor     TEXT NOT NULL,
  snapshot      TEXT NOT NULL,
  PRIMARY KEY (file, start_line, start_col, extractor, snapshot));
```

---

## 4. 列の定義

### 4.1 `analysis_run`

**単位は「(言語, 実行)」。** `extractor` は言語ごとの値なので、1回の実行が言語の数だけ行グループを持つ。
設定値は言語の数だけ重複するが、A-3 が全テーブルに3列を持たせたのと同じ性質の冗長。

`(extractor, snapshot)` は**行グループを選ぶジョインキー**であり、外部キー制約ではない。
**このテーブルだけ `lang` を持たない**（実行が多言語にまたがるため。A-3 の明示的な例外）。

| `key` | 値 | 繰り返し |
|---|---|---|
| `repo_name` | `symbols.root` と一致する文字列 | |
| `root` | 解析対象のルートパス | |
| `boundary_level` | `0`（既定）/ `1`（追加ソースツリー）/ `2`（システムヘッダ）/ `3`（ビルドコンテキスト） | |
| `extra_root` | `<repo-name>=<パス>` | **あり** |
| `closed_world` | `true` / `false` | |
| `stdlib_dict` | 辞書名＋版（`c99` / `posix` …） | **あり** |
| `tool_version` | `<パッケージ>=<版>` | **あり** |
| `config` | フル版＝構成識別子／簡易版＝`all_branches` | |
| `git_state` | `full` / `shallow` / `none` | |
| `scan_mode` | `full` / `incremental` | |
| `started_at` | ISO 8601 **UTC**（末尾 `Z`） | |
| `extractor_status` | `ok` / `failed` / `partial` | |
| `error_message` | 文字列 | |
| `load_errors` | 主キー衝突件数（取り込み後にローダーが追記） | |

**入力（設定）＋ `files` から導出できない実行結果だけを持つ。** ERROR を含むファイルの有無などは `files` から数える。

### 4.2 `files`

| 列 | 値域・規約 |
|---|---|
| `file` | ルートからの相対パス。**区切りは `/` に正規化**（Windows の `\` は同じファイルを別行にする） |
| `lang` | **検出した言語名をそのまま**（`c` / `cs` / `go` / `ruby` / `sh` …）＋ `unknown`。抽出器の有無は背負わない |
| `extract_status` | `extracted` / `skipped_no_extractor` / `skipped_binary` / `skipped_ignored` / `failed` |
| `lines` | 物理行数。最終行に改行が無くても1行。空ファイルは 0。CRLF / LF で同じ値 |
| `comment_lines` | **コメントだけの行**。コードとコメントが同じ行にあればコード行 |
| `parse_errors` / `missing_nodes` | tree-sitter の ERROR / MISSING ノード数（libclang は診断数 / 0） |
| `error_lines` | **ERROR / MISSING が覆う行数**（重複除く）。`error_ratio = error_lines / lines` は導出 |
| `content_hash` | **SHA-256 の先頭16桁**（16進小文字） |
| `confidence` | **`lang` 判定の確からしさ** |
| `extractor` | 抽出器の識別子。**抽出器を持たないファイルはオーケストレータの識別子**（例 `orchestrator-0.1`） |

**`extract_status` が `extracted` 以外の行は、整数列が NULL になりうる。** L3a は `WHERE extract_status='extracted'` で絞る。

### 4.3 `symbols`

| 列 | 値域・規約 |
|---|---|
| `id` | §2.6。**1シンボル N 行**になりうる |
| `root` | `repo-name`。**増分取り込みの削除条件に使う**（`WHERE file=? AND root=?`）。これが無いと追加ツリーの同名パスが巻き添えで消える |
| `kind` | `file` / `namespace` / `type` / `method` / `function` / `macro` / `variable` / `field`。**初版（C + C#）で出るのは前6つ** |
| `qualified_name` | 修飾名。**`kind='file'` は相対パス** |
| `container_id` | **常に埋める**（トップレベルはファイルシンボル）。**空はファイルシンボル自身のみ** |
| `file` | **`root` のルートからの相対パス**。解析対象ツリーに限り `files.file` と一致する。**外部キーではない** |
| `is_definition` | 定義なら 1。**`kind='file'` / `namespace` は 1** |
| `visibility` | `public` / `module` / `private` / `unknown`。**`kind='file'` は `module`** |
| `visibility_source` | `declaration` / `export_list` / `convention` / `linkage`。**`kind='file'` は `declaration`** |
| `storage_class` | C/C++ のみ（`static` / `extern` / `inline` …）。他言語は **`not_applicable`** |
| `branch_count` | 分岐ノードの計数（複雑度の**近似**。厳密な循環的複雑度ではない） |
| `guard` | 囲む `#if` 条件式。ネストは `&&` で連結。C 系で条件の外は**空**、Python / JS / TS は **`not_applicable`** |

### 4.4 `refs`

`calls` / `var_refs` /（未採用の）`imports` を統合した表。

| 列 | 値域・規約 |
|---|---|
| `src_id` | **囲む名前つき関数**。無名関数は `symbols` に登録しない（IDが位置ベースになり不安定なため） |
| `dst_id` | **呼び先の座標が同定できた場合**に埋める。`status='resolved'` とは**独立**（標準ライブラリは `unresolved` のまま座標が入る） |
| `dst_expr` | 元の式（`fp`、`handler->on_event`） |
| `kind` | `call` / `import` / `var_read` / `var_write` / `var_readwrite` / `var_address_of` / `var_unknown` |
| `dispatch` | **どうやって呼ぶか**（事実）。`direct` / `virtual` / `macro` / `function_pointer` / `implicit`。`kind≠'call'` は**空** |
| `status` | `resolved` / `unresolved` / `not_applicable` / `not_extracted`。**後半2値が現れる条件は現時点で無い** |
| `reason` | **なぜ解けなかったか**。`external` / `ambiguous` / `needs_type` / `needs_dataflow` / `unknown`。**`resolved` の行は空** |
| `lambda_depth` | 0 = ラムダの外、1 以上 = ネスト深さ。**常に整数** |
| `guard` | `symbols` と同じ |

**`reason` の値は「何を足せば解けるか」で分かれる。**

| 値 | 何を足せば解けるか |
|---|---|
| `external` | 解析範囲を広げる（`boundary_level`） |
| `ambiguous` | シグネチャ等の識別子 |
| `needs_type` | 型解決 |
| `needs_dataflow` | データフロー解析（どの関数が代入されたか） |
| `unknown` | 不明 |

### 4.5 `comments`

「コメント構文」ではなく「**人が書いた説明**」の器。Python の docstring も同じテーブルに入る。

| 列 | 値域・規約 |
|---|---|
| `kind` | `doc` / `file_header` / `inline` / `block` |
| `source_kind` | `comment` / `string_literal`（**Python の docstring は `comment` ノードに入らない**） |
| `attached_id` | 説明対象のシンボルID。**`kind='doc'` のときのみ** |
| `attached_line` | 説明対象の `symbols.start_line`。**`kind='doc'` のときのみ**。これが無いと同じ id の複数行に結合して増殖する |
| `marker` | `TODO` / `FIXME` / `HACK` / `XXX` / `NOTE` / `WARNING` / `AUTO_GENERATED` / 空 |

結合は `comments.(attached_id, file, attached_line)` = `symbols.(id, file, start_line)`。

---

## 5. 主キー一覧

| テーブル | 主キー |
|---|---|
| `analysis_run` | `(extractor, snapshot, key, seq)` |
| `files` | `(file, extractor, snapshot)` |
| `symbols` | `(id, file, start_line, extractor, snapshot)` |
| `refs` | `(file, start_line, start_col, end_line, end_col, kind, extractor, snapshot)` |
| `comments` | `(file, start_line, start_col, extractor, snapshot)` |

**`refs` に `kind` と終了位置が必要な理由**: `p->f()` は呼び出しと `p` の変数読み取りが同じ位置から始まる。
`f(x)(y)`（カリー化呼び出し）は外側と内側が同じ位置から始まる。

**複数の抽出器の結果を1つの DB に混ぜることは既定としない。** ただし主キーは混在に耐える形にしてある。

---

## 6. `confidence` の決め方

値域は `high` / `medium` / `low`。**数値（0.0〜1.0）は採らない**（根拠のない小数を書くことになるため）。
対象は「**その行が主張することのうち、最も弱い判断**」。

| テーブル | `high` | `medium` | `low` |
|---|---|---|---|
| `files` | 拡張子で `lang` が一意 | `.h` など複数言語がありうる拡張子 | 内容から推測 |
| `symbols` | ERROR 無しのファイル、かつ `visibility_source` が `declaration` / `export_list` / `linkage` | `visibility_source='convention'`、または**範囲内に ERROR がある** | 範囲内の ERROR が支配的 |
| `refs`（`resolved`） | 名前解決由来（フル版） | **閉世界仮定つきの演繹**、`dispatch='macro'` | 名前一致の推測（**L0 では出さない**） |
| `refs`（`unresolved`） | `ambiguous` / `needs_type` / `needs_dataflow` | `external` かつリポジトリ内に ERROR を含むファイルがある | `unknown` |
| `comments` | 明示的な doc 記法（`///` / `/**` / docstring） | 隣接しているだけ | ERROR ノードと同じ行／隣接行 |

**`symbols` の基準は範囲全体**（`branch_count` が本体由来のため）。

**閉世界仮定の破れ**: 条件コンパイルによる分岐（`dst_id` が複数行にマッチ）と `##` によるマクロ生成は検出でき、`low` に下げる。
**ビルドから除外されたファイルの同名定義は検出できない。** これは閉世界仮定そのものの限界であり、`analysis_run.closed_world` の注記で扱う。

**欠落は `confidence` では表現できない。** 括弧の不均衡でシンボルが1つも取れなかった場合、
下げる対象の行が存在しない。**欠落は `files.error_lines` で表し、レポートにファイル単位で列挙する。**

---

## 7. L0 → L1 取り込み

### 7.1 L0 の配置

```
facts/raw/
  run.tsv                        ← 実行単位。オーケストレータが書く。メタ情報行を持たない
  src/foo/bar.c.files.tsv
  src/foo/bar.c.symbols.tsv
  src/foo/bar.c.refs.tsv
  src/foo/bar.c.comments.tsv
```

ソースファイル単位の TSV は1行目が `#` で始まるメタ情報行（`snapshot` / `extractor` / `lang` を1回だけ書く）。
**`run.tsv` だけは例外で、メタ情報行を持たない**（内容自体がメタ情報であり、`snapshot` / `extractor` をデータ行として持つため）。

### 7.2 手順

```
1. ツリーを全走査し、files を毎回作り直す
2. 変更されたファイルについて:
     DELETE FROM T WHERE file = X                      -- symbols は AND root = <解析対象>
     INSERT INTO T ...
3. 消えたファイルを掃除する:
     DELETE FROM T WHERE file NOT IN (今回の files)
4. run.tsv を analysis_run へ。load_errors を追記
```

**3 が無いと、削除されたファイルの行が残り続ける**（概観レポートが存在しないファイルを数える）。
**2 の `root` 条件が無いと、追加ソースツリーの同名パスが巻き添えで消える。**

### 7.3 衝突の扱い

**`INSERT OR IGNORE` / `INSERT OR REPLACE` を使わない。** 素の `INSERT` で衝突させ、エラーにする。
件数を `analysis_run.load_errors` に記録し、レポートに出す。

> **主キーの役割は衝突を防ぐことではなく、検出して報せることである。**
> 静かに捨てると、シンボルの 17.7% が消えていても図は綺麗に出る。

### 7.4 既知の限界

`foo.c` のシンボルを変更しても、`bar.c` から `foo.c` を呼んでいる `refs` 行の `status` / `reason` は
**`bar.c` 自体を再抽出しない限り古いまま**になる。依存グラフの追跡は現時点で対象外。

---

## 8. L2（本文書の対象外）

**置き場所は `derived/db.sqlite`。** L1 を `ATTACH` して作る。
L1 は不変、L2 は再生成可能でライフサイクルが違うため、ファイルを分ける（捨てて作り直すのが `rm` 1回で済む）。

| 導出 | 規則 |
|---|---|
| `symbol_canonical` | 定義1つ＝正規／定義0＝宣言を正規／**定義複数＝畳まず `multiple_definitions`** |
| 到達可能性 | 既定は `lambda_depth` を問わず含める。**除いた版との差分**を「コールバック経由でのみ到達する範囲」として示す |
| 名前一致による結線 | **L0 では線を引かない。** L2 / L3a の「推測モード」として利用者が明示的に有効化する |

**`multiple_definitions` は異常ではなく事実。** `namespace` と `partial` 型は正常に複数行になる。

---

## 9. 検証

**本文書の DDL は実行して検証されている。**

```sh
python3 tools/schema-check/verify_schema.py
```

`SCHEMA.md` から DDL を抜き出して SQLite に流し、以下を確認する。

1. DDL が通る
2. **主キー列に NULL を入れると拒否される**（§2.1 が効いている）
3. `comments` の結合が `attached_line` 込みで正しい件数を返す（§2.5）
4. 5レポートの中核クエリが動く
5. `ATTACH` して `extractor` で絞ると二重計上しない（§2.4）

---

## 10. 根拠の所在

| 知りたいこと | 参照先 |
|---|---|
| 列ごとの決定の連鎖（どの決定が何を定めたか） | `SCHEMA_INDEX.md` |
| なぜそう決めたか | `OPEN_DECISIONS.md` の「決定事項」 |
| L0 の中間ファイル形式の詳細 | [構想] §7.6 |
| 層分離のルール | [構想] §7.3 |
| 「不確かさを黙って隠さない」という原則 | [構想] §2.3 |
