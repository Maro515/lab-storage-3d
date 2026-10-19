# -*- coding: utf-8 -*-
"""
ラボ全体（実験室・培養室・廊下・物品庫・小部屋）をBlenderで組み直してGLBに書き出す。

  blender -b -P blender/build_lab.py -- <出力ディレクトリ>

出力: lab.blend / lab.glb / units.json（什器メタデータ）
寸法・位置は 2026-10-18 のスキャン（scan/2026_10_18.glb）の
上面高さマップ・水平断面・壁面立面図から読み取った実測値（±5cm 程度）。
収納量（区画・段数）はあとで個別指定する前提なので、ここでは外観と配置だけを確定させる。
"""
import bpy, sys, os, math, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib, lib
importlib.reload(lib)
from lib import *  # noqa

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else os.path.join(HERE, '..', 'model')
os.makedirs(OUT, exist_ok=True)

H = 2.40      # 天井高（スキャン実測 2.398m）
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c

C_ARCH = coll('建築')
C_UNIT = coll('什器')
C_DECO = coll('小物')
C_CEIL = coll('天井')

# ───────── 床テクスチャ（長尺シート: ベージュ地に細かい石目＋0.6m目地）─────────
def make_floor_image():
    N = 1024
    rng = np.random.default_rng(7)
    base = np.array([0.86, 0.83, 0.77])
    noise = rng.normal(0, 1, (N, N))
    # 粗い斑＋細かい石目
    from numpy.fft import fft2, ifft2
    k = np.fft.fftfreq(N)
    kk = np.sqrt(k[:, None] ** 2 + k[None, :] ** 2)
    coarse = np.real(ifft2(fft2(rng.normal(0, 1, (N, N))) * np.exp(-(kk / 0.01) ** 2)))
    coarse = coarse / (np.abs(coarse).max() + 1e-9)
    fine = (noise > 2.2).astype(float) * 0.10 - (noise < -2.4).astype(float) * 0.06
    img = base[None, None, :] * (1 + 0.035 * coarse[..., None]) + fine[..., None] * 0.5
    # 目地（4×4枚 = 0.6m 角）
    seam = np.zeros((N, N))
    for i in range(0, N, N // 4):
        seam[i:i + 2, :] = 1; seam[:, i:i + 2] = 1
    img = img * (1 - 0.10 * seam[..., None])
    img = np.clip(img, 0, 1)
    rgba = np.concatenate([img, np.ones((N, N, 1))], axis=2).astype(np.float32)
    im = bpy.data.images.new('floor_tex', N, N, alpha=False)
    im.colorspace_settings.name = 'sRGB'
    im.pixels.foreach_set(rgba[::-1].ravel())
    im.pack()
    return im

FLOOR_IMG = make_floor_image()
P = init_materials(FLOOR_IMG)

META = []          # units.json 用
def tag(ob, uid, name, room, kind, storage, note=''):
    ob['lab_id'] = uid; ob['lab_name'] = name; ob['lab_room'] = room
    ob['lab_kind'] = kind; ob['lab_storage'] = 1 if storage else 0
    if note: ob['lab_note'] = note
    META.append(dict(id=uid, name=name, room=room, kind=kind, storage=bool(storage), note=note, obj=ob.name))

# ───────── 建築: 床・壁・梁・天井 ─────────
X0, X1, Y0, Y1 = -5.85, 5.77, -7.50, 7.50

def floor():
    import bmesh
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in ((X0, Y0, 0), (X1, Y0, 0), (X1, Y1, 0), (X0, Y1, 0))]
    f = bm.faces.new(vs)
    uv = bm.loops.layers.uv.new('UVMap')
    for l in f.loops:
        co = l.vert.co
        l[uv].uv = (co.x / 2.4, co.y / 2.4)
    me = bpy.data.meshes.new('床'); bm.to_mesh(me); bm.free()
    me.materials.append(P['floor'])
    ob = bpy.data.objects.new('床', me); C_ARCH.objects.link(ob)
    ob['lab_kind'] = 'floor'
floor()

ARCH = Geo()
ARCH_LOW = Geo()      # 俯瞰用の「腰高カット」版の壁（アプリで全高と切り替える）
CUT = 1.05

def wall_box(x0, x1, y0, y1, z0=0.0, z1=H, m='wall'):
    ARCH.box(x0, y0, z0, x1, y1, z1, P[m])
    if z0 < CUT:
        ARCH_LOW.box(x0, y0, z0, x1, y1, min(z1, CUT), P[m])
        if z1 > CUT:   # 切断面は濃いグレーで見せる（断面表現）
            ARCH_LOW.box(x0, y0, CUT - 0.004, x1, y1, CUT + 0.002, P['cutcap'])

