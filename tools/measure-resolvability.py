# -*- coding: utf-8 -*-
"""簡易版の解決可能性を測る（OPEN_DECISIONS.md E-3 の実測に使用したスクリプト）。

tree-sitter の構文木のみを入力とし、呼び出し1件ごとにどの分類へ落ちるかを数える。
ビルドは一切行わない（＝軸2 = ゼロの条件そのもの）。

準備:
    python3 -m venv .venv && .venv/bin/pip install tree-sitter tree-sitter-language-pack
    mkdir targets && cd targets
    for r in DaveGamble/cJSON commonmark/cmark leethomason/tinyxml2 \
             psf/requests tj/commander.js FluentValidation/FluentValidation; do
        git clone --depth 1 https://github.com/$r $(basename $r)
    done

実行:
    .venv/bin/python tools/measure-resolvability.py     # targets/ のある場所から

限界:
    「その形なら解けるはず」を数えたものであり、正解データとの突合はしていない。
    ②-a の的中率そのものは別途検証が要る（E-3 の「要実測」）。
"""

import os, glob, collections
from tree_sitter_language_pack import get_parser

EXCLUDE_DIR = ("test", "tests", "fuzz", "example", "examples", "samples", "sample",
               "benchmark", "bench", "node_modules", "third_party", "vendor", "api_test")
def excluded(path):
    p = path.lower().replace("\\", "/")
    if any(("/%s/" % e) in p for e in EXCLUDE_DIR): return True
    b = os.path.basename(p)
    return "test" in b or "bench" in b or b.startswith("fuzz")

CLASS_NODES = {
    "c": set(), "cpp": {"class_specifier", "struct_specifier"},
    "csharp": {"class_declaration", "struct_declaration", "record_declaration", "interface_declaration"},
    "python": {"class_definition"},
    "javascript": {"class_declaration", "class"},
}
FUNC_NODES = {
    "c": {"function_definition"}, "cpp": {"function_definition"},
    "csharp": {"method_declaration", "local_function_statement", "constructor_declaration"},
    "python": {"function_definition"},
    "javascript": {"function_declaration", "generator_function_declaration", "method_definition"},
}
CALL_NODES = {"c": {"call_expression"}, "cpp": {"call_expression"},
              "csharp": {"invocation_expression"}, "python": {"call"},
              "javascript": {"call_expression"}}
SIMPLE = {"identifier"}
MEMBER = {"field_expression", "member_access_expression", "attribute", "member_expression"}
QUALIFIED = {"qualified_identifier", "scoped_identifier"}
SELF_RECV = {"self", "this", "cls", "super"}

def decl_name(n):
    d = n.child_by_field_name("declarator")
    while d is not None and d.type not in ("identifier", "field_identifier", "qualified_identifier"):
        nd = d.child_by_field_name("declarator")
        if nd is None: return None
        d = nd
    return d

def walk(lang, node, path, cls, defs, macros, calls, cls_methods):
    """cls = 現在囲んでいるクラス名（無ければ None）"""
    t = node.type
    newcls = cls
    if t in CLASS_NODES[lang]:
        nm = node.child_by_field_name("name")
        newcls = nm.text.decode(errors="replace") if nm is not None else cls
    if t in FUNC_NODES[lang]:
        if lang in ("c", "cpp"):
            d = decl_name(node)
            if d is not None:
                raw = d.text.decode(errors="replace")
                name = raw.split("::")[-1]
                owner = raw.split("::")[0] if "::" in raw else cls
                prefix = node.text[: node.text.find(b"{") if b"{" in node.text else 60]
                is_static = b"static" in prefix.split(b"(")[0]
                defs[name].append((path, d.start_point[0] + 1, is_static))
                if owner: cls_methods[(owner, name)] = (path, d.start_point[0] + 1)
        else:
            nm = node.child_by_field_name("name")
            if nm is not None:
                name = nm.text.decode(errors="replace")
                defs[name].append((path, nm.start_point[0] + 1, False))
                if cls: cls_methods[(cls, name)] = (path, nm.start_point[0] + 1)
    elif t == "preproc_function_def":
        nm = node.child_by_field_name("name")
        if nm is not None: macros.add(nm.text.decode(errors="replace"))
    if t in CALL_NODES[lang]:
        f = node.child_by_field_name("function")
        if f is None:
            calls.append((path, cls, "indirect", None))
        elif f.type in SIMPLE:
            calls.append((path, cls, "direct", f.text.decode(errors="replace")))
        elif f.type in QUALIFIED:
            calls.append((path, cls, "direct", f.text.decode(errors="replace").split("::")[-1].split(".")[-1]))
        elif f.type in MEMBER:
            obj = f.child_by_field_name("object") or f.child_by_field_name("argument") or f.child_by_field_name("expression")
            fld = f.child_by_field_name("field") or f.child_by_field_name("attribute") or f.child_by_field_name("property") or f.child_by_field_name("name")
            recv = obj.text.decode(errors="replace") if obj is not None else ""
            mname = fld.text.decode(errors="replace") if fld is not None else None
            if recv in SELF_RECV and mname:
                calls.append((path, cls, "self_member", mname))
            else:
                calls.append((path, cls, "member", mname))
        else:
            calls.append((path, cls, "indirect", None))
    for c in node.children:
        walk(lang, c, path, newcls, defs, macros, calls, cls_methods)

