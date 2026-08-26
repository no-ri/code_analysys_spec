# -*- coding: utf-8 -*-
"""汎用スキーマ案の検証（OPEN_DECISIONS.md E-1 の実測に使用）。

C と C# を「同じ列」に出せるかを確かめる。言語固有の概念
（static/extern, namespace/type）を汎用概念（visibility, container_id）へ写す。

準備・実行は tools/README.md の「解決可能性の測定」と同じ。
    .venv/bin/python tools/emit-generic-schema.py

出力: facts.sqlite（files / symbols / refs の3テーブル）と、両言語の突き合わせ表。

注意: これは設計検証用の使い捨てスクリプトであり、実装の雛形ではない。
      既知の未対応: C# の file-scoped namespace（`namespace X;`）、
      シンボルID にシグネチャを含めていないためオーバーロードで衝突する
      （E-1「発見1」「発見2」。いずれも意図的に残し、問題を可視化している）。
"""

import os, glob, sqlite3, collections, subprocess
from tree_sitter_language_pack import get_parser

# ---------------- 汎用スキーマ ----------------
SCHEMA = """
CREATE TABLE files(
  path TEXT PRIMARY KEY, lang TEXT, lines INT, comment_lines INT,
  parse_errors INT, extractor TEXT, snapshot TEXT);
CREATE TABLE symbols(
  id TEXT PRIMARY KEY, kind TEXT, name TEXT, container_id TEXT,
  file TEXT, start_line INT, end_line INT,
  visibility TEXT, is_definition INT, branch_count INT,
  lang TEXT, extractor TEXT, snapshot TEXT, confidence TEXT);
CREATE TABLE refs(
  src_id TEXT, dst_id TEXT, dst_expr TEXT, kind TEXT,
  file TEXT, line INT, status TEXT, reason TEXT, confidence TEXT,
  lang TEXT, extractor TEXT, snapshot TEXT);
"""
BRANCH = {"if_statement","for_statement","while_statement","do_statement","switch_statement",
          "case_statement","switch_section","catch_clause","conditional_expression",
          "ternary_expression","for_each_statement","preproc_if","preproc_ifdef"}
COMMENT = {"comment"}

def snapshot_of(root):
    try:
        return subprocess.run(["git","describe","--always","--dirty"],cwd=root,
                              capture_output=True,text=True,timeout=10).stdout.strip() or "nogit"
    except Exception:
        return "nogit"

def count(node, types):
    st, k = [node], 0
    while st:
        n = st.pop()
        if n.type in types: k += 1
        st.extend(n.children)
    return k

def errors(node):
    st, k = [node], 0
    while st:
        n = st.pop()
        if n.type == "ERROR" or n.is_missing: k += 1
        st.extend(n.children)
    return k

# ---------------- C ----------------
def decl_ident(n):
    d = n.child_by_field_name("declarator")
    while d is not None and d.type not in ("identifier","field_identifier","qualified_identifier"):
        nd = d.child_by_field_name("declarator")
        if nd is None: return None
        d = nd
    return d

def extract_c(root, path, repo, snap, sink):
    file_id = f"local {repo} {snap} {path}/"
    sink.symbols.append((file_id,"file",os.path.basename(path),None,path,1,
                         root.end_point[0]+1,"module",1,0,"c","tree-sitter-c",snap,"high"))
    def walk(n, encl):
        t = n.type
        cur = encl
        if t == "function_definition":
            d = decl_ident(n)
            if d is not None:
                name = d.text.decode(errors="replace").split("::")[-1]
                head = n.text[:n.text.find(b"{")] if b"{" in n.text else n.text[:80]
                is_static = b"static" in head.split(b"(")[0]
                vis = "module" if is_static else "public"
                sid = (f"local {repo} {snap} {path}/{name}()." if is_static
                       else f"local {repo} {snap} {name}().")
                sink.symbols.append((sid,"function",name,file_id,path,
                                     n.start_point[0]+1,n.end_point[0]+1,vis,1,
                                     count(n,BRANCH),"c","tree-sitter-c",snap,"high"))
                sink.by_name[name].append((sid,path,vis))
                cur = sid
        elif t == "preproc_function_def":
            nm = n.child_by_field_name("name")
            if nm is not None:
                name = nm.text.decode(errors="replace")
                sid = f"local {repo} {snap} {path}/{name}!"      # SCIP の macro descriptor
                sink.symbols.append((sid,"macro",name,file_id,path,n.start_point[0]+1,
                                     n.end_point[0]+1,"module",1,0,"c","tree-sitter-c",snap,"high"))
                sink.macros[name] = sid
        elif t == "preproc_include":
            p = n.child_by_field_name("path")
            if p is not None:
                sink.rawrefs.append((cur or file_id, p.text.decode(errors="replace").strip('"<>'),
                                     "import", path, n.start_point[0]+1, "c"))
        elif t == "call_expression":
            f = n.child_by_field_name("function")
            shape = ("direct" if f is not None and f.type=="identifier" else
                     "member" if f is not None and f.type in ("field_expression",) else "indirect")
            expr = f.text.decode(errors="replace") if f is not None else "?"
            sink.rawcalls.append((cur or file_id, expr, shape, path, n.start_point[0]+1, "c"))
        for c in n.children: walk(c, cur)
    walk(root, None)

