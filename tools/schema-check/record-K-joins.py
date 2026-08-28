import os
import sqlite3, os
DDL=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'record-K-l2-attach.py')).read().split('DDL = """')[1].split('"""')[0]
def mk(path,ext,rows_s,rows_r):
    if os.path.exists(path): os.remove(path)
    d=sqlite3.connect(path); d.executescript(DDL)
    d.executemany("INSERT INTO symbols VALUES(%s)"%",".join("?"*21),rows_s)
    d.executemany("INSERT INTO refs VALUES(%s)"%",".join("?"*18),rows_r)
    d.commit(); return d
S=lambda i,f,l,d,ext:(i,"myrepo","function",i.split()[-1],i.split()[-1],
  "local myrepo . %s/"%f,f,l,1,l+5,2,d,"public","linkage","extern",1,"","medium","c",ext,"8f3ac21")
R=lambda s,dd,f,l,st,rs,ext:(s,dd,"x","call","direct","",0,f,l,3,l,20,st,rs,"medium","c",ext,"8f3ac21")

print("=== 3'. ATTACH: extractor を実際に変えて検証 ===")
E1,E2="tree-sitter-c","libclang-18.1.0"
simple=mk("s.db",E1,
 [S("local myrepo . a().","src/a.c",1,1,E1),S("local myrepo . b().","src/b.c",1,1,E1),
  S("local myrepo . b().","src/b.h",1,0,E1)],
 [R("local myrepo . a().","local myrepo . b().","src/a.c",4,"resolved",None,E1),
  R("local myrepo . a().",None,"src/a.c",5,"unresolved","needs_type",E1)])
full=mk("f.db",E2,[S("local myrepo . a().","src/a.c",1,1,E2)],
 [R("local myrepo . a().","local myrepo . b().","src/a.c",4,"resolved",None,E2),
  R("local myrepo . a().","local myrepo . c().","src/a.c",5,"resolved",None,E2)])
full.close()
simple.execute("ATTACH DATABASE 'f.db' AS fullv")
print("   絞らずに解決率:")
for r in simple.execute("""SELECT status,COUNT(*) FROM
  (SELECT status FROM refs UNION ALL SELECT status FROM fullv.refs) GROUP BY 1"""):
    print("     ",r)
print("   → 同じ src/a.c:4 の呼び出しが2回数えられている（E-4 決定2 の警告どおり）")
print("   extractor で絞ると:")
for r in simple.execute("""SELECT extractor,status,COUNT(*) FROM
  (SELECT extractor,status FROM refs UNION ALL SELECT extractor,status FROM fullv.refs)
  GROUP BY 1,2"""): print("     ",r)
print("   ⚠ §3.3 のSQL例も5レポートのクエリも extractor で絞っていない")

print("\n=== 4. 引き継ぎ書（E-4 決定5）を書いてみる ===")
for r in simple.execute("""
SELECT file, reason, COUNT(*) n FROM refs
WHERE status='unresolved' AND reason IN ('needs_type','ambiguous')
GROUP BY file, reason ORDER BY n DESC"""): print("   ",r)
print("   → 書ける。ただし『どのシンボルの中か』を出すには src_id → symbols の JOIN が要る")

print("\n=== 5. 被参照数レポート（N行問題の実害）===")
print("   JOIN 無し（正しい）:")
for r in simple.execute("SELECT dst_id,COUNT(*) FROM refs WHERE status='resolved' AND extractor=? GROUP BY 1",(E1,)): print("     ",r)
print("   symbols と JOIN して名前を出すと:")
for r in simple.execute("""SELECT s.name,COUNT(*) FROM refs r JOIN symbols s ON s.id=r.dst_id
  WHERE r.status='resolved' AND r.extractor=? GROUP BY 1""",(E1,)): print("     ",r,"← 宣言+定義で2倍")

print("\n=== 6. L2 到達可能性（推移閉包）===")
try:
    rows=simple.execute("""
    WITH RECURSIVE reach(id) AS (
      SELECT 'local myrepo . a().'
      UNION
      SELECT r.dst_id FROM refs r JOIN reach ON r.src_id=reach.id
      WHERE r.dst_id IS NOT NULL AND r.extractor=?)
    SELECT * FROM reach""",(E1,)).fetchall()
    print("   到達可能:",rows)
except Exception as e: print("   失敗:",e)
simple.close()
