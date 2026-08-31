# -*- coding: utf-8 -*-
"""②-a の的中率を人手で検証するための標本を抽出する（F-16）。

②-a は `status = resolved` / `confidence = medium` を名乗っているが、
**それが実際に正しい先を指しているかは一度も検証していない**。
本スクリプトは検証対象の標本を**規則ごとに層化して**抽出し、
人が judge するのに必要な文脈（呼び出し元・呼び先の実際の行）を並べて出す。

**規則ごとに層化する理由**: 規則によって外し方が違うため、全体の的中率より
「どの規則が外すか」の方が対策に直結する（規則ごとに confidence を分けられる）。
単純無作為だと出現数の少ない規則が標本に入らない。

突合キーは J-5 の `(file, start_line, start_col, kind)`。
対象コミットは固定（J-5「ゴールデンデータは特定コミットに固定する」）:
    cJSON            fb16e5cf358798aabb049655975cde8427101056
    FluentValidation daa00b795450881c233253488e3ddeb362f59f56

    .venv/bin/python tools/sample-golden.py --lang c|csharp [--seed 20260831]
"""

import glob, os, collections, random, argparse
from tree_sitter_language_pack import get_parser

EXCL = ("test", "tests", "fuzz", "example", "examples", "samples", "sample",
        "benchmark", "bench", "node_modules", "third_party", "vendor", "api_test")

def files_of(pats):
    out = []
    for p in pats: out.extend(glob.glob(p, recursive=True))
    r = []
    for f in sorted(set(out)):
        low = f.lower().replace("\\", "/")
        if any(("/%s/" % e) in low for e in EXCL): continue
        b = os.path.basename(low)
        if "test" in b or "bench" in b or b.startswith("fuzz"): continue
        r.append(f)
    return r

def txt(n): return n.text.decode(errors="replace")
def base_type(t): return t.rstrip("?").split("<")[0].split(".")[-1].replace("[]", "")
def src_lines(path): return open(path, encoding="utf-8", errors="replace").read().split("\n")

def context(path, line, before=1, after=1):
    L = src_lines(path)
    lo, hi = max(0, line - 1 - before), min(len(L), line + after)
    return [(i + 1, L[i]) for i in range(lo, hi)]

def collect_c(pats):
    P = get_parser("c"); files = files_of(pats)
    defs = collections.defaultdict(list); macros = set(); trees = {}
    for path in files:
        t = P.parse(open(path, "rb").read()); trees[path] = t
        st = [t.root_node]
        while st:
            n = st.pop()
            if n.type == "function_definition":
                d = n.child_by_field_name("declarator")
                while d is not None and d.type != "identifier":
                    nd = d.child_by_field_name("declarator")
                    if nd is None: break
                    d = nd
                if d is not None and d.type == "identifier":
                    head = n.text[:n.text.find(b"{")] if b"{" in n.text else b""
                    defs[txt(d)].append((path, d.start_point[0] + 1,
                                         b"static" in head.split(b"(")[0]))
            elif n.type == "preproc_function_def":
                nm = n.child_by_field_name("name")
                if nm is not None: macros.add(txt(nm))
            st.extend(n.children)
    rows = []
    for path in files:
        st = [trees[path].root_node]
        while st:
            n = st.pop()
            if n.type == "call_expression":
                f = n.child_by_field_name("function")
                if f is not None and f.type == "identifier":
                    nm = txt(f)
                    if nm not in macros:
                        c = defs.get(nm, [])
                        loc = [x for x in c if x[0] == path and x[2]]
                        rule = dst = None
                        if loc: rule, dst = "規則1 同一ファイルの static 優先", loc[0]
                        elif len(c) == 1: rule, dst = "規則2 閉世界で候補が一意", c[0]
                        if rule:
                            rows.append(dict(rule=rule, file=path,
                                             line=n.start_point[0] + 1, col=n.start_point[1] + 1,
                                             expr=txt(f), dst_file=dst[0], dst_line=dst[1],
                                             note="static" if dst[2] else "extern", cands=len(c)))
            st.extend(n.children)
    return rows

CS_TYPE = {"class_declaration", "struct_declaration", "record_declaration", "interface_declaration"}
CS_FUNC = {"method_declaration", "constructor_declaration", "local_function_statement"}

