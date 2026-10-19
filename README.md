# ラボ収納マップ 3D

2026-10-18 のラボ空間スキャン（`scan/2026_10_18.glb`）をもとに、すべての什器を Blender で作り直した 3D 収納管理アプリ。
`index.html` をダブルクリックで開けばオフラインで動きます（約 8MB の単一ファイル）。

## 構成

| パス | 役割 |
|---|---|
| `index.html` | 完成品（three.js・モデル・メタデータを全部埋め込み） |
| `blender/lib.py` | 什器の部品ビルダー（実験台・冷蔵庫・インキュベーター・安全キャビネット・棚…） |
| `blender/build_lab.py` | 間取りと全什器の配置表（スキャンから読み取った実測値） |
| `model/lab.blend` / `lab.glb` / `units.json` | Blender の出力（編集用 / 表示用 / 什器一覧） |
| `app/src/main.js`, `app/index.template.html` | ビューアのソース |
| `app/names.csv` | **什器の名前・温度・メモ**（Excelで編集→`assemble.py`で反映）。ここが正 |
| `app/storage_spec.json` | **収納量（区画・段数）の個別指定**。いまは空 `{}` |
| `build/assemble.py` | `index.html` を組み立てる |

## 作り直す手順

```bash
blender -b -P blender/build_lab.py -- model   # 什器を直したとき
python3 build/assemble.py                     # index.html を再生成
```

## 収納量の指定（あとで追記）

`app/storage_spec.json` に什器IDごとに区画を書くと、詳細パネルに表示されます。

```json
{
  "A-C1": { "sections": [
    { "code": "A-C1-1", "name": "左扉 1段目", "capacity": "ラック2本" },
    { "code": "A-C1-2", "name": "左扉 2段目" }
  ] }
}
```

## 座標

- Blender: X=東, Y=北, Z=上（m）。床=0、天井=2.40m。
- スキャンは Z 軸まわり +2.0° 回転、床を 1.395m 持ち上げると一致する（`scan/` は元データとして保管。アプリでは表示しない）。
