# -*- coding: utf-8 -*-
"""
ラボ3Dモデルの部品ビルダー群（Blender bpy/bmesh）。

座標系（Blenderワールド）: X=東, Y=北, Z=上, 単位メートル。床=Z0, 天井=Z2.40。
スキャン(2026_10_18.glb)を Z軸まわり +2.0° 回転・床を Z0 に合わせた座標と一致させている。

各什器は「ローカル座標で組み立て → 1オブジェクトに結合 → 中心・向きを与えて配置」する。
ローカル座標: x=幅方向(左→右), y=奥行方向(正面が -y 側), z=上。原点=フットプリント中心の床。
"""
import bpy, bmesh, math
from mathutils import Matrix, Vector

# ───────────────────────── マテリアル ─────────────────────────

def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [(v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]

_MATS = {}

def mat(name, hexcol, rough=0.6, metal=0.0, alpha=1.0, emit=None, emit_strength=1.0, image=None):
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    col = srgb(hexcol)
    bsdf.inputs['Base Color'].default_value = (*col, 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if alpha < 1.0:
        bsdf.inputs['Alpha'].default_value = alpha
        try:
            m.surface_render_method = 'BLENDED'
        except Exception:
            m.blend_method = 'BLEND'
    if emit:
        bsdf.inputs['Emission Color'].default_value = (*srgb(emit), 1)
        bsdf.inputs['Emission Strength'].default_value = emit_strength
    if image is not None:
        tex = m.node_tree.nodes.new('ShaderNodeTexImage')
        tex.image = image
        m.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    m.diffuse_color = (*col, alpha)
    _MATS[name] = m
    return m


def init_materials(floor_img=None):
    P = {}
    P['floor'] = mat('床_長尺シート', '#d8d0c0', 0.55, image=floor_img)
    P['wall'] = mat('壁_白', '#ebe8e1', 0.85)
    P['ceiling'] = mat('天井_岩綿吸音板', '#f1f0ec', 0.95)
    P['skirt'] = mat('幅木_グレー', '#8f8f8c', 0.6)
    P['cutcap'] = mat('壁_切断面', '#5d6166', 0.8)
    P['sash'] = mat('サッシ_アルミ', '#7e8287', 0.4, 0.6)
    P['glass'] = mat('窓ガラス', '#bcd3dc', 0.05, 0.0, alpha=0.22)
    P['top'] = mat('天板_黒エポキシ', '#1c1e21', 0.35)
    P['cab'] = mat('キャビネット_白', '#efeee9', 0.5)
    P['cab2'] = mat('キャビネット_扉', '#f6f5f1', 0.45)
    P['plinth'] = mat('台輪_グレー', '#5a5d61', 0.6)
    P['handle'] = mat('取手_金属', '#a3a8ad', 0.3, 0.8)
    P['steel'] = mat('スチール_グレー', '#c8cbcd', 0.45, 0.3)
    P['frame'] = mat('スチール_脚', '#d9dad8', 0.5, 0.2)
    P['stain'] = mat('ステンレス', '#c9ccce', 0.25, 0.9)
    P['basin'] = mat('ステンレス_シンク内', '#9da2a6', 0.3, 0.9)
    P['app'] = mat('機器_白', '#f1f1ed', 0.4)
    P['app2'] = mat('機器_アイボリー', '#e8e4d8', 0.45)
    P['panel'] = mat('操作パネル_黒', '#26292d', 0.3)
    P['display'] = mat('表示窓', '#0f2a24', 0.2, emit='#3fd28a', emit_strength=0.6)
    P['vent'] = mat('通気グリル', '#7f8388', 0.6)
    P['fglass'] = mat('扉ガラス', '#a9c6d1', 0.05, alpha=0.28)
    P['inner'] = mat('庫内_ライトグレー', '#dfe3e5', 0.6)
    P['wire'] = mat('ワイヤー棚_クローム', '#b9bdc1', 0.3, 0.85)
    P['angle'] = mat('スチール棚_ライトグレー', '#d7d8d4', 0.55, 0.15)
    P['board'] = mat('棚板_白', '#f3f2ee', 0.6)
    P['card'] = mat('段ボール', '#c39a6b', 0.85)
    P['card2'] = mat('段ボール_濃', '#a97f52', 0.85)
    P['blue'] = mat('樹脂_青', '#2f68b0', 0.5)
    P['navy'] = mat('座面_紺', '#272c3a', 0.6)
    P['black'] = mat('樹脂_黒', '#202225', 0.5)
    P['green'] = mat('ボンベ_緑', '#2d6b4c', 0.45, 0.2)
    P['gray_cyl'] = mat('ボンベ_灰', '#9aa1a6', 0.45, 0.3)
    P['yellow'] = mat('カゴ_黄', '#e7bf35', 0.6)
    P['bsc'] = mat('安全キャビネット_本体', '#e9e8e2', 0.45)
    P['door'] = mat('扉_クリーム', '#e6e2d8', 0.55)
    P['doorframe'] = mat('扉枠_グレー', '#9ea2a5', 0.45, 0.3)
    P['frost'] = mat('扉_ガラス', '#d5e2e7', 0.15, alpha=0.45)
    P['mat_green'] = mat('玄関マット', '#2f6a3c', 0.9)
    P['light'] = mat('照明', '#ffffff', 0.4, emit='#ffffff', emit_strength=2.0)
    P['ac'] = mat('空調カセット', '#e2e1dc', 0.6)
    P['acgrill'] = mat('空調グリル', '#b9b9b4', 0.7)
    P['clock'] = mat('時計_文字盤', '#f7f7f4', 0.4)
    P['red'] = mat('赤', '#b8322f', 0.5)
    P['orange'] = mat('橙', '#df7a2c', 0.6)
    P['screen'] = mat('モニター画面', '#111316', 0.15)
    P['white_plast'] = mat('樹脂_白', '#f4f4f1', 0.5)
    P['sticker'] = mat('ラベル_黄', '#f0d84a', 0.6)
    return P

# ───────────────────────── ジオメトリ構築 ─────────────────────────

class Geo:
    """1什器ぶんのメッシュをbmeshで組み立て、マテリアルはスロット番号で管理する。"""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _quad_faces(self, vs, idx, m, smooth=False):
        f = self.bm.faces.new([vs[i] for i in idx])
        f.material_index = self.mi(m)
        f.smooth = smooth
        return f

    def box(self, x0, y0, z0, x1, y1, z1, m, xf=None):
        """軸平行ボックス。xf(Matrix)を与えると頂点に変換を掛ける（回転部品用）。"""
        if x0 > x1: x0, x1 = x1, x0
        if y0 > y1: y0, y1 = y1, y0
        if z0 > z1: z0, z1 = z1, z0
        if x1 - x0 < 1e-5 or y1 - y0 < 1e-5 or z1 - z0 < 1e-5:
            return
        P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        if xf is not None:
            P = [tuple(xf @ Vector(p)) for p in P]
        vs = [self.bm.verts.new(p) for p in P]
        for idx in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self._quad_faces(vs, idx, m)

    def cyl(self, cx, cy, z0, z1, r, m, seg=20, r1=None, axis='z', xf=None, cap=True):
        """円柱（r1を与えると円錐台）。axis='x'/'y' で横倒し（cx,cy,z0..z1 は軸方向の座標指定に読み替え）。"""
        r1 = r if r1 is None else r1
        bot, top = [], []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            ca, sa = math.cos(a), math.sin(a)
            if axis == 'z':
                pb = (cx + r * ca, cy + r * sa, z0); pt = (cx + r1 * ca, cy + r1 * sa, z1)
            elif axis == 'x':   # (cy,cz)=(cx,cy) 引数を (y,z) と読む。z0..z1 は x 範囲
                pb = (z0, cx + r * ca, cy + r * sa); pt = (z1, cx + r1 * ca, cy + r1 * sa)
            else:               # axis y: (cx,cy)=(x,z), z0..z1 は y 範囲
                pb = (cx + r * ca, z0, cy + r * sa); pt = (cx + r1 * ca, z1, cy + r1 * sa)
            if xf is not None:
                pb = tuple(xf @ Vector(pb)); pt = tuple(xf @ Vector(pt))
            bot.append(self.bm.verts.new(pb)); top.append(self.bm.verts.new(pt))
        k = self.mi(m)
        for i in range(seg):
            j = (i + 1) % seg
            f = self.bm.faces.new([bot[i], bot[j], top[j], top[i]])
            f.material_index = k; f.smooth = True
        if cap:
            f = self.bm.faces.new(list(reversed(bot))); f.material_index = k
            f = self.bm.faces.new(top); f.material_index = k

    def to_object(self, name, coll, loc=(0, 0, 0), rotz=0.0, bevel=0.0):
        me = bpy.data.meshes.new(name)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        ob.rotation_euler = (0, 0, rotz)
        coll.objects.link(ob)
        if bevel > 0:
            md = ob.modifiers.new('Bevel', 'BEVEL')
            md.width = bevel; md.segments = 1; md.limit_method = 'ANGLE'
            md.angle_limit = math.radians(40); md.harden_normals = False
            md.use_clamp_overlap = True
        return ob


FACE_ROT = {'S': 0.0, 'N': math.pi, 'E': math.pi / 2, 'W': -math.pi / 2}


def place_dims(x0, x1, y0, y1, facing):
    """ワールドの範囲と正面向きから (中心, 幅w, 奥行d, 回転) を返す。"""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if facing in ('S', 'N'):
        w, d = x1 - x0, y1 - y0
    else:
        w, d = y1 - y0, x1 - x0
    return (cx, cy), abs(w), abs(d), FACE_ROT[facing]

# ───────────────────────── 共通の小部品 ─────────────────────────

def handle_bar_h(g, P, x0, x1, z, yf, depth=0.025, t=0.012):
    """水平バー取手（正面 yf の手前に出す）。"""
    g.box(x0, yf - depth, z - t / 2, x0 + 0.012, yf, z + t / 2, P['handle'])
    g.box(x1 - 0.012, yf - depth, z - t / 2, x1, yf, z + t / 2, P['handle'])
    g.box(x0, yf - depth, z - t / 2, x1, yf - depth + 0.01, z + t / 2, P['handle'])


def handle_bar_v(g, P, x, z0, z1, yf, depth=0.03, t=0.014):
    g.box(x - t / 2, yf - depth, z0, x + t / 2, yf - depth + 0.012, z1, P['handle'])
    g.box(x - t / 2, yf - depth, z0, x + t / 2, yf, z0 + 0.015, P['handle'])
    g.box(x - t / 2, yf - depth, z1 - 0.015, x + t / 2, yf, z1, P['handle'])


def cabinet(g, P, x0, x1, yf, yb, z0, z1, kind, face_sign=-1):
    """ベンチ下キャビネット1モジュール。yf=正面側y, yb=背面側y, face_sign=-1で -y 向き正面。
    kind: 'drawers' | 'drawers3' | 'doors' | 'door' | 'open' | 'mixed'(上引出し+下扉)"""
    if kind == 'open':
        return
    ylo, yhi = min(yf, yb), max(yf, yb)
    plinth = 0.08
    # 台輪（少し引っ込める）
    if face_sign < 0:
        g.box(x0 + 0.01, yf + 0.04, z0, x1 - 0.01, yb, z0 + plinth, P['plinth'])
        g.box(x0, yf + 0.018, z0 + plinth, x1, yb, z1, P['cab'])
    else:
        g.box(x0 + 0.01, yb, z0, x1 - 0.01, yf - 0.04, z0 + plinth, P['plinth'])
        g.box(x0, yb, z0 + plinth, x1, yf - 0.018, z1, P['cab'])
    gap = 0.004
    fz0, fz1 = z0 + plinth, z1

    def front_panel(a0, a1, b0, b1):
        if face_sign < 0:
            g.box(a0 + gap, yf, b0 + gap, a1 - gap, yf + 0.018, b1 - gap, P['cab2'])
        else:
            g.box(a0 + gap, yf - 0.018, b0 + gap, a1 - gap, yf, b1 - gap, P['cab2'])

    def hbar(a0, a1, z):
        w = a1 - a0; c = (a0 + a1) / 2; hw = min(0.09, w * 0.3)
        if face_sign < 0:
            handle_bar_h(g, P, c - hw, c + hw, z, yf)
        else:
            # 背面向き: 鏡像で +y 側に出す
            g.box(c - hw, yf, z - 0.006, c + hw, yf + 0.022, z + 0.006, P['handle'])

    def vbar(x, b0, b1):
        if face_sign < 0:
            handle_bar_v(g, P, x, b0, b1, yf)
        else:
            g.box(x - 0.007, yf, b0, x + 0.007, yf + 0.026, b1, P['handle'])

    H = fz1 - fz0
    if kind in ('drawers', 'drawers3'):
        n = 4 if kind == 'drawers' else 3
        # 上段ほど浅い引き出し（実験台の定番構成）
        ratios = [0.18, 0.22, 0.28, 0.32] if n == 4 else [0.25, 0.35, 0.40]
        z = fz1
        for r in ratios:
            zz = z - H * r
            front_panel(x0, x1, zz, z)
            hbar(x0, x1, z - min(0.05, H * r * 0.35))
            z = zz
    elif kind == 'doors':
        xm = (x0 + x1) / 2
        front_panel(x0, xm, fz0, fz1); front_panel(xm, x1, fz0, fz1)
        vbar(xm - 0.04, fz1 - 0.22, fz1 - 0.06); vbar(xm + 0.04, fz1 - 0.22, fz1 - 0.06)
    elif kind == 'door':
        front_panel(x0, x1, fz0, fz1)
        vbar(x1 - 0.05, fz1 - 0.22, fz1 - 0.06)
    elif kind == 'mixed':
        zt = fz1 - H * 0.24
        front_panel(x0, x1, zt, fz1); hbar(x0, x1, fz1 - 0.05)
        xm = (x0 + x1) / 2
        front_panel(x0, xm, fz0, zt); front_panel(xm, x1, fz0, zt)
        vbar(xm - 0.04, zt - 0.2, zt - 0.05); vbar(xm + 0.04, zt - 0.2, zt - 0.05)


def module_plan(L, end='drawers'):
    """ベンチ長さLを引き出し/扉/足元スペースに割り付ける（両端=引出し、間は足元と扉を交互）。"""
    mods = []
    if L < 1.0:
        return [(0, L, 'doors')]
    e = 0.6
    mods.append((0, e, end))
    rest = L - 2 * e
    # 足元0.9 / 扉キャビ0.6 を交互に
    pattern = []
    while rest > 0.05:
        if not pattern or pattern[-1][1] != 'open':
            seg = min(0.95, rest); pattern.append((seg, 'open'))
        else:
            seg = min(0.6, rest); pattern.append((seg, 'doors' if seg > 0.45 else 'door'))
        rest -= seg
    # 最後が扉で終わると端の引出しと並んで不自然なので足元で終える調整
    x = e
    for seg, k in pattern:
        mods.append((x, x + seg, k)); x += seg
    mods.append((L - e, L, end))
    return mods

# ───────────────────────── 什器ビルダー ─────────────────────────

def build_bench(g, P, w, d, h=0.80, double=False, front=None, back=None, top='top', open_under=False):
    """実験台。double=Trueなら両面キャビネット（アイランド）。front/backはモジュール列。"""
    oh = 0.015
    g.box(-w / 2 - oh, -d / 2 - oh, h - 0.035, w / 2 + oh, d / 2 + oh, h, P[top])
    z1 = h - 0.035
    if open_under:
        # スチール脚フレームのテーブル（窓際・壁際の作業台）
        legs_x = [-w / 2 + 0.03]
        n = max(1, int(round(w / 1.8)))
        for i in range(1, n):
            legs_x.append(-w / 2 + w * i / n)
        legs_x.append(w / 2 - 0.03)
        for lx in legs_x:
            for ly in (-d / 2 + 0.03, d / 2 - 0.03):
                g.box(lx - 0.02, ly - 0.02, 0, lx + 0.02, ly + 0.02, z1, P['frame'])
            g.box(lx - 0.015, -d / 2 + 0.03, 0.10, lx + 0.015, d / 2 - 0.03, 0.13, P['frame'])
        g.box(-w / 2 + 0.03, d / 2 - 0.05, z1 - 0.10, w / 2 - 0.03, d / 2 - 0.02, z1, P['frame'])
        g.box(-w / 2 + 0.03, -d / 2 + 0.02, z1 - 0.06, w / 2 - 0.03, -d / 2 + 0.05, z1, P['frame'])
        return
    # 端の側板
    for sx in (-w / 2, w / 2 - 0.02):
        g.box(sx, -d / 2, 0, sx + 0.02, d / 2, z1, P['cab'])
    front = front or module_plan(w - 0.04)
    if double:
        back = back or module_plan(w - 0.04)
        ym = 0.0
        g.box(-w / 2 + 0.02, -0.01, 0.08, w / 2 - 0.02, 0.01, z1, P['cab'])   # 中央の幕板
        for a, b, k in front:
            cabinet(g, P, -w / 2 + 0.02 + a, -w / 2 + 0.02 + b, -d / 2, ym - 0.01, 0, z1, k, -1)
        for a, b, k in back:
            cabinet(g, P, -w / 2 + 0.02 + a, -w / 2 + 0.02 + b, d / 2, ym + 0.01, 0, z1, k, +1)
    else:
        g.box(-w / 2 + 0.02, d / 2 - 0.02, 0.08, w / 2 - 0.02, d / 2, z1, P['cab'])  # 背板
        for a, b, k in front:
            cabinet(g, P, -w / 2 + 0.02 + a, -w / 2 + 0.02 + b, -d / 2, d / 2 - 0.02, 0, z1, k, -1)


def build_reagent_shelf(g, P, w, y0, y1, z0, ztop=1.75, boards=(1.10, 1.42), posts=None):
    """アイランド中央の試薬棚（両面オープン）。"""
    t = 0.02
    n = posts or max(2, int(round(w / 1.2)) + 1)
    for i in range(n):
        x = -w / 2 + (w - 0.03) * i / (n - 1)
        g.box(x, y0, z0, x + 0.03, y1, ztop, P['board'])
    for z in list(boards) + [ztop - t]:
        g.box(-w / 2, y0, z, w / 2, y1, z + t, P['board'])
    # 落下防止の細い棚桟（両面）
    for z in list(boards):
        for yy in (y0, y1 - 0.012):
            g.box(-w / 2, yy, z + 0.06, w / 2, yy + 0.012, z + 0.075, P['steel'])


def build_wall_shelf(g, P, w, d, boards, posts=None):
    """壁付けの棚（ベンチ上）。boards=棚板Z。正面 -y, 奥 +y が壁。"""
    n = posts or max(2, int(round(w / 1.0)) + 1)
    zt = max(boards) + 0.02
    for i in range(n):
        x = -w / 2 + (w - 0.025) * i / (n - 1)
        g.box(x, -d / 2, min(boards) - 0.02, x + 0.025, d / 2, zt, P['board'])
    for z in boards:
        g.box(-w / 2, -d / 2, z, w / 2, d / 2, z + 0.02, P['board'])


def build_sink(g, P, w, d, h=0.85, basins=((0.0, 0.55),), faucet=True, legs=False):
    """流し台。basins=(中心x, 幅)。ステンレス天板＋白キャビ扉。"""
    z1 = h - 0.03
    if legs:
        # 脚付きステンレス流し（下はオープン、下段に棚板）
        for x in (-w / 2 + 0.03, w / 2 - 0.03):
            for y in (-d / 2 + 0.05, d / 2 - 0.05):
                g.cyl(x, y, 0, z1, 0.018, P['stain'], seg=10)
        g.box(-w / 2 + 0.02, -d / 2 + 0.04, 0.15, w / 2 - 0.02, d / 2 - 0.04, 0.17, P['stain'])
    else:
        # キャビネット（扉）
        nd = max(1, int(round(w / 0.75)))
        for i in range(nd):
            a = -w / 2 + w * i / nd; b = -w / 2 + w * (i + 1) / nd
            cabinet(g, P, a, b, -d / 2 + 0.03, d / 2, 0, z1, 'doors', -1)
    # 天板（シンク穴を避けて分割）
    bx = sorted([(c - bw / 2, c + bw / 2) for c, bw in basins])
    by0, by1 = -d / 2 + 0.10, d / 2 - 0.12
    x = -w / 2 - 0.01
    for a, b in bx:
        g.box(x, -d / 2, z1, a, d / 2 + 0.0, h, P['stain'])
        g.box(a, -d / 2, z1, b, by0, h, P['stain'])
        g.box(a, by1, z1, b, d / 2, h, P['stain'])
        # 槽（底と側面）
        g.box(a, by0, h - 0.22, b, by1, h - 0.21, P['basin'])
        g.box(a, by0, h - 0.22, a + 0.01, by1, h, P['basin'])
        g.box(b - 0.01, by0, h - 0.22, b, by1, h, P['basin'])
        g.box(a, by0, h - 0.22, b, by0 + 0.01, h, P['basin'])
        g.box(a, by1 - 0.01, h - 0.22, b, by1, h, P['basin'])
        if faucet:
            c = (a + b) / 2
            g.cyl(c, d / 2 - 0.06, h, h + 0.28, 0.014, P['stain'], seg=12)
            g.box(c - 0.012, d / 2 - 0.07, h + 0.26, c + 0.012, by1 - 0.06 + 0.02 - 0.15, h + 0.29, P['stain'])
            g.box(c - 0.05, d / 2 - 0.08, h + 0.17, c + 0.05, d / 2 - 0.04, h + 0.20, P['stain'])
        x = b
    g.box(x, -d / 2, z1, w / 2 + 0.01, d / 2, h, P['stain'])
    # バックガード
    g.box(-w / 2 - 0.01, d / 2 - 0.02, h, w / 2 + 0.01, d / 2, h + 0.10, P['stain'])


def build_fridge(g, P, w, d, h, style='solid2v', panel_top=True, split=0.5, brand_strip=None):
    """冷蔵庫・冷凍庫・ショーケース。正面 -y。
    style: glass2(両開きガラス) / glass1(片開きガラス) / glass2v(上下ガラス) / solid1 / solid2v(上下扉) / dual(上大下小)"""
    base = 0.09
    yf = -d / 2
    door_t = 0.045
    glass = style.startswith('glass')
    # 台座と通気グリル
    g.box(-w / 2 + 0.01, yf + 0.03, 0, w / 2 - 0.01, d / 2, base, P['plinth'])
    for i in range(6):
        z = 0.015 + i * 0.012
        g.box(-w / 2 + 0.06, yf + 0.025, z, w / 2 - 0.06, yf + 0.03, z + 0.005, P['vent'])
    body_y0 = yf + door_t
    if glass:
        # 中が見えるように箱を中空で組む（側板・背板・天板・底板）
        t = 0.03
        g.box(-w / 2, body_y0, base, -w / 2 + t, d / 2, h, P['app'])
        g.box(w / 2 - t, body_y0, base, w / 2, d / 2, h, P['app'])
        g.box(-w / 2, d / 2 - t, base, w / 2, d / 2, h, P['app'])
        g.box(-w / 2, body_y0, h - 0.16, w / 2, d / 2, h, P['app'])
        g.box(-w / 2, body_y0, base, w / 2, d / 2, base + 0.06, P['app'])
        g.box(-w / 2 + t, d / 2 - t - 0.005, base + 0.06, w / 2 - t, d / 2 - t, h - 0.16, P['inner'])
    else:
        g.box(-w / 2, body_y0, base, w / 2, d / 2, h, P['app'])
    zt = h - (0.16 if glass else 0.0)
    zb = base + (0.06 if glass else 0.0)
    gap = 0.006

    def solid_door(x0, x1, z0, z1, hx):
        g.box(x0 + gap, yf, z0 + gap, x1 - gap, body_y0, z1 - gap, P['app'])
        handle_bar_v(g, P, hx, z0 + (z1 - z0) * 0.30, z0 + (z1 - z0) * 0.75, yf)

    def glass_door(x0, x1, z0, z1, hx, shelves=4):
        fw = 0.055
        g.box(x0 + gap, yf, z0 + gap, x1 - gap, body_y0, z0 + fw, P['app'])
        g.box(x0 + gap, yf, z1 - fw, x1 - gap, body_y0, z1 - gap, P['app'])
        g.box(x0 + gap, yf, z0 + fw, x0 + fw, body_y0, z1 - fw, P['app'])
        g.box(x1 - fw, yf, z0 + fw, x1 - gap, body_y0, z1 - fw, P['app'])
        g.box(x0 + fw, yf + 0.018, z0 + fw, x1 - fw, yf + 0.024, z1 - fw, P['fglass'])
        handle_bar_v(g, P, hx, z0 + (z1 - z0) * 0.30, z0 + (z1 - z0) * 0.70, yf)
        # 庫内棚（ガラス越しに見える）
        for i in range(1, shelves):
            z = z0 + (z1 - z0) * i / shelves
            g.box(x0 + 0.04, body_y0 + 0.02, z, x1 - 0.04, d / 2 - 0.05, z + 0.012, P['wire'])

    if style == 'glass2':
        xm = 0.0
        glass_door(-w / 2, xm, zb, zt, xm - 0.05, 5); glass_door(xm, w / 2, zb, zt, xm + 0.05, 5)
    elif style == 'glass1':
        glass_door(-w / 2, w / 2, zb, zt, w / 2 - 0.07, 5)
    elif style == 'glass2v':
        zm = zb + (zt - zb) * split
        glass_door(-w / 2, w / 2, zm, zt, -w / 2 + 0.07, 3)
        glass_door(-w / 2, w / 2, zb, zm, -w / 2 + 0.07, 3)
        g.box(-w / 2, body_y0 - 0.002, zm - 0.02, w / 2, d / 2, zm + 0.02, P['app'])
    elif style == 'solid1':
        solid_door(-w / 2, w / 2, zb, zt, w / 2 - 0.07)
    elif style in ('solid2v', 'dual'):
        zm = zb + (zt - zb) * (split if style == 'solid2v' else 0.45)
        solid_door(-w / 2, w / 2, zm, zt, -w / 2 + 0.07)
        solid_door(-w / 2, w / 2, zb, zm, -w / 2 + 0.07)
    if panel_top and not glass:
        # 上部の操作パネル帯（PHC/SANYO系）
        g.box(-w / 2 + 0.05, yf - 0.004, h - 0.12, w / 2 - 0.05, yf + 0.002, h - 0.03, P['panel'])
        g.box(w / 2 - 0.26, yf - 0.007, h - 0.10, w / 2 - 0.08, yf - 0.003, h - 0.05, P['display'])
    if glass:
        g.box(-w / 2 + 0.05, yf + 0.0, h - 0.13, w / 2 - 0.05, body_y0, h - 0.03, P['app'])
        g.box(-0.12, yf - 0.004, h - 0.11, 0.12, yf + 0.001, h - 0.05, P['panel'])
        g.box(-0.08, yf - 0.006, h - 0.10, 0.02, yf - 0.002, h - 0.06, P['display'])


def build_incubator(g, P, w, d, tier_h, tiers=2, stand=0.10, window=True):
    """CO2インキュベーター（段積み）。正面 -y。"""
    yf = -d / 2
    if stand > 0:
        for sx in (-w / 2 + 0.03, w / 2 - 0.06):
            for sy in (yf + 0.05, d / 2 - 0.08):
                g.box(sx, sy, 0, sx + 0.03, sy + 0.03, stand, P['frame'])
        g.box(-w / 2, yf + 0.03, stand - 0.03, w / 2, d / 2, stand, P['frame'])
    z = stand
    for t in range(tiers):
        z0, z1 = z + 0.005, z + tier_h
        g.box(-w / 2, yf + 0.04, z0, w / 2, d / 2, z1, P['app2'])
        # 外扉
        g.box(-w / 2 + 0.01, yf, z0 + 0.04, w / 2 - 0.08, yf + 0.04, z1 - 0.12, P['app'])
        handle_bar_v(g, P, w / 2 - 0.12, z0 + 0.25 * tier_h, z0 + 0.6 * tier_h, yf)
        if window:
            wz0 = z0 + tier_h * 0.22; wz1 = z0 + tier_h * 0.72
            g.box(-0.07, yf - 0.002, wz0, 0.07, yf + 0.002, wz1, P['screen'])
        # 上部操作パネル
        g.box(-w / 2 + 0.03, yf + 0.0, z1 - 0.10, w / 2 - 0.03, yf + 0.04, z1 - 0.02, P['app'])
        g.box(-0.18, yf - 0.004, z1 - 0.09, 0.10, yf + 0.001, z1 - 0.03, P['panel'])
        g.box(-0.15, yf - 0.006, z1 - 0.08, -0.05, yf - 0.002, z1 - 0.04, P['display'])
        z = z1


def build_bsc(g, P, w, d, h=1.98, stand=0.72):
    """安全キャビネット（クラスII）。架台＋本体＋前面ガラスサッシ。正面 -y。"""
    yf = -d / 2
    # 架台
    for sx in (-w / 2 + 0.03, w / 2 - 0.07):
        for sy in (yf + 0.06, d / 2 - 0.09):
            g.box(sx, sy, 0, sx + 0.04, sy + 0.04, stand, P['frame'])
            g.box(sx - 0.01, sy - 0.01, 0, sx + 0.05, sy + 0.05, 0.02, P['plinth'])
    g.box(-w / 2 + 0.03, yf + 0.06, 0.18, w / 2 - 0.03, d / 2 - 0.05, 0.21, P['frame'])
    # 本体
    zb = stand
    g.box(-w / 2, yf + 0.06, zb, -w / 2 + 0.06, d / 2, h, P['bsc'])
    g.box(w / 2 - 0.06, yf + 0.06, zb, w / 2, d / 2, h, P['bsc'])
    g.box(-w / 2, d / 2 - 0.06, zb, w / 2, d / 2, h, P['bsc'])
    g.box(-w / 2, yf, zb, w / 2, d / 2, zb + 0.10, P['bsc'])          # 前面下部
    g.box(-w / 2 + 0.06, yf + 0.12, zb + 0.10, w / 2 - 0.06, d / 2 - 0.06, zb + 0.12, P['stain'])  # 作業台
    g.box(-w / 2 + 0.06, yf + 0.12, zb + 0.12, w / 2 - 0.06, d / 2 - 0.07, h - 0.45, P['inner'])     # 庫内
    zs0, zs1 = zb + 0.32, h - 0.50
    g.box(-w / 2 + 0.06, yf + 0.03, zs0, w / 2 - 0.06, yf + 0.04, zs1, P['fglass'])                    # サッシ
    g.box(-w / 2 + 0.06, yf + 0.025, zs0 - 0.03, w / 2 - 0.06, yf + 0.045, zs0, P['steel'])
    g.box(-w / 2, yf, h - 0.50, w / 2, d / 2, h, P['bsc'])                                            # 上部
    g.box(-w / 2 + 0.10, yf - 0.004, h - 0.40, w / 2 - 0.10, yf + 0.0, h - 0.30, P['app'])
    g.box(w / 2 - 0.45, yf - 0.007, h - 0.38, w / 2 - 0.15, yf - 0.003, h - 0.32, P['display'])
    g.box(-w / 2 + 0.15, yf - 0.006, h - 0.17, -w / 2 + 0.45, yf - 0.002, h - 0.10, P['blue'])        # ロゴ帯
    g.box(-w / 2 + 0.06, yf - 0.002, zb + 0.10, w / 2 - 0.06, yf + 0.03, zb + 0.12, P['steel'])


def build_fume_hood(g, P, w, d, h=2.30):
    yf = -d / 2
    zb = 0.85
    cabinet(g, P, -w / 2, w / 2, yf + 0.02, d / 2, 0, zb - 0.03, 'doors', -1)
    g.box(-w / 2 - 0.01, yf, zb - 0.03, w / 2 + 0.01, d / 2, zb, P['top'])
    g.box(-w / 2, yf, zb, -w / 2 + 0.08, d / 2, h, P['app'])
    g.box(w / 2 - 0.08, yf, zb, w / 2, d / 2, h, P['app'])
    g.box(-w / 2, d / 2 - 0.04, zb, w / 2, d / 2, h, P['inner'])
    g.box(-w / 2 + 0.08, yf + 0.10, zb, w / 2 - 0.08, d / 2 - 0.04, zb + 0.01, P['top'])
    g.box(-w / 2 + 0.08, yf + 0.04, zb + 0.45, w / 2 - 0.08, yf + 0.05, zb + 0.95, P['fglass'])
    g.box(-w / 2 + 0.08, yf + 0.03, zb + 0.42, w / 2 - 0.08, yf + 0.06, zb + 0.46, P['steel'])
    g.box(-w / 2, yf, zb + 0.95, w / 2, d / 2, h, P['app'])
    g.box(-w / 2 + 0.1, yf - 0.004, h - 0.30, w / 2 - 0.1, yf, h - 0.18, P['app2'])


def build_chest_freezer(g, P, w, d, h, panel_side='left'):
    """上開きのチェスト型フリーザー。正面 -y。panel_side=操作部のある端（正面から見て）。"""
    yf = -d / 2
    for sx in (-w / 2 + 0.06, w / 2 - 0.06):
        for sy in (yf + 0.08, d / 2 - 0.08):
            g.cyl(sx, sy, 0, 0.06, 0.03, P['black'], seg=10)
    g.box(-w / 2, yf, 0.06, w / 2, d / 2, h - 0.09, P['app'])
    g.box(-w / 2 - 0.005, yf - 0.012, h - 0.09, w / 2 + 0.005, d / 2, h, P['app'])
    g.box(-w / 2 + 0.01, yf - 0.013, h - 0.095, w / 2 - 0.01, yf - 0.011, h - 0.088, P['plinth'])
    hx = 0.0
    for c in ((-w * 0.18), (w * 0.18)):
        g.box(c - 0.12, yf - 0.05, h - 0.13, c + 0.12, yf - 0.012, h - 0.10, P['handle'])
    if panel_side == 'left':
        px0, px1 = -w / 2 + 0.04, -w / 2 + 0.44
    else:
        px0, px1 = w / 2 - 0.44, w / 2 - 0.04
    g.box(px0, yf - 0.006, h - 0.38, px1, yf + 0.001, h - 0.16, P['panel'])
    g.box(px0 + 0.04, yf - 0.009, h - 0.33, px0 + 0.20, yf - 0.005, h - 0.24, P['display'])
    # 吸排気グリル（操作部の下）
    for i in range(10):
        z = 0.12 + i * 0.03
        g.box(px0, yf - 0.004, z, px1, yf + 0.001, z + 0.012, P['vent'])
    g.box(px0, yf - 0.007, h - 0.48, px0 + 0.18, yf - 0.003, h - 0.42, P['sticker'])


def build_floor_centrifuge(g, P, w, d, h, round_lid=True):
    yf = -d / 2
    g.box(-w / 2, yf + 0.02, 0, w / 2, d / 2, 0.06, P['plinth'])
    g.box(-w / 2, yf, 0.06, w / 2, d / 2, h - 0.08, P['app'])
    g.box(-w / 2 + 0.03, yf - 0.004, h - 0.30, w / 2 - 0.03, yf + 0.001, h - 0.16, P['panel'])
    g.box(-w / 2 + 0.08, yf - 0.007, h - 0.27, -w / 2 + 0.30, yf - 0.003, h - 0.20, P['display'])
    for i in range(6):
        z = 0.12 + i * 0.035
        g.box(-w / 2 + 0.08, yf - 0.004, z, w / 2 - 0.08, yf + 0.001, z + 0.014, P['vent'])
    g.box(-w / 2, yf, h - 0.08, w / 2, d / 2, h, P['app2'])
    if round_lid:
        g.cyl(0, 0.03, h, h + 0.02, min(w, d) * 0.36, P['app'], seg=28)


def build_wire_rack(g, P, w, d, h, levels=5, casters=False):
    """スチールワイヤーラック（クローム）。"""
    z0 = 0.10 if casters else 0.02
    for x in (-w / 2 + 0.013, w / 2 - 0.013):
        for y in (-d / 2 + 0.013, d / 2 - 0.013):
            g.cyl(x, y, 0 if not casters else 0.08, h, 0.0125, P['wire'], seg=10)
            if casters:
                g.cyl(x, y, 0.0, 0.08, 0.03, P['black'], seg=10)
    for i in range(levels):
        z = z0 + (h - z0 - 0.03) * i / max(1, levels - 1)
        g.box(-w / 2 + 0.005, -d / 2 + 0.005, z, w / 2 - 0.005, d / 2 - 0.005, z + 0.006, P['wire'])
        g.box(-w / 2, -d / 2, z, w / 2, -d / 2 + 0.012, z + 0.03, P['wire'])
        g.box(-w / 2, d / 2 - 0.012, z, w / 2, d / 2, z + 0.03, P['wire'])
        # ワイヤーの桟（見た目用に数本）
        nb = max(3, int(w / 0.08))
        for k in range(1, nb):
            x = -w / 2 + w * k / nb
            g.box(x - 0.002, -d / 2, z + 0.006, x + 0.002, d / 2, z + 0.012, P['wire'])


def build_angle_shelf(g, P, w, d, h, levels=5, board='angle'):
    """軽量スチール棚（アングル棚）。"""
    t = 0.004
    for x, sx in ((-w / 2, 1), (w / 2, -1)):
        for y, sy in ((-d / 2, 1), (d / 2, -1)):
            g.box(x, y, 0, x + sx * 0.04, y + sy * t, h, P['angle'])
            g.box(x, y, 0, x + sx * t, y + sy * 0.04, h, P['angle'])
    for i in range(levels):
        z = 0.05 + (h - 0.08) * i / max(1, levels - 1)
        g.box(-w / 2 + 0.004, -d / 2 + 0.004, z, w / 2 - 0.004, d / 2 - 0.004, z + 0.012, P[board])
        g.box(-w / 2, -d / 2, z - 0.025, w / 2, -d / 2 + 0.006, z + 0.012, P[board])
        g.box(-w / 2, d / 2 - 0.006, z - 0.025, w / 2, d / 2, z + 0.012, P[board])


def build_open_shelf(g, P, w, d, h, boards, z0=0.0, back=True):
    """白いオープン棚（側板＋棚板＋背板）。boards は z0 からの相対高さ。"""
    t = 0.018
    g.box(-w / 2, -d / 2, z0, -w / 2 + t, d / 2, z0 + h, P['board'])
    g.box(w / 2 - t, -d / 2, z0, w / 2, d / 2, z0 + h, P['board'])
    g.box(-w / 2, -d / 2, z0 + h - t, w / 2, d / 2, z0 + h, P['board'])
    g.box(-w / 2, -d / 2, z0, w / 2, d / 2, z0 + t, P['board'])
    if back:
        g.box(-w / 2, d / 2 - 0.006, z0, w / 2, d / 2, z0 + h, P['board'])
    for b in boards:
        g.box(-w / 2 + t, -d / 2 + 0.01, z0 + b, w / 2 - t, d / 2, z0 + b + t, P['board'])


def build_tall_cabinet(g, P, w, d, h, tiers=2):
    """スチール収納庫（両開き扉・上下）。"""
    yf = -d / 2
    g.box(-w / 2, yf + 0.02, 0, w / 2, d / 2, 0.06, P['plinth'])
    g.box(-w / 2, yf + 0.02, 0.06, w / 2, d / 2, h, P['cab'])
    zs = [0.06 + (h - 0.06) * i / tiers for i in range(tiers + 1)]
    for i in range(tiers):
        z0, z1 = zs[i], zs[i + 1]
        g.box(-w / 2 + 0.005, yf, z0 + 0.005, -0.003, yf + 0.02, z1 - 0.005, P['cab2'])
        g.box(0.003, yf, z0 + 0.005, w / 2 - 0.005, yf + 0.02, z1 - 0.005, P['cab2'])
        handle_bar_v(g, P, -0.04, z0 + (z1 - z0) * 0.4, z0 + (z1 - z0) * 0.6, yf)
        handle_bar_v(g, P, 0.04, z0 + (z1 - z0) * 0.4, z0 + (z1 - z0) * 0.6, yf)


def build_table(g, P, w, d, h, top='top', leg='frame', panel_legs=False):
    g.box(-w / 2, -d / 2, h - 0.03, w / 2, d / 2, h, P[top])
    if panel_legs:
        g.box(-w / 2, -d / 2 + 0.05, 0, -w / 2 + 0.025, d / 2 - 0.02, h - 0.03, P[leg])
        g.box(w / 2 - 0.025, -d / 2 + 0.05, 0, w / 2, d / 2 - 0.02, h - 0.03, P[leg])
        g.box(-w / 2, d / 2 - 0.04, h - 0.35, w / 2, d / 2 - 0.02, h - 0.03, P[leg])
        return
    for x in (-w / 2 + 0.03, w / 2 - 0.03):
        for y in (-d / 2 + 0.03, d / 2 - 0.03):
            g.box(x - 0.02, y - 0.02, 0, x + 0.02, y + 0.02, h - 0.03, P[leg])
    g.box(-w / 2 + 0.03, d / 2 - 0.05, h - 0.12, w / 2 - 0.03, d / 2 - 0.02, h - 0.03, P[leg])


def build_star_base(g, P, z_top=0.10, r=0.30, col='black'):
    for i in range(5):
        a = 2 * math.pi * i / 5 + 0.3
        xf = Matrix.Rotation(a, 4, 'Z')
        g.box(0.02, -0.02, 0.05, r, 0.02, 0.08, P[col], xf=xf)
        cx, cy = r * 0.95 * math.cos(a), r * 0.95 * math.sin(a)
        g.cyl(cx, cy, 0.0, 0.05, 0.022, P['black'], seg=10)
    g.cyl(0, 0, 0.05, z_top, 0.04, P[col], seg=14)


def build_stool(g, P, h=0.58):
    build_star_base(g, P, 0.12, 0.27, 'steel')
    g.cyl(0, 0, 0.12, h - 0.06, 0.022, P['steel'], seg=12)
    g.cyl(0, 0, h - 0.07, h, 0.18, P['navy'], seg=28)
    g.cyl(0, 0, 0.30, 0.32, 0.20, P['steel'], seg=24, cap=True)


def build_office_chair(g, P):
    build_star_base(g, P, 0.14, 0.32, 'black')
    g.cyl(0, 0, 0.14, 0.42, 0.025, P['steel'], seg=12)
    g.box(-0.24, -0.24, 0.42, 0.24, 0.22, 0.50, P['black'])
    g.box(-0.22, 0.20, 0.52, 0.22, 0.26, 0.98, P['black'])
    g.box(-0.03, 0.18, 0.44, 0.03, 0.24, 0.55, P['black'])


def build_gas_cylinder(g, P, h=1.30, r=0.11, col='green'):
    g.cyl(0, 0, 0.0, h - 0.12, r, P[col], seg=24)
    g.cyl(0, 0, h - 0.12, h - 0.04, r, P[col], seg=24, r1=r * 0.45)
    g.cyl(0, 0, h - 0.04, h + 0.06, 0.025, P['handle'], seg=12)
    g.box(-0.04, -0.01, h + 0.02, 0.06, 0.01, h + 0.04, P['handle'])
    g.cyl(0, 0, h * 0.62, h * 0.62 + 0.03, r + 0.006, P['plinth'], seg=24)


def build_boxes(g, P, w, d, h, rows=2, seed=0):
    """段ボールの積み重ね（見た目用）。"""
    import random
    rnd = random.Random(seed)
    z = 0.0
    lh = h / rows
    for r in range(rows):
        n = max(1, int(round(w / 0.42)))
        for i in range(n):
            a = -w / 2 + w * i / n + 0.01; b = -w / 2 + w * (i + 1) / n - 0.01
            hh = lh * rnd.uniform(0.78, 1.0)
            g.box(a, -d / 2 + rnd.uniform(0, 0.04), z, b, d / 2 - rnd.uniform(0, 0.04), z + hh, P['card' if (i + r) % 3 else 'card2'])
        z += lh


def build_dolly_boxes(g, P, w, d, h):
    g.box(-w / 2, -d / 2, 0.06, w / 2, d / 2, 0.10, P['blue'])
    for x in (-w / 2 + 0.05, w / 2 - 0.05):
        for y in (-d / 2 + 0.05, d / 2 - 0.05):
            g.cyl(x, y, 0, 0.06, 0.03, P['black'], seg=10)
    g.box(-w / 2 + 0.02, -d / 2 + 0.02, 0.10, w / 2 - 0.02, d / 2 - 0.02, 0.10 + (h - 0.10) * 0.5, P['card'])
    g.box(-w / 2 + 0.03, -d / 2 + 0.03, 0.10 + (h - 0.10) * 0.5, w / 2 - 0.03, d / 2 - 0.03, h, P['card'])
    g.box(-0.08, -d / 2 + 0.019, h * 0.75, 0.08, -d / 2 + 0.025, h * 0.85, P['red'])


def build_printer(g, P, w, d, h, col='black', stand=0.0):
    if stand > 0:
        build_table(g, P, w, d, stand, top='steel', leg='steel')
    z = stand
    g.box(-w / 2, -d / 2, z, w / 2, d / 2, z + h * 0.62, P[col])
    g.box(-w / 2 + 0.02, -d / 2 + 0.04, z + h * 0.62, w / 2 - 0.02, d / 2, z + h, P[col])
    g.box(-w / 2 + 0.06, -d / 2 - 0.002, z + h * 0.2, w / 2 - 0.06, -d / 2 + 0.002, z + h * 0.22, P['steel'])
    g.box(-w / 2 + 0.06, -d / 2 - 0.002, z + h * 0.42, w / 2 - 0.06, -d / 2 + 0.002, z + h * 0.44, P['steel'])
    g.box(w / 2 - 0.25, -d / 2 + 0.01, z + h - 0.02, w / 2 - 0.05, -d / 2 + 0.12, z + h + 0.03, P['panel'])


def build_monitor(g, P, x, y, z, w=0.55, h=0.34, facing=-1):
    g.box(x - 0.08, y - 0.08, z, x + 0.08, y + 0.08, z + 0.012, P['black'])
    g.box(x - 0.02, y - 0.01, z, x + 0.02, y + 0.03, z + 0.15, P['black'])
    g.box(x - w / 2, y - 0.02, z + 0.12, x + w / 2, y + 0.01, z + 0.12 + h, P['black'])
    g.box(x - w / 2 + 0.01, y - 0.022 if facing < 0 else y + 0.01, z + 0.13, x + w / 2 - 0.01, y - 0.019 if facing < 0 else y + 0.013, z + 0.11 + h, P['screen'])


def build_microscope(g, P, x, y, z):
    g.box(x - 0.13, y - 0.18, z, x + 0.13, y + 0.16, z + 0.06, P['app'])
    g.box(x - 0.05, y + 0.06, z + 0.06, x + 0.05, y + 0.16, z + 0.40, P['app'])
    g.box(x - 0.10, y - 0.10, z + 0.16, x + 0.10, y + 0.08, z + 0.19, P['black'])
    g.box(x - 0.05, y - 0.12, z + 0.36, x + 0.05, y + 0.14, z + 0.44, P['app'])
    g.cyl(x, y - 0.14, z + 0.40, z + 0.50, 0.025, P['black'], seg=12, r1=0.02)
