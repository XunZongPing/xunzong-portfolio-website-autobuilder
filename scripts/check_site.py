# -*- coding: utf-8 -*-
"""站点体检：把 index.html 里引用的每个本地资源都核一遍，缺谁报谁。

为什么不能靠抽样：2026-10-08 上线时抽查 40 张全过、按引用清单全量核验才暴露
4 张图缺失（线上直接裂图）。**必须按引用清单逐条核。**

用法：
    python check_site.py --site D:/sites/lisi
    python check_site.py --site D:/sites/lisi --publish     # 顺带核对 _publish_tmp/
"""
import argparse
import pathlib
import re
import sys
from urllib.parse import unquote

sys.stdout.reconfigure(encoding='utf-8')

# src="..." / href="..." / url('...')
# 前面加 (?<![.\w])：别把 JS 里的 `el.dataset.src = 'x'` 当成 src="x"（会凭空报一张缺图）
PAT = re.compile(r'''(?<![.\w])(?:src|href)\s*=\s*["']([^"']+)["']|url\(\s*["']?([^"')]+)["']?\s*\)''')
SKIP_PREFIX = ('http://', 'https://', '//', 'data:', 'mailto:', 'tel:', 'javascript:', '#')


def collect(html):
    refs = []
    for m in PAT.finditer(html):
        u = m.group(1) or m.group(2)
        if not u:
            continue
        # ⚠️ 先解码再判前缀：CSS 里的内联 SVG 噪声图写作
        # url("data:image/svg+xml,...%3Cfilter id='n'%3E...url(%23n)")，
        # 里面的 %23n 解码后才是 #n —— 不先解码就会被当成缺失资源。
        u = unquote(u.strip())
        if not u or u.startswith(SKIP_PREFIX):
            continue
        refs.append(u.split('?')[0].split('#')[0])
    # 去重但保序
    seen, out = set(), []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def check(root, refs, label):
    miss = []
    hit = 0
    for r in refs:
        p = (root / r.lstrip('/')).resolve()
        if p.is_file():
            hit += 1
        else:
            miss.append(r)
    print('[%s] 引用 %d 个，命中 %d 个，缺 %d 个' % (label, len(refs), hit, len(miss)))
    for m in miss:
        print('   ✗ %s' % m)
    return len(miss)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    ap.add_argument('--publish', action='store_true')
    a = ap.parse_args()

    site = pathlib.Path(a.site).expanduser().resolve()
    idx = site / 'portfolio' / 'index.html'
    if not idx.exists():
        raise SystemExit('没有 %s —— 先跑 build.py' % idx)

    refs = collect(idx.read_text(encoding='utf-8'))
    bad = check(site / 'portfolio', refs, 'portfolio')

    if a.publish:
        pub = site / '_publish_tmp'
        if not (pub / 'index.html').exists():
            print('[发布副本] 不存在 —— 先跑 sync_publish.py')
            bad += 1
        else:
            # 发布副本用同一份 index.html，所以引用清单一致
            bad += check(pub, refs, '发布副本')

    if bad:
        print('体检不通过：%d 处缺失' % bad)
        return 1
    print('体检通过：引用资源一个不缺')
    return 0


if __name__ == '__main__':
    sys.exit(main())
