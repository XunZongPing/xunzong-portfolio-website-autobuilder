# -*- coding: utf-8 -*-
"""跑生成器：<site>/portfolio/data.json → <site>/portfolio/index.html

用法：
    python build.py --site D:/sites/lisi
    python build.py --site D:/sites/lisi --check      # 生成后再核验引用资源
"""
import argparse
import os
import pathlib
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = pathlib.Path(__file__).resolve().parent

# 解释器：优先环境变量 SITE_PY，否则用当前解释器（需装 Pillow）
PY = os.environ.get('SITE_PY') or sys.executable


def child_env(site):
    """子进程 IO 钉成 UTF-8。

    ⚠️ 本机 ANSI 代码页是 936(GBK)。Python 的 stdout 变成管道时按 locale 选编码，
    于是子进程吐 GBK 字节、父进程按 utf-8 解 → 每个中文变 U+FFFD（乱码）。
    """
    e = dict(os.environ)
    e['PYTHONIOENCODING'] = 'utf-8'
    e['PYTHONUTF8'] = '1'
    e['SITE_BASE'] = str(site)
    return e


def decode_out(b):
    for enc in ('utf-8', 'gbk'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode('utf-8', 'replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--no-validate', action='store_true',
                    help='跳过 data.json 形状体检（不建议：跳过只会把 ValueError 推到渲染里）')
    a = ap.parse_args()

    site = pathlib.Path(a.site).expanduser().resolve()
    gen = site / 'build' / 'gen_site.py'
    if not gen.exists():
        raise SystemExit('找不到生成器：%s（先跑 new_site.py）' % gen)

    env = child_env(site)
    if a.no_validate:
        env['SITE_SKIP_VALIDATE'] = '1'

    # 体检在生成器内部做（同一份代码后台也在用），这里不做第二遍 ——
    # 两边各跑一次只会让同一句报错打印两遍。
    r = subprocess.run([PY, str(gen)], cwd=str(site),
                       capture_output=True, env=env)
    out = decode_out(r.stdout or b'') + decode_out(r.stderr or b'')
    print(out.strip())
    if r.returncode != 0:
        print('!! 生成失败（退出码 %d）' % r.returncode)
        return r.returncode

    idx = site / 'portfolio' / 'index.html'
    if idx.exists():
        print('产物：%s  %.1f KB' % (idx, idx.stat().st_size / 1024))

    if a.check:
        r2 = subprocess.run([PY, str(HERE / 'check_site.py'), '--site', str(site)],
                            capture_output=True, env=child_env(site))
        print(decode_out(r2.stdout or b'').strip())
    return 0


if __name__ == '__main__':
    sys.exit(main())
