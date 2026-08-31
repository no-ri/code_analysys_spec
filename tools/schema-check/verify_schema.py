#!/usr/bin/env python3
"""SCHEMA.md の DDL を抜き出して実行し、文書に書いた性質が実際に成り立つか確かめる。

「スキーマを説明した文書」ではなく「実行される DDL を含む文書」にするための検証。
J 群 / K 群で見つかった破綻（NOT NULL の欠落・JOIN の増殖・ATTACH の二重計上）は
すべて「決定は正しいのに動かない」形だったため、記述だけでは防げない。
"""
import os, re, sqlite3, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MD = os.path.join(ROOT, "spec", "SCHEMA.md")

def ddl_from_schema_md():
    body = open(MD, encoding="utf-8").read()
    blocks = re.findall(r"```sql\n(.*?)```", body, re.S)
    ddl = "\n".join(b for b in blocks if "CREATE TABLE" in b)
    if ddl.count("CREATE TABLE") != 5:
        raise SystemExit(f"CREATE TABLE が 5 個ではない: {ddl.count('CREATE TABLE')}")
    return ddl

fails = []
def check(name, cond, detail=""):
    print(f"  [{'OK' if cond else 'NG'}] {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond: fails.append(name)

DDL = ddl_from_schema_md()
E, SNAP = "tree-sitter-c", "8f3ac21"

print("1. DDL が通る")
db = sqlite3.connect(":memory:"); db.executescript(DDL)
tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
check("5テーブルが作られる", tables == {"analysis_run","files","symbols","refs","comments"}, str(tables))

print("\n2. 主キー列の NOT NULL が効いている（§2.1）")
for t, cols in [("files","file,extractor,snapshot"),("symbols","id,file,start_line,extractor,snapshot"),
                ("refs","file,start_line,start_col,end_line,end_col,kind,extractor,snapshot"),
                ("comments","file,start_line,start_col,extractor,snapshot"),
                ("analysis_run","extractor,snapshot,key,seq")]:
    pk = [r[1] for r in db.execute(f"PRAGMA table_info({t})") if r[5]]
    nn = {r[1] for r in db.execute(f"PRAGMA table_info({t})") if r[3]}
    check(f"{t}: 主キー列が全て NOT NULL", set(pk) <= nn, f"PK={pk} NOTNULL={sorted(nn)}")

db.execute("INSERT INTO files(file,extractor,snapshot) VALUES('a.c',?,?)",(E,SNAP))
try:
    db.execute("INSERT INTO files(file,extractor,snapshot) VALUES('b.go',NULL,?)",(SNAP,))
    check("extractor=NULL が拒否される", False, "INSERT が通ってしまった")
except sqlite3.IntegrityError:
    check("extractor=NULL が拒否される", True)

print("\n3. 衝突が黙って捨てられない（§7.3）")
try:
    db.execute("INSERT INTO files(file,extractor,snapshot) VALUES('a.c',?,?)",(E,SNAP))
    check("主キー衝突がエラーになる", False, "重複 INSERT が通ってしまった")
except sqlite3.IntegrityError:
    check("主キー衝突がエラーになる", True)

print("\n4. comments の結合が増殖しない（§2.5）")
S=lambda i,f,l,d:(i,"cJSON","function",i.split()[-1],i.split()[-1],"local cJSON . %s/"%f,f,l,1,l+5,2,
                  d,"public","linkage","extern",1,"","high","c",E,SNAP)
db.executemany("INSERT INTO symbols VALUES(%s)"%",".join("?"*21),
  [S("local cJSON . free_buf(Buf).","src/a.h",5,0), S("local cJSON . free_buf(Buf).","src/a.c",40,1),
   S("local cJSON . open_port().","src/a.c",3,1),  S("local cJSON . open_port().","src/a.c",8,1)])
db.executemany("INSERT INTO comments VALUES(%s)"%",".join("?"*16),
  [("src/a.h",4,1,4,9,"doc","comment","local cJSON . free_buf(Buf).",5,"","x","","high","c",E,SNAP),
   ("src/a.c",2,1,2,9,"doc","comment","local cJSON . open_port().",3,"","Windows 版","_WIN32","high","c",E,SNAP),
   # #ifdef の両枝それぞれに doc が付く。attached_line が無いと両方が両方にマッチする
   ("src/a.c",7,1,7,9,"doc","comment","local cJSON . open_port().",8,"","POSIX 版","!_WIN32","high","c",E,SNAP)])
J="""SELECT COUNT(*) FROM symbols s LEFT JOIN comments c
     ON c.attached_id=s.id AND c.file=s.file {extra}
        AND c.extractor=s.extractor AND c.snapshot=s.snapshot AND c.kind='doc'
     WHERE s.is_definition=1"""
with_line = db.execute(J.format(extra="AND c.attached_line=s.start_line")).fetchone()[0]
without    = db.execute(J.format(extra="")).fetchone()[0]
check("attached_line 込みなら定義行数と一致", with_line == 3, f"{with_line} (期待 3)")
check("attached_line を外すと増殖する（列が必要な証拠）", without > with_line, f"{without} vs {with_line}")

print("\n5. 位置の包含で src_id / container_id が一意に決まる（§2.5）")
db.executemany("INSERT INTO refs VALUES(%s)"%",".join("?"*19),
  [("local cJSON . open_port().","local cJSON . free_buf(Buf).","free_buf","call","direct","",0,
    "src/a.c",4,3,4,20,"resolved",None,"unique_in_repo","medium","c",E,SNAP)])
n=db.execute("""SELECT COUNT(*) FROM refs r JOIN symbols s
  ON s.file=r.file AND s.extractor=r.extractor AND s.snapshot=r.snapshot
 AND r.start_line BETWEEN s.start_line AND s.end_line WHERE r.extractor=?""",(E,)).fetchone()[0]
check("位置の包含なら1行に決まる", n == 1, f"{n} 行")
n2=db.execute("SELECT COUNT(*) FROM refs r JOIN symbols s ON s.id=r.dst_id WHERE r.extractor=?",(E,)).fetchone()[0]
check("dst_id での JOIN は増える（規約が必要な証拠）", n2 > 1, f"{n2} 行")

print("\n6. ATTACH しても extractor で絞れば二重計上しない（§2.4）")
tmp = tempfile.mkdtemp(); fp = os.path.join(tmp,"full.db")
f = sqlite3.connect(fp); f.executescript(DDL)
f.execute("INSERT INTO refs VALUES(%s)"%",".join("?"*19),
  ("local cJSON . open_port().","local cJSON . free_buf(Buf).","free_buf","call","direct","",0,
   "src/a.c",4,3,4,20,"resolved",None,"unique_in_repo","high","c","libclang-18.1.0",SNAP))
f.commit(); f.close()
db.execute(f"ATTACH DATABASE '{fp}' AS fullv")
naive = db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM refs UNION ALL SELECT 1 FROM fullv.refs)").fetchone()[0]
scoped= db.execute("""SELECT COUNT(*) FROM
  (SELECT extractor FROM refs UNION ALL SELECT extractor FROM fullv.refs) WHERE extractor=?""",(E,)).fetchone()[0]
