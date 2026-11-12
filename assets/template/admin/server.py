# -*- coding: utf-8 -*-
"""作品集本地后台 —— 读写 portfolio/data.json，一键重新生成 portfolio/index.html

启动： python admin/server.py      （双击 admin/start-admin.bat；macOS 用 start-admin.command）
打开： http://127.0.0.1:8848/

站点根（BASE）解析顺序：环境变量 SITE_BASE → 本文件上两级目录（<BASE>/admin/server.py）。
端口：环境变量 SITE_PORT，缺省 8848。

接口：
  GET  /                  后台界面
  GET  /api/data          读 data.json
  POST /api/save          存 data.json（自动备份到 portfolio/_bak）
  POST /api/upload        上传图片 {dir:'cover'|'award'|'photo2'|'hero'|'about'|'projects'|'logo',
                                    name, b64, overwrite} → {path, thumb}
  POST /api/build         重跑 build/gen_site.py → {ok, out, ms, size, refs, at, label,
                                    first, site, launchers, opened}
                          第一次生成（产物还没有过）会顺手打开网页、在站点根放两个双击启动文件
  POST /api/thumbs        给存量图片补缩略图 → {ok, made, skipped}
  POST /api/favicon       由头像重做整套收藏夹图标 → {ok, out}
  POST /api/delimg        删掉 portfolio 下的某个文件 {path}
  GET  /api/export        导出产物直传浏览器 ?fmt=html|zip（附件，前端不再需要找路径）
  GET  /api/health        轻量探活（起后台的脚本轮询用，别用 /api/ping —— 那个要跑 env_check）
  GET  /api/palettes      主题配色预设清单 + 默认色
  GET  /api/palette       由主色算整套色板 ?accent=%23e0651c（后台实时预览用）
  GET  /pf/<rel>          portfolio 目录静态文件（后台缩略图 + 预览站点）
"""
import json, pathlib, sys, base64, subprocess, datetime, shutil, os, threading, io
import re, zipfile, mimetypes, tempfile, webbrowser
from urllib.parse import unquote, quote, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE = pathlib.Path(
    os.environ.get('SITE_BASE')
    or pathlib.Path(__file__).resolve().parents[1]
)
PF = BASE / 'portfolio'
DATA = PF / 'data.json'
BAK = PF / '_bak'
ADMIN = BASE / 'admin'
GEN = BASE / 'build' / 'gen_site.py'
LOG = ADMIN / 'build.log'
PORT = int(os.environ.get('SITE_PORT') or 8848)

BUILD_LOCK = threading.Lock()          # 连点两次生成会同时写 index.html，必须串行

# 论文内页导入（PDF / Word → 图）。独立成一个模块，缺了不影响其它功能：
# 老站点升级时可能只拷了 server.py 没拷它，那时接口明确报「缺文件」而不是让整个后台崩。
sys.path.insert(0, str(ADMIN))
try:
    import doc_import
except ImportError:
    doc_import = None

# 主题配色：预设与「主色 → 整套色板」的推导都在 build/palette.py，
# 生成器和后台共用同一份，后台预览才不会和网上的实际效果差一档。
# 同样按可选导入处理：老站点只拷了 server.py 时，配色接口报缺文件，别的功能照常用。
sys.path.insert(0, str(BASE / 'build'))
try:
    import palette as PALETTE
except ImportError:
    PALETTE = None

# 生成网页用的解释器：优先带 Pillow 的 venv，退回当前解释器
# 生成网页用的解释器：优先环境变量 SITE_PY，否则用当前解释器。
# 注意当前解释器需要 Pillow（缩略图 / 图片压缩 / 摄影墙宽高比计算要用）。
PY = os.environ.get('SITE_PY') or sys.executable

# ⚠️ 子进程 stdout 走管道时，Python 用 locale.getpreferredencoding() 决定编码。
# 本机 ANSI 代码页是 936（GBK），生成器又没有自己 reconfigure，
# 于是它吐出来的是 GBK 字节，父进程按 utf-8 解码 → 每个中文字都变成 U+FFFD（乱码）。
# 这里把子进程的 IO 编码强制钉成 UTF-8，两端才对齐。
# 顺带把 stdout/stderr 都设成 UTF-8（PYTHONUTF8 影响文件 IO，PYTHONIOENCODING 影响管道）。
def _child_env():
    e = dict(os.environ)
    e['PYTHONIOENCODING'] = 'utf-8'
    e['PYTHONUTF8'] = '1'
    return e

MIME = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.webp': 'image/webp', '.svg': 'image/svg+xml', '.ico': 'image/x-icon'}


def backup():
    if not DATA.exists():
        return
    BAK.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dst = BAK / ('data-%s.json' % stamp)
    # 时间戳只到秒：同一秒里连保存两次，后一次会把前一次的备份盖掉，中间那版就永远没了。
    # 撞名就补序号（和图片备份同一套处理）。
    k = 1
    while dst.exists():
        k += 1
        dst = BAK / ('data-%s-%d.json' % (stamp, k))
    shutil.copy2(DATA, dst)
    olds = sorted(BAK.glob('data-*.json'), key=lambda f: f.stat().st_mtime)[:-30]
    for f in olds:
        f.unlink()


def _bak_key(p):
    """排序键 = (日期, 时刻, 序号)。同一秒里连保存三次会是 …-224853.json / -2 / -3。

    ⚠️ 不能按 mtime 排：backup() 用的是 copy2，会把**源文件**的 mtime 带过来，
    连点几次时几份备份的 mtime 是同一个值，顺序会乱。
    ⚠️ 也不能直接按文件名字符串排：'.' 的码位比 '-' 大，
    `data-…-224853.json` 会排到 `data-…-224853-3.json` 后面（新旧正好颠倒）。
    """
    m = re.match(r'data-(\d{8})-(\d{6})(?:-(\d+))?\.json$', p.name)
    return (m.group(1), m.group(2), int(m.group(3) or 1)) if m else ('', '', 0)


def _bak_files():
    """历史版本清单：新的在前。最多 30 份（backup() 里裁过）。"""
    if not BAK.exists():
        return []
    return sorted(BAK.glob('data-*.json'), key=_bak_key, reverse=True)


def _bak_time(p):
    """data-20261029-223612.json → 2026-10-29 22:36:12；名字不合规就退回文件时间。"""
    m = re.match(r'data-(\d{8})-(\d{6})(?:-(\d+))?\.json$', p.name)
    if m:
        d, t, n = m.groups()
        return '%s-%s-%s %s:%s:%s%s' % (d[:4], d[4:6], d[6:], t[:2], t[2:4], t[4:],
                                        (' #' + n) if n else '')
    return datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')


