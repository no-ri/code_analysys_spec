# -*- coding: utf-8 -*-
"""C# の「35〜40% まで上がる見込み」が実測 31.8% に届かなかった理由を追跡する（F-11 の実測）。

見込みは measure-csharp-receivers.py の
  「レシーバが型名（static 呼び出し）」  199 件 (28.1%)
  「型が明示 & 型がリポジトリ内 → 解決可能」136 件 (19.2%)
から立てた。本スクリプトは**その 335 件が実際にどこへ着地したか**を数える。

分かること:
  1. 28.1% / 19.2% は**メンバ呼び出し 707 件**が分母であり、全呼び出し 1,022 件ではない
  2. 「レシーバが型名」は識別子の**先頭が大文字かどうかだけ**で判定しており、
     その型がリポジトリ内にあるかも、そのメソッドが存在するかも確かめていない

結論は `docs/OPEN_DECISIONS.md` F-11。

    .venv/bin/python tools/measure-csharp-forecast.py
"""

import glob, os, collections
from tree_sitter_language_pack import get_parser

PATS = ["targets/FluentValidation/src/FluentValidation/**/*.cs"]
EXCL = ("test", "tests", "fuzz", "example", "examples", "bench", "benchmark")
CS_TYPE = {"class_declaration", "struct_declaration", "record_declaration", "interface_declaration"}
CS_FUNC = {"method_declaration", "constructor_declaration", "local_function_statement"}

def files_of(pats):
    out = []
    for p in pats: out.extend(glob.glob(p, recursive=True))
    r = []
    for f in sorted(set(out)):
        low = f.lower()
        if any(("/%s/" % e) in low for e in EXCL): continue
        if "test" in os.path.basename(low) or "bench" in os.path.basename(low): continue
        r.append(f)
    return r

def txt(n): return n.text.decode(errors="replace")
def base_type(t): return t.rstrip("?").split("<")[0].split(".")[-1].replace("[]", "")

def declarations(root):
    """ファイル内の『名前 -> 宣言型』。型を書かずに var で受けたものは別に返す"""
    typed = {}; untyped = set()
    st = [root]
    while st:
        n = st.pop()
        if n.type in ("variable_declaration", "field_declaration", "property_declaration", "parameter"):
            ty = n.child_by_field_name("type")
            if ty is not None:
                tn = txt(ty); names = []
                if n.type == "parameter":
                    nm = n.child_by_field_name("name")
                    if nm is not None: names = [txt(nm)]
                else:
                    s2 = [n]
                    while s2:
                        m = s2.pop()
                        if m.type == "variable_declarator":
                            nm = m.child_by_field_name("name")
                            if nm is not None: names.append(txt(nm))
                        s2.extend(m.children)
                    if n.type == "property_declaration":
                        nm = n.child_by_field_name("name")
                        if nm is not None: names.append(txt(nm))
                for nm2 in names:
                    if tn == "var": untyped.add(nm2)
                    else: typed[nm2] = tn
        st.extend(n.children)
    return typed, untyped

P = get_parser("csharp")
files = files_of(PATS)
types = {}; methods = collections.defaultdict(set); bases = {}; trees = {}
for path in files:
    t = P.parse(open(path, "rb").read()); trees[path] = t
    st = [(t.root_node, None)]
    while st:
        n, cls = st.pop(); cur = cls
        if n.type in CS_TYPE:
            nm = n.child_by_field_name("name")
            if nm is not None:
                cur = txt(nm); types[cur] = path
                bl = n.child_by_field_name("bases")
                if bl is not None:
                    bases[cur] = [base_type(x) for x in txt(bl).lstrip(":").split(",")]
        elif n.type in CS_FUNC:
            nm = n.child_by_field_name("name")
            if nm is not None and cls: methods[cls].add(txt(nm))
        for c in n.children: st.append((c, cur))

