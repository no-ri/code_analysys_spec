# -*- coding: utf-8 -*-
"""安価な改良の効果を測る（OPEN_DECISIONS.md E-1「初版に含める改良」の実測）。

同じ入力に対して before（改良なし）／after（改良あり）を並べて数える。

  改良A: 同一 container 優先（C# の this. 省略呼び出し。基底型チェーンも辿る）
  改良B: レシーバの宣言型がソースにある → その型のメソッドへ
  改良C: レシーバが型名 → static 呼び出しとして解決
  改良D: ローカル変数／引数として束縛された名前の呼び出し → via_function_pointer

いずれも「1ファイルの構文木 ＋ リポジトリ内の定義表」で完結し、
軸2 = ゼロ（ビルドコンテキストを要求しない）を崩さない。

準備・実行は tools/README.md の「解決可能性の測定」と同じ。
    .venv/bin/python tools/measure-improvements.py
"""

import glob, os, collections
from tree_sitter_language_pack import get_parser

EXCL=("test","tests","fuzz","example","examples","bench","benchmark")
def files_of(pats):
    out=[]
    for p in pats: out.extend(glob.glob(p,recursive=True))
    r=[]
    for f in sorted(set(out)):
        low=f.lower()
        if any(("/%s/"%e) in low for e in EXCL): continue
        if "test" in os.path.basename(low) or "bench" in os.path.basename(low): continue
        r.append(f)
    return r

CS_TYPE={"class_declaration","struct_declaration","record_declaration","interface_declaration"}
CS_FUNC={"method_declaration","constructor_declaration","local_function_statement"}

def txt(n): return n.text.decode(errors="replace")
def base_type(t): return t.rstrip("?").split("<")[0].split(".")[-1].replace("[]","")

def analyze_cs(pats):
    P=get_parser("csharp"); files=files_of(pats)
    types={}; methods=collections.defaultdict(set); byname=collections.defaultdict(list)
    bases={}; trees={}
    for path in files:
        t=P.parse(open(path,"rb").read()); trees[path]=t
        st=[(t.root_node,None)]
        while st:
            n,cls=st.pop()
            cur=cls
            if n.type in CS_TYPE:
                nm=n.child_by_field_name("name")
                if nm is not None:
                    cur=txt(nm); types[cur]=path
                    bl=n.child_by_field_name("bases")
                    if bl is not None:
                        bases[cur]=[base_type(x) for x in txt(bl).lstrip(":").split(",")]
            elif n.type in CS_FUNC:
                nm=n.child_by_field_name("name")
                if nm is not None:
                    mn=txt(nm)
                    if cls: methods[cls].add(mn)
                    byname[mn].append((path,cls))
            for c in n.children: st.append((c,cur))

    def has_method(cls,name,depth=0):
        if not cls or depth>6: return False
        if name in methods.get(cls,()): return True
        return any(has_method(b,name,depth+1) for b in bases.get(cls,()))

    before=collections.Counter(); after=collections.Counter()
    for path in files:
        root=trees[path].root_node
        # そのファイル内の「名前 -> 宣言型」と「ローカル束縛の名前集合」
        declared={}; bound=set()
        st=[root]
        while st:
            n=st.pop()
            if n.type in ("variable_declaration","field_declaration","property_declaration","parameter"):
                ty=n.child_by_field_name("type")
                names=[]
                if n.type=="parameter":
                    nm=n.child_by_field_name("name")
                    if nm is not None: names=[txt(nm)]
                else:
                    s2=[n]
                    while s2:
                        m=s2.pop()
                        if m.type=="variable_declarator":
                            nm=m.child_by_field_name("name")
                            if nm is not None: names.append(txt(nm))
                        s2.extend(m.children)
                    if n.type=="property_declaration":
                        nm=n.child_by_field_name("name")
                        if nm is not None: names.append(txt(nm))
                for nm2 in names:
                    bound.add(nm2)
                    if ty is not None and txt(ty)!="var": declared[nm2]=base_type(txt(ty))
            st.extend(n.children)

        st=[(root,None)]
        while st:
            n,cls=st.pop()
            cur=cls
            if n.type in CS_TYPE:
                nm=n.child_by_field_name("name")
                if nm is not None: cur=txt(nm)
            if n.type=="invocation_expression":
                f=n.child_by_field_name("function")
                # ---- before（現行実装）----
                if f is None: b="via_function_pointer"
                elif f.type=="identifier":
                    nm=txt(f); c=byname.get(nm,[])
                    b = "resolved" if len(c)==1 else ("external" if not c else "ambiguous")
                elif f.type=="member_access_expression":
                    recv=txt(f).rsplit(".",1)[0]
                    b = "resolved" if recv in ("this","base") else "needs_type"
                else: b="via_function_pointer"
                before[b]+=1
                # ---- after（改良後）----
                if f is None: a="via_function_pointer"
                elif f.type=="identifier":
                    nm=txt(f)
                    if nm in bound:                       a="via_function_pointer"   # 改良D
                    elif has_method(cur,nm):              a="resolved"               # 改良A
                    else:
                        c=byname.get(nm,[])
                        a = "resolved" if len(c)==1 else ("external" if not c else "ambiguous")
                elif f.type=="member_access_expression":
                    recv=txt(f).rsplit(".",1)[0]; mn=txt(f).rsplit(".",1)[-1]
                    if recv in ("this","base"):           a="resolved" if has_method(cur,mn) else "needs_type"
                    elif recv in types and has_method(recv,mn): a="resolved"          # 改良C(static)
                    elif recv in declared and has_method(declared[recv],mn): a="resolved"  # 改良B
                    elif recv in declared and declared[recv] not in types: a="external"
                    else:                                 a="needs_type"
                else: a="via_function_pointer"
                after[a]+=1
            for c in n.children: st.append((c,cur))
    return before, after