def wall_run(x0, x1, y0, y1, openings=(), along='x'):
    """壁1本。openings=[(a0,a1,zb,zt)] は壁の長手方向座標。開口の上下は腰壁・垂れ壁で埋める。"""
    a_lo, a_hi = (x0, x1) if along == 'x' else (y0, y1)
    cuts = sorted(openings)
    a = a_lo
    def seg(p, q, z0, z1):
        if q - p < 1e-4: return
        if along == 'x': wall_box(p, q, y0, y1, z0, z1)
        else: wall_box(x0, x1, p, q, z0, z1)
    for o0, o1, zb, zt in cuts:
        seg(a, o0, 0, H)
        if zb > 0: seg(o0, o1, 0, zb)
        if zt < H: seg(o0, o1, zt, H)
        a = o1
    seg(a, a_hi, 0, H)

# 実験室A（メイン）: 内法 x -5.70..0.72 / y -7.00..7.02、東側に冷蔵庫アルコーブ（x 0.72..1.75）
WIN = [(-6.75, -0.45), (0.70, 6.80)]                     # 西面の連窓（腰 0.92 / 頭 2.30）
wall_run(-5.85, -5.70, -7.15, 7.17, [(a, b, 0.92, 2.30) for a, b in WIN], along='y')
wall_run(-5.85, 1.92, 7.02, 7.17)                        # 北壁
wall_run(-5.85, 1.50, -7.15, -7.00)                      # 南壁
wall_run(1.75, 1.92, -0.53, 7.50, along='y')              # アルコーブ奥＝培養室の西壁
wall_box(0.72, 1.75, 6.55, 7.02)                          # 北東の柱
wall_box(0.72, 1.75, -0.53, 0.55)                         # 廊下入口脇の柱（掲示物のある柱）
# 廊下・培養室
wall_run(1.92, 5.62, -0.53, -0.37, [(2.20, 3.20, 0, 2.10)])          # 培養室の南壁（扉）
wall_box(1.92, 5.62, -0.37, 0.20, 2.25, H)                            # 培養室南側の下がり天井
wall_run(1.40, 5.62, -2.95, -2.78)                                    # 物品庫の北壁
wall_run(1.40, 1.50, -7.50, -4.35, along='y')                         # 物品庫の西壁
wall_box(0.70, 1.40, -7.00, -4.35)                                    # 実験室南東のパイプスペース（スキャン上は天井まで塞がった塊）
wall_run(5.62, 5.77, -7.50, 7.50, [(-1.65, -0.75, 0, 2.10), (-4.45, -3.60, 0, 2.10)], along='y')  # 東外壁
wall_run(1.75, 5.77, 7.35, 7.50)                                      # 培養室の北壁
wall_run(1.40, 5.77, -7.50, -7.35)                                    # 物品庫の南壁
wall_run(3.52, 3.62, -7.35, -5.45, [(-6.40, -5.60, 0, 2.10)], along='y')  # 小部屋の間仕切り（扉）
wall_run(3.52, 5.62, -5.55, -5.45)                                    # 小部屋の北側間仕切り
# 梁・垂れ壁
wall_box(-5.70, 0.72, -0.05, 0.25, 2.28, H)                           # 実験室を横切る梁
wall_box(-5.70, 0.70, -7.00, -6.30, 2.05, H)                          # 南壁沿いの下がり天井
wall_box(1.40, 1.50, -4.35, -2.95, 2.10, H)                           # 実験室→物品庫の開口の垂れ壁
ob = ARCH.to_object('壁', C_ARCH); ob['lab_kind'] = 'wall'
ob = ARCH_LOW.to_object('壁_腰高', C_ARCH); ob['lab_kind'] = 'wall_low'
ob.hide_set(True); ob.hide_render = True     # .blend 上では全高の壁を表示（アプリ側で切替）

# 幅木（主要な壁の室内側）
SK = Geo()
def skirt(x0, x1, y0, y1):
    SK.box(x0, y0, 0, x1, y1, 0.07, P['skirt'])
skirt(-5.70, 0.72, 7.005, 7.02); skirt(-5.70, 0.70, -7.00, -6.985)
skirt(-5.70, -5.685, -7.0, 7.02); skirt(1.735, 1.75, 0.55, 6.55)
skirt(1.92, 1.935, -0.37, 7.35); skirt(1.92, 5.62, 7.335, 7.35); skirt(5.605, 5.62, -0.37, 7.35)
skirt(1.92, 5.62, -0.37, -0.355); skirt(0.72, 5.62, -0.545, -0.53); skirt(1.40, 5.62, -2.795, -2.78)
skirt(1.50, 1.515, -7.35, -4.35); skirt(1.50, 3.52, -7.35, -7.335); skirt(1.50, 5.62, -2.965, -2.95); skirt(0.685, 0.70, -7.0, -4.35)
skirt(5.605, 5.62, -7.35, -0.545)
SK.to_object('幅木', C_ARCH)['lab_kind'] = 'wall'

