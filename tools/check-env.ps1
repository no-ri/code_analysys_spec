# 解析ツールの実行環境を確認する（Windows / PowerShell 用）
# 判定内容の根拠は docs/CODE_ANALYSIS_CONCEPT.md §9.3
# 使い方: powershell -ExecutionPolicy Bypass -File tools\check-env.ps1
#        -NuGet を付けると NuGet の実復元テストも行う（数十秒かかる）
param([switch]$NuGet)

$script:ok = 0; $script:ng = 0; $script:optMissing = 0

function Write-Head($t) { Write-Host "`n--- $t ---" -ForegroundColor White }

function Test-Tool {
    param([string]$Name, [string]$Cmd, [string]$Purpose, [string]$VerArgs = '--version', [switch]$Optional)
    $c = Get-Command $Cmd -ErrorAction SilentlyContinue
    if ($c) {
        $ver = ''
        try { $ver = (& $Cmd $VerArgs.Split(' ') 2>&1 | Select-Object -First 1) } catch {}
        Write-Host ("  [OK] {0,-14} {1,-40} {2}" -f $Name, $ver, $c.Source) -ForegroundColor Green
        $script:ok++
    } elseif ($Optional) {
        Write-Host ("  [--] {0,-14} 未インストール（{1}）" -f $Name, $Purpose) -ForegroundColor Yellow
        $script:optMissing++
    } else {
        Write-Host ("  [NG] {0,-14} 未インストール（{1} で必要）" -f $Name, $Purpose) -ForegroundColor Red
        $script:ng++
    }
}

Write-Host "==================================================="
Write-Host " 解析ツール実行環境チェック (Windows)"
Write-Host (" {0}" -f [System.Environment]::OSVersion.VersionString)
Write-Host "==================================================="

Write-Head "Phase 1: C#（最小構成）"

# dotnet.exe の存在だけでは不十分。ランタイムのみのインストールでも dotnet.exe は入る。
# Roslyn のビルド・復元には SDK が要るため --list-sdks で実体を確認する（§9.3.2）
$dn = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dn) {
    Write-Host ("  [NG] {0,-14} 未インストール（Phase 1 で必要）" -f 'dotnet') -ForegroundColor Red
    $script:ng++
} else {
    $sdks = @(& dotnet --list-sdks 2>&1 | Where-Object { $_ -match '^\d+\.\d+\.\d+' })
    if ($sdks.Count -gt 0) {
        Write-Host ("  [OK] {0,-14} SDK {1,-35} {2}" -f 'dotnet', ($sdks[-1] -split ' ')[0], $dn.Source) -ForegroundColor Green
        $script:ok++
        Write-Host ("       導入済み SDK: {0}" -f (($sdks | ForEach-Object { ($_ -split ' ')[0] }) -join ', ')) -ForegroundColor Gray
    } else {
        Write-Host ("  [NG] {0,-14} dotnet.exe はあるが .NET SDK が無い" -f 'dotnet') -ForegroundColor Red
        Write-Host "       ※ ランタイムのみ、または Visual Studio 同梱の共有ホストだけの状態です" -ForegroundColor Yellow
        Write-Host "       ※ 「.NET Framework 4.x SDK」は別物で、これの代わりにはなりません（§9.3.2）" -ForegroundColor Yellow
        Write-Host "       → https://dotnet.microsoft.com/download から .NET SDK 8.0 を導入" -ForegroundColor Yellow
        $script:ng++
        $rts = @(& dotnet --list-runtimes 2>&1 | Where-Object { $_ -match '^Microsoft\.' })
        if ($rts.Count -gt 0) {
            Write-Host ("       参考: 導入済みランタイム {0} 件" -f $rts.Count) -ForegroundColor Gray
        }
    }
}
Test-Tool 'git'    'git'    'Phase 1'

Write-Head "Phase 2: C/C++（Phase 1 のみなら不要）"
# Windows の Python は python / py の2系統がある
$pyCmd = $null
foreach ($cand in @('python', 'py')) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) { $pyCmd = $cand; break }
}
if ($pyCmd) {
    $pv = (& $pyCmd --version 2>&1 | Select-Object -First 1)
    Write-Host ("  [OK] {0,-14} {1,-40} {2}" -f 'python', $pv, (Get-Command $pyCmd).Source) -ForegroundColor Green
    $script:ok++
} else {
    Write-Host ("  [NG] {0,-14} 未インストール（全Phase で必要。TSV→SQLite ローダー）" -f 'python') -ForegroundColor Red
    $script:ng++
}
Test-Tool 'clang' 'clang' 'Phase 2' -Optional
Test-Tool 'cmake' 'cmake' 'Phase 2' -Optional

