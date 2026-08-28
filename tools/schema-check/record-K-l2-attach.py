import sqlite3, os
DDL = """
CREATE TABLE analysis_run(extractor TEXT NOT NULL,snapshot TEXT NOT NULL,key TEXT NOT NULL,
  value TEXT,seq INT NOT NULL, PRIMARY KEY(extractor,snapshot,key,seq));
CREATE TABLE symbols(id TEXT NOT NULL,root TEXT NOT NULL,kind TEXT,name TEXT,qualified_name TEXT,
  container_id TEXT,file TEXT NOT NULL,start_line INT NOT NULL,start_col INT,end_line INT,end_col INT,
  is_definition INT,visibility TEXT,visibility_source TEXT,storage_class TEXT,branch_count INT,
  guard TEXT,confidence TEXT,lang TEXT,extractor TEXT NOT NULL,snapshot TEXT NOT NULL,
  PRIMARY KEY(id,file,start_line,extractor,snapshot));
CREATE TABLE refs(src_id TEXT,dst_id TEXT,dst_expr TEXT,kind TEXT NOT NULL,dispatch TEXT,guard TEXT,
  lambda_depth INT,file TEXT NOT NULL,start_line INT NOT NULL,start_col INT NOT NULL,
  end_line INT NOT NULL,end_col INT NOT NULL,status TEXT,reason TEXT,confidence TEXT,lang TEXT,
  extractor TEXT NOT NULL,snapshot TEXT NOT NULL,
  PRIMARY KEY(file,start_line,start_col,end_line,end_col,kind,extractor,snapshot));
"""
def mk(path, ext, snap, rows_s, rows_r):
    if os.path.exists(path): os.remove(path)
    d=sqlite3.connect(path); d.executescript(DDL)
    d.executemany("INSERT INTO symbols VALUES(%s)"%",".join("?"*21), rows_s)
    d.executemany("INSERT INTO refs VALUES(%s)"%",".join("?"*18), rows_r)
    d.commit(); return d

S=lambda i,f,l,d,g: (i,"myrepo","function",i.split()[-1],i.split()[-1],
                     "local myrepo . %s/"%f,f,l,1,l+5,2,d,"public","linkage","extern",1,g,
                     "medium","c","tree-sitter-c","8f3ac21")
R=lambda s,dd,f,l,st,rs: (s,dd,"x","call","direct","",0,f,l,3,l,20,st,rs,"medium","c",
                          "tree-sitter-c","8f3ac21")

print("=== 1. L2 の symbol_canonical（F-13③）を実際に書く ===")
db=mk("simple.db","tree-sitter-c","8f3ac21",
  [S("local myrepo . free_buf(Buf).","src/a.h",5,0,""),
   S("local myrepo . free_buf(Buf).","src/a.c",40,1,""),
   S("local myrepo . open_port().","src/a.c",3,1,"_WIN32"),
   S("local myrepo . open_port().","src/a.c",8,1,"!_WIN32"),
   S("local myrepo . solo().","src/b.c",2,1,"")],
  [R("local myrepo . open_port().","local myrepo . free_buf(Buf).","src/a.c",4,"resolved",None)])
for r in db.execute("""
WITH defs AS (SELECT id, COUNT(*) n FROM symbols WHERE is_definition=1 GROUP BY id)
SELECT s.id, s.file, s.start_line, s.is_definition,
       CASE WHEN d.n>1 THEN 1 ELSE 0 END multiple_definitions
FROM symbols s LEFT JOIN defs d ON d.id=s.id ORDER BY s.id, s.start_line"""):
    print("   ",r)
print("   → 定義1つ=正規1行 / 定義0(宣言のみ) / 定義複数=畳まない、が出せる")

print("\n=== 2. refs.dst_id → symbols の結合（N行問題）===")
for r in db.execute("""
SELECT r.dst_id, COUNT(*) matched_symbol_rows
FROM refs r JOIN symbols s ON s.id=r.dst_id
WHERE r.status='resolved' GROUP BY r.dst_id"""):
    print("   ",r, "← 宣言と定義の2行にマッチ")
print("   ⚠ 被参照数レポート（中核シンボルの特定）で JOIN すると件数が倍になる")

print("\n=== 3. ATTACH でフル版DBと結合（E-4 決定2）===")
full=mk("full.db","libclang-18.1.0","8f3ac21",
  [S("local myrepo . free_buf(Buf).","src/a.c",40,1,"")],
  [R("local myrepo . open_port().","local myrepo . free_buf(Buf).","src/a.c",4,"resolved",None)])
full.close()
db.execute("ATTACH DATABASE 'full.db' AS fullv")
print("   簡易版 refs:",db.execute("SELECT COUNT(*) FROM refs").fetchone()[0],
      "/ フル版 refs:",db.execute("SELECT COUNT(*) FROM fullv.refs").fetchone()[0])
for r in db.execute("""
SELECT extractor, COUNT(*) FROM (
  SELECT extractor FROM refs UNION ALL SELECT extractor FROM fullv.refs) GROUP BY 1"""):
    print("   ",r)
print("   → extractor で区別できる（E-4 決定3 のとおり）")
try:
    db.execute("SELECT * FROM refs UNION ALL SELECT * FROM fullv.refs").fetchall()
    print("   UNION ALL 可（列が一致）")
except Exception as e: print("   UNION 失敗:",e)
db.close()