check("絞らないと二重計上する（規約が必要な証拠）", naive == 2, f"{naive}")
check("extractor で絞れば1件", scoped == 1, f"{scoped}")

print("\n7. 5レポートの中核クエリが動く")
Q={"R1 概観":"SELECT rtrim(file,replace(file,'/','')) d,COUNT(*) FROM files WHERE extractor=? GROUP BY d",
   "R2 見取り図":"SELECT file,text FROM comments WHERE kind IN('doc','file_header') AND extractor=?",
   "R3 ホットスポット":"""SELECT s.file,COUNT(DISTINCT s.id) defs,
       SUM(c.attached_id IS NOT NULL) doc FROM symbols s LEFT JOIN comments c
       ON c.attached_id=s.id AND c.file=s.file AND c.attached_line=s.start_line
       WHERE s.is_definition=1 AND s.extractor=? GROUP BY s.file""",
   "R4 コンポーネント依存":"""SELECT rtrim(r.file,replace(r.file,'/','')) d,COUNT(*)
       FROM refs r WHERE r.status='resolved' AND r.extractor=? GROUP BY d""",
   "R5 解決サマリ":"""SELECT status,COALESCE(reason,'-'),dispatch,confidence,
       COALESCE(resolved_by,'-'),COUNT(*)
       FROM refs WHERE kind='call' AND extractor=? GROUP BY 1,2,3,4,5"""}
for k,q in Q.items():
    try: db.execute(q,(E,)).fetchall(); check(k, True)
    except Exception as e: check(k, False, str(e))

print("\n8. 索引との突き合わせ")
idx=open(os.path.join(ROOT,"docs","SCHEMA_INDEX.md"),encoding="utf-8").read()
for t in ("analysis_run","files","symbols","refs","comments"):
    cols={r[1] for r in db.execute(f"PRAGMA table_info({t})")}
    missing=[c for c in cols if f"`{c}`" not in idx]
    check(f"{t}: 全列が索引に載っている", not missing, f"索引に無い: {missing}")

print("\n" + ("すべて通過" if not fails else f"失敗 {len(fails)} 件: {fails}"))
sys.exit(1 if fails else 0)
