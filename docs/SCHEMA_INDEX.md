# スキーマ索引 — 決定の追跡表

**作成日**: 2026-08-27
**目的**: `SCHEMA.md` を書く前に、**列ごとに「どの決定が何を定めたか」を1箇所に並べる**。
**役割**: `SCHEMA.md` の入力。空白セル（未定）と矛盾セルがゼロになったら `SCHEMA.md` を書く。

> ## なぜ索引を先に作るか
>
> `reason` の値域は **A-1 → F-2 → H-5 → I-3** と4回、`refs` の主キーは **F-3 → F-1 → H-6** と3回
> 書き換わっており、**最終形がどこにも書かれていない**。決定事項を読むだけでは、4箇所を頭の中で
> 合成しないと現在の姿が分からない。
>
> この状態で `SCHEMA.md` を書くと「列定義が書かれた6箇所目」になり、F-8（F-1 のテーブル一覧が古い）
> と同じ腐り方をする。**索引で合成を先に済ませ、抜けと食い違いを機械的に洗い出す。**
>
> **この索引が保証しないもの**: 「決定どおり書いたのに動かない」（J-1 の `NOT NULL`、K-1 の JOIN、
> K-2 の `ATTACH` はすべてこの形だった）。それは `SCHEMA.md` の DDL を `tools/schema-check/` で
> **実行して**確かめる。

**凡例**: 空欄なし＝決定済み ／ **⚠ 未定**＝空白セル ／ **⛔ 矛盾**＝食い違い

---

## 0. 全テーブル共通

| 項目 | 決定 | 出典 |
|---|---|---|
| `lang` / `extractor` / `snapshot` | **全テーブルに持たせる**（`analysis_run` を除く） | A-3 |
| `analysis_run` の例外 | **`lang` を持たない**（実行が多言語にまたがる） | G-9 |
| 主キー列 | **すべて `NOT NULL` を明示**。SQLite の主キーは NOT NULL を含意しない | J-1 |
| 位置の列名 | `start_line` / `start_col` / `end_line` / `end_col` | F-3 決定1 |
| 位置の起点・端点・単位 | **1 起点**／`end` は**排他**／`col` は**文字数**（Unicode コードポイント） | F-3 決定2 |
| 「空」と `not_applicable` | 空＝**その行に該当しない**／`not_applicable`＝**その言語に概念が無い** | §7.6, G-7 |
| 整数列の未測定 | **NULL = 未測定**（「数えた 0」と区別する必要がある列のみ） | J-2 |
| 集計クエリ | **必ず `extractor` で絞る**（`ATTACH` 時の二重計上を防ぐ） | K-2 |
| `id` での結合 | `src_id` / `container_id` は**位置の包含**／`dst_id` は `refs` 側で集計／`attached_id` は `attached_line` | K-1 |
| 時刻 | **UTC**（`started_at` は末尾 `Z`、B-4 の `nogit-` も UTC） | I-7 |

---

## 1. `analysis_run`（縦持ち）

**主キー**: `(extractor, snapshot, key, seq)` — H-1
**`(extractor, snapshot)` はジョインキー**（外部キー制約ではない）— H-1
**単位**: 「**(言語, 実行)**」。設定値は言語の数だけ重複する — H-1

| 列 | 型 / 値域 | NULL | 決定の連鎖 |
|---|---|---|---|
| `extractor` | TEXT | NOT NULL | F-4 → H-1（言語の単位）→ J-1（抽出器が無い場合はオーケストレータ識別子） |
| `snapshot` | TEXT | NOT NULL | B-4 → I-7（UTC） |
| `key` | TEXT | NOT NULL | G-10 |
| `value` | TEXT | | G-10 |
| `seq` | INT | NOT NULL | G-10（繰り返しキーの順序） |

### `key` の値域

