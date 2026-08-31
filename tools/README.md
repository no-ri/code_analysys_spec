# tools

構想・仕様リポジトリだが、環境確認だけは実際に動くスクリプトとして置いておく。
判定内容の根拠はすべて `docs/CODE_ANALYSIS_CONCEPT.md` §9.3。

| ファイル | 対象 | 実行方法 |
|---|---|---|
| **`schema-check/verify_schema.py`** | **`SCHEMA.md` の DDL を実行して検証** | `python3 tools/schema-check/verify_schema.py` |
| **`schema-check/verify_docs.py`** | **文書間の参照が壊れていないか検証** | `python3 tools/schema-check/verify_docs.py` |
| `schema-check/record-*.py` | J 群 / K 群の実測の出典（使い捨ての記録） | 下記 |
| `full-version/check-env.sh` | Linux / WSL（**フル版用**） | `bash tools/full-version/check-env.sh [--nuget]` |
| `full-version/check-env.ps1` | Windows（**フル版用**） | `powershell -ExecutionPolicy Bypass -File tools\full-version\check-env.ps1 [-NuGet]` |
| `measure-resolvability.py` | 簡易版の検討（E-3） | 下記「解決可能性の測定」 |
| `measure-csharp-receivers.py` | 同上（C# の追加測定） | 同上 |
| `emit-generic-schema.py` | 簡易版の検討（E-1） | 同上 |
| `measure-improvements.py` | 同上（改良の効果測定） | 同上 |
| `measure-count-rules.py` | 数字の食い違いの説明（F-12） | 下記「記述で決めていたことを測り直す」 |
| `measure-csharp-forecast.py` | 見込みと実測の差の追跡（F-11） | 同上 |
| `measure-component-deps.py` | レポート4 が C# で成立するか（F-10） | 同上 |
| `sample-golden.py` | **②-a の的中率を人手検証するための標本抽出（F-16）** | 下記「②-a の的中率の検証」 |

> `check-env.*` は**フル版**用（§9.3）。**2026-08-27 に `tools/full-version/` へ退避した。**`measure-*.py` は**簡易版**の検討で使った測定スクリプトで、
> 前提が違う（ビルドを一切必要としない）。混同しないこと。

**Phase 1 は C#**（§10.1 で C/C++ と順序を入れ替えた）。`dotnet` / `git` / `python3` が揃っていれば始められる。

## 見方

| 表示 | 意味 |
|---|---|
| `[OK]` | 導入済み |
| `[NG]` | **必須なのに未導入**。解消が必要 |
| `[--]` | 任意、または後続 Phase 用。Phase 1 を始めるだけなら無くてよい |

終了コードは NG の件数（0 なら Phase 1 を開始できる）。

## NuGet の実復元テスト

`--nuget` / `-NuGet` を付けると、一時プロジェクトを作って Roslyn パッケージを実際に `dotnet restore` する。
数十秒かかるため既定では実行しない。**フィード設定を見るだけでは疎通は分からない**ので、
社内プロキシ環境などで確実を期すときに使う（§9.3.2）。

## 単なる有無確認ではない項目

コマンドの存在確認だけでは分からない、実際に動くかどうかを確認している。

- **Clang 組み込みヘッダ** — `clang -print-resource-dir` の下に `stddef.h` があるか（§9.3.4）
- **実パース通し確認** — `#include <stdio.h>` を含むファイルを libclang で実際にパースし、致命的エラーが出ないか
- **compile_commands.json 生成** — 小さな CMake プロジェクトを実際に configure して生成されるか（§4.3、Phase 2 用）
- **NuGet フィード設定** — `nuget.org` が有効なフィードとして登録されているか（§9.3.2）

## Windows 固有の注意

- **`cl.exe` は「Developer PowerShell for VS」から実行しないと PATH に現れない**。通常の PowerShell で C コンパイラが未検出になった場合は、そちらから再実行すること
- **`CMAKE_EXPORT_COMPILE_COMMANDS` は Visual Studio ジェネレータでは機能しない**とされる。スクリプトは ninja があれば `-G Ninja` を使う。**この挙動は Windows 実機で未検証**
- Python は `python` と `py` の2系統があるため、両方を探索する


## 解決可能性の測定（簡易版の検討用）

`docs/OPEN_DECISIONS.md` の E-3 に載せた実測値を再現するためのスクリプト。
**tree-sitter の構文木だけ**を入力とし、ビルドは一切行わない（＝軸2 = ゼロの条件）。

```sh
python3 -m venv .venv
.venv/bin/pip install tree-sitter tree-sitter-language-pack

mkdir targets && cd targets
for r in DaveGamble/cJSON commonmark/cmark leethomason/tinyxml2 \
         psf/requests tj/commander.js FluentValidation/FluentValidation; do
    git clone --depth 1 "https://github.com/$r" "$(basename $r)"
done
cd ..

.venv/bin/python tools/measure-resolvability.py
.venv/bin/python tools/measure-csharp-receivers.py
```

対象は §8.3 の推奨セット。`targets/` は **リポジトリに取り込まない**（§8.4 の方針）。

**この測定の限界**: 呼び出しを「その形なら解けるはず」で分類したものであり、
**正解データとの突合はしていない**。的中率の検証は別途必要（E-3 の「要実測」／F-16）。

> **この断り書きは 2026-08-31 に現実になった（F-11）。** 形の上で「解けるはず」と数えた C# の 335 件を
> 改良後の規則で追跡したところ、**実際に解けたのは 180 件（53.7%）**だった。
> **形での分類は約2倍に膨らむ。** 見込みを出すときは分母を明示し、**上限であることを書く**こと。