def analyze_c(pats):
    P=get_parser("c"); files=files_of(pats)
    defs=collections.defaultdict(list); macros=set(); trees={}
    for path in files:
        t=P.parse(open(path,"rb").read()); trees[path]=t
        st=[t.root_node]
        while st:
            n=st.pop()
            if n.type=="function_definition":
                d=n.child_by_field_name("declarator")
                while d is not None and d.type!="identifier":
                    nd=d.child_by_field_name("declarator")
                    if nd is None: break
                    d=nd
                if d is not None and d.type=="identifier":
                    head=n.text[:n.text.find(b"{")] if b"{" in n.text else b""
                    defs[txt(d)].append((path, b"static" in head.split(b"(")[0]))
            elif n.type=="preproc_function_def":
                nm=n.child_by_field_name("name")
                if nm is not None: macros.add(txt(nm))
            st.extend(n.children)

    before=collections.Counter(); after=collections.Counter()
    for path in files:
        root=trees[path].root_node
        bound=set()
        st=[root]
        while st:
            n=st.pop()
            if n.type in ("parameter_declaration","declaration"):
                d=n.child_by_field_name("declarator")
                s2=[d] if d is not None else []
                while s2:
                    m=s2.pop()
                    if m.type=="identifier": bound.add(txt(m))
                    s2.extend(m.children)
            st.extend(n.children)
        st=[root]
        while st:
            n=st.pop()
            if n.type=="call_expression":
                f=n.child_by_field_name("function")
                if f is not None and f.type=="identifier":
                    nm=txt(f)
                    if nm in macros: b=a="macro"
                    else:
                        c=defs.get(nm,[])
                        loc=[x for x in c if x[0]==path and x[1]]
                        b = "resolved" if (loc or len(c)==1) else ("external" if not c else "ambiguous")
                        a = "via_function_pointer" if nm in bound and not c else b   # 改良D
                    before[b]+=1; after[a]+=1
                elif f is not None and f.type=="field_expression":
                    before["needs_type"]+=1; after["needs_type"]+=1
                else:
                    before["via_function_pointer"]+=1; after["via_function_pointer"]+=1
            st.extend(n.children)
    return before, after

def report(name, before, after):
    keys=sorted(set(before)|set(after))
    tot=sum(before.values()) or 1
    print(f"--- {name}  呼び出し {tot:,} 件")
    print(f"    {'分類':22s} {'before':>8s} {'after':>8s} {'差':>8s}")
    for k in keys:
        d=after[k]-before[k]
        mark=" ★" if abs(d)>=10 else ""
        print(f"    {k:22s} {before[k]:8,} {after[k]:8,} {d:+8,}{mark}")
    print(f"    {'resolved 率':22s} {before['resolved']*100.0/tot:7.1f}% {after['resolved']*100.0/tot:7.1f}%"
          f"  →  {(after['resolved']-before['resolved'])*100.0/tot:+.1f} ポイント\n")

b,a=analyze_c(["targets/cJSON/*.c","targets/cJSON/*.h"]);              report("cJSON [C]",b,a)
b,a=analyze_c(["targets/cmark/src/**/*.c","targets/cmark/src/**/*.h"]); report("cmark [C]",b,a)
b,a=analyze_cs(["targets/FluentValidation/src/FluentValidation/**/*.cs"]); report("FluentValidation [C#]",b,a)
