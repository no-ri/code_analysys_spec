# -*- coding: utf-8 -*-
"""C# のメンバ呼び出しのレシーバ内訳を測る（OPEN_DECISIONS.md E-3 の追加測定）。

measure-resolvability.py が C# で ②-a 5.2% と出したのが過小評価かを確かめるためのもの。
レシーバが単純識別子で、その宣言に明示的な型が書いてあれば、型推論なしで
（段階1+3 だけで）型が分かる。準備と実行方法は measure-resolvability.py と同じ。
"""

import glob, os, collections
from tree_sitter_language_pack import get_parser

EXCLUDE_DIR = ("test","tests","fuzz","example","examples","samples","sample","benchmark","bench","node_modules")
def excluded(p):
    p=p.lower().replace("\\","/")
    if any(("/%s/"%e) in p for e in EXCLUDE_DIR): return True
    b=os.path.basename(p); return "test" in b or "bench" in b

def analyze_csharp(patterns):
    parser=get_parser("csharp")
    files=sorted(set(f for pat in patterns for f in glob.glob(pat,recursive=True) if not excluded(f)))
    # 型が明示された変数/フィールド/プロパティ/引数の名前 -> 型名（ファイル単位）
    stats=collections.Counter(); typed_ex=collections.Counter(); untyped_ex=collections.Counter()
    repo_types=set()
    per_file=[]
    for path in files:
        src=open(path,'rb').read(); tree=parser.parse(src)
        typed={}; untyped=set()
        st=[tree.root_node]
        while st:
            n=st.pop()
            if n.type in ("class_declaration","struct_declaration","record_declaration","interface_declaration"):
                nm=n.child_by_field_name("name")
                if nm is not None: repo_types.add(nm.text.decode(errors="replace"))
            if n.type in ("variable_declaration","field_declaration","property_declaration","parameter"):
                ty=n.child_by_field_name("type")
                if ty is not None:
                    tname=ty.text.decode(errors="replace")
                    names=[]
                    if n.type=="parameter":
                        nm=n.child_by_field_name("name")
                        if nm is not None: names=[nm.text.decode(errors="replace")]
                    else:
                        s2=[n]
                        while s2:
                            m=s2.pop()
                            if m.type=="variable_declarator":
                                nm=m.child_by_field_name("name")
                                if nm is not None: names.append(nm.text.decode(errors="replace"))
                            s2.extend(m.children)
                        if n.type=="property_declaration":
                            nm=n.child_by_field_name("name")
                            if nm is not None: names.append(nm.text.decode(errors="replace"))
                    for nm2 in names:
                        if tname=="var": untyped.add(nm2)
                        else: typed[nm2]=tname
            st.extend(n.children)
        per_file.append((path,tree,typed,untyped))

    for path,tree,typed,untyped in per_file:
        st=[tree.root_node]
        while st:
            n=st.pop()
            if n.type=="invocation_expression":
                f=n.child_by_field_name("function")
                if f is not None and f.type=="member_access_expression":
                    obj=f.child_by_field_name("expression")
                    if obj is None: obj=f.child_by_field_name("object")
                    if obj is not None and obj.type=="identifier":
                        rname=obj.text.decode(errors="replace")
                        if rname in ("this","base"): stats["self/base"]+=1
                        elif rname in typed:
                            t=typed[rname].rstrip("?").split("<")[0]
                            if t in repo_types:
                                stats["型が明示 & 型がリポジトリ内 → 解決可能"]+=1; typed_ex[typed[rname]]+=1
                            else:
                                stats["型が明示だが型がリポジトリ外"]+=1
                        elif rname in untyped:
                            stats["var 宣言（型推論が要る）"]+=1; untyped_ex[rname]+=1
                        elif rname and rname[0].isupper():
                            stats["レシーバが型名（static 呼び出し）"]+=1
                        else:
                            stats["宣言が同一ファイルに見つからない"]+=1
                    else:
                        stats["レシーバが式（チェーン等）"]+=1
            st.extend(n.children)
    return stats, typed_ex.most_common(5), untyped_ex.most_common(5), len(repo_types)

stats, tex, uex, ntypes = analyze_csharp(["targets/FluentValidation/src/FluentValidation/**/*.cs"])
tot=sum(stats.values()) or 1
print("FluentValidation [csharp] メンバ呼び出しの内訳（リポジトリ内で宣言された型 %d 種）" % ntypes)
for k,v in stats.most_common():
    print(f"  {k:38s} {v:5,}  {v*100.0/tot:5.1f}%")
print("\n  型が明示されていた例:", ", ".join(f"{n}({c})" for n,c in tex))
print("  var だった例        :", ", ".join(f"{n}({c})" for n,c in uex))