`emit-generic-schema.py` は **C と C# を同じ列に出せるか**を確かめるためのもの（E-1）。
設計検証用の使い捨てであり、実装の雛形ではない。
既知の未対応（C# の file-scoped namespace、シグネチャ無しの ID 衝突）は
**問題を可視化するために意図的に残してある**。


## 記述で決めていたことを測り直す（2026-08-31 追加）

F-10 / F-11 / F-12 / F-15 はいったん「記述の不整合」として注記で処理していたが、
**測れば決まる**種類だった。実際に測ったところ**4件とも結論が変わった**。

```sh
.venv/bin/python tools/emit-generic-schema.py     # facts.sqlite を作る（先に必要）
.venv/bin/python tools/measure-count-rules.py     # F-12: resolved が 53/55/56 になる理由
.venv/bin/python tools/measure-csharp-forecast.py # F-11: 見込み 335 件の着地先
.venv/bin/python tools/measure-component-deps.py  # F-10: レポート4 が C# で描けるか
```

| スクリプト | 分かったこと |
|---|---|
| `measure-count-rules.py` | 3者は **53 ⊂ 55 ⊂ 56** の包含関係で、差は**わずか3件**。「規則が違うだけ」ではなく**2つは誤り**だった（53 は C# の `base` を取りこぼし、56 はメソッドの存在確認をせず過大計上）。**正しいのは 55** |
| `measure-csharp-forecast.py` | 見込み 335 件のうち解けたのは 180 件。主因は「レシーバが型名」を**先頭が大文字かだけ**で判定していたこと（199 件中 119 件が .NET BCL の型で、`ArgumentNullException` だけで 103 件） |
| `measure-component-deps.py` | 改良後はコンポーネント間エッジが **6 本 / 97 件**立つ。E-1 の「C# では描けない」は改良前の測定だった |

**F-12 が示した実装上の教訓**: 原因は**3つのスクリプトが同じ判定を別々に書き直していた**こと。
実装では**判定規則を1箇所に置き、言語ごとに変えるのは集合の中身だけ**にする
（C# は `{this, base}`、Python は `{self, cls}`、JS は `{this, super}`）。

## ②-a の的中率の検証（F-16、2026-08-31）

②-a は `status = resolved` / `confidence = medium` を名乗るが、**正しい先を指しているかは
一度も検証されていなかった**。C と C# の両方を標本で検証した。

```sh
.venv/bin/python tools/sample-golden.py --lang c      --per-rule 25   # 人が読む形
.venv/bin/python tools/sample-golden.py --lang csharp --per-rule 20
.venv/bin/python tools/sample-golden.py --lang c --tsv > spec/golden/cjson-2a-sample.tsv
```

**規則ごとに層化抽出する。** 規則によって外し方が違い、全体の的中率より「どの規則が外すか」の方が
対策に直結するため（規則ごとに `confidence` を分けられる）。単純無作為だと少数の規則が標本に入らない。

判定結果は **`spec/golden/*.tsv`**（J-5 の突合キー `(file, start_line, start_col, kind)` ＋ `verdict`）。
対象コミットは cJSON `fb16e5c` / FluentValidation `daa00b7` に固定。

| 言語 | 標本 | 正 | 的中率 |
|---|---:|---:|---:|
| **C（cJSON）** | 50 | 50 | **100%** |
| **C#（FluentValidation）** | 66 | 44 | **66.7%** |

**C# の誤り 22 件のうち 20 件はオーバーロードの取り違え**（`SetValidator` 15件ほか）、
**2 件は `base.` を自分自身に向けたもの**。結論は `DECISIONS.md` の F-16。

> **注意**: 標本のサイズは規則ごとに 20〜25 件で、**規則Bの 25% は 95% 信頼区間で概ね 9〜49%** と幅が広い。
> 「規則Bは他より明確に低い」は言えるが、25% という点推定を確定値として扱わないこと。

## スキーマの検証（`schema-check/`）

**2つが正式な検証**で、変更のたびに走らせる。

| スクリプト | 何を保証するか |
|---|---|
| `verify_schema.py` | **`SCHEMA.md` から DDL を抜き出して実行**し、文書に書いた性質（主キーの `NOT NULL`、衝突がエラーになること、`attached_line` 込みの結合、`extractor` での絞り込み、5レポートのクエリ、索引との一致）が実際に成り立つか |
| `verify_docs.py` | 決定ID（232件）と `§N.M` とファイル名の**参照がすべて解決するか**。資料の移動・分割で参照が壊れていないことを機械的に示す |

`record-*.py` は **J 群 / K 群で「決定どおり書いたのに動かない」を見つけたときの記録**であり、
実装の雛形ではない。数字の出典として残してある。

| スクリプト | 何を見つけたか |
|---|---|
| `record-J-reports.py` | `attached_line` を外すと doc 欠落率の結合が 3 行 → 5 行に増殖する（G-8 の裏付け） |
| `record-J-operations.py` | `extractor=NULL` で主キーが素通しになる（J-1）／`0` が「0件」と「未測定」の両方を指す（J-2）／削除されたファイルの行が残る（J-4） |
| `record-K-l2-attach.py` | L2 の `symbol_canonical` と推移閉包が書けること／`ATTACH` の挙動（K 群） |
| `record-K-joins.py` | `id` での JOIN が件数を倍にする／位置の包含なら一意（K-1）／`ATTACH` の二重計上（K-2） |