# 上传后统一压一遍，不然大图（手机原图 / 航拍直出）塞进网页会拖垮加载甚至打不开
# maxside=最长边上限 ｜ target=目标体积（字节）｜ q0=起始 JPEG 质量，不够小就逐级降
KIND_CFG = {
    'cover':  dict(maxside=1600, target=420 * 1024, q0=84),
    'award':  dict(maxside=1600, target=420 * 1024, q0=84),
    'hero':   dict(maxside=2000, target=600 * 1024, q0=85),
    'about':  dict(maxside=2000, target=600 * 1024, q0=85),
    'photo2': dict(maxside=2400, target=900 * 1024, q0=86),   # 摄影要留画质，放宽
    'projects': dict(maxside=1600, target=420 * 1024, q0=84),  # 技术内容的项目截图
    'design': dict(maxside=1600, target=420 * 1024, q0=84),    # 设计物料：海报/门票，尺寸要留
}


def compress(src: pathlib.Path, kind='cover', force_jpeg=False):
    """把 src 压到目标体积内，原地覆盖。返回 (新体积, 尺寸, 是否被压缩)"""
    cfg = KIND_CFG.get(kind, KIND_CFG['cover'])
    from PIL import Image, ImageOps
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)                  # 手机竖拍的方向信息，不然会躺倒
    orig_size = src.stat().st_size
    ow, oh = im.size
    if not force_jpeg and orig_size <= cfg['target'] and max(ow, oh) <= cfg['maxside']:
        im.close()
        return orig_size, (ow, oh), False             # 本来就够小够清晰，不动它

    # 透明通道：白底合成，避免转 JPEG 后发黑
    if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert('RGB')
    # 限最长边
    if max(im.size) > cfg['maxside']:
        r = cfg['maxside'] / max(im.size)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    # 体积不达标就降质量，最低 55 收手（再低就是糊的）
    q = cfg['q0']
    while True:
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
        if buf.tell() <= cfg['target'] or q <= 55:
            break
        q -= 5
    src.write_bytes(buf.getvalue())
    im.close()
    return src.stat().st_size, Image.open(src).size, True


def thumb(src, dst, w=520):
    """生成后台列表用的小图。

    输出格式跟目标文件名走：.png 存 PNG 并保留透明通道（logo 要用），
    其余一律存 JPEG。以前不管扩展名一律写 JPEG，logo.png 里装 JPEG 字节，
    服务端按扩展名发的还是 image/png —— 能显示，但透明底一定丢。
    """
    try:
        from PIL import Image
    except Exception:
        return False
    im = Image.open(src)
    png = dst.suffix.lower() == '.png'
    im = im.convert('RGBA' if png else 'RGB')
    if im.width > w:
        im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if png:
        im.save(dst, 'PNG', optimize=True)
    else:
        im.save(dst, 'JPEG', quality=86)
    return True


# 后台列表用小缩略图的宽度（按用途分）；跟 /api/upload 里保持一致
TH_W = {'photo2': 520, 'award': 240, 'projects': 300}


def backfill_thumbs(only=None, verbose=False):
    """给存量图片补缩略图。

    /api/upload 只对「新传的图」生成缩略图，老图不会自己长出来。
    跑一次这个就能把 assets/<kind>/ 下的存量图全部补齐，
    之后后台列表不再拉原图（33M → 几百 KB）。
    返回 (生成数, 跳过数)。
    """
    made = skipped = 0
    for kind in ('cover', 'award', 'photo2', 'hero', 'about', 'projects', 'design'):
        if only and kind not in only:
            continue
        src_dir = PF / 'assets' / kind
        if not src_dir.is_dir():
            continue
        w = TH_W.get(kind, 260)
        th_dir = src_dir / 't'
        for f in sorted(src_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
                continue
            dst = th_dir / (f.stem + '.jpg')      # 统一 jpg，与前端拼的路径一致
            if dst.exists() and dst.stat().st_mtime >= f.stat().st_mtime:
                skipped += 1
                continue
            try:
                thumb(f, dst, w=w)
                made += 1
                if verbose:
                    print('  +', dst.relative_to(PF))
            except Exception as e:
                print('  ! 缩略图失败 %s：%s' % (f.name, e))
    return made, skipped


# 上传的「目录短名」→ portfolio 下的实际目录。
# logo 和 hero 落在同一个目录（都在 assets/hero），但短名必须分开：
# 前端靠短名决定压缩策略（logo 不转 JPEG）和缩略图宽度。
def auto_name(outdir, sub, ext):
    """导入照片的统一命名：`<目录短名>-<日期>-<序号><扩展名>`，例 `cover-20261104-01.jpg`。

    **不用原文件名**。手机 / 微信导出来的名字是「图片(30).jpg」
    「微信图片_20260421120512_3653_331.jpg」这种：看不出是什么内容，括号在 URL 里要转义
    （1.21.1 的单文件裂图就是括号引起的），中文名经 zip 分发还容易乱码（pitfalls 71）。
    统一规则：全 ASCII、按天分组、序号递增、永不覆盖 —— 同一张图传两次得到两个文件，
    旧图仍然有效（网页上不会突然裂）。
    """
    day = datetime.datetime.now().strftime('%Y%m%d')
    pre = '%s-%s-' % (sub, day)
    n = 1
    for p in outdir.glob(pre + '*'):
        m = re.match(r'^%s(\d+)$' % re.escape(pre), p.stem)
        if m:
            n = max(n, int(m.group(1)) + 1)
    while True:
        cand = outdir / ('%s%02d%s' % (pre, n, ext))
        if not cand.exists():
            return cand
        n += 1


UPLOAD_DIRS = {
    'cover':    'assets/cover',
    'award':    'assets/award',
    'photo2':   'assets/photo2',
    'hero':     'assets/hero',
    'about':    'assets/about',
    'projects': 'assets/projects',
    'design':   'assets/design',
    'digital':  'assets/digital',
    'logo':     'assets/hero',
}


def fit_logo(src, maxside=512):
    """logo 专用：只缩最长边，不换格式。

    为什么不能走 compress()：那里面一律存 JPEG，透明的 PNG 会变成白底方块，
    深色顶栏上就是一块白斑。svg 更是连 Image.open 都过不去，原样留着。
    """
    from PIL import Image, ImageOps
    orig = src.stat().st_size
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    ow, oh = im.size
    if max(ow, oh) > maxside:
        r = maxside / max(ow, oh)
        im = im.resize((round(ow * r), round(oh * r)), Image.LANCZOS)
    sfx = src.suffix.lower()
    if sfx == '.png':
        im.convert('RGBA').save(src, 'PNG', optimize=True)
    elif sfx in ('.jpg', '.jpeg'):
        im.convert('RGB').save(src, 'JPEG', quality=88, optimize=True, progressive=True)
    elif sfx == '.webp':
        im.save(src, 'WEBP', quality=90)
    else:
        im.close()
        return orig, (ow, oh), False
    im.close()
    return src.stat().st_size, Image.open(src).size, True


def make_icons(src):
    """由一张头像生成整套收藏夹图标，落到 portfolio/ 根下。

    与 scripts/make_favicon.py 同一套参数（满幅 + 圆角 22% / 18% + 白底），
    区别是这里先居中裁成正方形 —— 直接 resize 成正方形会把竖构图的人脸压扁。
    后台的「重新生成图标」按钮走这里，站点目录因此不需要额外带脚本。
    """
    from PIL import Image, ImageDraw, ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGBA')
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))

    def rounded(size, ratio):
        canvas = Image.new('RGBA', (size, size), (255, 255, 255, 255))
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, size - 1, size - 1), radius=max(1, int(size * ratio)), fill=255)
        canvas.paste(im.resize((size, size), Image.LANCZOS), (0, 0), mask)
        return canvas

    made = []
    for size, name in ((32, 'favicon-32.png'), (180, 'apple-touch-icon.png'),
                       (192, 'icon-192.png'), (512, 'icon-512.png')):
        img = rounded(size, 0.18 if size <= 32 else 0.22)
        img.save(PF / name, 'PNG', optimize=True)
        made.append('%s (%dx%d)' % (name, size, size))
        if size == 32:
            ico = [rounded(n, 0.18) for n in (16, 32, 48)]
            ico[0].save(PF / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)],
                        append_images=ico[1:])
            made.append('favicon.ico (16/32/48)')
    return made