def has_method(cls, name, d=0):
    if not cls or d > 6: return False
    if name in methods.get(cls, ()): return True
    return any(has_method(b, name, d + 1) for b in bases.get(cls, ()))

buckets = collections.Counter(); land = collections.defaultdict(collections.Counter)
why = collections.defaultdict(collections.Counter); ext_recv = collections.Counter()
total_calls = 0
for path in files:
    root = trees[path].root_node
    typed, untyped = declarations(root)
    declared = {k: base_type(v) for k, v in typed.items()}
    st = [(root, None)]
    while st:
        n, cls = st.pop(); cur = cls
        if n.type in CS_TYPE:
            nm = n.child_by_field_name("name")
            if nm is not None: cur = txt(nm)
        if n.type == "invocation_expression":
            total_calls += 1
            f = n.child_by_field_name("function")
            if f is not None and f.type == "member_access_expression":
                obj = f.child_by_field_name("expression") or f.child_by_field_name("object")
                mn = txt(f).rsplit(".", 1)[-1]; recv = txt(f).rsplit(".", 1)[0]
                # measure-csharp-receivers.py の分類（＝見込みの根拠）
                if obj is not None and obj.type == "identifier":
                    rn = txt(obj)
                    if rn in ("this", "base"): b = "self/base"
                    elif rn in typed:
                        b = ("型が明示&リポジトリ内" if base_type(typed[rn]) in types
                             else "型が明示だがリポジトリ外")
                    elif rn in untyped: b = "var 宣言"
                    elif rn and rn[0].isupper(): b = "型名(static)"
                    else: b = "宣言が同一ファイルに無い"
                else: b = "レシーバが式(チェーン等)"
                buckets[b] += 1
                # measure-improvements.py の after 規則（＝実測）
                if recv in ("this", "base"): a = "resolved" if has_method(cur, mn) else "needs_type"
                elif recv in types and has_method(recv, mn): a = "resolved"
                elif recv in declared and has_method(declared[recv], mn): a = "resolved"
                elif recv in declared and declared[recv] not in types: a = "external"
                else: a = "needs_type"
                land[b][a] += 1
                if a != "resolved" and b in ("型名(static)", "型が明示&リポジトリ内"):
                    t2 = recv if b == "型名(static)" else declared.get(recv)
                    if t2 not in types:
                        why[b]["受け側の型がリポジトリ外"] += 1; ext_recv[t2] += 1
                    else:
                        why[b]["型はあるがメソッドが見つからない"] += 1
        for c in n.children: st.append((c, cur))

tot = sum(buckets.values())
print("全呼び出し %d 件 / うちメンバ呼び出し %d 件（receivers スクリプトの分母）\n" % (total_calls, tot))
print("  %-26s %6s %7s │ after 規則での着地" % ("receivers の分類", "件数", "比率"))
for b, c in buckets.most_common():
    s = ", ".join("%s=%d" % (k, v) for k, v in land[b].most_common())
    print("  %-26s %6d %6.1f%% │ %s" % (b, c, c * 100.0 / tot, s))

print("\n--- 見込みに数えた2分類が解けなかった理由")
for b in ("型名(static)", "型が明示&リポジトリ内"):
    print("  %-22s %s" % (b, ", ".join("%s=%d" % (k, v) for k, v in why[b].most_common())))
print("  リポジトリ外だったレシーバ 上位: "
      + ", ".join("%s(%d)" % (k, v) for k, v in ext_recv.most_common(6)))

fc = buckets["型名(static)"] + buckets["型が明示&リポジトリ内"]
rs = land["型名(static)"]["resolved"] + land["型が明示&リポジトリ内"]["resolved"]
print("\n見込みに数えた2分類 %d 件 → 実際に resolved になったのは %d 件 (%.1f%%)" % (fc, rs, rs * 100.0 / fc))
print("全呼び出し %d 件に対して: 見込み %.1fpt ぶん → 実測 %.1fpt ぶん"
      % (total_calls, fc * 100.0 / total_calls, rs * 100.0 / total_calls))
