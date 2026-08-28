import sqlite3
db=sqlite3.connect(":memory:")
db.executescript(open('schema_test.py').read().split('db.executescript("""')[1].split('""")')[0])
ins="INSERT INTO files VALUES(%s)"%",".join("?"*17)

print("=== 1. 多言語混在: 抽出器を持たない言語のファイル ===")
try:
    # Go のファイル。抽出器が無い → extractor に何を入れる？
    db.execute(ins,("cmd/main.go","go","skipped_no_extractor",900,42,
                    None,None,None,None,None,"ab12",3,2,"2026-08-01","high",None,"8f3ac21"))
    print("   extractor=NULL で INSERT 成功 →", db.execute(
        "SELECT file,extract_status,extractor,comment_lines FROM files").fetchall())
    print("   ⚠ PK の一部が NULL。SQLite は許すが (file,extractor,snapshot) が一意にならない")
    db.execute(ins,("cmd/main.go","go","skipped_no_extractor",900,42,
                    None,None,None,None,None,"ab12",3,2,"2026-08-01","high",None,"8f3ac21"))
    print("   ⚠⚠ 同じ行がもう一度 INSERT できた →", db.execute("SELECT COUNT(*) FROM files").fetchone())
except sqlite3.IntegrityError as e:
    print("   IntegrityError:",e)

print("\n=== 2. comment_lines = 0 と「数えていない」の区別 ===")
db.execute("DELETE FROM files")
db.execute(ins,("src/empty.c","c","extracted",0,0,0,0,0,0,0,"e3",1,1,"2026-08-01","high","tree-sitter-c","8f3ac21"))
db.execute(ins,("cmd/main.go","go","skipped_no_extractor",900,42,0,0,0,0,0,"ab12",3,2,"2026-08-01","high","orchestrator","8f3ac21"))
print("   コメント密度レポート:")
for r in db.execute("SELECT file,lines,comment_lines,parse_errors FROM files"):
    print("   ",r)
print("   ⚠ main.go の comment_lines=0 / parse_errors=0 は『0件』ではなく『測っていない』")
print("     → 全体のコメント密度・パース健全性の集計に紛れ込む")

print("\n=== 3. 増分取り込み: 削除されたファイル ===")
db.execute("DELETE FROM files")
for f in ("src/a.c","src/b.c","src/old.c"):
    db.execute(ins,(f,"c","extracted",100,50,10,5,0,0,0,"h",1,1,"2026-08-01","high","tree-sitter-c","8f3ac21"))
print("   1回目:",[r[0] for r in db.execute("SELECT file FROM files ORDER BY file")])
# src/old.c がリポジトリから削除された。src/a.c だけ変更された想定で増分取り込み
db.execute("DELETE FROM files WHERE file=?",("src/a.c",))
db.execute(ins,("src/a.c","c","extracted",120,60,12,5,0,0,0,"h2",2,1,"2026-08-02","high","tree-sitter-c","9b4cd10"))
print("   増分後:",[r[0] for r in db.execute("SELECT file FROM files ORDER BY file")])
print("   ⚠ src/old.c が残っている（§7.6 の増分は『変更されたファイル』しか回さない）")
print("   概観レポートのファイル数:",db.execute("SELECT COUNT(*) FROM files").fetchone()[0],"（実際は 2）")

print("\n=== 4. ゴールデンデータの突合キー ===")
print("   refs の主キー = (file,start_line,start_col,end_line,end_col,kind,extractor,snapshot)")
print("   人手で書く正解データは extractor（版が上がる）と snapshot（コミットで変わる）を固定できない")
print("   → 突合キーを別に決める必要がある")
db.close()
