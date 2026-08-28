#!/usr/bin/env python3
"""文書間の参照が壊れていないかを確かめる。

資料の整理（移動・分割）で参照が壊れていないことを機械的に示すための安全網。
移動の前に基準値を取り、各ステップ後に同じ結果になることを確認する。

検査:
  1. 決定ID（A-1 〜 L-7 等）の参照が、すべて実在する定義に解決するか
  2. §N.M の参照が、実在する見出しに解決するか
  3. 文書中のファイル名参照が実在するか
"""
import os, re, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = sorted(glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True))
ALL  = DOCS + [os.path.join(ROOT, "CLAUDE.md"), os.path.join(ROOT, "tools", "README.md")]
rel  = lambda p: os.path.relpath(p, ROOT)

ID_RE = re.compile(r'\b([A-L])-(\d{1,2})\b')
# 除外: 日付（2026-08-27）や ISO 時刻の断片は ID_RE に当たらない（英字1文字が必要）

def read(p): return open(p, encoding="utf-8").read()

# ---- 1. 決定ID ----
defined, referenced = set(), {}
for p in ALL:
    if not os.path.exists(p): continue
    for line in read(p).split("\n"):
        ids = {f"{a}-{b}" for a, b in ID_RE.findall(line)}
        if not ids: continue
        head = line.startswith("#")
        # 表の第1列（| **F-1** | ... ）も定義とみなす
        first_cell = line.startswith("|") and any(i in line.split("|")[1] for i in ids)
        if head or first_cell: defined |= ids
        for i in ids: referenced.setdefault(i, set()).add(rel(p))

dangling = {i: v for i, v in referenced.items() if i not in defined}

# ---- 2. §N.M ----
# 節番号は文書をまたいで共有される（[構想] / [フル版計画] / [現実]）。
# さらに各文書は自分自身の節も参照するため、両方を許す。
SEC_RE = re.compile(r'§(\d+(?:\.\d+)*)')
HEAD_RE = re.compile(r'^#{2,5}\s+(?:\d+\.\s+)?(\d+(?:\.\d+)*)')

def headings_of(p):
    out = set()
    for line in read(p).split("\n"):
        m = re.match(r'^#{2,5}\s+(\d+(?:\.\d+)*)', line)
        if m:
            n = m.group(1); out.add(n)
            while "." in n:                     # §3.1.1 があれば §3.1 / §3 も有効
                n = n.rsplit(".", 1)[0]; out.add(n)
    return out

SHARED = [os.path.join(ROOT, "docs", "CODE_ANALYSIS_CONCEPT.md"),
          os.path.join(ROOT, "docs", "full-version", "FULL_VERSION_PLAN.md"),
          os.path.join(ROOT, "docs", "full-version", "EXTRACTABLE_DATA_MATRIX.md"),
          os.path.join(ROOT, "docs", "ANALYSIS_VIEWPOINTS.md")]
sections = set()
for q in SHARED:
    if os.path.exists(q): sections |= headings_of(q)

bad_sec = {}
for p in ALL:
    if not os.path.exists(p): continue
    own = headings_of(p)                        # 自文書内の節も有効
    for n in SEC_RE.findall(read(p)):
        if n not in sections and n not in own:
            bad_sec.setdefault(n, set()).add(rel(p))

# ---- 3. ファイル名参照 ----
FILE_RE = re.compile(r'`((?:docs/|tools/)?[\w./-]+\.(?:md|py|sh|ps1|sqlite|tsv|json))`')
known = {rel(p) for p in glob.glob(os.path.join(ROOT, "**", "*"), recursive=True) if os.path.isfile(p)}
basenames = {os.path.basename(k) for k in known}
bad_file = {}
GENERIC = {"db.sqlite", "run.tsv", "facts.sqlite", "compile_commands.json", "analysis.toml",
           "findings.csv", "symbols.csv", "calls.csv", "var_refs.csv", "comments.csv",
           "cfg_blocks.csv", "package.json", "tsconfig.json"}
for p in ALL:
    if not os.path.exists(p): continue
    for f in FILE_RE.findall(read(p)):
        base = os.path.basename(f)
        if base in GENERIC or base.endswith((".tsv", ".sqlite", ".csv")): continue
        if f in known or base in basenames: continue
        bad_file.setdefault(f, set()).add(rel(p))

print(f"決定ID       : 定義 {len(defined)} 件 / 参照 {len(referenced)} 種")
print(f"§ 参照       : 見出し {len(sections)} 件")
print(f"ファイル参照 : 実在 {len(known)} 件")
print()
ng = 0
for label, bad in (("解決しない決定ID", dangling), ("解決しない § 参照", bad_sec),
                   ("実在しないファイル参照", bad_file)):
    if bad:
        ng += len(bad)
        print(f"[NG] {label}: {len(bad)} 件")
        for k, v in sorted(bad.items()):
            print(f"     {k}  ← {', '.join(sorted(v))}")
    else:
        print(f"[OK] {label}: 0 件")
sys.exit(1 if ng else 0)