# ---------------- C# ----------------
CS_TYPE = {"class_declaration","struct_declaration","record_declaration","interface_declaration"}
CS_FUNC = {"method_declaration","constructor_declaration","local_function_statement"}
ACCESS = {"public":"public","internal":"module","private":"private",
          "protected":"private","file":"module"}

def extract_cs(root, path, repo, snap, sink):
    file_id = f"local {repo} {snap} {path}/"
    sink.symbols.append((file_id,"file",os.path.basename(path),None,path,1,
                         root.end_point[0]+1,"module",1,0,"csharp","tree-sitter-c-sharp",snap,"high"))
    def vis_of(n):
        for c in n.children:
            if c.type == "modifier" and c.text.decode(errors="replace") in ACCESS:
                return ACCESS[c.text.decode(errors="replace")]
        return "private" if n.type in CS_FUNC else "module"
    def walk(n, encl, desc):
        t = n.type; cur, d2 = encl, desc
        if t == "namespace_declaration":
            nm = n.child_by_field_name("name")
            if nm is not None:
                nsname = nm.text.decode(errors="replace")
                d2 = desc + nsname.replace(".","/") + "/"
                sid = f"local {repo} {snap} {d2}"
                sink.symbols.append((sid,"namespace",nsname,encl,path,n.start_point[0]+1,
                                     n.end_point[0]+1,"public",1,0,"csharp","tree-sitter-c-sharp",snap,"high"))
                cur = sid
        elif t in CS_TYPE:
            nm = n.child_by_field_name("name")
            if nm is not None:
                tn = nm.text.decode(errors="replace")
                d2 = desc + tn + "#"
                sid = f"local {repo} {snap} {d2}"
                sink.symbols.append((sid,"type",tn,encl,path,n.start_point[0]+1,n.end_point[0]+1,
                                     vis_of(n),1,0,"csharp","tree-sitter-c-sharp",snap,"high"))
                sink.types[tn] = sid
                cur = sid; d2 = d2
        elif t in CS_FUNC:
            nm = n.child_by_field_name("name")
            if nm is not None:
                mn = nm.text.decode(errors="replace")
                sid = f"local {repo} {snap} {desc}{mn}()."
                sink.symbols.append((sid,"method",mn,encl,path,n.start_point[0]+1,n.end_point[0]+1,
                                     vis_of(n),1,count(n,BRANCH),"csharp","tree-sitter-c-sharp",snap,"high"))
                sink.by_name[mn].append((sid,path,vis_of(n)))
                if encl: sink.owner_methods[(encl,mn)] = sid
                cur = sid
        elif t == "using_directive":
            sink.rawrefs.append((cur or file_id, n.text.decode(errors="replace")[5:].strip().rstrip(";"),
                                 "import", path, n.start_point[0]+1, "csharp"))
        elif t == "invocation_expression":
            f = n.child_by_field_name("function")
            shape = ("direct" if f is not None and f.type=="identifier" else
                     "member" if f is not None and f.type=="member_access_expression" else "indirect")
            expr = f.text.decode(errors="replace") if f is not None else "?"
            sink.rawcalls.append((cur or file_id, expr, shape, path, n.start_point[0]+1, "csharp"))
        for c in n.children: walk(c, cur, d2)
    walk(root, None, "")

class Sink:
    def __init__(self):
        self.symbols=[]; self.rawcalls=[]; self.rawrefs=[]
        self.by_name=collections.defaultdict(list); self.macros={}
        self.types={}; self.owner_methods={}

EXCL=("test","tests","fuzz","example","examples","bench","benchmark","node_modules")
def files_of(pats):
    out=[]
    for p in pats: out.extend(glob.glob(p,recursive=True))
    res=[]
    for f in sorted(set(out)):
        low=f.lower()
        if any(("/%s/"%e) in low for e in EXCL): continue
        if "test" in os.path.basename(low) or "bench" in os.path.basename(low): continue
        res.append(f)
    return res

