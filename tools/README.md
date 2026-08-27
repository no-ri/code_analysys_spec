# tools

構想・仕様リポジトリだが、環境確認だけは実際に動くスクリプトとして置いておく。
判定内容の根拠はすべて `docs/CODE_ANALYSIS_CONCEPT.md` §9.3。

| ファイル | 対象 | 実行方法 |
|---|---|---|
| `full-version/check-env.sh` | Linux / WSL（**フル版用**） | `bash tools/full-version/check-env.sh [--nuget]` |
| `full-version/check-env.ps1` | Windows（**フル版用**） | `powershell -ExecutionPolicy Bypass -File tools\full-version\check-env.ps1 [-NuGet]` |
| `measure-resolvability.py` | 簡易版の検討（E-3） | 下記「解決可能性の測定」 |
| `measure-csharp-receivers.py` | 同上（C# の追加測定） | 同上 |
| `emit-generic-schema.py` | 簡易版の検討（E-1） | 同上 |
| `measure-improvements.py` | 同上（改良の効果測定） | 同上 |

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
**正解データとの突合はしていない**。的中率の検証は別途必要（E-3 の「要実測」）。

`emit-generic-schema.py` は **C と C# を同じ列に出せるか**を確かめるためのもの（E-1）。
設計検証用の使い捨てであり、実装の雛形ではない。
既知の未対応（C# の file-scoped namespace、シグネチャ無しの ID 衝突）は
**問題を可視化するために意図的に残してある**。