# 窓（西面）: 枠・方立・ガラス・室内側の窓台
WG = Geo()
for a, b in WIN:
    n = max(1, int(round((b - a) / 1.30)))
    WG.box(-5.80, a, 0.92, -5.72, b, 0.95, P['sash'])
    WG.box(-5.80, a, 2.27, -5.72, b, 2.30, P['sash'])
    WG.box(-5.70, a, 0.90, -5.62, b, 0.93, P['board'])          # 窓台
    for i in range(n + 1):
        y = a + (b - a) * i / n
        WG.box(-5.80, y - 0.03, 0.92, -5.72, y + 0.03, 2.30, P['sash'])
        if i < n:
            ym = y + (b - a) / n / 2
            WG.box(-5.79, ym - 0.012, 0.95, -5.73, ym + 0.012, 2.27, P['sash'])   # 引違いの召合せ
    WG.box(-5.775, a, 0.95, -5.765, b, 2.27, P['glass'])
WG.to_object('窓', C_ARCH)['lab_kind'] = 'window'

# 扉
def door(name, cx, cy, w, h, rot, style='steel', t=0.15):
    g = Geo()
    fw = 0.05
    g.box(-w / 2 - fw, -t / 2 - 0.01, 0, -w / 2, t / 2 + 0.01, h + fw, P['doorframe'])
    g.box(w / 2, -t / 2 - 0.01, 0, w / 2 + fw, t / 2 + 0.01, h + fw, P['doorframe'])
    g.box(-w / 2, -t / 2 - 0.01, h, w / 2, t / 2 + 0.01, h + fw, P['doorframe'])
    g.box(-w / 2 + 0.003, -0.02, 0.01, w / 2 - 0.003, 0.02, h - 0.003, P['door'])
    if style == 'steel':
        g.box(w / 2 - 0.30, -0.025, h * 0.40, w / 2 - 0.22, 0.025, h * 0.80, P['screen'])   # 縦長の覗き窓
    elif style == 'frost':
        g.box(-w / 2 + 0.10, -0.025, h * 0.35, w / 2 - 0.10, 0.025, h * 0.90, P['frost'])
    for s in (-1, 1):
        g.box(-w / 2 + 0.06, s * 0.02, 1.00, -w / 2 + 0.20, s * 0.065, 1.03, P['handle'])
    ob = g.to_object(name, C_ARCH, (cx, cy, 0), rot, bevel=0.003)
    ob['lab_kind'] = 'door'
    return ob

door('扉_培養室', 2.70, -0.45, 1.00, 2.10, 0.0, 'frost', t=0.16)
door('扉_出入口', 5.695, -1.20, 0.90, 2.10, math.pi / 2, 'steel')
door('扉_物品庫東', 5.695, -4.025, 0.85, 2.10, math.pi / 2, 'steel')
door('扉_小部屋', 3.57, -6.00, 0.80, 2.10, math.pi / 2, 'steel')

# 時計（西面の棚の上）
g = Geo(); g.cyl(0, 0, 0, 0.04, 0.16, P['clock'], seg=32, axis='y'); g.cyl(0, 0, -0.005, 0.0, 0.17, P['black'], seg=32, axis='y')
g.box(-0.005, -0.045, -0.002, 0.005, -0.04, 0.12, P['black']); g.box(-0.004, -0.045, -0.004, 0.09, -0.04, 0.004, P['black'])
ob = g.to_object('時計', C_DECO, (-5.69, 0.12, 2.12), -math.pi / 2); ob['lab_kind'] = 'decor'

# 天井（アプリでは既定で非表示）と照明・空調
CG = Geo()
CG.box(X0, Y0, H, X1, Y1, H + 0.03, P['ceiling'])
CG.to_object('天井', C_CEIL)['lab_kind'] = 'ceiling'
LG = Geo()
def light(x, y, along='x', L=1.25):
    if along == 'x': LG.box(x - L / 2, y - 0.11, H - 0.03, x + L / 2, y + 0.11, H, P['light'])
    else: LG.box(x - 0.11, y - L / 2, H - 0.03, x + 0.11, y + L / 2, H, P['light'])
for y in (6.0, 4.3, 2.6, 0.9, -1.0, -2.8, -4.4, -6.0):
    for x in (-4.6, -2.7, -0.8):
        light(x, y)
for y in (6.5, 4.5, 2.5, 0.6): light(3.7, y, 'y')
for x in (1.8, 3.4, 4.9): light(x, -1.15)
for y in (-3.6, -5.0, -6.6): light(2.4, y, 'y')
light(4.6, -4.0); light(4.6, -6.5)
for x, y in ((-3.6, 5.3), (-1.4, 5.3), (-3.6, 1.8), (-1.4, -1.8), (-3.6, -5.3), (-1.4, -5.3), (3.7, 3.3)):
    LG.box(x - 0.42, y - 0.42, H - 0.04, x + 0.42, y + 0.42, H, P['ac'])
    LG.box(x - 0.30, y - 0.30, H - 0.045, x + 0.30, y + 0.30, H - 0.04, P['acgrill'])
LG.to_object('照明・空調', C_CEIL)['lab_kind'] = 'ceiling'

# ───────── 什器 ─────────
def unit(uid, name, room, kind, storage, ext, facing, build, z=0.0, bevel=0.004, coll_=None, note=''):
    x0, x1, y0, y1 = ext
    (cx, cy), w, d, rot = place_dims(x0, x1, y0, y1, facing)
    g = Geo()
    build(g, w, d)
    ob = g.to_object(uid, coll_ or C_UNIT, (cx, cy, z), rot, bevel=bevel)
    tag(ob, uid, name, room, kind, storage, note)
    ob['lab_facing'] = facing
    return ob

