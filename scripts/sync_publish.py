# -*- coding: utf-8 -*-
"""把 <site>/portfolio/ 同步成可发布的副本 <site>/_publish_tmp/。

用法：python sync_publish.py --site D:/sites/lisi

为什么不能直接发布 portfolio/：
  portfolio/_shot/（调试截图，动辄数百 MB）+ _bak/（备份）都会被一起传上去。

关于 t/ 缩略图目录（⚠️ 别一刀切全排除，踩过）：
  - `assets/photo2/t/` 是**网页摄影墙正在用的资源**：生成器给每个 <figure> 的
    <img src> 写的就是 t/ 下的缩略图（data-full 才是原图）。排掉 = 摄影区整片裂图。
  - 其余 `assets/{cover,award,projects,hero,about}/t/` 只是后台列表在用，网页不引用。
  所以只排除 photo2 之外的 t/。

关于根目录散件（⚠️ 静默漏文件，踩过）：
  生成器只在 <head> 里写图标引用，**不搬文件**。老脚本只显式拷 index.html，
  于是 favicon 全漏、线上 404。现在改成**按 index.html 的引用清单**把根下散件都带上。
"""
import argparse
import os
import pathlib
import re
import shutil
import sys
from urllib.parse import unquote

sys.stdout.reconfigure(encoding='utf-8')

KEEP_T = {'photo2'}          # 唯一被网页引用的 t/ 目录
SKIP_PREFIX = ('http://', 'https://', '//', 'data:', 'mailto:', 'tel:', 'javascript:', '#')
PAT = re.compile(r'''(?:src|href)\s*=\s*["']([^"']+)["']|url\(\s*["']?([^"')]+)["']?\s*\)''')


def root_refs(html):
    """index.html 里引用到的「根目录下散件」（不含 / 的相对路径）。"""
    out = []
    for m in PAT.finditer(html):
        u = unquote((m.group(1) or m.group(2) or '').strip())   # 先解码再判前缀
        if not u or u.startswith(SKIP_PREFIX):
            continue
        u = u.split('?')[0].split('#')[0]
        if '/' not in u and '.' in u:
            out.append(u)
    return sorted(set(out))


def copy_assets(src, dst):
    n = skip = 0
    for dp, dn, fn in os.walk(src):
        rel = os.path.relpath(dp, src)
        parts = [] if rel == '.' else rel.split(os.sep)
        if parts and parts[-1] == 't' and (len(parts) < 2 or parts[-2] not in KEEP_T):
            skip += len(fn)
            dn[:] = []
            continue
        out = dst if rel == '.' else os.path.join(dst, rel)
        os.makedirs(out, exist_ok=True)
        for f in fn:
            shutil.copy2(os.path.join(dp, f), os.path.join(out, f))
            n += 1
    return n, skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    a = ap.parse_args()

    site = pathlib.Path(a.site).expanduser().resolve()
    SRC = site / 'portfolio'
    DST = site / '_publish_tmp'
    if not SRC.is_dir():
        print('找不到源目录：%s' % SRC)
        return 1

    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True, exist_ok=True)

    idx = SRC / 'index.html'
    shutil.copy2(idx, DST / 'index.html')

    # 根下散件：按引用清单拷（favicon 这类不再静默漏掉）
    n_root, miss_root = 0, []
    for rel in root_refs(idx.read_text(encoding='utf-8')):
        p = SRC / rel
        if p.is_file():
            shutil.copy2(p, DST / rel)
            n_root += 1
        else:
            miss_root.append(rel)

    n, skip = copy_assets(SRC / 'assets', DST / 'assets')

    for bad in ('_shot', '_bak'):
        p = DST / bad
        if p.exists():
            print('!! 泄漏 %s，已移除' % bad)
            shutil.rmtree(p)

    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, dn, fn in os.walk(DST) for f in fn)
    print('index.html 已同步')
    print('根下散件 %d 张%s' % (n_root, ('，缺：' + '、'.join(miss_root)) if miss_root else ''))
    print('拷贝原图 %d 张，跳过缩略图 %d 张' % (n, skip))
    print('发布副本大小：%.1f MB' % (total / 1024.0 / 1024.0))
    print('目录：%s' % DST)
    return 0


if __name__ == '__main__':
    sys.exit(main())