def build(db, project, lang, repo_root, pats):
    snap = snapshot_of(repo_root)
    parser = get_parser("c" if lang=="c" else "csharp")
    sink = Sink(); frows=[]
    for path in files_of(pats):
        src=open(path,"rb").read(); tree=parser.parse(src)
        frows.append((path, lang, src.count(b"\n"), count(tree.root_node,COMMENT),
                      errors(tree.root_node),
                      "tree-sitter-c" if lang=="c" else "tree-sitter-c-sharp", snap))
        (extract_c if lang=="c" else extract_cs)(tree.root_node, path, project, snap, sink)

    # ---- 解決 ----
    refrows=[]
    ext="tree-sitter-c" if lang=="c" else "tree-sitter-c-sharp"
    for src_id, expr, shape, path, line, lg in sink.rawcalls:
        dst=None; status="unresolved"; reason=None; conf="low"
        if shape=="member":
            recv, _, mname = expr.rpartition(".")
            if recv in ("this","base") and lang=="csharp":
                owner = src_id.rsplit("#",1)[0]+"#" if "#" in src_id else None
                key=None
                for (o,m),sid in sink.owner_methods.items():
                    if m==mname and o and src_id.startswith(o.rsplit(" ",1)[0]): key=sid; break
                if key: dst, status, reason, conf = key, "resolved", None, "medium"
                else:   reason, conf = "needs_type", "low"
            else:
                reason, conf = "needs_type", "low"
        elif shape=="indirect":
            reason, conf = "via_function_pointer", "low"
        else:
            name=expr.split("::")[-1].split(".")[-1]
            if name in sink.macros:
                dst, status, reason, conf = sink.macros[name], "resolved", "macro_expanded", "medium"
            else:
                cands=sink.by_name.get(name,[])
                local=[c for c in cands if c[1]==path and c[2]=="module"]
                if local:            dst,status,conf = local[0][0],"resolved","medium"
                elif len(cands)==1:  dst,status,conf = cands[0][0],"resolved","medium"
                elif not cands:      reason,conf = "external","high"
                else:                reason,conf = "ambiguous","low"
        refrows.append((src_id,dst,expr,"call",path,line,status,reason,conf,lg,ext,snap))
    for src_id, target, kind, path, line, lg in sink.rawrefs:
        refrows.append((src_id,None,target,kind,path,line,"unresolved","external","low",lg,ext,snap))

    db.executemany("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?)", frows)
    db.executemany("INSERT OR REPLACE INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sink.symbols)
    db.executemany("INSERT INTO refs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", refrows)
    db.commit()
    return snap

dbpath="facts.sqlite"
if os.path.exists(dbpath): os.remove(dbpath)
db=sqlite3.connect(dbpath); db.executescript(SCHEMA)
s1=build(db,"cJSON","c","targets/cJSON",["targets/cJSON/*.c","targets/cJSON/*.h"])
s2=build(db,"FluentValidation","csharp","targets/FluentValidation",
         ["targets/FluentValidation/src/FluentValidation/**/*.cs"])
print("snapshot: cJSON=%s  FluentValidation=%s\n" % (s1,s2))

def show(sql, title, params=()):
    print("--- %s" % title)
    cur=db.execute(sql,params)
    cols=[d[0] for d in cur.description]; rows=cur.fetchall()
    w=[max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c)) for i,c in enumerate(cols)]
    w=[min(x,46) for x in w]
    print("  " + " | ".join(str(c).ljust(w[i])[:w[i]] for i,c in enumerate(cols)))
    for r in rows:
        print("  " + " | ".join(str(x).ljust(w[i])[:w[i]] for i,x in enumerate(r)))
    print()

show("SELECT lang, COUNT(*) files, SUM(lines) lines, SUM(comment_lines) comments, SUM(parse_errors) errs FROM files GROUP BY lang","files")
show("SELECT lang, kind, COUNT(*) n FROM symbols GROUP BY lang,kind ORDER BY lang,n DESC","symbols: kind の分布（同じ列で両言語）")
show("SELECT lang, visibility, COUNT(*) n FROM symbols WHERE kind IN('function','method') GROUP BY lang,visibility ORDER BY lang,n DESC","symbols: visibility（static/extern と public/internal を同じ語彙へ）")
show("SELECT lang, status, COALESCE(reason,'-') reason, confidence, COUNT(*) n FROM refs WHERE kind='call' GROUP BY lang,status,reason,confidence ORDER BY lang, n DESC","refs: 呼び出しの解決状況")
show("SELECT id, kind, name, visibility, branch_count FROM symbols WHERE lang='c' AND kind='function' ORDER BY branch_count DESC LIMIT 4","C のシンボルID実例")
show("SELECT id, kind, name, visibility, branch_count FROM symbols WHERE lang='csharp' AND kind='method' ORDER BY branch_count DESC LIMIT 4","C# のシンボルID実例")
db.close()
