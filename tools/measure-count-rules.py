# -*- coding: utf-8 -*-
"""同じ対象の `resolved` 件数が測定ごとに違う理由を突き合わせる（F-12 の実測）。

FluentValidation の解決済み件数は3つのスクリプトで 53 / 55 / 56 と食い違っていた。
本スクリプトは**同じ呼び出し集合**に3つの分類規則を当て、差の出た呼び出しを列挙する。

  measure-resolvability.py   … 53 件（Phase 0、②-a 5.2%）
  emit-generic-schema.py     … 55 件（facts.sqlite の実出力）
  measure-improvements.py    … 56 件（before、5.5%）

結論は `docs/OPEN_DECISIONS.md` F-12。差は分類規則の違いであって、対象や
パーサの揺れではない（3者は 53 ⊂ 55 ⊂ 56 の包含関係になる）。

準備・実行は tools/README.md の「解決可能性の測定」と同じ。
    .venv/bin/python tools/measure-count-rules.py
"""

import glob, os, collections, sqlite3
from tree_sitter_language_pack import get_parser

PATS = ["targets/FluentValidation/src/FluentValidation/**/*.cs"]

# 各スクリプトのファイル除外規則。除外リストの差が効いていないことも確かめる
EXCL_RESOLVABILITY = ("test", "tests", "fuzz", "example", "examples", "samples", "sample",
                      "benchmark", "bench", "node_modules", "third_party", "vendor", "api_test")
EXCL_IMPROVEMENTS = ("test", "tests", "fuzz", "example", "examples", "bench", "benchmark")

def files_of(pats, excl):
    out = []
    for p in pats: out.extend(glob.glob(p, recursive=True))
    r = []
    for f in sorted(set(out)):
        low = f.lower().replace("\\", "/")
        if any(("/%s/" % e) in low for e in excl): continue
        b = os.path.basename(low)
        if "test" in b or "bench" in b or b.startswith("fuzz"): continue
        r.append(f)
    return r

CS_TYPE = {"class_declaration", "struct_declaration", "record_declaration", "interface_declaration"}
CS_FUNC = {"method_declaration", "constructor_declaration", "local_function_statement"}
def txt(n): return n.text.decode(errors="replace")

# 「自分自身」とみなすレシーバ。ここが2つのスクリプトで違っていた
SELF_RESOLVABILITY = {"self", "this", "cls", "super"}   # C# の base が無い
SELF_IMPROVEMENTS  = {"this", "base"}

fr = files_of(PATS, EXCL_RESOLVABILITY)
fi = files_of(PATS, EXCL_IMPROVEMENTS)
print("ファイル集合: resolvability=%d  improvements=%d  差=%s"
      % (len(fr), len(fi), sorted(set(fr) ^ set(fi)) or "なし"))

P = get_parser("csharp")
files = fr
trees = {f: P.parse(open(f, "rb").read()) for f in files}

# 定義表（3者で共通の作り方）
byname = collections.defaultdict(list); clsmeth = {}
for path in files:
    st = [(trees[path].root_node, None)]
    while st:
        n, cls = st.pop(); cur = cls
        if n.type in CS_TYPE:
            nm = n.child_by_field_name("name")
            if nm is not None: cur = txt(nm)
        elif n.type in CS_FUNC:
            nm = n.child_by_field_name("name")
            if nm is not None:
                byname[txt(nm)].append(path)
                if cls: clsmeth[(cls, txt(nm))] = path
        for c in n.children: st.append((c, cur))

R = set(); I = set(); total = 0
for path in files:
    st = [(trees[path].root_node, None)]
    while st:
        n, cls = st.pop(); cur = cls
        if n.type in CS_TYPE:
            nm = n.child_by_field_name("name")
            if nm is not None: cur = txt(nm)
        if n.type == "invocation_expression":
            total += 1
            f = n.child_by_field_name("function")
            kind = "none" if f is None else f.type
            full = txt(f) if f is not None else "?"
            key = (path, n.start_point[0] + 1, full)
            recv = full.rsplit(".", 1)[0] if kind == "member_access_expression" else None
            mn = full.rsplit(".", 1)[-1] if kind in ("member_access_expression", "identifier") else None
            # measure-resolvability.py の規則
            if kind == "identifier" and len(byname.get(mn, [])) == 1: R.add(key)
            elif kind == "member_access_expression" and recv in SELF_RESOLVABILITY \
                 and cur and (cur, mn) in clsmeth: R.add(key)
            # measure-improvements.py（before）の規則
            if kind == "identifier" and len(byname.get(mn, [])) == 1: I.add(key)
            elif kind == "member_access_expression" and recv in SELF_IMPROVEMENTS: I.add(key)
        for c in n.children: st.append((c, cur))

E = set()
if os.path.exists("facts.sqlite"):
    db = sqlite3.connect("facts.sqlite")
    E = {(p, l, e) for p, l, e in db.execute(
        "SELECT file, line, dst_expr FROM refs "
        "WHERE lang='csharp' AND kind='call' AND status='resolved'")}
else:
    print("\n※ facts.sqlite が無いので emit-generic-schema.py の実出力は比較から外す")
    print("   先に .venv/bin/python tools/emit-generic-schema.py を実行すること")

print("\n呼び出し総数: %d" % total)
print("resolved 件数:  resolvability=%d  emit-generic-schema=%d  improvements(before)=%d"
      % (len(R), len(E), len(I)))

if E:
    print("\n包含関係: R⊆E=%s  E⊆I=%s" % (R <= E, E <= I))
    for label, s in (("emit にあり resolvability に無い", E - R),
                     ("improvements にあり emit に無い ", I - E),
                     ("resolvability にあり emit に無い", R - E),
                     ("emit にあり improvements に無い ", E - I)):
        print("\n--- %s : %d 件" % (label, len(s)))
        for k in sorted(s)[:10]:
            print("      %s:%d  %s" % (os.path.basename(k[0]), k[1], k[2]))