def deco(name, ext, facing, build, room='', z=0.0, bevel=0.003):
    x0, x1, y0, y1 = ext
    (cx, cy), w, d, rot = place_dims(x0, x1, y0, y1, facing)
    g = Geo(); build(g, w, d)
    ob = g.to_object(name, C_DECO, (cx, cy, z), rot, bevel=bevel)
    ob['lab_kind'] = 'decor'; ob['lab_room'] = room
    return ob

A, B, CR, D, E = '生化学実験室', '培養室', '廊下', '物品庫', '小部屋'

# ── 生化学実験室: アイランド実験台（両面キャビネット＋中央試薬棚）──
def island(g, w, d):
    build_bench(g, P, w, d, 0.80, double=True)
    build_reagent_shelf(g, P, w, -0.15, 0.15, 0.80, 1.75)
unit('A-D1', 'アイランド実験台1', A, 'bench', 1, (-3.92, -0.30, 3.55, 5.10), 'S', island)
unit('A-D2', 'アイランド実験台2', A, 'bench', 1, (-3.95, -0.42, 0.68, 2.15), 'S', island)
unit('A-D3', 'アイランド実験台3', A, 'bench', 1, (-4.05, 0.05, -2.22, -0.82), 'S', island)
unit('A-D4', 'アイランド実験台4（窓側に接続）', A, 'bench', 1, (-5.68, -0.55, -4.95, -3.50), 'S', island)

# ── 北壁 ──
unit('A-D5', '北壁 作業台', A, 'bench', 1, (-5.70, -1.85, 6.42, 7.02), 'S',
     lambda g, w, d: build_bench(g, P, w, d, 0.80, open_under=True))
unit('A-S1', '北壁 吊り棚（3段）', A, 'shelf', 1, (-5.00, -2.00, 6.72, 7.02), 'S',
     lambda g, w, d: build_wall_shelf(g, P, w, d, (1.12, 1.38, 1.65)))
unit('A-S2', '北壁 流し台', A, 'sink', 1, (-1.80, -0.25, 6.42, 7.02), 'S',
     lambda g, w, d: build_sink(g, P, w, d, 0.85, basins=((0.30, 0.55),)))
unit('A-S3', 'ワイヤーカート（北東）', A, 'rack', 1, (-0.15, 0.55, 6.45, 6.97), 'S',
     lambda g, w, d: build_wire_rack(g, P, w, d, 0.65, 3, casters=True))

# ── 西面（窓際）──
unit('A-D6', '窓際 作業台', A, 'bench', 1, (-5.65, -4.70, -0.40, 5.30), 'E',
     lambda g, w, d: build_bench(g, P, w, d, 0.80, open_under=True))
unit('A-S4', '窓際 オープン棚（作業台上）', A, 'shelf', 1, (-5.65, -5.33, -0.38, 0.62), 'E',
     lambda g, w, d: build_open_shelf(g, P, w, d, 1.25, (0.30, 0.62, 0.93)), z=0.80)
unit('A-S5', '北西 低キャビネット', A, 'cabinet', 1, (-5.65, -5.05, 5.35, 5.95), 'E',
     lambda g, w, d: build_bench(g, P, w, d, 0.85, front=[(0, w - 0.04, 'doors')], top='cab'))
unit('A-S6', '西面 ワイヤーラック', A, 'rack', 1, (-5.65, -4.98, -2.90, -1.50), 'E',
     lambda g, w, d: build_wire_rack(g, P, w, d, 2.05, 5))
deco('複合機', (-5.40, -4.95, -1.45, -0.55), 'E', lambda g, w, d: build_printer(g, P, w, d, 0.55, 'black', stand=0.40), A)
unit('A-S17', 'ワイヤーカート（複合機横）', A, 'rack', 1, (-5.68, -5.42, -1.45, -0.55), 'E',
     lambda g, w, d: build_wire_rack(g, P, w, d, 1.00, 4, casters=True))
unit('A-S18', '白ワゴン（窓際）', A, 'cabinet', 1, (-5.65, -5.00, -3.45, -2.95), 'E',
     lambda g, w, d: build_bench(g, P, w, d, 0.90, front=[(0, w - 0.04, 'drawers')], top='cab'))
unit('A-S7', 'ワイヤーカート（西）', A, 'rack', 1, (-5.62, -5.05, -5.50, -4.98), 'E',
     lambda g, w, d: build_wire_rack(g, P, w, d, 0.95, 3, casters=True))
deco('ゴミ箱_青', (-5.62, -5.28, -5.85, -5.50), 'E', lambda g, w, d: g.box(-w / 2, -d / 2, 0, w / 2, d / 2, 0.60, P['blue']), A)
unit('A-S8', '床置き機器（白）', A, 'equipment', 0, (-5.62, -5.05, -6.55, -6.00), 'E',
     lambda g, w, d: build_floor_centrifuge(g, P, w, d, 0.80, round_lid=False), note='製氷機などの床置き機器（要確認）')

