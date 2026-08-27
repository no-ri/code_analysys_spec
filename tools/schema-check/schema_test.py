import sqlite3
db=sqlite3.connect(":memory:")
db.executescript("""
CREATE TABLE analysis_run(extractor TEXT,snapshot TEXT,key TEXT,value TEXT,seq INT,
  PRIMARY KEY(extractor,snapshot,key,seq));
CREATE TABLE files(file TEXT,lang TEXT,extract_status TEXT,bytes INT,lines INT,
  comment_lines INT,blank_lines INT,parse_errors INT,missing_nodes INT,error_lines INT,
  content_hash TEXT,git_commits INT,git_authors INT,git_last_modified TEXT,
  confidence TEXT,extractor TEXT,snapshot TEXT, PRIMARY KEY(file,extractor,snapshot));
CREATE TABLE symbols(id TEXT,root TEXT,kind TEXT,name TEXT,qualified_name TEXT,
  container_id TEXT,file TEXT,start_line INT,start_col INT,end_line INT,end_col INT,
  is_definition INT,visibility TEXT,visibility_source TEXT,storage_class TEXT,
  branch_count INT,guard TEXT,confidence TEXT,lang TEXT,extractor TEXT,snapshot TEXT,
  PRIMARY KEY(id,file,start_line,extractor,snapshot));
CREATE TABLE refs(src_id TEXT,dst_id TEXT,dst_expr TEXT,kind TEXT,dispatch TEXT,
  guard TEXT,lambda_depth INT,file TEXT,start_line INT,start_col INT,end_line INT,
  end_col INT,status TEXT,reason TEXT,confidence TEXT,lang TEXT,extractor TEXT,snapshot TEXT,
  PRIMARY KEY(file,start_line,start_col,end_line,end_col,kind,extractor,snapshot));
CREATE TABLE comments(file TEXT,start_line INT,start_col INT,end_line INT,end_col INT,
  kind TEXT,source_kind TEXT,attached_id TEXT,attached_line INT,marker TEXT,text TEXT,
  guard TEXT,confidence TEXT,lang TEXT,extractor TEXT,snapshot TEXT,
  PRIMARY KEY(file,start_line,start_col,extractor,snapshot));
""")
SNAP="8f3ac21"; EC="tree-sitter-c"
# cJSON 風: a.h に宣言(doc付き) / a.c に定義 / #ifdef 両枝
S=[("local cJSON . free_buf(Buf).","cJSON","function","free_buf","free_buf",
    "local cJSON . src/a.h/","src/a.h",5,1,5,30,0,"public","linkage","extern",0,"","high","c",EC,SNAP),
   ("local cJSON . free_buf(Buf).","cJSON","function","free_buf","free_buf",
    "local cJSON . src/a.c/","src/a.c",40,1,50,2,1,"public","linkage","extern",3,"","high","c",EC,SNAP),
   ("local cJSON . open_port().","cJSON","function","open_port","open_port",
    "local cJSON . src/a.c/","src/a.c",3,1,6,2,1,"public","linkage","extern",1,"_WIN32","high","c",EC,SNAP),
   ("local cJSON . open_port().","cJSON","function","open_port","open_port",
    "local cJSON . src/a.c/","src/a.c",8,1,11,2,1,"public","linkage","extern",1,"!_WIN32","high","c",EC,SNAP),
   ("local cJSON . src/a.c/","cJSON","file","a.c","src/a.c",None,"src/a.c",1,1,60,1,1,
    "module","linkage","not_applicable",0,"","high","c",EC,SNAP)]
db.executemany("INSERT INTO symbols VALUES(%s)"%",".join("?"*21),S)
C=[("src/a.h",4,1,4,28,"doc","comment","local cJSON . free_buf(Buf).",5,"","バッファを解放する","","high","c",EC,SNAP),
   ("src/a.c",2,1,2,20,"doc","comment","local cJSON . open_port().",3,"","Windows 版","_WIN32","high","c",EC,SNAP),
   ("src/a.c",7,1,7,20,"doc","comment","local cJSON . open_port().",8,"","POSIX 版","!_WIN32","high","c",EC,SNAP),
   ("src/a.c",1,1,1,15,"file_header","comment",None,None,"","JSON パーサ","","high","c",EC,SNAP)]
db.executemany("INSERT INTO comments VALUES(%s)"%",".join("?"*16),C)
R=[("local cJSON . open_port().","local cJSON . free_buf(Buf).","free_buf","call","direct","_WIN32",0,
    "src/a.c",4,3,4,20,"resolved",None,"medium","c",EC,SNAP),
   ("local cJSON . open_port().",None,"printf","call","direct","_WIN32",0,
    "src/a.c",5,3,5,18,"unresolved","external","high","c",EC,SNAP)]
db.executemany("INSERT INTO refs VALUES(%s)"%",".join("?"*18),R)

def q(t,sql):
    print("\n### "+t); [print("   ",r) for r in db.execute(sql)]

# G-8 の紐付け（attached_line 込み）が効くか
q("R3 doc 欠落率（G-8 の結合を検証）", """
SELECT s.file, COUNT(*) defs, SUM(c.attached_id IS NOT NULL) documented
FROM symbols s LEFT JOIN comments c
  ON c.attached_id=s.id AND c.file=s.file AND c.attached_line=s.start_line
     AND c.extractor=s.extractor AND c.snapshot=s.snapshot AND c.kind='doc'
WHERE s.is_definition=1 AND s.kind='function'
GROUP BY s.file""")

q("attached_line を外すと（G-8 以前の結合）", """
SELECT s.file, COUNT(*) rows_after_join
FROM symbols s LEFT JOIN comments c
  ON c.attached_id=s.id AND c.file=s.file AND c.kind='doc'
WHERE s.is_definition=1 AND s.kind='function' GROUP BY s.file""")

q("R1 概観（ディレクトリ抽出）", """
SELECT rtrim(file, replace(file,'/','')) dir, COUNT(*) n FROM symbols
WHERE kind='file' GROUP BY dir""")

q("R5 解決サマリ", """
SELECT status, COALESCE(reason,'-') reason, dispatch, confidence, COUNT(*) n
FROM refs WHERE kind='call' GROUP BY 1,2,3,4""")
db.close()
