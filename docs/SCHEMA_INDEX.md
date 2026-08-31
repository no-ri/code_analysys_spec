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
| `bytes` | INT | **NULL = 未測定** | F-5 → **L-1**（J-2 のリストに追加。`skipped_binary` は NULL） |
| `lines` | INT。物理行数。最終行に改行が無くても1行。空ファイルは 0 | **NULL = 未測定** | F-5 → **L-1**（同上。`skipped_binary` は行数が無意味なので NULL） |
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
| `qualified_name` | TEXT。**`kind='file'` は相対パス** | | F-1 決定4 → **L-2** |
| `container_id` | TEXT。**常に埋める**。空はファイルシンボル自身のみ | | §3.1 ⛔ E-1 → **G-1 で解決** |
| `file` | TEXT。**`root` のルートからの相対パス** | NOT NULL | G-3 → **H-2**（解析対象ツリーに限り `files.file` と一致。外部キーではない） |
| `start_line` | INT | NOT NULL | F-3 決定1 / 決定2 |
| `start_col` / `end_line` / `end_col` | INT | | F-3 決定1 / 決定2 |
| 位置の範囲 | **宣言・定義全体**（修飾子・属性を含む先頭から本体の閉じ括弧まで） | | **G-4** |
| `is_definition` | INT。**`kind='file'` / `namespace` は 1**（ファイルも名前空間宣言も実在する） | | F-1 決定4 → **L-2 / L-3** |
| `visibility` | `public` / `module` / `private` / `unknown`。**`kind='file'` は `module`**（ファイルの外から名前で参照されない） | | §3.1.4 → **L-2** |
| `visibility_source` の `kind='file'` | **`declaration`**（ファイルの存在そのものが宣言） | | **L-5**（L-2 の副作用として判明） |
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
**対象**: 解析対象ツリーのみ — F-5 決定5
**`root` 列を持たない理由**: F-5 決定5 により `refs` / `comments` / `files` は**解析対象ツリーだけ**を載せるので `root` は常に一定。
`symbols` にだけ `root` があるのは、**追加ソースツリーの行が混在するから**（I-2。増分 `DELETE` の巻き添えを防ぐ）— **L-4**

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
| `resolved_by` | `same_file_static` / `unique_in_repo` / `same_container` / `declared_type` / `type_name_static` / `self_receiver` / `macro` / `stdlib_dict` / `not_resolved` | | **F-16 決定4**（規則ごとに的中率が 25〜100% とばらけたため。`confidence` はこの値ごとに決める） |
| `confidence` | `high` / `medium` / `low` | | A-2 → E-4 決定3 → **F-6 決定3**（`unresolved` 行は `reason` の確からしさ。`ambiguous`＝`high`）→ **F-16 決定4**（②-a 一律 `medium` を廃し、`resolved_by` ごとに決める） |
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

## 5.5 `confidence` の決め方（全テーブル）— **L-6 で索引に追加**

値域は `high` / `medium` / `low`（A-2。**数値は採らない**）。**対象は「その行の主張のうち最も弱い判断」**（F-6 決定2、H-3 で「この行が主張する全項目」に拡張）。

| テーブル | `high` | `medium` | `low` |
|---|---|---|---|
| `files` | 拡張子で `lang` が一意 | `.h` など複数言語がありうる拡張子 | 内容から推測 |
| `symbols` | ERROR 無しのファイル、かつ `visibility_source` が `declaration` / `export_list` / `linkage` | `visibility_source = convention`、または**範囲内に ERROR がある** | 範囲内の ERROR が支配的 |
| `refs`（`resolved`） | フル版の名前解決由来 | **②-a**（閉世界仮定つきの演繹）、`dispatch = macro` | ②-b（**L0 では出さない**） |