# ---------- 导出：单文件 HTML / 整站压缩包 ----------
# 设计原则：后台点「生成网页」之后，用户不该再去文件夹里翻产物。
# 所以这里把打包逻辑放进服务端，前端拿到的是**可下载的字节流**，
# 配合浏览器的「另存为」直接落到用户手上。

# 只认「看起来就是本地媒体文件」的值：有序扩展名、无协议头、无 %xx、无 #
# 只认「看起来就是本地媒体文件」的值：有序扩展名、无协议头、无锚点。
# ⚠️ 以前写成严格白名单（只允许字母数字 . / - 和汉字），`图片(30).jpg`、
# `8月4日(1)(3)-封面.jpg` 这类带括号的名字会被静默跳过 —— 单 HTML 裂图，
# 而「找不到」列表里也不出现，最难查。现在只挡协议 / 锚点 / 空值。
_MEDIA_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.ico', '.avif',
              '.mp4', '.webm')
_SCHEME = re.compile(r'^[a-z][a-z0-9+.\-]*:', re.I)


def _is_media(u):
    u = (u or '').strip()
    if not u or len(u) > 400:
        return False
    if u.startswith(('#', '//', 'data:')):
        return False
    if _SCHEME.match(u):                # http: https: mailto: javascript: file: blob:
        return False
    if any(c in u for c in '<>"\''):
        return False
    return re.split(r'[?#]', u, 1)[0].lower().endswith(_MEDIA_EXT)
# 不枚举属性名，凡是「值看起来就是本地媒体路径」的都内联。
# 踩过：只写 src/poster/href 时，摄影墙的 data-full（点开看原图）和
# 奖项徽标的 data-img 被漏掉，单文件里灯箱一片裂图。
_ATTR = re.compile(r'(\b[\w-]+\s*=\s*["\'])([^"\']+)(["\'])')
_CSSURL = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', re.I)
_ICONLINK = re.compile(r'<link[^>]+rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*>\s*', re.I)


def site_label():
    """产物文件名用的站点名：site.brand → site.owner → 目录名"""
    try:
        d = json.loads(DATA.read_text(encoding='utf-8'))
    except Exception:
        return BASE.name or 'portfolio'
    s = d.get('site') or {}
    for k in ('brand', 'owner'):
        v = (s.get(k) or '').strip()
        if v:
            return re.sub(r'[\\/:*?"<>|\s]+', '', v)[:40] or BASE.name
    return BASE.name or 'portfolio'


def make_launchers():
    """在站点根目录放两个双击就能用的启动文件，返回文件名列表。

    **文件名用中文（给人找的），内容纯 ASCII（给 cmd 的）。**
    cmd 按 OEM 代码页解析 .bat，文件里只要出现 UTF-8 中文，解析器的文件偏移就会错位，
    后面的行从句子中间开始执行（详见 admin/start-admin.bat 顶部注释）。这两个文件只做
    一句最简单的事，不需要任何提示文字，所以干脆一行中文都不写。
    macOS 对应物是 .command（双击开终端跑），内容同样纯 ASCII，写完补执行位；
    没执行位时双击没反应，`sh 文件名` 照样能跑（start-admin.command 顶部有说明）。
    """
    made = []

    if os.name == 'nt':
        site_bat = BASE / '打开网站.bat'
        site_bat.write_text('@echo off\r\nstart "" "%~dp0portfolio\\index.html"\r\n',
                            encoding='ascii', newline='')
        made.append(site_bat.name)

        admin_bat = BASE / '打开后台.bat'
        admin_bat.write_text('@echo off\r\ncall "%~dp0admin\\start-admin.bat"\r\n',
                             encoding='ascii', newline='')
        made.append(admin_bat.name)
        return made

    if sys.platform == 'darwin':
        site_sh = BASE / '打开网站.command'
        site_sh.write_text(
            '#!/bin/sh\n'
            'DIR=$(cd "$(dirname "$0")" && pwd) || exit 1\n'
            'open "$DIR/portfolio/index.html"\n',
            encoding='ascii', newline='')
        made.append(site_sh.name)

        admin_sh = BASE / '打开后台.command'
        admin_sh.write_text(
            '#!/bin/sh\n'
            'DIR=$(cd "$(dirname "$0")" && pwd) || exit 1\n'
            'exec sh "$DIR/admin/start-admin.command"\n',
            encoding='ascii', newline='')
        made.append(admin_sh.name)
        for f in (site_sh, admin_sh):
            try:
                os.chmod(f, 0o755)
            except OSError:
                pass
        return made

    return []            # 其它平台不放双击启动文件（入口走 open_admin.py）