# ── 南壁 ──
def south_shelf(g, w, d):
    build_open_shelf(g, P, w, d, 2.0, (0.45, 0.85, 1.25, 1.62), back=False)
    g.cyl(-0.15, 0.0, 0.02, 0.42, 0.17, P['blue'], seg=20)
unit('A-S9', '南壁 オープン棚', A, 'shelf', 1, (-4.40, -3.30, -7.00, -6.50), 'N', south_shelf)
def south_bench(g, w, d):
    build_bench(g, P, w, d, 0.80, front=[(0, 0.6, 'drawers'), (0.6, w - 0.64, 'open'), (w - 0.64, w - 0.04, 'doors')])
    # 純水装置
    g.box(-w / 2 + 0.85, -0.05, 0.80, -w / 2 + 1.15, 0.25, 1.30, P['blue'])
    g.box(-w / 2 + 0.85, -0.06, 1.12, -w / 2 + 1.15, -0.05, 1.22, P['panel'])
unit('A-D7', '南壁 実験台', A, 'bench', 1, (-3.30, -1.90, -7.00, -6.30), 'N', south_bench)
unit('A-S10', '南壁 流し台', A, 'sink', 1, (-1.88, -0.40, -7.00, -6.30), 'N',
     lambda g, w, d: build_sink(g, P, w, d, 0.85, basins=((0.0, 0.60),)))
unit('A-S11', '南東 ワイヤーラック', A, 'rack', 1, (-0.40, 0.55, -7.00, -6.45), 'N',
     lambda g, w, d: build_wire_rack(g, P, w, d, 1.75, 5))

# ── 東側の冷蔵庫・冷凍庫列（西向き）。名称・温度は既存アプリ（実験室管理アプリ）の現物ヒアリングに準拠 ──
def fr(style, h, **kw):
    return lambda g, w, d: build_fridge(g, P, w, d, h, style, **kw)
unit('A-C1', '冷蔵庫 4℃（両開き・ガラス扉）', A, 'fridge', 1, (0.80, 1.55, 5.05, 6.50), 'W', fr('glass2', 1.95))
unit('A-C2', '冷凍庫 -20℃（5段・ガラス扉）', A, 'fridge', 1, (0.80, 1.55, 4.20, 5.00), 'W', fr('glass1', 1.80))
unit('A-C3', '冷凍庫 -20℃（上下2段）', A, 'fridge', 1, (0.80, 1.55, 3.35, 4.15), 'W', fr('solid2v', 1.95))
unit('A-C4', '冷蔵庫 4℃', A, 'fridge', 1, (0.80, 1.55, 2.42, 3.27), 'W', fr('dual', 1.95))
unit('A-C5', '冷凍庫 -20℃（上下2段）', A, 'fridge', 1, (0.80, 1.55, 1.48, 2.33), 'W', fr('dual', 1.95))
unit('A-C6', '冷凍庫 -20℃（上下2段）', A, 'fridge', 1, (0.80, 1.55, 0.58, 1.42), 'W', fr('solid2v', 1.90))
unit('A-S12', '床置き遠心機', A, 'equipment', 0, (-0.05, 0.45, 3.55, 4.15), 'W',
     lambda g, w, d: build_floor_centrifuge(g, P, w, d, 0.85))

# ── 南東（培養庫まわり）──
unit('A-C7', '冷蔵庫 4℃（上下2段・ガラス扉）', A, 'fridge', 1, (0.05, 0.70, -5.00, -4.05), 'W', fr('glass2v', 1.90))
unit('A-S13', 'インキュベーター1', A, 'incubator', 1, (0.10, 0.70, -5.65, -5.02), 'W',
     lambda g, w, d: build_incubator(g, P, w, d, 1.66, 1, 0.10))
unit('A-S14', 'インキュベーター2', A, 'incubator', 1, (0.10, 0.70, -6.30, -5.67), 'W',
     lambda g, w, d: build_incubator(g, P, w, d, 1.66, 1, 0.10))
unit('A-S15', '南東 ワイヤーラック（インキュベーター横）', A, 'rack', 1, (0.15, 0.70, -7.00, -6.35), 'W',
     lambda g, w, d: build_wire_rack(g, P, w, d, 1.75, 5))
unit('A-D8', 'プリンター台', A, 'table', 0, (-0.35, 0.35, -3.20, -2.45), 'W',
     lambda g, w, d: (build_table(g, P, w, d, 0.72, top='app', leg='steel'),
                      g.box(-0.22, -0.18, 0.72, 0.22, 0.20, 0.98, P['app']),
                      g.box(-0.20, -0.19, 0.84, 0.20, -0.18, 0.86, P['steel'])))
unit('A-S16', '東面 ワイヤーラック', A, 'rack', 1, (0.15, 0.65, -3.62, -3.22), 'W',
     lambda g, w, d: build_wire_rack(g, P, w, d, 1.60, 4))