> **F-16 決定4 による改訂（2026-08-31）**: 上の「②-a はすべて `medium`」は**実測で否定された**。
> 的中率は規則によって **25% 〜 100%** とばらける。**`confidence` は `resolved_by` ごとに決める。**
>
> | `resolved_by` | F-16 の実測的中率 | `confidence` |
> |---|---|---|
> | `same_file_static` / `unique_in_repo` | 100%（C 50/50、C# 4/4） | `medium` |
> | `type_name_static` | 95%（19/20） | `medium` |
> | `same_container` | 80%（16/20） | `medium` |
> | `declared_type` | **25%（5/20）** | **`low`** |
> | `self_receiver` | **0%（2/2、全数）** | **決定3 で実装を修正。修正後に測り直す** |
>
> **オーバーロードのある呼び出しは `resolved` にしない**（`unresolved` / `ambiguous`）。
> 誤りの 22 件中 20 件がオーバーロードの取り違えだったため。
| `refs`（`unresolved`） | `ambiguous` / `needs_type` / `needs_dataflow` | `external` かつリポジトリ内に ERROR を含むファイルがある | `unknown` |
| `comments` | 明示的な doc 記法（`///` / `/**` / docstring） | 隣接しているだけ | ERROR ノードと同じ行／隣接行 |

**`symbols` の基準行は「範囲全体」**（H-3。`branch_count` が本体由来のため）。F-6 決定4 の「同じ行／隣接行」は H-3 が上書きした。

**②-a の破れ**: 条件コンパイルによる分岐（`dst_id` が複数行にマッチ）と `##` によるマクロ生成は検出でき、`low` に下げる。
**ビルド除外ファイルの同名定義は検出できない**（軸2 = ゼロの帰結）— F-6 決定5

**`confidence` 単独でフィルタしない。** `WHERE status='resolved' AND confidence='high'` と組にする — F-6 決定3

---

## 6. L2（`SCHEMA.md` の対象外。一覧のみ）

**置き場所**: `derived/db.sqlite`（L1 を `ATTACH` して作る）— K-4
**`SCHEMA.md` は L1 のみを正本とする** — K-3

| 導出 | 規則 | 出典 |
|---|---|---|
| `symbol_canonical` | 定義1つ＝正規／定義0＝宣言を正規／**定義複数＝畳まず `multiple_definitions`** | F-13③ |
| ↑ の注意 | **`namespace` と `partial` 型は正常に複数行になる。** `multiple_definitions` は**異常ではなく事実**であり、`#ifdef` の両枝と同じ扱い | **L-7**（L-3 の副作用として判明） |
| 到達可能性（推移閉包） | 既定は `lambda_depth` を問わず含める。**除いた版との差分**を「コールバック経由でのみ到達する範囲」として示す | K-5 |
| 名前一致による結線（②-b） | **L0 では線を引かない**。L2 / L3a の「推測モード」 | E-3 |

---

## 7. 空白セルの解消（2026-08-27）

| # | 箇所 | 決定 |
|---|---|---|
| **L-1** | `files.bytes` / `files.lines` | **NULL 許容にする**（J-2 のリストに追加）。`skipped_binary` は両方 NULL |
| **L-2** | `symbols` の `kind='file'` | `qualified_name` = 相対パス／`is_definition` = 1／`visibility` = `module` |
| **L-3** | `symbols` の `kind='namespace'` | `is_definition` = 1（C# の名前空間宣言は定義とみなす） |
| **L-4** | `refs` に `root` が無い | F-5 決定5 により解析対象ツリーだけを載せるので常に一定。**`symbols` にだけ必要な理由**（I-2）を明記 |

### 更新後の再点検で出たもの（**更新そのものが生んだ**）

| # | 箇所 | 決定 |
|---|---|---|
| **L-5** | `symbols.visibility_source` の `kind='file'` | **`declaration`**。L-2 で `visibility` を決めたが**由来を決め忘れていた** |
| **L-6** | 索引に `confidence` の決め方が無かった | F-6 決定4 の表と H-3 の上書きを **§5.5 として索引に取り込んだ**。値域だけでは `SCHEMA.md` を書けない |
| **L-7** | `symbol_canonical` の `multiple_definitions` | **`namespace` と `partial` 型は正常に複数行になる。** 異常ではなく事実であることを注記（L-3 で名前空間を `is_definition = 1` にした副作用） |

**⚠ 空白セル: 0 件 ／ ⛔ 矛盾セル: 0 件** — `SCHEMA.md` を書ける状態になった。
