# -*- coding: utf-8 -*-
"""把上传的 PDF / Word 转成论文内页图。

论文板块的内页本来要手填「图片路径 | 说明」，作者得先自己把 PDF 截成图。
这个模块把那段活接过来：给一份文件，吐出前 N 页的 jpg + 每页的说明。

两条路，能力不同，界面上要如实区分：
  • **PDF —— 推荐**。用 PyMuPDF 直接渲染页面，原样保真（排版、图表、公式都在）。
  • **.docx —— 降级**。不装 Word 也不装 python-docx 的前提下，只能从
    word/document.xml 里抠出段落文字，再用 Pillow 按 A4 重新排一遍。
    文字都在，**但表格结构、图片、公式会丢** —— 所以界面把 PDF 标成「推荐」。
  • **.doc（97-2003 老格式）不支持**：二进制格式，标准库解不开。提示另存为 PDF。

用法（单独跑，方便验证和排查）：
    python doc_import.py --file 论文.pdf --out ../portfolio/assets/papers
    python doc_import.py --file 论文.docx --out ../portfolio/assets/papers --pages 3
"""
import argparse
import datetime
import io
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.stdout.reconfigure(encoding='utf-8')

MAX_PAGES = 6          # 一次最多导 6 页：内页是「翻两页看看样子」，不是整本
DPI = 150              # A4 @150dpi ≈ 1240×1754，够 86vh 的灯箱看清楚，又不至于几 MB
QUALITY = 82

NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

# 中文优先的字体候选。Pillow 找不到 ttf 时默认字体画不出汉字（全是方块/空白），
# 所以字号可以凑合，字体不能凑合 —— 一个都找不到就明确报错，别生成一堆空白页。
FONT_CANDIDATES = [
    r'C:\Windows\Fonts\msyh.ttc',        # 微软雅黑
    r'C:\Windows\Fonts\simsun.ttc',      # 宋体
    '/System/Library/Fonts/PingFang.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
]
# 标题的加粗字体。Pillow 不会合成粗体，只能另找一个字重文件；
# 一个都找不到时退回常规体 —— 标题靠字号拉开层次也够看。
FONT_BOLD = [
    r'C:\Windows\Fonts\msyhbd.ttc',
    r'C:\Windows\Fonts\simhei.ttf',
    '/System/Library/Fonts/PingFang.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
]


def _font(size, bold=False):
    from PIL import ImageFont
    for p in (FONT_BOLD if bold else []) + FONT_CANDIDATES:
        if pathlib.Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    raise RuntimeError('找不到中文字体（试过 msyh / simsun / PingFang / Noto CJK）。'
                       'docx 转图需要它，PDF 那条路不需要。')


def auto_prefix(out_dir):
    """内页图的统一前缀：`<目录名>-<日期>-<序号>`，例 `papers-20261104-01` → `…_p1.jpg`。

    **不用原文件名**。论文叫《毕业论文》时以前会落成「毕业论文_p1.jpg」：中文名经 zip
    分发容易乱码（pitfalls 71），而且同一份文档重新导入得靠 _2/_3 反复避让。
    现在按天分组、序号递增、永不覆盖 —— 旧内页仍然可用，新导入不会把上一份盖掉。
    """
    day = datetime.datetime.now().strftime('%Y%m%d')
    pre = '%s-%s-' % (out_dir.name or 'doc', day)
    n = 1
    for p in out_dir.glob(pre + '*_p*.jpg'):
        m = re.match(r'^%s(\d+)_p\d+$' % re.escape(pre), p.stem)
        if m:
            n = max(n, int(m.group(1)) + 1)
    while any(out_dir.glob('%s%02d_p*.jpg' % (pre, n))):
        n += 1
    return '%s%02d' % (pre, n)


def _save(im, out_dir, prefix, page_no):
    p = out_dir / ('%s_p%d.jpg' % (prefix, page_no))
    im.convert('RGB').save(p, 'JPEG', quality=QUALITY, optimize=True)
    return p


# ---------- PDF ----------
def pdf_pages(data, out_dir, prefix, max_pages=MAX_PAGES):
    """返回 (落盘文件列表, 总页数)。用 PyMuPDF 渲染，保真。"""
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise RuntimeError('没装 PyMuPDF：pip install pymupdf（装完重启后台）')

    from PIL import Image
    doc = fitz.open(stream=data, filetype='pdf')
    total = doc.page_count
    n = min(max_pages, total)
    out = []
    for i in range(n):
        pix = doc[i].get_pixmap(dpi=DPI)
        im = Image.open(io.BytesIO(pix.tobytes('png')))
        out.append(_save(im, out_dir, prefix, i + 1))
    doc.close()
    return out, total


# ---------- docx ----------
def _docx_paragraphs(data):
    """从 word/document.xml 里抠段落。返回 [(文本, 层级)]，层级 0=正文 1/2/3=标题。"""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read('word/document.xml')
    root = ET.fromstring(xml)
    out = []
    for p in root.iter(NS + 'p'):
        txt = ''.join(t.text or '' for t in p.iter(NS + 't')).strip()
        if not txt:
            continue
        lvl = 0
        st = p.find('%spPr/%spStyle' % (NS, NS))
        if st is not None:
            name = (st.get(NS + 'val') or '').lower()
            if 'title' in name or '标题' in name:
                lvl = 1
            elif 'heading' in name or 'head' in name:
                m = re.search(r'(\d)', name)
                lvl = min(3, int(m.group(1)) if m else 1) or 1
        if not lvl:                      # 中文 Word 常不写 pStyle，只给大纲级别
            ol = p.find('%spPr/%soutlineLvl' % (NS, NS))
            if ol is not None:
                try:
                    lv = int(ol.get(NS + 'val') or 9)
                    lvl = min(3, lv + 1) if lv < 3 else 0
                except ValueError:
                    pass
        out.append((txt, lvl))
    return out