def basket_cart(g, w, d):
    build_wire_rack(g, P, w, d, 0.85, 3, casters=True)
    g.box(-w / 2 + 0.03, -d / 2 + 0.03, 0.85, w / 2 - 0.03, d / 2 - 0.03, 1.02, P['yellow'])
deco('台車（黄カゴ）', (-0.62, -0.02, -5.00, -4.25), 'W', basket_cart, A)
deco('段ボール台車（廃棄物）', (0.85, 1.40, -4.30, -3.62), 'W', lambda g, w, d: build_dolly_boxes(g, P, w, d, 1.40), A)

# 椅子・スツール（スキャン上の位置）
for i, (x, y) in enumerate(((-3.05, 6.05), (-1.35, 5.45), (-2.35, 3.20), (-1.10, 3.05), (-3.30, 2.55), (-2.05, 2.70),
                            (-1.20, 0.35), (-3.15, 0.40), (-2.10, -0.45), (-0.95, -2.55), (-3.40, -2.65), (-2.60, -5.35),
                            (-1.35, -5.45), (-4.30, 0.05), (-4.40, 5.80))):
    g = Geo(); build_stool(g, P)
    ob = g.to_object(f'スツール{i + 1}', C_DECO, (x, y, 0), 0.3 * i, bevel=0.0); ob['lab_kind'] = 'decor'; ob['lab_room'] = A
g = Geo(); build_office_chair(g, P)
ob = g.to_object('事務椅子_実験室', C_DECO, (-2.65, 6.15, 0), 0.4); ob['lab_kind'] = 'decor'

# ── 廊下（南側に冷凍庫・遠心機）──
deco('段ボール台車（廊下）', (0.98, 1.48, -2.72, -1.85), 'N', lambda g, w, d: build_dolly_boxes(g, P, w, d, 1.65), CR)
unit('C-C1', 'チェスト型フリーザー（上開き）', CR, 'chestFreezer', 1, (1.52, 3.58, -2.76, -1.82), 'N',
     lambda g, w, d: build_chest_freezer(g, P, w, d, 0.95, panel_side='right'), note='温度帯は要確認（超低温の可能性）')
unit('C-C2', '冷凍庫（上下2段）', CR, 'fridge', 1, (3.70, 4.50, -2.76, -1.88), 'N', fr('solid2v', 2.00),
     note='扉に -30 の表示あり（要確認）')
unit('C-S1', '大型冷却遠心機', CR, 'equipment', 0, (4.55, 5.50, -2.72, -1.88), 'N',
     lambda g, w, d: build_floor_centrifuge(g, P, w, d, 0.85, round_lid=False))
deco('遠心機上の段ボール', (4.62, 5.40, -2.64, -1.98), 'N', lambda g, w, d: build_boxes(g, P, w, d, 0.45, 2, seed=3), CR, z=0.85)
deco('玄関マット', (4.75, 5.45, -1.75, -0.85), 'S', lambda g, w, d: g.box(-w / 2, -d / 2, 0, w / 2, d / 2, 0.012, P['mat_green']), CR)

# ── 培養室 ──
unit('B-S1', 'ワイヤーラック（入口脇）', B, 'rack', 1, (1.95, 2.45, 0.10, 1.30), 'E',
     lambda g, w, d: build_wire_rack(g, P, w, d, 2.00, 5))
for i, (x, y, c) in enumerate(((2.17, 1.52, 'gray_cyl'), (2.17, 1.80, 'gray_cyl'), (2.15, 2.10, 'green'),
                               (2.15, 2.40, 'green'), (2.15, 5.40, 'green'))):
    g = Geo(); build_gas_cylinder(g, P, 1.30 if c == 'green' else 1.20, 0.11, c)
    ob = g.to_object(f'ガスボンベ{i + 1}', C_DECO, (x, y, 0), 0.0, bevel=0.0); ob['lab_kind'] = 'decor'; ob['lab_room'] = B
unit('B-D1', '西面 作業台', B, 'bench', 1, (1.95, 2.55, 2.55, 3.55), 'E',
     lambda g, w, d: build_bench(g, P, w, d, 0.85, front=[(0, w - 0.04, 'doors')]))
unit('B-S2', '卓上インキュベーター', B, 'incubator', 1, (1.98, 2.50, 2.72, 3.38), 'E',
     lambda g, w, d: build_incubator(g, P, w, d, 0.82, 1, 0.0), z=0.85)
unit('B-S3', 'CO2インキュベーター（2段）南', B, 'incubator', 1, (1.95, 2.65, 3.60, 4.35), 'E',
     lambda g, w, d: build_incubator(g, P, w, d, 0.88, 2, 0.10))
unit('B-S4', 'CO2インキュベーター（2段）北', B, 'incubator', 1, (1.95, 2.65, 4.42, 5.20), 'E',
     lambda g, w, d: build_incubator(g, P, w, d, 0.88, 2, 0.10))