| キー | 値 | 繰り返し | 出典 |
|---|---|---|---|
| `repo_name` | 文字列（`symbols.root` と一致） | | I-6 |
| `root` | 解析対象のルートパス | | F-4 |
| `boundary_level` | `0` / `1` / `2` / `3` | | F-4（E-3 の「つまみ」） |
| `extra_root` | `<repo-name>=<パス>` | **あり** | F-4 |
| `closed_world` | `true` / `false` | | F-4 |
| `stdlib_dict` | 辞書名＋版（`c99` / `posix` …） | **あり** | F-4 |
| `tool_version` | `<パッケージ>=<版>` | **あり** | F-4 |
| `config` | フル版＝構成識別子／簡易版＝`all_branches` | | F-13② |
| `git_state` | `full` / `shallow` / `none` | | F-5 決定1 |
| `scan_mode` | `full` / `incremental` | | J-4 |
| `started_at` | ISO 8601 UTC（末尾 `Z`） | | I-7 |
| `load_errors` | 主キー衝突件数 | | F-4, G-11 |
| `extractor_status` | `ok` / `failed` / `partial` | | J-3 |
| `error_message` | 文字列 | | J-3 |

---

## 2. `files`

**主キー**: `(file, extractor, snapshot)` — F-3 決定3
**対象**: **解析対象ツリーのみ**（追加ソースツリーは載せない）— F-5 決定5
**取り込み**: **毎回全走査で作り直す**。`file NOT IN (今回の files)` を他テーブルから削除 — J-4

| 列 | 型 / 値域 | NULL | 決定の連鎖 |
|---|---|---|---|
| `file` | TEXT。ルートからの相対パス、区切りは `/` に正規化 | NOT NULL | F-5 決定2（`path`→`file` は F-3 決定6） |
| `lang` | TEXT。**検出した言語名そのまま** ＋ `unknown` | | F-5 → **I-4**（7値では Go/Ruby/sh が丸められる） |
| `extract_status` | `extracted` / `skipped_no_extractor` / `skipped_binary` / `skipped_ignored` / `failed` | | F-5 決定2 |
| `bytes` | INT | **⚠ 未定** | F-5（未測定ケースの扱いが J-2 の対象外） |
| `lines` | INT。物理行数。最終行に改行が無くても1行。空ファイルは 0 | **⚠ 未定** | F-5（同上。`skipped_binary` で行数は無意味） |
| `comment_lines` | INT。**コメントだけの行** | **NULL = 未測定** | F-5 → J-2 |
| `blank_lines` | INT | **NULL = 未測定** | F-5 → J-2 |
| `parse_errors` | INT。ERROR ノード数 | **NULL = 未測定** | E-3 → F-5 → J-2 |
| `missing_nodes` | INT。MISSING ノード数（libclang は 0） | **NULL = 未測定** | F-5 → J-2 |
| `error_lines` | INT。ERROR / MISSING が覆う行数（重複除く） | **NULL = 未測定** | **F-6 決定1** → J-2 |
| `content_hash` | TEXT。SHA-256 の先頭16桁（16進小文字） | | F-5 → I-7 |
| `git_commits` | INT | **NULL = 未測定** | F-5 → J-2 |
| `git_authors` | INT | **NULL = 未測定** | F-5 → J-2 |
| `git_last_modified` | TEXT | **NULL = 未測定** | F-5 → J-2 |
| `confidence` | `high` / `medium` / `low`。**`lang` 判定の確からしさ** | | F-5 → F-6 決定2 / 決定4 |
| `extractor` | TEXT | NOT NULL | J-1（抽出器が無いファイルはオーケストレータ識別子） |
| `snapshot` | TEXT | NOT NULL | B-4 |

**同じ行にコードとコメント** → コード行として数える。`comment_lines` はコメントだけの行 — F-5

---

## 3. `symbols`

**主キー**: `(id, file, start_line, extractor, snapshot)` — F-3 決定4 →（暫定）→ **F-13③ で確定**
**1シンボル N 行**。正規化は **L2 の `symbol_canonical`** — F-13③

