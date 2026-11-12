# -*- coding: utf-8 -*-
"""把一个站点压成**单个 HTML 文件**（图片全部内联成 base64）。

    python scripts/pack_single.py --site D:/sites/lisi
    python scripts/pack_single.py --site D:/sites/lisi --out D:/桌面/我的作品集.html

什么时候用：
- 要发微信 / 邮件 / 网盘，对方不想解压也不要开服务器；
- 要当面给客户看，双击就能开。

代价：体积涨到原来的 1.3 倍左右（base64 膨胀 33%），且**以后改内容要重新打包**。
图片多的站（几百张原图）不建议走这条路，用 zip 或直接部署更合适。
"""
import argparse
import base64
import mimetypes
import pathlib
import re
import sys
from urllib.parse import unquote

sys.stdout.reconfigure(encoding='utf-8')

# 只认「看起来就是本地媒体文件」的值：有序扩展名、无协议头、无锚点。
# ⚠️ 以前写成严格白名单（只允许字母数字 . / - 和汉字），结果 `图片(30).jpg`、
# `8月4日(1)(3)-封面.jpg` 这类带括号的名字被漏在单文件外面：站内预览正常（浏览器
# 自己会处理括号），单 HTML 却裂图 —— 而且它们连「找不到」都不报，静默跳过最坑。
# 现在路径里允许空格、括号、& + , 等常见字符，只把「协议 / 锚点 / 空值」挡在外面。
MEDIA_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.ico', '.avif',
             '.mp4', '.webm')
SCHEME = re.compile(r'^[a-z][a-z0-9+.\-]*:', re.I)


def is_media(u):
    u = (u or '').strip()
    if not u or len(u) > 400:
        return False
    if u.startswith(('#', '//', 'data:')):
        return False
    if SCHEME.match(u):                 # http: https: mailto: javascript: file: blob:
        return False
    if any(c in u for c in '<>"\''):
        return False
    return re.split(r'[?#]', u, 1)[0].lower().endswith(MEDIA_EXT)
# 不枚举属性名，凡是「值看起来就是本地媒体路径」的都内联。
# 踩过：只写 src/poster/href 时，摄影墙的 data-full（点开看原图）和
# 奖项徽标的 data-img 被漏掉，单文件里灯箱一片裂图。
ATTR = re.compile(r'(\b[\w-]+\s*=\s*["\'])([^"\']+)(["\'])')
CSSURL = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', re.I)
# 单文件里图标没意义（还要多背 5 个 base64），直接摘掉这几行
ICON_LINK = re.compile(r'<link[^>]+rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*>\s*', re.I)
# 万一将来生成器拆出了外链 css/js，也得内联进去
LINK_CSS = re.compile(r'<link[^>]+href=["\']([^"\']+\.css)["\'][^>]*>', re.I)
SCRIPT_SRC = re.compile(r'<script[^>]+src=["\']([^"\']+\.js)["\'][^>]*>\s*</script>', re.I)


def mime_of(p):
    m, _ = mimetypes.guess_type(p.name)
    return m or 'application/octet-stream'


def bundle(site, out=None, quiet=False):
    site = pathlib.Path(site).expanduser().resolve()
    src = site / 'portfolio' / 'index.html'
    if not src.exists():
        raise SystemExit('找不到 %s，先跑 scripts/build.py --site "%s"' % (src, site))

    root = src.parent.resolve()
    html = src.read_text(encoding='utf-8')
    cache, missing, inlined = {}, [], []

    def resolve(u):
        u = (u or '').strip()
        if not is_media(u):
            return None
        rel = unquote(re.split(r'[?#]', u, 1)[0])
        p = (root / rel).resolve()
        if root not in p.parents or not p.is_file():
            if u not in missing:
                missing.append(u)
            return None
        return p

    def as_uri(p):
        return 'data:%s;base64,%s' % (mime_of(p), base64.b64encode(p.read_bytes()).decode())

    def uri_of(u):
        if u in cache:
            return cache[u]
        p = resolve(u)
        if p is None:
            return None
        cache[u] = as_uri(p)
        inlined.append((u, p.stat().st_size))
        return cache[u]

    html = ICON_LINK.sub('', html)

    # 外链样式 / 脚本 → 内联标签（本模板不产生外链，留着以防版式改造）
    def css_tag(m):
        p = (root / unquote(m.group(1))).resolve()
        return '<style>%s</style>' % p.read_text(encoding='utf-8') if p.is_file() else m.group(0)

    def js_tag(m):
        p = (root / unquote(m.group(1))).resolve()
        return '<script>%s</script>' % p.read_text(encoding='utf-8') if p.is_file() else m.group(0)

    html = LINK_CSS.sub(css_tag, html)
    html = SCRIPT_SRC.sub(js_tag, html)

    def inline_attr(m):
        head, val, tail = m.group(1), m.group(2), m.group(3)
        uri = uri_of(val)
        return m.group(0) if uri is None else head + uri + tail

    html = ATTR.sub(inline_attr, html)

    def inline_css(m):
        uri = uri_of(m.group(1))
        return m.group(0) if uri is None else 'url("%s")' % uri

    html = CSSURL.sub(inline_css, html)

    if out is None:
        out = site / '_deploy' / (site.name + '-single.html')
    out = pathlib.Path(out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding='utf-8')

    total = out.stat().st_size
    if not quiet:
        print('已内联 %d 个资源，产出单个 HTML' % len(inlined))
        print('  文件：%s' % out)
        print('  体积：%.1f MB' % (total / 1024.0 / 1024.0))
        big = [x for x in inlined if x[1] > 2 * 1024 * 1024]
        if big:
            print('  ! %d 个文件超过 2MB，单文件会偏大：' % len(big))
            for v, s in big[:5]:
                print('      %s  %.1f MB' % (v, s / 1024.0 / 1024.0))
        if missing:
            print('  ! %d 个引用找不到（原样保留，双击后会裂图）：' % len(missing))
            for v in missing[:8]:
                print('      %s' % v)
        if total > 30 * 1024 * 1024:
            print('  ! 超过 30MB，微信/邮件可能传不动，建议改用 zip 或直接部署')
    return out, len(inlined), missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    ap.add_argument('--out', help='输出文件（默认 <site>/_deploy/<目录名>-single.html）')
    a = ap.parse_args()
    bundle(a.site, a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
