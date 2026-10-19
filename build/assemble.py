#!/usr/bin/env python3
"""
単一HTML（オフライン動作）を組み立てる。

  1) blender -b -P blender/build_lab.py -- model     # モデルを作り直すとき
  2) python3 build/assemble.py                       # index.html を生成

app/src/main.js を esbuild で three.js ごと1本に束ね、model/lab.glb（base64）と
model/units.json・app/storage_spec.json を埋め込んで index.html に書き出す。
"""
import base64, csv, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, 'build')
esbuild = os.path.join(B, 'bin', 'esbuild')
three = os.path.join(B, 'vendor', 'three')

out_js = os.path.join(B, 'app.bundle.js')
subprocess.run([
    esbuild, os.path.join(ROOT, 'app', 'src', 'main.js'), '--bundle', '--format=iife', '--minify',
    '--target=es2020', '--legal-comments=none', f'--outfile={out_js}',
    f'--alias:three={os.path.join(three, "build", "three.module.js")}',
    f'--alias:three/addons={os.path.join(three, "examples", "jsm")}',
], check=True)

with open(os.path.join(ROOT, 'app', 'index.template.html'), encoding='utf-8') as f:
    html = f.read()
with open(out_js, encoding='utf-8') as f:
    js = f.read()
with open(os.path.join(ROOT, 'model', 'units.json'), encoding='utf-8') as f:
    meta = json.load(f)

# ───── 什器の名前・温度は app/names.csv（Excelで編集可）が正。無ければ units.json から作る ─────
NAMES = os.path.join(ROOT, 'app', 'names.csv')
COLS = ['ID', '部屋', '種別', '名前', '温度', 'メモ']
KIND_JA = {'fridge': '冷蔵・冷凍庫', 'chestFreezer': 'チェスト型フリーザー', 'incubator': 'インキュベーター', 'bench': '実験台',
           'table': '机・台', 'shelf': '棚', 'rack': 'ワイヤーラック', 'cabinet': 'キャビネット', 'sink': '流し台',
           'hood': 'ドラフト', 'bsc': '安全キャビネット', 'equipment': '機器'}
TEMP_RE = re.compile(r'\s*(-?\d+(?:/-?\d+)?℃)')

def read_names():
    if not os.path.exists(NAMES):
        return []
    raw = open(NAMES, 'rb').read()
    for enc in ('utf-8-sig', 'cp932'):      # Excelで「CSV」保存するとShift_JISになることがある
        try:
            text = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    return [{k: (r.get(k) or '').strip() for k in COLS} for r in csv.DictReader(text.splitlines())]

rows = read_names()
known = {r['ID'] for r in rows}
added = 0
for u in meta['units']:
    if u['id'] in known:
        continue
    m = TEMP_RE.search(u['name'])
    temp = m.group(1) if m else ''
    name = TEMP_RE.sub('', u['name']).strip() if m else u['name']
    rows.append({'ID': u['id'], '部屋': u['room'], '種別': KIND_JA.get(u['kind'], u['kind']),
                 '名前': name, '温度': temp, 'メモ': u.get('note', '')})
    added += 1
if added or not os.path.exists(NAMES):
    with open(NAMES, 'w', encoding='utf-8-sig', newline='') as f:   # BOM付きでExcelでも文字化けしない
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader(); w.writerows(rows)
    print(f'names.csv に {added} 行追加')
by_id = {r['ID']: r for r in rows}
for u in meta['units']:
    r = by_id.get(u['id'])
    if not r:
        continue
    if r['名前']: u['name'] = r['名前']
    u['temp'] = r['温度']
    u['note'] = r['メモ']
unused = known - {u['id'] for u in meta['units']}
if unused:
    print('注意: names.csv にあるがモデルに無いID:', ', '.join(sorted(unused)))

spec_path = os.path.join(ROOT, 'app', 'storage_spec.json')
spec = {}
if os.path.exists(spec_path):
    with open(spec_path, encoding='utf-8') as f:
        spec = json.load(f)
with open(os.path.join(ROOT, 'model', 'lab.glb'), 'rb') as f:
    glb = base64.b64encode(f.read()).decode('ascii')

safe = lambda s: s.replace('</script', '<\\/script')
html = html.replace('/*META*/null', safe(json.dumps(meta, ensure_ascii=False)))
html = html.replace('/*SPEC*/null', safe(json.dumps(spec, ensure_ascii=False)))
html = html.replace('/*GLB*/', glb)
html = html.replace('/*APP*/', safe(js))
dst = os.path.join(ROOT, 'index.html')
with open(dst, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'index.html {os.path.getsize(dst) / 1e6:.1f} MB')