def open_site(idx):
    """第一次生成完，用默认浏览器直接把网页打开。

    走 file:// 而不是 http://127.0.0.1 —— 站点是纯静态的，后台关掉照样能看。
    打不开只记日志：这是锦上添花，不该让「生成成功」变成失败。
    """
    try:
        return bool(webbrowser.open(idx.resolve().as_uri()))
    except Exception as e:
        log('打开浏览器失败：%s' % e)
        return False


def bundle_single(dest):
    """把 portfolio/index.html 的全部本地资源内联，写到 dest。返回统计。"""
    src = PF / 'index.html'
    if not src.exists():
        raise RuntimeError('还没有 index.html，先点「生成网页」')
    root = PF.resolve()
    html = src.read_text(encoding='utf-8')
    cache, missing, inlined = {}, [], []

    def resolve(u):
        u = (u or '').strip()
        if not _is_media(u):
            return None
        rel = unquote(re.split(r'[?#]', u, 1)[0])
        p = (root / rel).resolve()
        if root not in p.parents or not p.is_file():
            if u not in missing:
                missing.append(u)
            return None
        return p

    def uri_of(u):
        if u in cache:
            return cache[u]
        p = resolve(u)
        if p is None:
            return None
        m, _ = mimetypes.guess_type(p.name)
        cache[u] = 'data:%s;base64,%s' % (m or 'application/octet-stream',
                                          base64.b64encode(p.read_bytes()).decode())
        inlined.append((u, p.stat().st_size))
        return cache[u]

    html = _ICONLINK.sub('', html)                    # 单文件里图标没意义，还要多背 5 份 base64

    def inline_attr(m):
        head, val, tail = m.group(1), m.group(2), m.group(3)
        uri = uri_of(val)
        return m.group(0) if uri is None else head + uri + tail

    html = _ATTR.sub(inline_attr, html)

    def inline_css(m):
        uri = uri_of(m.group(1))
        return m.group(0) if uri is None else 'url("%s")' % uri

    html = _CSSURL.sub(inline_css, html)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding='utf-8')
    return {'n': len(inlined), 'missing': missing, 'size': dest.stat().st_size}


# 打包只发这三样：网站本体、后台、生成器 —— 跟下面 README_TXT 写的结构一致。
# 以前是 os.walk(BASE) 走整个工程根目录、再靠几个目录名排除：用户工作目录里只要
# 多出 _portfolio_build / _github_upload / _upgrade_xxx / .workbuddy 这类目录，
# 就一起进包（实测 2 万个文件，真正的网站只有 6 千多个）。白名单不会随目录增多失效。
ZIP_TOPS = ('portfolio', 'admin', 'build')
ZIP_TOP_FILES = ('.nojekyll', '打开网站.bat', '打开后台.bat',
                 '打开网站.command', '打开后台.command')
ZIP_SKIP_DIR = {'__pycache__', '_bak', '_deploy', '_publish_tmp', '.git',
                'node_modules', '.workbuddy', '.pytest_cache', '__MACOSX'}
ZIP_SKIP_FILE = {'.DS_Store', 'Thumbs.db', 'desktop.ini', 'build.log', '.admin.json'}
ZIP_SKIP_EXT = {'.pyc', '.pyo', '.log', '.tmp', '.bak', '.swp', '.orig', '.zip'}

README_TXT = """这个文件夹就是你的作品集网站

  portfolio/          网站本体（index.html + 图片）
  admin/              本地后台（Windows 双击 start-admin.bat，macOS 双击 start-admin.command）
  build/              生成器（改完数据重跑它）
  .nojekyll           给 GitHub Pages 用的，别删

怎么改内容
  双击 admin/start-admin.bat（macOS：admin/start-admin.command）
  → 浏览器打开 http://127.0.0.1:8848/ → 改完点「生成网页」

怎么发布
  · 最简单：在 WorkBuddy 里说「发布上线」，平台托管、给在线链接
  · GitHub 网页版（全程浏览器）：github.com/new 建空仓库 → 上传 gh-pages 目录
    → Settings → Pages → Source 选 Deploy from a branch → main / (root) → 等 1 分钟
  · Netlify Drop：把 portfolio/ 整个目录拖到 https://app.netlify.com/drop
  · 自己有服务器：portfolio/ 的文件全量覆盖上去，纯静态

想用自己的域名（www.你自己的名字.com）：告诉我，有一步一步的图文指引带着弄。

注意：.nojekyll 不能删。GitHub Pages 默认跑 Jekyll，会把下划线开头的目录吞掉。
"""


def bundle_zip(dest):
    """整站打包：portfolio + admin + build + 双击入口 + .nojekyll，解压即可部署或继续用后台改。

    只走 ZIP_TOPS 白名单，不再遍历工程根目录 —— 工作目录里的临时/备份目录
    （_portfolio_build、_upgrade_xxx、_github_upload、.workbuddy…）一律不进包。
    """
    if not (PF / 'index.html').exists():
        raise RuntimeError('还没有 index.html，先点「生成网页」')
    n = 0
    top = site_label()
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for sub in ZIP_TOPS:
            base = BASE / sub
            if not base.is_dir():
                continue
            for root, dirs, names in os.walk(base):
                dirs[:] = sorted(d for d in dirs
                                 if d not in ZIP_SKIP_DIR and not d.startswith('_bak'))
                for fn in sorted(names):
                    p = pathlib.Path(root) / fn
                    if fn in ZIP_SKIP_FILE or p.suffix.lower() in ZIP_SKIP_EXT:
                        continue
                    if fn.startswith('_'):      # _preview_sizes.png 这类运行期调试产物
                        continue
                    z.write(p, '%s/%s' % (top, p.relative_to(BASE).as_posix()))
                    n += 1
        for fn in ZIP_TOP_FILES:            # 站点根的双击入口（打开网站 / 打开后台）
            p = BASE / fn
            if p.is_file():
                z.write(p, '%s/%s' % (top, fn))
                n += 1
        # 没有就补一个空 .nojekyll（GitHub Pages 的坑）
        if not (BASE / '.nojekyll').exists():
            z.writestr('%s/.nojekyll' % top, '')
            n += 1
        z.writestr('%s/先读我.txt' % top, README_TXT)
        n += 1
    return {'n': n, 'size': dest.stat().st_size}


