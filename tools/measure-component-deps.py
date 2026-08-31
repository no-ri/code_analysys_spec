# -*- coding: utf-8 -*-
"""レポート4「コンポーネント依存」が C# で成立するかを再測定する（F-10 の実測）。

E-1 は「C# の内部コンポーネント依存図は、この最小構成では描けない」と結論したが、
その実測は**改良A〜D を入れる前**（`resolved` 5.5%）の DB に対するものだった。
改良A〜D は E-1 が初版必須と決めたものなので、**改良後（31.8%）で測り直す**必要がある。

E-1 の帰結文自身が「描くには段階5（型解決）か、少なくとも**レシーバの型名からの近似**が要る」
と書いており、改良B（レシーバの宣言型を使う）／改良C（型名なら static 呼び出し）が
まさにその近似にあたる。

解決した呼び出しを src ディレクトリ → dst ディレクトリに畳み、
コンポーネント間のエッジが何本立つかを数える。結論は `docs/OPEN_DECISIONS.md` F-10。

    .venv/bin/python tools/measure-component-deps.py
"""
import glob, os, collections
from tree_sitter_language_pack import get_parser
ROOT="targets/FluentValidation/src/FluentValidation"
PATS=[ROOT+"/**/*.cs"]
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
P=get_parser("csharp")
CS_TYPE={"class_declaration","struct_declaration","record_declaration","interface_declaration"}
CS_FUNC={"method_declaration","constructor_declaration","local_function_statement"}
def txt(n): return n.text.decode(errors="replace")
def bt(t): return t.rstrip("?").split("<")[0].split(".")[-1].replace("[]","")
def comp(path):
    d=os.path.dirname(os.path.relpath(path, ROOT))
    return d if d else "(root)"
files=files_of(PATS)
types={}; methods=collections.defaultdict(set); byname=collections.defaultdict(list)
bases={}; trees={}; mfile={}
for path in files:
    t=P.parse(open(path,"rb").read()); trees[path]=t
    st=[(t.root_node,None)]
    while st:
        n,cls=st.pop(); cur=cls
        if n.type in CS_TYPE:
            nm=n.child_by_field_name("name")
            if nm is not None:
                cur=txt(nm); types[cur]=path
                bl=n.child_by_field_name("bases")
                if bl is not None: bases[cur]=[bt(x) for x in txt(bl).lstrip(":").split(",")]
        elif n.type in CS_FUNC:
            nm=n.child_by_field_name("name")
            if nm is not None:
                if cls: methods[cls].add(txt(nm)); mfile[(cls,txt(nm))]=path
                byname[txt(nm)].append((path,cls))
        for c in n.children: st.append((c,cur))
def owner_of(cls,name,d=0):
    """メソッドを実際に宣言している型を返す（基底も辿る）。無ければ None"""
    if not cls or d>6: return None
    if name in methods.get(cls,()): return cls
    for b in bases.get(cls,()):
        r=owner_of(b,name,d+1)
        if r: return r
    return None

edges=collections.Counter(); resolved=0; total=0
for path in files:
    root=trees[path].root_node
    declared={}; bound=set()
    st=[root]
    while st:
        n=st.pop()
        if n.type in ("variable_declaration","field_declaration","property_declaration","parameter"):
            ty=n.child_by_field_name("type"); names=[]
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
                if ty is not None and txt(ty)!="var": declared[nm2]=bt(txt(ty))
        st.extend(n.children)
    st=[(root,None)]
    while st:
        n,cls=st.pop(); cur=cls
        if n.type in CS_TYPE:
            nm=n.child_by_field_name("name")
            if nm is not None: cur=txt(nm)
        if n.type=="invocation_expression":
            total+=1
            f=n.child_by_field_name("function"); dstf=None
            if f is not None and f.type=="identifier":
                nm=txt(f)
                if nm in bound: pass                               # 改良D
                else:
                    o=owner_of(cur,nm)                             # 改良A
                    if o: dstf=mfile.get((o,nm))
                    else:
                        c=byname.get(nm,[])
                        if len(c)==1: dstf=c[0][0]
            elif f is not None and f.type=="member_access_expression":
                recv=txt(f).rsplit(".",1)[0]; mn=txt(f).rsplit(".",1)[-1]
                if recv in ("this","base"):
                    o=owner_of(cur,mn)
                    if o: dstf=mfile.get((o,mn))
                elif recv in types:
                    o=owner_of(recv,mn)                            # 改良C(static)
                    if o: dstf=mfile.get((o,mn))
                elif recv in declared:
                    o=owner_of(declared[recv],mn)                  # 改良B
                    if o: dstf=mfile.get((o,mn))
            if dstf:
                resolved+=1; edges[(comp(path),comp(dstf))]+=1
        for c in n.children: st.append((c,cur))

print(f"呼び出し {total} 件 / 解決 {resolved} 件 ({resolved*100.0/total:.1f}%)\n")
comps=sorted({c for e in edges for c in e})
print(f"コンポーネント（ディレクトリ）数: {len(comps)}  → {comps}")
self_e=[e for e in edges if e[0]==e[1]]; cross=[e for e in edges if e[0]!=e[1]]
print(f"エッジ: 合計 {len(edges)} 種  自己ループ {len(self_e)} 種  "
      f"**コンポーネント間 {len(cross)} 種**")
print(f"呼び出し件数: 自己ループ内 {sum(edges[e] for e in self_e)}  コンポーネント間 {sum(edges[e] for e in cross)}\n")
print("--- コンポーネント間のエッジ（依存図に描かれる線）")
for (a,b),c in sorted(edges.items(), key=lambda x:-x[1]):
    if a!=b: print(f"  {a:22s} → {b:22s} {c:5d}")
print("\n--- 自己ループ（参考）")
for (a,b),c in sorted(edges.items(), key=lambda x:-x[1]):
    if a==b: print(f"  {a:22s} → {b:22s} {c:5d}")
