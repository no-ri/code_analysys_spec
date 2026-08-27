#!/usr/bin/env bash
# 解析ツールの実行環境を確認する（Linux / WSL 用）
# 判定内容の根拠は docs/CODE_ANALYSIS_CONCEPT.md §9.3
# 使い方: bash tools/check-env.sh [--nuget]
#        --nuget を付けると NuGet の実復元テストも行う（数十秒かかる）

ok=0; ng=0; opt_missing=0
do_nuget=0; [ "${1:-}" = "--nuget" ] && do_nuget=1

hdr() { printf '\n\033[1m--- %s ---\033[0m\n' "$1"; }

# $1=表示名 $2=コマンド $3=用途 $4=バージョン取得コマンド $5=opt なら任意扱い
chk() {
  local name=$1 cmd=$2 phase=$3 vercmd=$4 optional=${5:-} path ver
  path=$(command -v "$cmd" 2>/dev/null)
  if [ -n "$path" ]; then
    ver=$(eval "$vercmd" 2>/dev/null | head -1)
    printf '  \033[32m[OK]\033[0m %-14s %-40s %s\n' "$name" "${ver:-(版不明)}" "$path"
    ok=$((ok+1))
  elif [ "$optional" = "opt" ]; then
    printf '  \033[33m[--]\033[0m %-14s %s\n' "$name" "未インストール（$phase）"
    opt_missing=$((opt_missing+1))
  else
    printf '  \033[31m[NG]\033[0m %-14s %s\n' "$name" "未インストール（$phase で必要）"
    ng=$((ng+1))
  fi
}

echo "==================================================="
echo " 解析ツール実行環境チェック (Linux / WSL)"
echo " $(uname -sr)"
grep -qi microsoft /proc/version 2>/dev/null && echo " ※ WSL 環境として検出"
echo "==================================================="

hdr "Phase 1: C#（最小構成）"

# dotnet の存在だけでは不十分。ランタイムのみでも dotnet は入るため
# --list-sdks で SDK の実体を確認する（§9.3.2）
if ! command -v dotnet >/dev/null 2>&1; then
  printf '  \033[31m[NG]\033[0m %-14s %s\n' "dotnet" "未インストール（Phase 1 で必要）"; ng=$((ng+1))
