# tools

構想・仕様リポジトリだが、環境確認だけは実際に動くスクリプトとして置いておく。
判定内容の根拠はすべて `docs/CODE_ANALYSIS_CONCEPT.md` §9.3。

| ファイル | 対象 | 実行方法 |
|---|---|---|
| `check-env.sh` | Linux / WSL | `bash tools/check-env.sh` |
| `check-env.ps1` | Windows | `powershell -ExecutionPolicy Bypass -File tools\check-env.ps1` |

## 見方

| 表示 | 意味 |
|---|---|
| `[OK]` | 導入済み |
| `[NG]` | **必須なのに未導入**。解消が必要 |
| `[--]` | 任意、または後続 Phase 用。Phase 1 を始めるだけなら無くてよい |

終了コードは NG の件数（0 なら Phase 1 を開始できる）。

## 単なる有無確認ではない項目

コマンドの存在確認だけでは分からない、実際に動くかどうかを確認している。

- **Clang 組み込みヘッダ** — `clang -print-resource-dir` の下に `stddef.h` があるか（§9.3.2）
- **実パース通し確認** — `#include <stdio.h>` を含むファイルを libclang で実際にパースし、致命的エラーが出ないか
- **compile_commands.json 生成** — 小さな CMake プロジェクトを実際に configure して生成されるか（§4.3）

## Windows 固有の注意

- **`cl.exe` は「Developer PowerShell for VS」から実行しないと PATH に現れない**。通常の PowerShell で C コンパイラが未検出になった場合は、そちらから再実行すること
- **`CMAKE_EXPORT_COMPILE_COMMANDS` は Visual Studio ジェネレータでは機能しない**とされる。スクリプトは ninja があれば `-G Ninja` を使う。**この挙動は Windows 実機で未検証**
- Python は `python` と `py` の2系統があるため、両方を探索する
