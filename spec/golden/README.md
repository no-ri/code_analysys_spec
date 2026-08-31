# ゴールデンデータ（人手判定）

②-a（`status = resolved` / `confidence = medium` を名乗る行）が、**実際に正しい先を指しているか**を
人手で判定した記録。F-16 の実測の出典。

| ファイル | 対象 | コミット | 標本 | 正 | 的中率 |
|---|---|---|---:|---:|---:|
| `cjson-2a-sample.tsv` | cJSON [C] | `fb16e5cf358798aabb049655975cde8427101056` | 50 | 50 | **100%** |
| `fluentvalidation-2a-sample.tsv` | FluentValidation [C#] | `daa00b795450881c233253488e3ddeb362f59f56` | 66 | 44 | **66.7%** |

## 列

突合キーは **J-5** の `(file, start_line, start_col, kind)`。`extractor` / `snapshot` は
人手で固定できない（版が上がる／コミットで変わる）ので突合から除く。

| 列 | 意味 |
|---|---|
| `file` / `start_line` / `start_col` / `kind` | 突合キー |
| `rule` | どの規則で解いたか（層化抽出の層）。`SCHEMA.md` の `refs.resolved_by` に対応する |
| `expr` | 呼び出し式 |
| `claimed_dst_file` / `claimed_dst_line` | ツールが主張した呼び先 |
| `n_overload` | 同名の定義の数（2 以上ならオーバーロード） |
| **`verdict`** | **人手判定。`正` / `誤`** |
| `correct_dst_file` / `correct_dst_line` | `誤` のときの正しい呼び先。空なら `external`（リポジトリ外） |
| `note` | なぜ誤りか |

## 再現

```sh
.venv/bin/python tools/sample-golden.py --lang c      --per-rule 25 --tsv
.venv/bin/python tools/sample-golden.py --lang csharp --per-rule 20 --tsv
```

seed は既定の `20260831`。**`verdict` 以降の列は人手で付けたもの**なので、
再生成すると失われる（再生成する場合は判定を突合キーで引き継ぐこと）。

## 注意

標本サイズは規則ごとに 20〜25 件。**規則Bの 25% は 95% 信頼区間で概ね 9〜49%** と幅が広い。
「規則Bは他の規則より明確に低い」は言えるが、**点推定を確定値として扱わないこと**。

結論と決定は **`../EXTRACTION.md` §5**（判定手順）と `../TESTING.md` §3（使い方）。
決定の根拠（なぜそう決めたか）は**仕様リポジトリの `docs/DECISIONS.md` の F-16**。