else
  sdks=$(dotnet --list-sdks 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+' || true)
  if [ -n "$sdks" ]; then
    printf '  \033[32m[OK]\033[0m %-14s SDK %-35s %s\n' "dotnet" \
      "$(echo "$sdks" | tail -1 | cut -d' ' -f1)" "$(command -v dotnet)"; ok=$((ok+1))
  else
    printf '  \033[31m[NG]\033[0m %-14s %s\n' "dotnet" "dotnet はあるが .NET SDK が無い（ランタイムのみ）"
    printf '       ※ 「.NET Framework 4.x SDK」は別物で代わりになりません（§9.3.2）\n'
    ng=$((ng+1))
  fi
fi
chk "git"      git      "Phase 1"  "git --version"
chk "python3"  python3  "全Phase（TSV→SQLite ローダー）"  "python3 --version"

hdr "Phase 2: C/C++（Phase 1 のみなら不要）"
chk "clang"    clang    "Phase 2"  "clang --version" opt
chk "gcc"      gcc      "Phase 2"  "gcc --version" opt
chk "cmake"    cmake    "Phase 2"  "cmake --version" opt

hdr "Phase 3: TypeScript / JavaScript（Phase 1 のみなら不要）"
chk "node"     node     "Phase 3"  "node --version" opt
chk "npm"      npm      "Phase 3"  "npm --version" opt

hdr "任意（あると便利）"
chk "sqlite3"  sqlite3  "DBを手で覗く用。Python同梱版があるので必須ではない" "sqlite3 --version" opt
chk "ninja"    ninja    "cmake を高速化したい場合"  "ninja --version" opt
chk "bear"     bear     "Makefile プロジェクトを対象にする場合" "bear --version" opt

hdr "詳細チェック"

# NuGet が取得できるか（§9.3.2）
if command -v dotnet >/dev/null 2>&1 && dotnet --list-sdks 2>/dev/null | grep -qE "^[0-9]+\.[0-9]+\.[0-9]+"; then
  src=$(dotnet nuget list source 2>&1)
  if echo "$src" | grep -q 'nuget\.org' && echo "$src" | grep -q '\[Enabled\]'; then
    printf '  \033[32m[OK]\033[0m NuGet フィード設定に nuget.org が有効で登録されている\n'; ok=$((ok+1))
  else
    printf '  \033[33m[要確認]\033[0m nuget.org が有効なフィードとして見つからない（社内フィードのみ？）\n'
    printf '           dotnet nuget list source で確認してください\n'
  fi
  if [ "$do_nuget" = "1" ]; then
    printf '  ... NuGet 実復元テスト中（数十秒かかります）\n'
    t=$(mktemp -d)
    dotnet new classlib -o "$t" >/dev/null 2>&1
    dotnet add "$t" package Microsoft.CodeAnalysis.CSharp.Workspaces >/dev/null 2>&1
    if dotnet restore "$t" >/dev/null 2>&1; then
      printf '  \033[32m[OK]\033[0m Roslyn パッケージの復元に成功（NuGet 取得可）\n'; ok=$((ok+1))
    else
      printf '  \033[31m[NG]\033[0m Roslyn パッケージの復元に失敗。プロキシ / 認証 / フィードを確認（§9.3.2）\n'; ng=$((ng+1))
    fi
    rm -rf "$t"
  else
    printf '  \033[33m[--]\033[0m NuGet 実復元テストは未実行（--nuget を付けると実行）\n'
  fi
fi

# Python バージョン（§9.3.1: 3.10 以上に統一）
if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
    printf '  \033[32m[OK]\033[0m Python は 3.10 以上（jedi の要求を満たす）\n'; ok=$((ok+1))
  else
    printf '  \033[33m[要注意]\033[0m Python が 3.10 未満。Phase 1 は動くが Phase 3 の jedi が入らない\n'
  fi

  # SQLite は Python 同梱（§9.3）
  if python3 -c 'import sqlite3' 2>/dev/null; then
    printf '  \033[32m[OK]\033[0m sqlite3 モジュール利用可（%s）— 単体インストール不要\n' \
      "$(python3 -c 'import sqlite3;print(sqlite3.sqlite_version)')"; ok=$((ok+1))
  else
    printf '  \033[31m[NG]\033[0m Python の sqlite3 モジュールが無い（通常は同梱。ビルド構成を確認）\n'; ng=$((ng+1))
  fi

  # libclang（pip）
  if python3 -c 'import clang.cindex' 2>/dev/null; then
    printf '  \033[32m[OK]\033[0m libclang（pip）導入済み\n'; ok=$((ok+1))
  else
    printf '  \033[33m[未]\033[0m libclang（pip）未導入 → pip install libclang\n'
  fi
fi

# clang の組み込みヘッダ（§9.3.4 の要点）
if command -v clang >/dev/null 2>&1; then
  res=$(clang -print-resource-dir 2>/dev/null)
  if [ -f "$res/include/stddef.h" ]; then
    printf '  \033[32m[OK]\033[0m Clang 組み込みヘッダあり: %s/include\n' "$res"; ok=$((ok+1))
  else
    printf '  \033[31m[NG]\033[0m Clang 組み込みヘッダが見つからない（%s）\n' "$res"; ng=$((ng+1))
  fi
fi

# libc ヘッダ
if [ -f /usr/include/stdio.h ]; then
  printf '  \033[32m[OK]\033[0m libc 開発ヘッダあり (/usr/include/stdio.h)\n'; ok=$((ok+1))
else
  printf '  \033[31m[NG]\033[0m libc 開発ヘッダが無い → apt install libc6-dev\n'; ng=$((ng+1))
fi

# 実際にパースできるかの通し確認（§9.3.4 の自己診断に相当）
if command -v python3 >/dev/null 2>&1 && python3 -c 'import clang.cindex' 2>/dev/null && command -v clang >/dev/null 2>&1; then
  tmp=$(mktemp -d)
  printf '#include <stdio.h>\nvoid g(void){ printf("x"); }\n' > "$tmp/t.c"
  if python3 - "$tmp/t.c" <<'PY' 2>/dev/null
import sys, subprocess, clang.cindex as ci
res = subprocess.check_output(['clang','-print-resource-dir'], text=True).strip()
tu = ci.Index.create().parse(sys.argv[1], args=['-I'+res+'/include'])
sys.exit(0 if not [d for d in tu.diagnostics if d.severity >= 3] else 1)
PY
  then
    printf '  \033[32m[OK]\033[0m 実パース通し確認に成功（#include が解決できた）\n'; ok=$((ok+1))
  else
    printf '  \033[31m[NG]\033[0m 実パースで致命的エラー。ヘッダ探索パスを確認すること\n'; ng=$((ng+1))
  fi
  rm -rf "$tmp"
fi

# cmake が compile_commands.json を出せるか（§4.3 の必須前提）
if command -v cmake >/dev/null 2>&1 && command -v gcc >/dev/null 2>&1; then
  tmp=$(mktemp -d)
  printf 'cmake_minimum_required(VERSION 3.10)\nproject(t C)\nadd_library(t t.c)\n' > "$tmp/CMakeLists.txt"
  printf 'int f(void){return 0;}\n' > "$tmp/t.c"
  cmake -S "$tmp" -B "$tmp/b" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON >/dev/null 2>&1
  if [ -f "$tmp/b/compile_commands.json" ]; then
    printf '  \033[32m[OK]\033[0m cmake が compile_commands.json を生成できる\n'; ok=$((ok+1))
  else
    printf '  \033[31m[NG]\033[0m cmake が compile_commands.json を生成できない\n'; ng=$((ng+1))
  fi
  rm -rf "$tmp"
fi

echo
echo "==================================================="
printf ' 必須: OK %d 件 / NG %d 件   任意で未導入: %d 件\n' "$ok" "$ng" "$opt_missing"
if [ "$ng" -eq 0 ]; then
  echo " → Phase 1（C#）を始められる状態です"
else
  echo " → 上の [NG] を解消してください（§9.3 参照）"
fi
echo "==================================================="
[ "$ng" -eq 0 ]