def _wrap(text, font, maxw):
    lines, cur = [], ''
    for ch in text:
        if font.getlength(cur + ch) <= maxw:
            cur += ch
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or ['']


def _docx_to_images(paras, out_dir, prefix, max_pages):
    from PIL import Image, ImageDraw
    W, H = 1240, 1754               # A4 @150dpi
    ML, MR, MT, MB = 118, 118, 120, 130
    maxw = W - ML - MR
    body, head1, head2 = _font(23), _font(33, bold=True), _font(27, bold=True)
    gap = 14

    pages, im, dr = [], Image.new('RGB', (W, H), 'white'), None
    y = MT

    def flush():
        nonlocal im, dr
        im = Image.new('RGB', (W, H), 'white')
        dr = ImageDraw.Draw(im)

    def push():
        """收页：给每页右下角打页码，避免导出的几页图看着一模一样。"""
        nonlocal im, dr, y
        if dr is not None:
            dr.text((W - MR - 60, H - 76), str(len(pages) + 1), fill=(150, 155, 165), font=_font(18))
            pages.append(im)
        y = MT
        flush()

    flush()
    for txt, lvl in paras:
        font = head1 if lvl == 1 else head2 if lvl else body
        lh = int(font.size * 1.62)
        for line in _wrap(txt, font, maxw):
            if y + lh > H - MB:
                push()
                if len(pages) >= max_pages:
                    break
            dr.text((ML, y), line, fill=(24, 28, 36), font=font)
            y += lh
        y += gap + (10 if lvl else 0)
        if len(pages) >= max_pages:
            break
    if len(pages) < max_pages and dr is not None:
        push()

    return [_save(p, out_dir, prefix, i + 1) for i, p in enumerate(pages[:max_pages])]


def docx_pages(data, out_dir, prefix, max_pages=MAX_PAGES):
    """返回 (落盘文件列表, 段落数)。降级排版：只有文字，表格/图片/公式不保。"""
    paras = _docx_paragraphs(data)
    if not paras:
        raise RuntimeError('这份 .docx 里没读出文字（可能整篇都是图片或表格）')
    return _docx_to_images(paras, out_dir, prefix, max_pages), len(paras)


# ---------- 统一入口 ----------
def convert(data, filename, out_dir, max_pages=MAX_PAGES, note_prefix='P'):
    """把一个文件转成内页图。返回 dict：

        {'prefix': 'lunwen', 'files': [路径...], 'total': 12, 'kind': 'pdf',
         'note': 'P1', 'hint': '只取了前 4 页（共 12 页）'}

    路径是**相对 portfolio/** 的 posix 路径，直接能写进 data.json。
    """
    out_dir = pathlib.Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = pathlib.Path(filename).suffix.lower()
    pre = auto_prefix(out_dir)

    if ext == '.pdf':
        files, total = pdf_pages(data, out_dir, pre, max_pages)
        kind = 'pdf'
    elif ext == '.docx':
        files, total = docx_pages(data, out_dir, pre, max_pages)
        kind = 'docx'
    elif ext in ('.doc', '.wps', '.rtf'):
        raise RuntimeError('%s 是旧版二进制格式，读不了。请在 Word/WPS 里「另存为 PDF」再上传'
                           '（PDF 保真度也更高）' % ext)
    else:
        raise RuntimeError('只认 .pdf 和 .docx，收到的是 %r' % (ext or '无扩展名'))

    rel = ['assets/papers/' + p.name for p in files]

    if kind == 'pdf':
        # 这句会被前端套进「已导入 4 页（…）」的括号里，所以自己不能再带括号
        hint = '' if total <= len(files) else '只取了前 %d 页，共 %d 页' % (len(files), total)
        notes = ['%s%d' % (note_prefix, i + 1) for i in range(len(files))]
    else:
        hint = 'Word 走的是降级排版：只保留文字，表格、图片和公式会丢'
        notes = ['%s%d' % (note_prefix, i + 1) for i in range(len(files))]

    return {'prefix': pre, 'files': rel, 'total': len(files), 'kind': kind,
            'notes': notes, 'hint': hint}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True)
    ap.add_argument('--out', required=True, help='图片输出目录（一般是 portfolio/assets/papers）')
    ap.add_argument('--pages', type=int, default=MAX_PAGES)
    a = ap.parse_args()

    p = pathlib.Path(a.file).expanduser().resolve()
    r = convert(p.read_bytes(), p.name, a.out, a.pages)
    print('类型 %s ｜ 出图 %d 页 ｜ 前缀 %s' % (r['kind'], r['total'], r['prefix']))
    for f, n in zip(r['files'], r['notes']):
        print('  %-40s %s' % (f, n))
    if r['hint']:
        print('注意：' + r['hint'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