def errors(root):
    st, k = [root], 0
    while st:
        n = st.pop()
        if n.type == "ERROR" or n.is_missing: k += 1
        st.extend(n.children)
    return k

def analyze(project, lang, patterns):
    parser = get_parser(lang)
    files = sorted(set(f for pat in patterns for f in glob.glob(pat, recursive=True) if not excluded(f)))
    defs = collections.defaultdict(list); macros = set(); calls = []; cls_methods = {}
    lines = errn = errf = 0
    for path in files:
        src = open(path, "rb").read(); lines += src.count(b"\n")
        tree = parser.parse(src)
        e = errors(tree.root_node); errn += e; errf += 1 if e else 0
        walk(lang, tree.root_node, path, None, defs, macros, calls, cls_methods)

    t = collections.Counter(); amb = collections.Counter(); ext = collections.Counter()
    for path, cls, shape, name in calls:
        if shape == "indirect":
            t["③ 間接(関数ポインタ等)"] += 1; continue
        if shape == "self_member":
            if cls and (cls, name) in cls_methods: t["②-a 自クラス(self./this.)"] += 1
            elif name in defs:                     t["②-b 継承先の可能性"] += 1
            else:                                  t["external(リポジトリ外)"] += 1; ext[name] += 1
            continue
        if shape == "member":
            t["③ 要型解決(他オブジェクトのメンバ)"] += 1; continue
        if name in macros:
            t["macro(関数形式マクロ)"] += 1; continue
        cands = defs.get(name, [])
        same_local = [c for c in cands if c[0] == path and c[2]]
        if same_local:                t["②-a 決定的(同一ファイル優先)"] += 1
        elif len(cands) == 1:         t["②-a 決定的(閉世界で一意)"] += 1
        elif len(cands) == 0:         t["external(リポジトリ外)"] += 1; ext[name] += 1
        else:                         t["②-b 推測(候補複数)"] += 1; amb[name] += 1
    return dict(project=project, lang=lang, files=len(files), lines=lines, errf=errf, errn=errn,
                defs=sum(len(v) for v in defs.values()), macros=len(macros), calls=len(calls),
                t=t, amb=amb.most_common(4), ext=ext.most_common(5))

TARGETS = [
    ("cJSON",            "c",          ["targets/cJSON/*.c", "targets/cJSON/*.h"]),
    ("cmark",            "c",          ["targets/cmark/src/**/*.c", "targets/cmark/src/**/*.h"]),
    ("tinyxml2",         "cpp",        ["targets/tinyxml2/*.cpp", "targets/tinyxml2/*.h"]),
    ("requests",         "python",     ["targets/requests/src/**/*.py"]),
    ("commander.js",     "javascript", ["targets/commander.js/lib/**/*.js", "targets/commander.js/index.js"]),
    ("FluentValidation", "csharp",     ["targets/FluentValidation/src/FluentValidation/**/*.cs"]),
]
A_KEYS = ["②-a 決定的(同一ファイル優先)", "②-a 決定的(閉世界で一意)", "②-a 自クラス(self./this.)"]
B_KEYS = ["②-b 推測(候補複数)", "②-b 継承先の可能性"]
ORDER = A_KEYS + B_KEYS + ["macro(関数形式マクロ)", "external(リポジトリ外)",
                           "③ 要型解決(他オブジェクトのメンバ)", "③ 間接(関数ポインタ等)"]
res = []
for n, l, p in TARGETS:
    r = analyze(n, l, p); res.append(r)
    print("=" * 76)
    print(f"{r['project']}  [{r['lang']}]  {r['files']} ファイル / {r['lines']:,} 行 / 呼び出し {r['calls']:,}")
    print(f"  ERROR: {r['errf']}/{r['files']} ファイル、ノード計 {r['errn']}")
    tot = sum(r['t'].values()) or 1
    for k in ORDER:
        if r['t'].get(k): print(f"    {k:36s} {r['t'][k]:6,}  {r['t'][k]*100.0/tot:5.1f}%")
    a = sum(r['t'][k] for k in A_KEYS); b = sum(r['t'][k] for k in B_KEYS)
    print(f"    {'=== ②-a 合計':36s} {a:6,}  {a*100.0/tot:5.1f}%      ②-b 合計 {b:,} ({b*100.0/tot:.1f}%)")
    if r['amb']: print("  候補複数:", ", ".join(f"{n2}({c})" for n2, c in r['amb']))
    if r['ext']: print("  外部の例:", ", ".join(f"{n2}({c})" for n2, c in r['ext']))

print("\n" + "=" * 76)
print(f"{'project':17s} {'lang':11s} {'呼出':>6s} {'②-a':>7s} {'②-b':>6s} {'macro':>6s} {'外部':>7s} {'型解決':>7s} {'間接':>5s}")
for r in res:
    tot = sum(r['t'].values()) or 1
    a = sum(r['t'][k] for k in A_KEYS); b = sum(r['t'][k] for k in B_KEYS)
    print(f"{r['project']:17s} {r['lang']:11s} {r['calls']:6,} {a*100.0/tot:6.1f}% {b*100.0/tot:5.1f}% "
          f"{r['t']['macro(関数形式マクロ)']*100.0/tot:5.1f}% {r['t']['external(リポジトリ外)']*100.0/tot:6.1f}% "
          f"{r['t']['③ 要型解決(他オブジェクトのメンバ)']*100.0/tot:6.1f}% {r['t']['③ 間接(関数ポインタ等)']*100.0/tot:4.1f}%")