| 列 | 型 / 値域 | NULL | 決定の連鎖 |
|---|---|---|---|
| `id` | TEXT。`local <repo-name> <version欄> <descriptor>` | NOT NULL | B-1 → §3.2.2（**シグネチャ必須**）→ **I-1（`snapshot` を外す）** → I-8（5欄） |
| `root` | TEXT。`repo-name` | NOT NULL | **I-2**（増分 `DELETE` の巻き添えを防ぐ） |
| `kind` | `file` / `namespace` / `type` / `method` / `function` / `macro` / `variable` / `field` | | §3.1 → **I-5**（`...` を閉じた。初版で出るのは前6つ） |
| `name` | TEXT | | §3.1 |
| `qualified_name` | TEXT | **⚠ 未定** | F-1 決定4（残すと決めたが、`kind='file'` の値が未定） |
| `container_id` | TEXT。**常に埋める**。空はファイルシンボル自身のみ | | §3.1 ⛔ E-1 → **G-1 で解決** |
| `file` | TEXT。**`root` のルートからの相対パス** | NOT NULL | G-3 → **H-2**（解析対象ツリーに限り `files.file` と一致。外部キーではない） |
| `start_line` | INT | NOT NULL | F-3 決定1 / 決定2 |
| `start_col` / `end_line` / `end_col` | INT | | F-3 決定1 / 決定2 |
| 位置の範囲 | **宣言・定義全体**（修飾子・属性を含む先頭から本体の閉じ括弧まで） | | **G-4** |
| `is_definition` | INT | **⚠ 未定** | F-1 決定4（`kind='file'` / `namespace` の値が未定） |
| `visibility` | `public` / `module` / `private` / `unknown` | **⚠ 未定** | §3.1.4（`kind='file'` の値が未定） |
| `visibility_source` | `declaration` / `export_list` / `convention` / `linkage` | | §3.1.4, E-1 |
| `storage_class` | C/C++ のみ。他言語は `not_applicable` | | §3.1.4 |
| `branch_count` | INT | **NULL = 未測定** | E-1 → F-1 決定4 → J-2 |
| `guard` | TEXT。`#if` 条件式。ネストは `&&` 連結 | | **F-13②** → G-7（C系で条件外＝空／Python・JS・TS＝`not_applicable`） |
| `confidence` | `high` / `medium` / `low`。**範囲全体**を基準 | | A-2 → F-6 決定2 / 決定4 → **H-3**（対象は「この行が主張する全項目」） |
| `lang` / `extractor` / `snapshot` | | NOT NULL（後2つ） | A-3, J-1 |

---

## 4. `refs`

**主キー**: `(file, start_line, start_col, end_line, end_col, kind, extractor, snapshot)` — F-3 決定3
**統合**: `calls` / `var_refs` /（未採用の）`imports` を1表に — F-1 決定1
**対象**: 解析対象ツリーのみ — F-5 決定5 → **⚠ `symbols` と違い `root` 列を持たない理由が未記載**

| 列 | 型 / 値域 | NULL | 決定の連鎖 |
|---|---|---|---|
| `src_id` | TEXT。**囲む名前つき関数**（ラムダは `symbols` に登録しない） | | E-1 → F-1 決定2（`caller_id`→`src_id`）→ K-1（**位置の包含で結合**） |
| `dst_id` | TEXT。**呼び先の座標が同定できた場合**（`resolved` とは独立） | | F-1 決定2 → **F-4 決定2**（A-1 の文言を修正）→ K-1 |
| `dst_expr` | TEXT。元の式 | | F-1 決定2 |
| `kind` | `call` / `import` / `var_read` / `var_write` / `var_readwrite` / `var_address_of` / `var_unknown` | NOT NULL | F-1 決定1・3 → **G-6**（`var_unknown`）→ **H-6**（`address_of`→`var_address_of`） |
| `dispatch` | `direct` / `virtual` / `macro` / `function_pointer` / `implicit`。`kind≠call` は**空** | | F-1 決定3（旧 `call_kind`）→ **F-2**（「呼び方」を寄せた）→ H-5 |
| `guard` | TEXT | | F-13② → G-7 |
| `lambda_depth` | INT。**常に整数**（0＝ラムダの外）。`not_applicable` を使わない | | E-1（両論併記）→ **G-5**（bool→整数）→ **H-4** |
| `file` / `start_line` / `start_col` / `end_line` / `end_col` | | NOT NULL | F-3 |
| 位置の範囲 | **参照式全体**（`p->f(a,b)` 全体、`#include "x.h"` の行全体） | | **G-4** |
| `status` | `resolved` / `unresolved` / `not_applicable` / `not_extracted` | | A-1 → **I-3**（後半2値が現れる条件は現時点で無い、と明記） |
| `reason` | `external` / `ambiguous` / `needs_type` / `needs_dataflow` / `unknown`。`resolved` は**空** | | A-1（4値）→ E-3・E-1（3値追加）→ **F-2**（3値を `dispatch` へ移動、`needs_dataflow` 新設） |
| `confidence` | `high` / `medium` / `low` | | A-2 → E-4 決定3 → **F-6 決定3**（`unresolved` 行は `reason` の確からしさ。`ambiguous`＝`high`） |
| `lang` / `extractor` / `snapshot` | | NOT NULL（後2つ） | A-3 |

