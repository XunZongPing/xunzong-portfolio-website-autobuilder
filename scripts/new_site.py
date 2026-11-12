# -*- coding: utf-8 -*-
"""液态玻璃作品集 · 一键脚手架。

按一份 profile（或直接给一份 data.json）生成一个可用的新站点目录：

    <out>/
    ├── portfolio/
    │   ├── data.json                ← 唯一真源（后台读写它）
    │   ├── assets/{hero,cover,award,photo2,about,projects}/
    │   └── _bak/                    ← 后台自动备份
    ├── admin/{index.html,server.py,doc_import.py,start-admin.bat,start-admin.command}
    ├── build/gen_site.py            ← 站点生成器
    ├── build/site.css               ← 全站样式（生成器读它内联进 <style>）
    ├── build/palette.py             ← 主题配色（一个主色 → 整套色板，生成器与后台共用）
    └── _publish_tmp/                ← 发布副本（跑 sync_publish.py 产出）

用法：
    python new_site.py --out D:/sites/lisi --profile profile.json
    python new_site.py --out D:/sites/lisi --name 李四 --brand "四时记录" --brand-en "SISHI"
    python new_site.py --out D:/sites/lisi --data D:/somewhere/data.json   # 直接用整份数据
    python new_site.py --out D:/sites/lisi --force                          # 允许写进非空目录

profile 是**部分** data.json：写了的键覆盖骨架，没写的保留骨架默认值（深合并，数组整体替换）。
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
TEMPLATE = SKILL / 'assets' / 'template'
SKELETON = SKILL / 'assets' / 'data_skeleton.json'

ASSET_DIRS = ['hero', 'cover', 'award', 'photo2', 'about', 'projects']


def deep_merge(base, over):
    """深合并：dict 递归，其它（含数组）整体替换。"""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base.get(k), v) if k in base else v
        return out
    return over


def data_images(d):
    """从 data.json 里收集所有被引用的图片路径（相对 portfolio/）。"""
    out = []

    def add(u):
        if isinstance(u, str) and u and not u.startswith(('http://', 'https://', '//', 'data:')):
            out.append(u)

    for g in (d.get('work') or {}).get('groups') or []:
        for it in g.get('items') or []:
            add(it.get('img'))
            for s in it.get('subs') or []:
                add(s.get('img'))
    for g in (d.get('projects') or {}).get('groups') or []:
        for it in g.get('items') or []:
            for sh in it.get('shots') or []:
                if isinstance(sh, (list, tuple)) and sh:
                    add(sh[0])
    for v in (d.get('awards') or {}).values():
        for row in v or []:
            if isinstance(row, (list, tuple)) and len(row) > 2:
                add(row[2])
    # 论文：封面 + 内页（内页是 [路径, 说明] 二元组，路径留空＝待补）
    for it in (d.get('papers') or {}).get('items') or []:
        add(it.get('cover'))
        for row in it.get('pages') or []:
            if isinstance(row, (list, tuple)) and row:
                add(row[0])
    # 评论与随笔：只有缩略图
    for it in (d.get('opeds') or {}).get('items') or []:
        add(it.get('cover'))
    # 设计与物料：每组 [路径, 图注, 版式] + 每组末尾那张通栏大图
    for pj in (d.get('design') or {}).get('projects') or []:
        for g in pj.get('groups') or []:
            for row in g.get('items') or []:
                if isinstance(row, (list, tuple)) and row:
                    add(row[0])
            if isinstance(g.get('wide'), (list, tuple)) and g['wide']:
                add(g['wide'][0])
    out = [u for u in out if u]
    return sorted(set(out))


def placeholder(path, w, h, label, c1=(120, 160, 255), c2=(255, 168, 205)):
    """造一张渐变占位图，避免刚建站就到处裂图。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print('  ! 没装 Pillow，跳过占位图 %s' % path.name)
        return False
    im = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)],
               fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    d.text((16, h - 34), label, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, 'JPEG', quality=82)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='新站点根目录')
    ap.add_argument('--profile', help='profile.json（部分 data.json）')
    ap.add_argument('--data', help='直接给一份完整 data.json')
    ap.add_argument('--name', help='本人姓名 → hero.name / site.owner')
    ap.add_argument('--en', help='英文名 → hero.en')
    ap.add_argument('--brand', help='站名 / 首屏大标题 → site.brand')
    ap.add_argument('--brand-en', dest='brand_en', help='站名英文 → site.brand_en')
    ap.add_argument('--tagline', help='一句话介绍 → hero.tagline')
    ap.add_argument('--force', action='store_true', help='允许写进非空目录')
    ap.add_argument('--no-placeholder', action='store_true', help='不生成占位图')
    ap.add_argument('--no-favicon', action='store_true', help='不生成站点图标（稍后自己跑）')
    a = ap.parse_args()

    out = pathlib.Path(a.out).expanduser().resolve()
    if not TEMPLATE.is_dir():
        raise SystemExit('找不到模板目录：%s' % TEMPLATE)

    if out.exists() and any(out.iterdir()) and not a.force:
        raise SystemExit('%s 非空，加 --force 才继续（不会删已有文件，只补缺的）' % out)

    # ---------- 1. 目录 ----------
    for d in ['portfolio', 'portfolio/_bak', 'admin', 'build', '_publish_tmp']:
        (out / d).mkdir(parents=True, exist_ok=True)
    for d in ASSET_DIRS:
        (out / 'portfolio' / 'assets' / d).mkdir(parents=True, exist_ok=True)

    # ---------- 2. 模板 ----------
    # 这三个文件是一套：gen_site 读同目录的 site.css 内联样式、读 validate_data 做数据体检，
    # 少一个要么跑不了、要么退回「不做体检直接崩」。
    shutil.copy2(TEMPLATE / 'build' / 'gen_site.py', out / 'build' / 'gen_site.py')
    shutil.copy2(TEMPLATE / 'build' / 'site.css', out / 'build' / 'site.css')
    shutil.copy2(TEMPLATE / 'build' / 'validate_data.py', out / 'build' / 'validate_data.py')
    # 主题配色：生成器 import 它，后台的 /api/palette 也 import 它（两边共用同一套推导）。
    # 漏拷这一个文件，生成会直接 ImportError，所以它和上面三个是一套，不能单独省。
    shutil.copy2(TEMPLATE / 'build' / 'palette.py', out / 'build' / 'palette.py')
    shutil.copy2(TEMPLATE / 'admin' / 'server.py', out / 'admin' / 'server.py')
    # 论文内页导入模块：server.py 里是可选 import，缺了后台不崩、但那个功能会报「缺文件」
    shutil.copy2(TEMPLATE / 'admin' / 'doc_import.py', out / 'admin' / 'doc_import.py')
    shutil.copy2(TEMPLATE / 'admin' / 'index.html', out / 'admin' / 'index.html')
    bat = TEMPLATE / 'admin' / 'start-admin.bat'
    if bat.exists():
        shutil.copy2(bat, out / 'admin' / 'start-admin.bat')
    # macOS 双击启动（.command）。zip 分发会丢执行位，拷完补上；
    # 双击没反应时也能 `sh admin/start-admin.command` 直接跑（文件顶部有说明）。
    cmdf = TEMPLATE / 'admin' / 'start-admin.command'
    if cmdf.exists():
        shutil.copy2(cmdf, out / 'admin' / 'start-admin.command')
        try:
            os.chmod(out / 'admin' / 'start-admin.command', 0o755)
        except OSError:
            pass

    # ---------- 3. data.json ----------
    data = json.loads(SKELETON.read_text(encoding='utf-8'))
    if a.data:
        merged = json.loads(pathlib.Path(a.data).read_text(encoding='utf-8'))
        data = merged
    elif a.profile:
        prof = json.loads(pathlib.Path(a.profile).read_text(encoding='utf-8'))
        data = deep_merge(data, prof)

    site = data.setdefault('site', {})
    hero = data.setdefault('hero', {})
    if a.name:
        hero['name'] = a.name
        site.setdefault('owner', a.name)
    if a.en:
        hero['en'] = a.en
    if a.brand:
        site['brand'] = a.brand
    if a.brand_en:
        site['brand_en'] = a.brand_en
    if a.tagline:
        hero['tagline'] = a.tagline
    if not site.get('owner'):
        site['owner'] = hero.get('name') or ''

    (out / 'portfolio' / 'data.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    # ---------- 4. 占位图 ----------
    made = 0
    if not a.no_placeholder:
        P = out / 'portfolio' / 'assets'
        jobs = [
            (P / 'hero' / 'avatar.jpg', 480, 480, 'avatar'),
            (P / 'hero' / 'cover.jpg', 1920, 1080, 'cover'),
            (P / 'about' / 'portrait.jpg', 560, 700, 'portrait'),
        ]
        for p, w, h, lab in jobs:
            if not p.exists() and placeholder(p, w, h, lab):
                made += 1
        # data.json 里已经引用了的图：还没有就给张占位图，免得一建站就到处裂图
        for rel in data_images(data):
            p = out / 'portfolio' / rel
            if not p.exists() and pathlib.Path(rel).suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
                # 论文是 A4 竖版（3:4），按横版 16:9 造占位图会被封面框裁掉半页
                w, h = (1200, 1600) if rel.replace('\\', '/').startswith('assets/papers/') else (1280, 720)
                if placeholder(p, w, h, pathlib.Path(rel).stem):
                    made += 1
        # 摄影墙不存路径，只存「分类 key + 张数」，路径由生成器拼：
        # assets/photo2/<key>_<NN>.jpg（缩略图同名放 t/）。
        # 这里必须按同一规则造占位图，否则首次 build --check 会报整面墙都缺失。
        for c in (data.get('photo') or {}).get('cats') or []:
            try:
                key, cn, n = c[0], c[1], int(c[3] or 0)
            except (IndexError, TypeError, ValueError):
                continue
            for j in range(1, n + 1):
                p = P / 'photo2' / ('%s_%02d.jpg' % (key, j))
                if not p.exists() and placeholder(p, 1200, 800, '%s %02d' % (cn, j)):
                    made += 1
        # 缩略图目录（摄影墙用 t/，后台列表也用）
        for d in ASSET_DIRS:
            (P / d / 't').mkdir(parents=True, exist_ok=True)

    # ---------- 4.5 补齐缩略图 ----------
    # 生成器给摄影墙写的 <figure> 指向 assets/photo2/t/<名字>.jpg，
    # 而 /api/upload 只给「新传的图」生成缩略图 —— 占位图/批量导进来的图不会自己长出来。
    # 不补这一步，首次 build --check 会报几十个「缺失」，看着像建站失败。
    thumbs = (0, 0)
    if not a.no_placeholder:
        r = subprocess.run([sys.executable, str(out / 'admin' / 'server.py'), '--thumbs'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace',
                           env=dict(os.environ, SITE_BASE=str(out),
                                    PYTHONIOENCODING='utf-8', PYTHONUTF8='1'))
        if r.returncode == 0:
            try:
                thumbs = (int(r.stdout.split('新生成')[1].split('，')[0]),
                          int(r.stdout.split('跳过')[1].split()[0]))
            except Exception:
                thumbs = (-1, -1)
        else:
            print('  ! 缩略图补齐失败：%s' % (r.stdout or r.stderr or '').strip()[:200])

    # ---------- 5. 站点图标 ----------
    # 生成器只写 <link> 引用、不搬文件；不生成的话体检会报 3 个缺失。
    ico = 0
    if not a.no_favicon:
        try:
            r = subprocess.run([sys.executable, str(HERE / 'make_favicon.py'),
                                '--site', str(out)], capture_output=True)
            if r.returncode == 0:
                ico = 3
            else:
                print('  ! 图标生成失败（多半是还没有头像），稍后跑 scripts/make_favicon.py')
        except Exception as e:
            print('  ! 图标生成异常：%s' % e)

    print('站点已建好：%s' % out)
    print('  portfolio/data.json  ← 改内容改这里（或跑后台）')
    print('  build/gen_site.py    ← 生成网页（同目录 site.css 是样式）')
    print('  admin/server.py      ← 后台（双击 admin/start-admin.bat；macOS 用 start-admin.command）')
    if made:
        print('  占位图 %d 张（换成真图时保持同名直接覆盖）' % made)
    if thumbs[0] > 0:
        print('  缩略图 %d 张已生成（摄影墙和后台列表用小图，不拉原图）' % thumbs[0])
    if ico:
        print('  站点图标已生成（favicon.ico / favicon-32.png / apple-touch-icon.png）')
    print()
    print('下一步：')
    print('  python "%s" --site "%s" --check' % (HERE / 'build.py', out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