unit('B-C1', '冷蔵庫 4℃（1列×5段・ガラス扉）', B, 'fridge', 1, (1.95, 2.38, 6.62, 7.35), 'S', fr('glass1', 1.95))
unit('B-C2', '冷蔵庫 4℃（2列×5段・ガラス扉）', B, 'fridge', 1, (2.45, 3.22, 6.62, 7.35), 'S', fr('glass1', 1.95))
def pc_cart(g, w, d):
    build_table(g, P, w, d, 0.75, top='app', leg='steel')
    build_monitor(g, P, 0.0, 0.05, 0.75, 0.48, 0.30)
unit('B-D2', 'PCワゴン', B, 'table', 0, (3.45, 4.15, 6.25, 6.92), 'S', pc_cart)
unit('B-D6', '北面 低キャビネット', B, 'cabinet', 1, (3.25, 4.28, 6.95, 7.35), 'S',
     lambda g, w, d: build_bench(g, P, w, d, 0.75, front=[(0, 0.5, 'drawers3'), (0.5, w - 0.04, 'doors')], top='cab'))
def pc_desk(g, w, d):
    build_table(g, P, w, d, 0.72, top='top', leg='frame', panel_legs=True)
    build_monitor(g, P, 0.15, 0.12, 0.72)
    g.box(0.0, -0.20, 0.72, 0.42, -0.06, 0.74, P['black'])
unit('B-D3', 'PCデスク', B, 'table', 1, (4.30, 5.58, 6.35, 7.32), 'S', pc_desk)
g = Geo(); build_office_chair(g, P)
ob = g.to_object('事務椅子_培養室', C_DECO, (4.70, 5.95, 0), math.pi + 0.3); ob['lab_kind'] = 'decor'
unit('B-D4', '中央 作業台', B, 'bench', 1, (3.20, 4.05, 1.75, 4.75), 'W',
     lambda g, w, d: build_bench(g, P, w, d, 0.85))
unit('B-S5', '安全キャビネット1', B, 'bsc', 0, (4.80, 5.60, 1.00, 2.50), 'W', lambda g, w, d: build_bsc(g, P, w, d, 1.98))
unit('B-S6', '安全キャビネット2', B, 'bsc', 0, (4.80, 5.60, 2.52, 3.95), 'W', lambda g, w, d: build_bsc(g, P, w, d, 1.98))
unit('B-S7', '安全キャビネット3', B, 'bsc', 0, (4.80, 5.60, 3.97, 5.35), 'W', lambda g, w, d: build_bsc(g, P, w, d, 1.98))
unit('B-S8', '南東 オープン棚', B, 'shelf', 1, (5.00, 5.60, -0.37, 0.90), 'W',
     lambda g, w, d: build_open_shelf(g, P, w, d, 2.00, (0.40, 0.85, 1.25, 1.62)))
unit('B-D5', '南面 作業台', B, 'bench', 1, (3.90, 5.00, -0.37, 0.40), 'N',
     lambda g, w, d: build_bench(g, P, w, d, 0.85, front=[(0, 0.5, 'drawers3'), (0.5, w - 0.04, 'doors')]))
unit('B-S9', '培養室 流し台（ステンレス脚付き）', B, 'sink', 0, (3.22, 3.90, -0.37, 0.48), 'N',
     lambda g, w, d: build_sink(g, P, w, d, 0.85, basins=((0.0, 0.48),), legs=True))

# ── 物品庫 ──
unit('D-S2', '北面 試薬棚（白）', D, 'shelf', 1, (1.95, 3.30, -3.55, -2.95), 'S',
     lambda g, w, d: build_angle_shelf(g, P, w, d, 2.20, 5, board='board'))
unit('D-S3', '北面 スチール棚1', D, 'shelf', 1, (3.30, 4.40, -3.55, -2.95), 'S',
     lambda g, w, d: build_angle_shelf(g, P, w, d, 2.20, 5))
unit('D-S4', '北面 スチール棚2', D, 'shelf', 1, (4.40, 5.55, -3.55, -2.95), 'S',
     lambda g, w, d: build_angle_shelf(g, P, w, d, 2.20, 5))
deco('段ボール（感染性廃棄物）', (1.52, 2.00, -4.30, -3.65), 'E', lambda g, w, d: build_boxes(g, P, w, d, 1.40, 3, seed=5), D)
def scope_bench(g, w, d):
    build_bench(g, P, w, d, 0.75, open_under=True)
    build_microscope(g, P, -0.25, 0.0, 0.75)
    build_monitor(g, P, 0.25, 0.10, 0.75)