---

## 5. `comments`

**主キー**: `(file, start_line, start_col, extractor, snapshot)` — F-3 決定3
**対象**: 解析対象ツリーのみ — F-5 決定5

| 列 | 型 / 値域 | NULL | 決定の連鎖 |
|---|---|---|---|
| `file` / `start_line` / `start_col` | | NOT NULL | F-3 決定3（`col` は G-8 の反例で必須と判明） |
| `end_line` / `end_col` | INT | | F-3 決定1 |
| 位置の範囲 | コメント（または docstring リテラル）全体 | | G-4 |
| `kind` | `doc` / `file_header` / `inline` / `block` | | §3.1.6, E-1 |
| `source_kind` | `comment` / `string_literal` | | E-1（Python の docstring はコメントではない） |
| `attached_id` | TEXT。**`kind='doc'` のときのみ** | | §3.1.6 → **H-9** |
| `attached_line` | INT。説明対象の `symbols.start_line`。**`kind='doc'` のときのみ** | | **G-8**（`(attached_id, file)` は一意にならない）→ H-9 |
| `marker` | `TODO` / `FIXME` / `HACK` / `XXX` / `NOTE` / `WARNING` / **`AUTO_GENERATED`** / 空 | | §3.1 → **F-5 決定4**（`AUTO_GENERATED` 追加） |
| `text` | TEXT | | §3.1.6 |
| `guard` | TEXT | | F-13② → G-7 |
| `confidence` | 明示的な doc 記法＝`high` ／ 隣接だけ＝`medium` ／ ERROR と同じ行・隣接行＝`low` | | E-1 → §3.1.6 → F-6 決定4 |
| `lang` / `extractor` / `snapshot` | | NOT NULL（後2つ） | A-3 |

---

## 6. L2（`SCHEMA.md` の対象外。一覧のみ）

**置き場所**: `derived/db.sqlite`（L1 を `ATTACH` して作る）— K-4
**`SCHEMA.md` は L1 のみを正本とする** — K-3

| 導出 | 規則 | 出典 |
|---|---|---|
| `symbol_canonical` | 定義1つ＝正規／定義0＝宣言を正規／**定義複数＝畳まず `multiple_definitions`** | F-13③ |
| 到達可能性（推移閉包） | 既定は `lambda_depth` を問わず含める。**除いた版との差分**を「コールバック経由でのみ到達する範囲」として示す | K-5 |
| 名前一致による結線（②-b） | **L0 では線を引かない**。L2 / L3a の「推測モード」 | E-3 |

---

## 7. 空白セル（`SCHEMA.md` を書く前に埋める）

| # | 箇所 | 未定の内容 |
|---|---|---|
| **1** | `files.bytes` / `files.lines` | `skipped_binary` のとき行数は無意味。J-2 の NULL 許容リストに入っていない |
| **2** | `symbols` の `kind='file'` 行 | `qualified_name` / `is_definition` / `visibility` の値が未定 |
| **3** | `symbols` の `kind='namespace'` 行 | `is_definition` の意味が未定（名前空間に「定義」はあるか） |
| **4** | `refs` に `root` が無い | `symbols` にだけ `root` を足した（I-2）理由と、`refs` に不要な理由が未記載 |

**⛔ 矛盾セル: 0 件**（`container_id` の §3.1 ⇔ E-1 は G-1 で解決済み）
