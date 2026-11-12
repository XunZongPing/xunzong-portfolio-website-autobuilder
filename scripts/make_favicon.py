# -*- coding: utf-8 -*-
"""用一张头像生成 favicon 全套尺寸，落到 <site>/portfolio/ 根下。

用法：
    python make_favicon.py --site D:/sites/lisi
    python make_favicon.py --site D:/sites/lisi --src D:/pic/me.jpg

缺省源图 = <site>/portfolio/assets/hero/avatar.jpg

产出（都放 portfolio/ 根下，方便 index.html 用相对路径引用）：
  favicon.ico          —— 16/32/48 多尺寸，浏览器标签页 + 老浏览器
  favicon-32.png       —— 标准 png 图标
  apple-touch-icon.png —— 180x180，iOS 添加到主屏 / 微信收藏
  icon-192.png / icon-512.png —— Android / PWA

处理要点（2026-10-09 改版，从「圆形 + 白边」改成「满幅圆角方块」）：
1. **满幅**：原方案四周留 5%~8% 白边，16px 下可用像素只剩约 190 个，细节全糊。
   现在图片铺满整张画布，可像素从 ~190 提到 ~256。
2. **圆角而非正圆**：圆角比方块柔和、又比正圆多保住四个角的像素（正圆会砍掉
   约 21% 的面积），是 16px 尺度下的折中。圆角半径按尺寸等比取 22%。
3. **小尺寸微调**：16px 下圆角抗锯齿后边缘发灰，所以 ≤32px 用较小圆角半径。
4. **背景必须白色而不是透明**：favicon 在深色主题栏里，透明背景会露出底层，
   头像的暗部会和背景糊在一起。填白底能保证任何主题下都看得清。

`--zoom`（2026-10-30 加）：源图是「环境人像 / 半身照」时，人脸只占画幅一小块，
缩到 16px 就剩几个像素、认不出是个人。给个 0.78~0.85 把画面往里收一圈再缩，
脸能大一倍。**别低于 0.7** —— 再往里就会切到额头或下巴，反而更糟。
缺省 1.0（原样），只有确实嫌脸小的时候才动它。
"""
import argparse
import pathlib
import sys
import tempfile

from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding='utf-8')

# 圆角半径占边长的比例。小尺寸用小半径，避免抗锯齿把边缘糊成灰圈。
RADIUS_SMALL = 0.18   # <= 32px
RADIUS_LARGE = 0.22   # 大尺寸，观感更接近 iOS 图标


def rounded(im, size, radius_ratio=RADIUS_LARGE, bg=(255, 255, 255, 255), zoom=1.0):
    """满幅缩放 + 圆角裁切。图片铺满整张画布，不留白边。

    先居中裁成正方形再缩 —— 直接 resize 会把竖构图的人脸压扁。
    zoom < 1 时在方形基础上再往里收一圈（同样居中），让小尺寸图标里的人脸更大。
    """
    canvas = Image.new('RGBA', (size, size), bg)
    w, h = im.size
    s = min(w, h)
    im = im.convert('RGBA').crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    if zoom < 1:
        n = max(1, round(s * zoom))
        off = (s - n) // 2
        im = im.crop((off, off, off + n, off + n))
    im = im.resize((size, size), Image.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    r = max(1, int(size * radius_ratio))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=255)
    canvas.paste(im, (0, 0), mask)
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    ap.add_argument('--src', help='源图，缺省 portfolio/assets/hero/avatar.jpg')
    ap.add_argument('--zoom', type=float, default=1.0,
                    help='裁切倍率，1.0 原样、0.78~0.85 把脸放大（环境人像用），不小于 0.7')
    a = ap.parse_args()

    zoom = max(0.7, min(1.0, a.zoom))
    if zoom != a.zoom:
        print('!! --zoom %.2f 超范围，已收进 [0.7, 1.0] 用 %.2f' % (a.zoom, zoom))

    site = pathlib.Path(a.site).expanduser().resolve()
    OUT = site / 'portfolio'
    SRC = pathlib.Path(a.src).expanduser().resolve() if a.src else OUT / 'assets' / 'hero' / 'avatar.jpg'
    if not SRC.exists():
        print('!! 找不到源图：%s' % SRC)
        return 1
    src = Image.open(SRC)
    print('源图：%s  %s  裁切倍率 %.2f' % (SRC, src.size, zoom))

    for size, name in (
        (32, 'favicon-32.png'),
        (180, 'apple-touch-icon.png'),
        (192, 'icon-192.png'),
        (512, 'icon-512.png'),
    ):
        rr = RADIUS_SMALL if size <= 32 else RADIUS_LARGE
        img = rounded(src, size, radius_ratio=rr, zoom=zoom)
        p = OUT / name
        img.save(p, 'PNG', optimize=True)
        print('  + %-24s %d x %d  %d B  (圆角 %d%%)'
              % (name, size, size, p.stat().st_size, int(rr * 100)))

    ico_sizes = [16, 32, 48]
    frames = [rounded(src, s, radius_ratio=RADIUS_SMALL, zoom=zoom).convert('RGBA') for s in ico_sizes]
    ico_path = OUT / 'favicon.ico'
    frames[-1].save(ico_path, format='ICO',
                    sizes=[(s, s) for s in ico_sizes],
                    append_images=frames[:-1])
    print('  + %-24s %s  %d B' % ('favicon.ico', ico_sizes, ico_path.stat().st_size))

    print()
    print('=== 自检 ===')
    for name in ('favicon.ico', 'favicon-32.png', 'apple-touch-icon.png',
                 'icon-192.png', 'icon-512.png'):
        p = OUT / name
        if not p.exists():
            print('  !! 缺失 %s' % name)
            return 1
        im = Image.open(p)
        print('  %-24s %s  %s' % (name, im.size, im.mode))

    strip = Image.new('RGB', (560, 220), (245, 247, 250))
    for i, (name, sz) in enumerate((('favicon-32.png', 16),
                                    ('favicon-32.png', 32),
                                    ('apple-touch-icon.png', 180))):
        Z = 180
        im = Image.open(OUT / name).convert('RGBA')
        im = im.resize((Z, Z), Image.NEAREST if sz <= 32 else Image.LANCZOS)
        strip.paste(im, (20 + i * (Z + 10), 20), im)
    # 这张图只是给你肉眼确认 16/32/180 三个尺寸的实际观感，不属于站点资源。
    # 以前落在 <site>/build/ 下，结果被打包、发布一起带走（Demo 里就多出个 13KB 的
    # _preview_sizes.png），所以改到系统临时目录。
    pv = pathlib.Path(tempfile.gettempdir()) / 'pf_favicon_preview.png'
    strip.save(pv)
    print()
    print('预览图（16 / 32 / 180 真实观感）：%s' % pv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