def collect_cs(pats):
    P = get_parser("csharp"); files = files_of(pats)
    types = {}; methods = collections.defaultdict(set); byname = collections.defaultdict(list)
    bases = {}; trees = {}; mloc = {}; arity = collections.defaultdict(set)
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
                if nm is not None:
                    mn = txt(nm)
                    pl = n.child_by_field_name("parameters")
                    na = len([c for c in pl.children if c.type == "parameter"]) if pl is not None else -1
                    if cls:
                        methods[cls].add(mn)
                        mloc.setdefault((cls, mn), []).append((path, nm.start_point[0] + 1, na))
                        arity[(cls, mn)].add(na)
                    byname[mn].append((path, cls, nm.start_point[0] + 1))
            for c in n.children: st.append((c, cur))

    def owner_of(cls, name, d=0):
        if not cls or d > 6: return None
        if name in methods.get(cls, ()): return cls
        for b in bases.get(cls, ()):
            r = owner_of(b, name, d + 1)
            if r: return r
        return None

    rows = []
    for path in files:
        root = trees[path].root_node
        declared = {}; bound = set()
        st = [root]
        while st:
            n = st.pop()
            if n.type in ("variable_declaration", "field_declaration", "property_declaration", "parameter"):
                ty = n.child_by_field_name("type"); names = []
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
                    bound.add(nm2)
                    if ty is not None and txt(ty) != "var": declared[nm2] = base_type(txt(ty))
            st.extend(n.children)
        st = [(root, None)]
        while st:
            n, cls = st.pop(); cur = cls
            if n.type in CS_TYPE:
                nm = n.child_by_field_name("name")
                if nm is not None: cur = txt(nm)
            if n.type == "invocation_expression":
                f = n.child_by_field_name("function")
                al = n.child_by_field_name("arguments")
                nargs = len([c for c in al.children if c.type == "argument"]) if al is not None else -1
                rule = owner = mn = None
                if f is not None and f.type == "identifier":
                    mn = txt(f)
                    if mn in bound: pass
                    elif owner_of(cur, mn): rule, owner = "規則A 同一 container(this. 省略)", owner_of(cur, mn)
                    elif len(byname.get(mn, [])) == 1: rule = "規則2 閉世界で候補が一意"
                elif f is not None and f.type == "member_access_expression":
                    recv = txt(f).rsplit(".", 1)[0]; mn = txt(f).rsplit(".", 1)[-1]
                    if recv in ("this", "base") and owner_of(cur, mn):
                        rule, owner = "規則3 this./base. 経由", owner_of(cur, mn)
                    elif recv in types and owner_of(recv, mn):
                        rule, owner = "規則C 型名 → static", owner_of(recv, mn)
                    elif recv in declared and owner_of(declared[recv], mn):
                        rule, owner = "規則B レシーバの宣言型", owner_of(declared[recv], mn)
                if rule:
                    if owner:
                        locs = mloc.get((owner, mn), []); ar = sorted(arity.get((owner, mn), []))
                    else:
                        b0 = byname[mn][0]; locs = [(b0[0], b0[2], -1)]; ar = []
                    rows.append(dict(rule=rule, file=path, line=n.start_point[0] + 1,
                                     col=n.start_point[1] + 1, expr=txt(f) if f is not None else "?",
                                     owner=owner, mname=mn, nargs=nargs,
                                     dst_file=locs[0][0] if locs else None,
                                     dst_line=locs[0][1] if locs else None,
                                     n_overload=len(locs), arities=ar, enclosing=cur))
            for c in n.children: st.append((c, cur))
    return rows

def emit(rows, per_rule, seed, title):
    rnd = random.Random(seed)
    by = collections.defaultdict(list)
    for r in rows: by[r["rule"]].append(r)
    print("=" * 78)
    print(f"{title}   母集団 {len(rows)} 件 / seed={seed}")
    print("=" * 78)
    for rule in sorted(by):
        pop = sorted(by[rule], key=lambda r: (r["file"], r["line"], r["col"]))
        k = min(per_rule, len(pop))
        smp = sorted(rnd.sample(pop, k), key=lambda r: (r["file"], r["line"]))
        print(f"\n### {rule}   母集団 {len(pop)} 件 → 標本 {k} 件\n")
        for i, r in enumerate(smp, 1):
            print(f"[{i:02d}] {os.path.relpath(r['file'])}:{r['line']}:{r['col']}  `{r['expr']}`")
            if r.get("owner") is not None or r.get("n_overload"):
                extra = f"  owner={r.get('owner')} 実引数={r.get('nargs')}"
                if r.get("n_overload", 0) > 1:
                    extra += f"  **オーバーロード {r['n_overload']} 件 引数個数={r.get('arities')}**"
                elif r.get("arities"): extra += f" 仮引数={r['arities']}"
                print("     " + extra)
            else:
                print(f"     候補 {r.get('cands')} 件 / 呼び先は {r.get('note')}")
            print("     -- 呼び出し元 --")
            for ln, s in context(r["file"], r["line"], 1, 1):
                print(f"     {'>' if ln == r['line'] else ' '}{ln:6d}| {s[:105]}")
            if r["dst_file"]:
                print(f"     -- 主張する呼び先: {os.path.relpath(r['dst_file'])}:{r['dst_line']} --")
                for ln, s in context(r["dst_file"], r["dst_line"], 1, 0):
                    print(f"     {'>' if ln == r['dst_line'] else ' '}{ln:6d}| {s[:105]}")
            print()

def emit_tsv(rows, per_rule, seed):
    """J-5 の突合キー (file, start_line, start_col, kind) で標本を TSV 出力する。"""
    rnd = random.Random(seed)
    by = collections.defaultdict(list)
    for r in rows: by[r["rule"]].append(r)
    print("file\tstart_line\tstart_col\tkind\trule\texpr\tclaimed_dst_file\tclaimed_dst_line\tn_overload")
    for rule in sorted(by):
        pop = sorted(by[rule], key=lambda r: (r["file"], r["line"], r["col"]))
        for r in sorted(rnd.sample(pop, min(per_rule, len(pop))), key=lambda r: (r["file"], r["line"])):
            print("\t".join(str(x) for x in [
                os.path.relpath(r["file"]), r["line"], r["col"], "call", rule, r["expr"],
                os.path.relpath(r["dst_file"]) if r["dst_file"] else "",
                r["dst_line"] if r["dst_line"] else "", r.get("n_overload", 1)]))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["c", "csharp"], required=True)
    ap.add_argument("--seed", type=int, default=20260831)
    ap.add_argument("--per-rule", type=int, default=25)
    ap.add_argument("--tsv", action="store_true", help="人手判定を書き込むための TSV を出す")
    a = ap.parse_args()
    rows = (collect_c(["targets/cJSON/*.c", "targets/cJSON/*.h"]) if a.lang == "c"
            else collect_cs(["targets/FluentValidation/src/FluentValidation/**/*.cs"]))
    title = ("cJSON [C] fb16e5c  ②-a の標本" if a.lang == "c"
             else "FluentValidation [C#] daa00b7  ②-a（改良後 resolved）の標本")
    (emit_tsv(rows, a.per_rule, a.seed) if a.tsv else emit(rows, a.per_rule, a.seed, title))