Write-Head "C コンパイラ（Phase 2 用。cmake の configure に必要）"
# Windows では MSVC(cl.exe) か MinGW(gcc) のいずれか
$hasCompiler = $false
foreach ($cc in @('cl', 'gcc', 'clang-cl')) {
    if (Get-Command $cc -ErrorAction SilentlyContinue) {
        Write-Host ("  [OK] {0,-14} 検出" -f $cc) -ForegroundColor Green
        $hasCompiler = $true; $script:ok++
    }
}
if (-not $hasCompiler) {
    Write-Host "  [--] C コンパイラ未検出（Phase 2 で cl.exe / gcc / clang-cl のいずれかが必要）" -ForegroundColor Yellow
    Write-Host "       ※ cl.exe は「Developer PowerShell for VS」から実行しないと PATH に出ません" -ForegroundColor Yellow
    $script:optMissing++
}

Write-Head "Phase 3: TypeScript / JavaScript（Phase 1 のみなら不要）"
Test-Tool 'node' 'node' 'Phase 3' -Optional
Test-Tool 'npm'  'npm'  'Phase 3' -Optional

Write-Head "任意（あると便利）"
Test-Tool 'sqlite3' 'sqlite3' 'DBを手で覗く用。Python同梱版があるので必須ではない' -Optional
Test-Tool 'ninja'   'ninja'   'compile_commands.json 生成に推奨（下記参照）' -Optional

Write-Head "詳細チェック"

# NuGet が取得できるか（§9.3.2）
if ((Get-Command dotnet -ErrorAction SilentlyContinue) -and
    (@(& dotnet --list-sdks 2>&1 | Where-Object { $_ -match '^\d+\.\d+\.\d+' }).Count -gt 0)) {
    $srcOut = (& dotnet nuget list source 2>&1 | Out-String)
    if ($srcOut -match 'nuget\.org' -and $srcOut -match '\[Enabled\]') {
        Write-Host "  [OK] NuGet フィード設定に nuget.org が有効で登録されている" -ForegroundColor Green
        $script:ok++
    } else {
        Write-Host "  [要確認] nuget.org が有効なフィードとして見つからない（社内フィードのみ？）" -ForegroundColor Yellow
        Write-Host "           dotnet nuget list source で確認してください" -ForegroundColor Yellow
    }

    if ($NuGet) {
        Write-Host "  ... NuGet 実復元テスト中（数十秒かかります）" -ForegroundColor Gray
        $tmp = Join-Path $env:TEMP ("nugetchk_" + [guid]::NewGuid().ToString('N'))
        & dotnet new classlib -o $tmp *> $null
        & dotnet add $tmp package Microsoft.CodeAnalysis.CSharp.Workspaces *> $null
        & dotnet restore $tmp *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] Roslyn パッケージの復元に成功（NuGet 取得可）" -ForegroundColor Green
            $script:ok++
        } else {
            Write-Host "  [NG] Roslyn パッケージの復元に失敗。プロキシ / 認証 / フィードを確認（§9.3.2）" -ForegroundColor Red
            $script:ng++
        }
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    } else {
        Write-Host "  [--] NuGet 実復元テストは未実行（-NuGet を付けると実行）" -ForegroundColor Yellow
    }
}

if ($pyCmd) {
    # Python バージョン（§9.3.1: 3.10 以上に統一）
    & $pyCmd -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Python は 3.10 以上（jedi の要求を満たす）" -ForegroundColor Green; $script:ok++
    } else {
        Write-Host "  [要注意] Python が 3.10 未満。Phase 1 は動くが Phase 3 の jedi が入らない" -ForegroundColor Yellow
    }

    # SQLite は Python 同梱（§9.3）
    & $pyCmd -c "import sqlite3" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $sv = & $pyCmd -c "import sqlite3;print(sqlite3.sqlite_version)"
        Write-Host "  [OK] sqlite3 モジュール利用可（$sv）— 単体インストール不要" -ForegroundColor Green; $script:ok++
    } else {
        Write-Host "  [NG] Python の sqlite3 モジュールが無い" -ForegroundColor Red; $script:ng++
    }

    # libclang（pip）
    & $pyCmd -c "import clang.cindex" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] libclang（pip）導入済み" -ForegroundColor Green; $script:ok++
    } else {
        Write-Host "  [未] libclang（pip）未導入 → pip install libclang" -ForegroundColor Yellow
    }
}