def decode_out(b):
    """子进程输出解码：优先 UTF-8，失败再退 GBK。

    正常路径下 _child_env() 已经把子进程钉成 UTF-8，这里一次就成。
    留 GBK 兜底是为了老解释器 / 外部直接调用等没吃到环境变量的场合，
    不至于又把中文糊成一片 U+FFFD。
    """
    if not b:
        return ''
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return b.decode('gbk')
        except Exception:
            return b.decode('utf-8', 'replace')


def env_check():
    """环境自检：生成失败时第一眼看这个"""
    info = {'py': PY, 'py_ok': os.path.exists(PY), 'gen': str(GEN), 'gen_ok': GEN.exists(),
            'data': str(DATA), 'data_ok': DATA.exists()}
    try:
        r = subprocess.run([PY, '-c', 'import sys,PIL;print(sys.version.split()[0], PIL.__version__)'],
                           capture_output=True, timeout=30, env=_child_env())
        info['pillow'] = decode_out(r.stdout).strip() or decode_out(r.stderr).strip()[:120]
    except Exception as e:
        info['pillow'] = '检查失败：%s' % e
    return info


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('[%s] %s\n' % (datetime.datetime.now().strftime('%m-%d %H:%M:%S'), msg))
    except Exception:
        pass


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                   # 关掉刷屏的访问日志

    # ---------- 通用 ----------
    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False), code)

    def _file(self, p: pathlib.Path):
        if not p.exists() or p.is_dir():
            return self._send('404', 404, 'text/plain; charset=utf-8')
        body = p.read_bytes()
        ctype = MIME.get(p.suffix.lower(), 'application/octet-stream')
        # 预览页必须每次拿最新的：光 no-store 不够，浏览器还可能把它塞进 bfcache。
        # 对 html 再补 Pragma/Expires，并显式声明 no-cache 走协商。
        extra = None
        if p.suffix.lower() in ('.html', '.htm'):
            extra = [('Pragma', 'no-cache'), ('Expires', '0')]
        self._send(body, 200, ctype, extra=extra)

    def _send(self, body, code=200, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    # ---------- GET ----------
    def _safe(self, root: pathlib.Path, rel: str):
        """把 URL 里的相对路径解析成 root 下的真实文件，越界一律不给。

        两件事必须做：
        1. **unquote** —— 浏览器发的路径是 percent-encoded。
           中文名的图（如 图片(30).jpg）在 self.path 里是 %E5%9B%BE%E7%89%87(30).jpg，
           不解码就拿去拼路径 → 找不到文件 → 后台缩略图和预览里的中文图全 404。
           （ASCII 名的图不受影响，所以这个 bug 藏了很久：photo2 全是 aerial_02 这种名。）
        2. 越界检查 —— 解码后可能出现 ../ ，必须挡住。
        """
        rel = unquote(rel)
        p = (root / rel).resolve()
        root = root.resolve()
        if not (p == root or root in p.parents):
            return None
        return p

    def do_GET(self):
        raw = self.path.split('?')[0]
        path = unquote(raw)
        if path in ('/', '/index.html'):
            return self._file(ADMIN / 'index.html')
        if path == '/api/data':
            return self._json(json.loads(DATA.read_text(encoding='utf-8')))
        # 历史版本：每次保存都会留一份，这里把清单给后台的「历史版本」卡片。
        # 只回文件名/时间/大小，不回正文 —— 30 份 data.json 一起塞进响应没必要。
        if path == '/api/backups':
            return self._json({'ok': True, 'items': [
                {'name': b.name, 'at': _bak_time(b), 'size': b.stat().st_size}
                for b in _bak_files()]})
        # 轻量探活：给「起后台的脚本」轮询用。
        # 别拿 /api/ping 来轮询 —— 它要跑 env_check（起子进程验 Pillow / 生成器），
        # 冷启动时可能要一两秒，轮询方设 0.4s 超时就会误判「没起来」。
        if path == '/api/health':
            return self._json({'ok': True, 'app': 'portfolio-admin',
                               'label': site_label(), 'pid': os.getpid(),
                               'base': str(BASE)})
        # 主题配色：预设清单 + 由主色推导出的整套色板。
        # 推导只写在 build/palette.py 一处，后台只负责「拿过来显示」——
        # 如果两边各算一套，后台预览的橙和网页上的橙迟早会对不上。
        if path == '/api/palettes':
            return self._json({
                'ok': True,
                'default': PALETTE.DEFAULT if PALETTE else '#2f6bff',
                'presets': PALETTE.PRESETS if PALETTE else [],
            })
        if path == '/api/palette':
            if PALETTE is None:
                return self._json({'ok': False, 'err': '缺 build/palette.py，没法算派生色'}, 500)
            q = parse_qs(urlparse(self.path).query)
            want = (q.get('accent') or [''])[0]
            accent = PALETTE.normalize(want)
            if want and not PALETTE.is_hex(want):
                return self._json({'ok': False, 'accent': accent,
                                   'err': '「%s」不是合法色值，已按默认色显示' % want[:24]}, 400)
            r = PALETTE.resolve(accent)
            return self._json({'ok': True, 'accent': accent,
                               'light': r['light'], 'dark': r['dark'],
                               # 现成的柔光背景串：后台预览直接用，免得前端再抄一遍
                               # 那四团渐变的几何和透明度（抄了就会和 site.css 漂）。
                               'washLight': PALETTE.wash_css(r['light']),
                               'washDark': PALETTE.wash_css(r['dark'], night=True)})
        if path == '/api/ping':
            e = env_check()
            e['ok'] = True
            e['label'] = site_label()
            e['has_html'] = (PF / 'index.html').exists()
            return self._json(e)
        # 导出：现场打包，直接以附件下发。（GET 而不是 POST，浏览器原生下载才能触发）
        if path == '/api/export':
            fmt = (parse_qs(urlparse(self.path).query).get('fmt') or ['html'])[0].lower()
            if fmt not in ('html', 'zip'):
                return self._json({'ok': False, 'err': 'fmt 只能是 html 或 zip'}, 400)
            label = site_label()
            day = datetime.datetime.now().strftime('%Y%m%d')
            name = '%s-%s.%s' % (label, day, 'html' if fmt == 'html' else 'zip')
            tmp = pathlib.Path(tempfile.mkdtemp(prefix='pfexport-'))
            try:
                dst = tmp / name
                t0 = datetime.datetime.now()
                if fmt == 'html':
                    st = bundle_single(dst)
                    if st['missing']:
                        log('导出 HTML：%d 个引用找不到（%s）' % (len(st['missing']), st['missing'][:3]))
                else:
                    st = bundle_zip(dst)
                body = dst.read_bytes()
                ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
                log('导出 %s：%s ｜ %d 文件 ｜ %.1f KB ｜ %dms'
                    % (fmt, name, st['n'] if 'n' in st else 1, len(body) / 1024.0, ms))
                ctype = 'text/html; charset=utf-8' if fmt == 'html' else 'application/zip'
                # filename 给不认 RFC 5987 的老浏览器兜底（中文会被替成 ?，所以换成中性名）；
                # filename* 才是正路，中文名不乱码。
                plain = name if name.isascii() else 'portfolio-%s.%s' % (day, 'html' if fmt == 'html' else 'zip')
                cd = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (plain, quote(name))
                self._send(body, 200, ctype, extra=[('Content-Disposition', cd)])
                return None
            except Exception as e:
                log('导出失败：%s' % e)
                return self._json({'ok': False, 'err': '%s: %s' % (type(e).__name__, e)}, 500)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        if path.startswith('/pf/'):
            rel = path[4:] or 'index.html'
            p = self._safe(PF, rel)
            return self._send('404', 404, 'text/plain; charset=utf-8') if p is None else self._file(p)
        if path.startswith('/admin/'):
            p = self._safe(ADMIN, path[7:])
            return self._send('404', 404, 'text/plain; charset=utf-8') if p is None else self._file(p)
        if path.startswith('/api/'):
            return self._json({'ok': False,
                               'err': '%s 要用 POST 请求（前端调用方式不对，刷新页面拿最新后台）' % path}, 405)
        return self._send('404', 404, 'text/plain; charset=utf-8')

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split('?')[0]
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b'{}'
        try:
            body = json.loads(raw.decode('utf-8'))
        except Exception as e:
            return self._json({'ok': False, 'err': 'JSON 解析失败：%s' % e}, 400)

        if path == '/api/save':
            # 主题色是唯一一个「写坏了整站配色就崩」的字段：它会被拼进 CSS 变量，
            # 一个非法值能让整段样式失效（不是变丑，是按钮/阴影全部掉回浏览器默认）。
            # 所以在落盘前拦一道，指名道姓告诉用户是哪一项。
            if PALETTE is not None and isinstance(body, dict):
                th = ((body.get('site') or {}).get('theme') or {})
                if 'accent' in th:
                    if not PALETTE.is_hex(th.get('accent')):
                        return self._json({'ok': False, 'err': (
                            '主题色不是合法色值（site.theme.accent 需要 #rrggbb，'
                            '现在写的是 %r），这一版没有保存' % (th.get('accent'),))}, 400)
                    th['accent'] = PALETTE.normalize(th['accent'])
            try:
                backup()
                DATA.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding='utf-8')
                return self._json({'ok': True, 'size': DATA.stat().st_size})
            except Exception as e:
                return self._json({'ok': False, 'err': str(e)}, 500)

        # 回到某个历史版本。回滚本身也要先备份 —— 否则「想撤销这次回滚」就没退路了。
        if path == '/api/restore':
            name = str(body.get('name') or '')
            src = BAK / name
            # 只认 _bak 里的纯文件名：挡掉 ../ 和子目录
            if not name or pathlib.Path(name).name != name or src.suffix != '.json' or not src.exists():
                return self._json({'ok': False, 'err': '这个历史版本不在了（可能在 _bak 里被 30 份上限裁掉）'}, 400)
            try:
                try:
                    json.loads(src.read_text(encoding='utf-8'))
                except Exception:
                    return self._json({'ok': False, 'err': '这份备份本身不是合法 JSON，没敢用'}, 400)
                backup()
                shutil.copy2(src, DATA)
                log('restore %s' % name)
                return self._json({'ok': True, 'size': DATA.stat().st_size, 'name': name})
            except Exception as e:
                return self._json({'ok': False, 'err': str(e)}, 500)

        # 论文内页：上传 PDF / Word，抽出前几页转成图，直接能写进 data.json 的 pages。
        # 用 JSON + base64 而不是 multipart —— 解析 multipart 要自己写边界切分和容错，
        # base64 让传输体积多 33%，换后端零解析依赖，值。文件本身也就几 MB。
        if path == '/api/import_doc':
            if doc_import is None:
                return self._json({'ok': False,
                    'err': '缺 admin/doc_import.py —— 它要和 server.py 同目录（升级站点时被漏拷了）'}, 500)
            name = str(body.get('name') or '')
            b64 = str(body.get('b64') or '')
            if not b64:
                return self._json({'ok': False, 'err': '没收到文件内容'}, 400)
            try:
                data = base64.b64decode(b64.split(',', 1)[-1])
            except Exception as e:
                return self._json({'ok': False, 'err': '文件解码失败：%s' % e}, 400)
            if len(data) > 48 * 1024 * 1024:
                return self._json({'ok': False,
                    'err': '文件 %d MB，太大了。内页只取前几页，压一下或者先删掉附录再传'
                           % (len(data) // 1024 // 1024)}, 400)
            try:
                r = doc_import.convert(data, name, PF / 'assets' / 'papers',
                                       int(body.get('pages') or doc_import.MAX_PAGES))
            except Exception as e:
                log('import_doc 失败 %s: %s' % (name, e))
                return self._json({'ok': False, 'err': str(e)}, 400)
            log('import_doc %s → %d 页 (%s)' % (name, r['total'], r['kind']))
            return self._json(dict(ok=True, **r))

        if path == '/api/build':
            if not BUILD_LOCK.acquire(timeout=180):
                return self._json({'ok': False, 'err': '上一次生成还没结束，稍等再点', 'env': env_check()})
            # 「第一次」= 用户还没拿到交付落点。注意不能只看 index.html 在不在：
            # 建站脚本（setup_site / new_site）往往已经把网页生成过了，用户却还没拿到
            # 「打开网站.bat」这种双击入口 —— 那种情况也该帮他打开、把入口放好。
            idx = PF / 'index.html'
            want = ('打开网站.bat' if os.name == 'nt'
                    else '打开网站.command' if sys.platform == 'darwin' else '')
            first = not idx.exists() or (want and not (BASE / want).exists())
            t0 = datetime.datetime.now()
            try:
                log('build 开始')
                r = subprocess.run([PY, str(GEN)], cwd=str(BASE), capture_output=True,
                                   timeout=180, env=_child_env())
                out = decode_out(r.stdout) + decode_out(r.stderr)
                ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
                log('build %s rc=%s %dms | %s' % ('成功' if r.returncode == 0 else '失败', r.returncode, ms,
                                                  out.replace('\n', ' ｜ ')[:400]))
                # 生成成功就把「这一版到底有多大、引了多少资源」一并回给前端，
                # 省得用户还要自己去文件夹里看文件大小。
                info = {'ok': r.returncode == 0, 'rc': r.returncode, 'out': out,
                        'env': env_check(), 'ms': ms, 'first': first}
                if r.returncode == 0 and idx.exists():
                    info['size'] = idx.stat().st_size
                    info['at'] = datetime.datetime.now().strftime('%H:%M:%S')
                    info['label'] = site_label()
                    html = idx.read_text(encoding='utf-8', errors='replace')
                    info['refs'] = len([m for m in _ATTR.findall(html) if _is_media(m[1])])
                    info['site'] = str(idx)
                    info['launchers'] = []
                    if first:
                        try:
                            info['launchers'] = make_launchers()
                            log('首次生成：放了启动文件 %s' % '、'.join(info['launchers']))
                        except Exception as e:
                            log('写启动文件失败：%s' % e)
                        # 只拦「弹浏览器」这一下：SITE_NO_OPEN 是给测试用的，
                        # 启动文件照放（它不打扰任何人，还是交付物的一部分）。
                        if os.environ.get('SITE_NO_OPEN'):
                            info['opened'] = False
                        else:
                            info['opened'] = open_site(idx)
                            log('首次生成：%s' % ('已打开网页'
                                                  if info['opened'] else '没能自动打开，路径 ' + str(idx)))
                return self._json(info)
            except subprocess.TimeoutExpired:
                log('build 超时')
                return self._json({'ok': False, 'err': '生成超过 180 秒还没结束，已中断', 'env': env_check()})
            except Exception as e:
                log('build 异常：%s' % e)
                return self._json({'ok': False, 'err': '%s: %s' % (type(e).__name__, e), 'env': env_check()})
            finally:
                BUILD_LOCK.release()

        if path == '/api/upload':
            try:
                sub = body.get('dir', 'cover')
                name = (body.get('name') or '').strip()
                b64 = body.get('b64') or ''
                if not name or not b64:
                    return self._json({'ok': False, 'err': '缺 name / b64'}, 400)
                if ',' in b64:                       # data:image/jpeg;base64,xxx
                    b64 = b64.split(',', 1)[1]
                data = base64.b64decode(b64)
                # 未知目录必须报错，不许静默兜底到 assets/cover：
                # 那样上传「看起来成功」，文件却落错目录，坑能藏很久
                # （UPLOAD_DIRS 启动时读一次，新登记的目录要重启后台才生效）。
                rel_dir = UPLOAD_DIRS.get(sub)
                if not rel_dir:
                    return self._json({'ok': False, 'err': '未知上传目录: %s' % sub})
                outdir = PF / rel_dir
                outdir.mkdir(parents=True, exist_ok=True)
                ext = pathlib.Path(name).suffix.lower() or '.jpg'
                stem = pathlib.Path(name).stem
                # overwrite 必须严格解析：bool("false") 是 True，会把字符串型的假值当真，
                # 结果就是"本不该覆盖"的上传把同名文件盖掉了。只认真布尔或明确的字符串真值。
                _ov = body.get('overwrite')
                overwrite = _ov is True or (isinstance(_ov, str) and _ov.strip().lower() in ('1', 'true', 'yes'))
                if sub != 'photo2' and not overwrite:
                    # 普通上传一律走统一命名，原文件名不参与（见 auto_name 的说明）。
                    # photo2 例外：它按 分类_NN.jpg 定点覆盖，生成器按名字找图。
                    final = auto_name(outdir, sub, ext)
                else:
                    # overwrite：形象照 portrait.jpg 这种固定名必须原地替换，不能变成 portrait-1
                    if sub != 'photo2':
                        stem = ''.join(c for c in stem if c not in ' /\\:*?"<>|') or 'img'
                    final = outdir / (stem + ext)
                # 会覆盖已有文件（摄影图按 分类_NN.jpg 定点替换）→ 先把原件挪进 _bak/img
                if final.exists():
                    ibak = PF / '_bak' / 'img'
                    ibak.mkdir(parents=True, exist_ok=True)
                    # 时间戳只到秒，同一秒内连续覆盖同一文件时后一次会把前一次的备份盖掉，
                    # 中间版本就丢了 → 撞名时补序号，保证每次覆盖都留得下。
                    _stamp = datetime.datetime.now().strftime('%m%d-%H%M%S')
                    _b = ibak / ('%s-%s%s' % (final.stem, _stamp, final.suffix))
                    _k = 1
                    while _b.exists():
                        _k += 1
                        _b = ibak / ('%s-%s-%d%s' % (final.stem, _stamp, _k, final.suffix))
                    shutil.copy2(final, _b)
                    olds = sorted(ibak.glob('*'))[-50:]
                    keep = set(olds)
                    for f in ibak.glob('*'):
                        if f not in keep:
                            try: f.unlink()
                            except Exception: pass

                final.write_bytes(data)
                orig_bytes = len(data)

                # 压一遍：大图不压会拖垮网页加载，极端情况直接打不开
                if sub == 'logo':
                    # logo 走单独一条路：只缩尺寸、不换格式（见 fit_logo 的说明）
                    if final.suffix.lower() == '.svg':
                        new_bytes, (W, H), did = orig_bytes, (0, 0), False
                    else:
                        try:
                            new_bytes, (W, H), did = fit_logo(final)
                        except Exception:
                            new_bytes, (W, H), did = orig_bytes, (0, 0), False
                else:
                    kind = sub if sub in KIND_CFG else 'cover'
                    new_bytes, (W, H), did = compress(
                        final, kind, force_jpeg=(sub == 'photo2'))   # 摄影图必须落 .jpg，生成器按 .jpg 找
                    if did and final.suffix.lower() not in ('.jpg', '.jpeg'):
                        jpg = final.with_suffix('.jpg')
                        final.rename(jpg)
                        final = jpg

                rel = '%s/%s' % (rel_dir, final.name)
                # 缩略图：后台列表 / 表单里的预览一律走 assets/<kind>/t/<name>，
                # 不生成的话前端只能挂原图 → 每开一次列表就把几 MB 大图全下一遍。
                # 以前只给 photo2 生成，其余全缺，这就是「新加的图不显示缩略图」的根因。
                # 现在所有图片类型统一生成，宽度按用途区分（列表小图不用 520 那么宽）。
                th_w = TH_W.get(sub, 260)
                try:                                     # svg 之类生成不了，别因此让上传报错
                    thumb(final, PF / rel_dir / 't' / final.name, w=th_w)
                except Exception:
                    pass
                # 压缩后扩展名可能从 png 变成 jpg，老缩略图残留会越积越多 → 顺手清掉同名旧后缀
                for _suf in ('.jpg', '.jpeg', '.png', '.webp'):
                    _old = PF / rel_dir / 't' / (final.stem + _suf)
                    if _old.name != final.name and _old.exists():
                        try: _old.unlink()
                        except Exception: pass
                # 前端拿不到「缩略图叫什么」的话还是只能拼原图路径，所以回传明确的名字
                th_rel = '%s/t/%s' % (rel_dir, final.name)
                return self._json({'ok': True, 'path': rel, 'file': final.name,
                                   'thumb': th_rel, 'thumb_w': th_w,
                                   'orig': orig_bytes, 'size': new_bytes,
                                   'w': W, 'h': H, 'compressed': did})
            except Exception as e:
                return self._json({'ok': False, 'err': str(e)}, 500)

        if path == '/api/thumbs':
            # 存量图补缩略图（后台列表提速用）。可重复跑，已存在的会跳过。
            try:
                kind = body.get('kind') or None
                made, skipped = backfill_thumbs(only=[kind] if kind else None)
                log('thumbs 补齐：新生成 %d，跳过 %d' % (made, skipped))
                return self._json({'ok': True, 'made': made, 'skipped': skipped})
            except Exception as e:
                return self._json({'ok': False, 'err': str(e)}, 500)

        if path == '/api/favicon':
            # 由头像重做整套收藏夹图标。后台「总设置 → 重新生成图标」调这里。
            try:
                d = json.loads(DATA.read_text(encoding='utf-8'))
                rel = ((d.get('site') or {}).get('avatar')) or 'assets/hero/avatar.jpg'
                src = (PF / rel).resolve()
                if PF.resolve() not in src.parents or not src.exists():
                    return self._json({'ok': False, 'err': '找不到头像 %s，先传一张头像' % rel})
                made = make_icons(src)
                log('favicon 重做：%s' % ', '.join(made))
                return self._json({'ok': True, 'out': '\n'.join('  + ' + m for m in made)})
            except Exception as e:
                return self._json({'ok': False, 'err': '%s: %s' % (type(e).__name__, e)}, 500)

        if path == '/api/delimg':
            try:
                rel = (body.get('path') or '').lstrip('/')
                p = PF / rel
                if p.exists() and p.is_file() and PF in p.parents:
                    p.unlink()
                return self._json({'ok': True})
            except Exception as e:
                return self._json({'ok': False, 'err': str(e)}, 500)

        return self._json({'ok': False, 'err': 'unknown route'}, 404)


class Srv(ThreadingHTTPServer):
    """浏览器/探活脚本提前断开是常态（轮询、切页、点取消），
    这类 ConnectionAborted/Reset 不该在日志里刷一屏 traceback —— 真正的错会被埋在下面。"""
    daemon_threads = True

    def handle_error(self, request, client_address):
        et = sys.exc_info()[0]
        if et is not None and issubclass(et, ConnectionError):
            return
        super().handle_error(request, client_address)


if __name__ == '__main__':
    # 建站流程会在首次生成后调这个，把 photography 墙的 t/ 缩略图一次补齐。
    # 不然刚建完站就体检，会报一堆 assets/photo2/t/*.jpg 缺失（其实只是还没生成）。
    if '--thumbs' in sys.argv:
        m, s = backfill_thumbs(verbose='-v' in sys.argv)
        print('缩略图：新生成 %d，跳过 %d' % (m, s))
        sys.exit(0)

    if not DATA.exists():
        print('✗ 找不到', DATA)
        sys.exit(1)
    e = env_check()
    print('环境自检：python %s ｜ Pillow %s ｜ 生成器 %s ｜ 数据 %s'
          % ('√' if e['py_ok'] else '✗', e.get('pillow'), '√' if e['gen_ok'] else '✗',
             '√' if e['data_ok'] else '✗'))
    for k in ('py_ok', 'gen_ok', 'data_ok'):
        if not e[k]:
            print('  ✗ %s 有问题：%s' % (k, e.get(k.replace('_ok', ''))))

    # 端口预检：Windows 上 SO_REUSEADDR 允许绑定已被占用的端口，
    # 两个后台同时"启动成功"，请求会随机落到其中一个 —— 排查起来像灵异事件。
    # 所以先探一下，占用了就明确退出（rc=3），别硬绑。
    import socket
    probe = socket.socket()
    probe.settimeout(0.4)
    busy = probe.connect_ex(('127.0.0.1', PORT)) == 0
    probe.close()
    if busy:
        print('✗ 端口 %d 已被占用 —— 可能已经有一个后台在跑。' % PORT)
        print('  直接用 http://127.0.0.1:%d/ 就行；要换端口启动：' % PORT)
        print('    %s' % ('set SITE_PORT=8849 && python admin/server.py' if os.name == 'nt'
                          else 'SITE_PORT=8849 python3 admin/server.py'))
        sys.exit(3)

    srv = Srv(('127.0.0.1', PORT), H)
    url = 'http://127.0.0.1:%d/' % PORT
    print('作品集后台已启动 → %s' % url)
    print('数据文件：', DATA)
    print('生成脚本：', GEN)
    print('解释器  ：', PY)
    print('')
    print('改完内容点右上角「生成网页」；第一次生成会自动帮你打开网站。')
    print('（关掉这个黑窗口 = 停止后台）')
    # SITE_OPEN 只由 admin/start-admin.bat / start-admin.command 设置：人双击启动时才自动开浏览器。
    # open_admin.py（agent / 托管会话）自己会开，selftest 则完全不碰浏览器。
    if os.environ.get('SITE_OPEN') and not os.environ.get('SITE_NO_OPEN'):
        try:
            webbrowser.open(url)
            print('已帮你打开浏览器；没弹出来的话，把上面的地址粘进去。')
        except Exception as e:
            print('自动打开浏览器失败：%s（手动打开上面的地址即可）' % e)
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n后台已停止。')