unit('D-D1', '顕微鏡台', D, 'bench', 1, (1.50, 2.08, -5.45, -4.35), 'E', scope_bench)
deco('段ボール（床置き）', (2.10, 2.55, -5.40, -4.45), 'E', lambda g, w, d: build_boxes(g, P, w, d, 0.60, 1, seed=8), D)
deco('クーラーボックス', (1.55, 2.00, -5.85, -5.50), 'E', lambda g, w, d: (g.box(-w / 2, -d / 2, 0, w / 2, d / 2, 0.36, P['blue']), g.box(-w / 2, -d / 2, 0.36, w / 2, d / 2, 0.40, P['white_plast'])), D)
deco('床置きトレー', (1.52, 1.85, -6.35, -5.90), 'E', lambda g, w, d: build_boxes(g, P, w, d, 0.25, 1, seed=13), D)
unit('D-S5', 'ドラフトチャンバー', D, 'hood', 1, (1.55, 2.55, -7.35, -6.55), 'N', lambda g, w, d: build_fume_hood(g, P, w, d, 2.30))
unit('D-S7', '薬品キャビネット（低）', D, 'cabinet', 1, (2.65, 3.25, -7.35, -6.85), 'N',
     lambda g, w, d: build_bench(g, P, w, d, 0.75, front=[(0, w - 0.04, 'doors')], top='cab'))
unit('D-D3', '間仕切り沿い 作業台', D, 'bench', 1, (3.00, 4.60, -5.45, -4.75), 'N',
     lambda g, w, d: build_bench(g, P, w, d, 0.75, open_under=True))
unit('D-S8', '作業台上 スチール棚', D, 'shelf', 1, (3.00, 4.60, -5.45, -5.05), 'N',
     lambda g, w, d: build_angle_shelf(g, P, w, d, 1.45, 4), z=0.75)
unit('D-S9', 'スチール収納庫', D, 'cabinet', 1, (4.65, 5.60, -5.45, -4.95), 'N',
     lambda g, w, d: build_tall_cabinet(g, P, w, d, 2.00, 2))

# ── 小部屋 ──
unit('E-D1', '机', E, 'table', 1, (4.30, 5.58, -7.33, -6.70), 'N',
     lambda g, w, d: build_table(g, P, w, d, 0.72, top='top', leg='frame', panel_legs=True))
deco('青いカバーの機器', (3.68, 4.05, -7.30, -6.75), 'N',
     lambda g, w, d: g.box(-w / 2, -d / 2, 0, w / 2, d / 2, 1.00, P['blue']), E)
deco('段ボール（小部屋）', (4.05, 5.20, -5.95, -5.57), 'S', lambda g, w, d: build_boxes(g, P, w, d, 0.90, 2, seed=11), E)
unit('E-C1', '小型冷蔵庫', E, 'fridge', 1, (5.12, 5.58, -6.55, -6.05), 'W', fr('solid1', 1.10), note='温度帯は要確認')
unit('E-S1', '南壁 吊り棚', E, 'shelf', 1, (4.00, 4.90, -7.35, -7.10), 'N',
     lambda g, w, d: build_wall_shelf(g, P, w, d, (1.45, 1.70)))
g = Geo(); build_office_chair(g, P)
ob = g.to_object('事務椅子_小部屋', C_DECO, (4.90, -6.35, 0), 0.2); ob['lab_kind'] = 'decor'

# ───────── 出力 ─────────
bpy.context.view_layer.update()
for m in META:
    ob = bpy.data.objects[m['obj']]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    cs = [ob.matrix_world @ v.co for v in ev.data.vertices]
    mn = [min(c[i] for c in cs) for i in range(3)]; mx = [max(c[i] for c in cs) for i in range(3)]
    m['bbox'] = dict(min=[round(v, 3) for v in mn], max=[round(v, 3) for v in mx])
    m['facing'] = ob.get('lab_facing', '')
    del m['obj']

ROOMS = [
    dict(id='A', name=A, poly=[[-5.70, -7.00], [0.70, -7.00], [0.70, -4.35], [1.40, -4.35], [1.40, -2.95], [0.72, -2.95], [0.72, 0.55], [1.75, 0.55], [1.75, 6.55], [0.72, 6.55], [0.72, 7.02], [-5.70, 7.02]]),
    dict(id='B', name=B, poly=[[1.92, -0.37], [5.62, -0.37], [5.62, 7.35], [1.92, 7.35]]),
    dict(id='C', name=CR, poly=[[0.72, -2.95], [1.40, -2.95], [1.40, -2.78], [5.62, -2.78], [5.62, -0.53], [0.72, -0.53]]),
    dict(id='D', name=D, poly=[[1.50, -7.35], [3.52, -7.35], [3.52, -5.45], [5.62, -5.45], [5.62, -2.95], [1.50, -2.95]]),
    dict(id='E', name=E, poly=[[3.62, -7.35], [5.62, -7.35], [5.62, -5.55], [3.62, -5.55]]),
]
meta = dict(source='2026_10_18.glb（ラボ空間スキャン）', coords='Blender: X=東, Y=北, Z=上 / glTF: x=東, y=上, z=南',
            scan_transform=dict(rotate_z_deg=2.0, floor_offset=1.395), ceiling=H, rooms=ROOMS, units=META)
with open(os.path.join(OUT, 'units.json'), 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'lab.blend'))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'lab.glb'), export_format='GLB', export_apply=True,
                          export_extras=True, export_yup=True, export_cameras=False, export_lights=False,
                          export_image_format='JPEG')
print('UNITS', len(META), 'storage', sum(1 for m in META if m['storage']))