# Clang 組み込みヘッダ（§9.3.4 の要点）
if (Get-Command clang -ErrorAction SilentlyContinue) {
    $res = (& clang -print-resource-dir 2>$null)
    if ($res -and (Test-Path (Join-Path $res 'include\stddef.h'))) {
        Write-Host "  [OK] Clang 組み込みヘッダあり: $res\include" -ForegroundColor Green; $script:ok++
    } else {
        Write-Host "  [NG] Clang 組み込みヘッダが見つからない（$res）" -ForegroundColor Red; $script:ng++
    }
}

# 実パース通し確認（§9.3.4 の自己診断に相当）
if ($pyCmd -and (Get-Command clang -ErrorAction SilentlyContinue)) {
    & $pyCmd -c "import clang.cindex" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $tmp = Join-Path $env:TEMP ("envchk_" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        $cfile = Join-Path $tmp 't.c'
        "#include <stdio.h>`nvoid g(void){ printf(`"x`"); }" | Set-Content -Path $cfile -Encoding ASCII
        $pyScript = Join-Path $tmp 'chk.py'
        @'
import sys, subprocess, clang.cindex as ci
res = subprocess.check_output(['clang','-print-resource-dir'], text=True).strip()
tu = ci.Index.create().parse(sys.argv[1], args=['-I'+res+'/include'])
bad = [d for d in tu.diagnostics if d.severity >= 3]
for d in bad[:3]: print('   ', d.spelling)
sys.exit(0 if not bad else 1)
'@ | Set-Content -Path $pyScript -Encoding ASCII
        & $pyCmd $pyScript $cfile
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] 実パース通し確認に成功（#include が解決できた）" -ForegroundColor Green; $script:ok++
        } else {
            Write-Host "  [NG] 実パースで致命的エラー。Windows SDK / MSVC のヘッダ探索パスを確認" -ForegroundColor Red; $script:ng++
        }
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

# cmake が compile_commands.json を出せるか（§4.3 の必須前提）
if ((Get-Command cmake -ErrorAction SilentlyContinue) -and $hasCompiler) {
    $tmp = Join-Path $env:TEMP ("cmakechk_" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    "cmake_minimum_required(VERSION 3.10)`nproject(t C)`nadd_library(t t.c)" |
        Set-Content -Path (Join-Path $tmp 'CMakeLists.txt') -Encoding ASCII
    "int f(void){return 0;}" | Set-Content -Path (Join-Path $tmp 't.c') -Encoding ASCII

    $gen = if (Get-Command ninja -ErrorAction SilentlyContinue) { @('-G','Ninja') } else { @() }
    & cmake -S $tmp -B (Join-Path $tmp 'b') -DCMAKE_EXPORT_COMPILE_COMMANDS=ON @gen *> $null

    if (Test-Path (Join-Path $tmp 'b\compile_commands.json')) {
        Write-Host "  [OK] cmake が compile_commands.json を生成できる" -ForegroundColor Green; $script:ok++
    } else {
        Write-Host "  [NG] compile_commands.json が生成されなかった" -ForegroundColor Red
        Write-Host "       ※ CMAKE_EXPORT_COMPILE_COMMANDS は Visual Studio ジェネレータでは無効。" -ForegroundColor Yellow
        Write-Host "         ninja を入れて 'cmake -G Ninja' を使うのが確実（要検証）" -ForegroundColor Yellow
        $script:ng++
    }
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "==================================================="
Write-Host (" 必須: OK {0} 件 / NG {1} 件   任意で未導入: {2} 件" -f $script:ok, $script:ng, $script:optMissing)
if ($script:ng -eq 0) {
    Write-Host " → Phase 1（C#）を始められる状態です" -ForegroundColor Green
} else {
    Write-Host " → 上の [NG] を解消してください（§9.3 参照）" -ForegroundColor Red
}
Write-Host "==================================================="
exit $script:ng
