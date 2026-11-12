# -*- coding: utf-8 -*-
"""建站第二步：抓参考网址的可用信息（标题 / 简介 / 主图 / 配色 / 联系方式）。

    python scripts/fetch_refs.py --url https://example.com
    python scripts/fetch_refs.py --url https://a.com --url https://b.com --save D:/sites/lisi/_setup/refs
    python scripts/fetch_refs.py --url https://a.com --download        # 主图一起下下来

为什么要这一步：用户手里通常已经有一个主页、一份公众号、一个 B 站空间。
这些页面上的**自我介绍、合作邮箱、主视觉**，比让用户重新口述一遍准得多。

只用标准库（urllib + HTMLParser），不装 requests / bs4 / lxml。
"""
import argparse
import gzip
import html
import json
import pathlib
import re
import sys
import urllib.request
import zlib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

sys.stdout.reconfigure(encoding='utf-8')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
TIMEOUT = 20

TEXT_TAGS = {'h1', 'h2', 'h3'}
META_WANT = {'og:title', 'og:description', 'og:image', 'og:site_name',
             'description', 'keywords', 'author', 'twitter:title',
             'twitter:description', 'twitter:image'}


class Pull(HTMLParser):
    """只捡需要的：meta / title / h1-h3 / mailto / tel。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = ''
        self.heads = []
        self.links = []
        self._tag = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'meta':
            key = (d.get('property') or d.get('name') or '').strip().lower()
            val = (d.get('content') or '').strip()
            if key and val and key in META_WANT and key not in self.meta:
                self.meta[key] = val
        elif tag in TEXT_TAGS or tag == 'title':
            self._tag = tag
            self._buf = []
        elif tag == 'a':
            href = (d.get('href') or '').strip()
            if href.lower().startswith(('mailto:', 'tel:')):
                self.links.append(href)

    def handle_data(self, data):
        if self._tag:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag != self._tag:
            return
        txt = re.sub(r'\s+', ' ', ''.join(self._buf)).strip()
        if txt:
            if tag == 'title':
                self.title = txt
            elif txt not in self.heads:
                self.heads.append(txt[:80])
        self._tag = None
        self._buf = []


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        # 明确要 identity：有些 CDN 不管请求头都塞 gzip 回来，
        # 按文本解会得到一堆乱码（标题全空就是这么来的），下面还有一层兜底。
        'Accept-Encoding': 'identity',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read(2 * 1024 * 1024)          # 2MB 足够，防着被大文件拖死
        ctype = r.headers.get('Content-Type', '')
        cenc = (r.headers.get('Content-Encoding') or '').lower()
        final = r.geturl()

    # 兜底：头里写着 identity 也可能真给压缩流，嗅一下魔数
    try:
        if 'gzip' in cenc or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        elif 'deflate' in cenc:
            raw = zlib.decompress(raw)
    except Exception:
        pass

    enc = 'utf-8'
    m = re.search(r'charset=([\w-]+)', ctype, re.I)
    if m:
        enc = m.group(1)
    else:
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:4096], re.I)
        if m:
            enc = m.group(1).decode('ascii', 'ignore')
    try:
        text = raw.decode(enc, 'replace')
    except LookupError:
        text = raw.decode('utf-8', 'replace')
    return text, final


def palette(img_path, n=4):
    """从主图里取几个主色。用来定站点的强调色，比让用户形容「偏冷还是偏暖」靠谱。"""
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        im = Image.open(img_path).convert('RGB')
        im.thumbnail((160, 160))
        q = im.quantize(colors=n, method=Image.MEDIANCUT)
        pal = q.getpalette() or []
        counts = sorted(q.getcolors() or [], reverse=True)
        out = []
        for cnt, idx in counts[:n]:
            rgb = pal[idx * 3:idx * 3 + 3]
            if len(rgb) == 3:
                out.append({'hex': '#%02x%02x%02x' % tuple(rgb),
                            'ratio': round(cnt / float(im.width * im.height), 3)})
        return out
    except Exception:
        return []


def one(url, save_dir, download):
    print('· %s' % url)
    info = {'url': url, 'ok': False}
    try:
        text, final = fetch(url)
    except Exception as e:
        info['err'] = '%s: %s' % (type(e).__name__, e)
        print('  ! 打不开：%s' % info['err'])
        return info

    p = Pull()
    try:
        p.feed(text)
    except Exception:
        pass                              # 半截 HTML 也能拿到大部分字段

    info.update({
        'ok': True,
        'final_url': final,
        'host': urlparse(final).netloc,
        'title': p.meta.get('og:title') or p.title,
        'desc': p.meta.get('og:description') or p.meta.get('description') or '',
        'site_name': p.meta.get('og:site_name') or '',
        'heads': p.heads[:8],
        'contacts': sorted(set(p.links)),
        'image': '',
    })

    og = p.meta.get('og:image') or p.meta.get('twitter:image') or ''
    if og:
        info['image'] = urljoin(final, og)

    # 邮箱经常藏在页面正文里而不是 mailto
    body_mail = sorted(set(re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', text)))
    if body_mail:
        info['mails'] = body_mail[:3]

    if download and info['image']:
        try:
            req = urllib.request.Request(info['image'], headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read(8 * 1024 * 1024)
            ext = pathlib.Path(urlparse(info['image']).path).suffix.lower() or '.jpg'
            if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
                ext = '.jpg'
            dst = save_dir / (urlparse(final).netloc.replace(':', '_') + ext)
            dst.write_bytes(data)
            info['image_file'] = str(dst)
            info['palette'] = palette(dst)
            print('  主图已下载 %s（%.0f KB）' % (dst.name, len(data) / 1024.0))
        except Exception as e:
            print('  ! 主图没下成：%s' % e)

    print('  标题：%s' % (info['title'] or '（无）'))
    if info['desc']:
        print('  简介：%s' % info['desc'][:100])
    if info['heads']:
        print('  小标题：%s' % ' ｜ '.join(info['heads'][:4]))
    if info.get('mails'):
        print('  邮箱：%s' % '、'.join(info['mails']))
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', action='append', required=True,
                    help='参考网址，可重复给多个')
    ap.add_argument('--save', help='结果存到哪（默认 ./_refs）')
    ap.add_argument('--download', action='store_true', help='把主视觉图一起下下来')
    ap.add_argument('--json', help='把结果写成一个 json 文件')
    a = ap.parse_args()

    save_dir = pathlib.Path(a.save or '_refs').expanduser().resolve()
    save_dir.mkdir(parents=True, exist_ok=True)

    print('[参考网址] 共 %d 个' % len(a.url))
    out = [one(u, save_dir, a.download) for u in a.url]

    ok = [o for o in out if o['ok']]
    print()
    print('抓到 %d / %d 个页面' % (len(ok), len(out)))

    jf = pathlib.Path(a.json) if a.json else (save_dir / 'refs.json')
    jf.parent.mkdir(parents=True, exist_ok=True)
    jf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print('结果：%s' % jf)
    if ok and any(o.get('palette') for o in ok):
        print('主色（可作站点强调色）：%s'
              % '  '.join(c['hex'] for o in ok for c in (o.get('palette') or [])[:3]))
    print()
    print('注意：抓到的文字只是**素材**。写进 data.json 之前要重写成人话，')
    print('      别把官网的营销腔整段搬进个人作品集。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
