# -*- coding: utf-8 -*-
"""本地预览：把 <site>/portfolio/ 用 http 起起来（走 127.0.0.1，图不会被浏览器拦）。

为什么不用 file:// ：file:// 下 iframe 跨源读不到 DOM，链接与灯箱也有些浏览器差异。
走本地 http 最接近真实环境。

用法：
    python preview.py --site D:/sites/lisi                 # 预览 portfolio/
    python preview.py --site D:/sites/lisi --publish       # 预览 _publish_tmp/
    python preview.py --site D:/sites/lisi --port 8890

停：Ctrl+C
"""
import argparse
import functools
import http.server
import pathlib
import socketserver
import sys
from urllib.parse import unquote

sys.stdout.reconfigure(encoding='utf-8')


class Handler(http.server.SimpleHTTPRequestHandler):
    # 预览必须破缓存，否则改了内容看不到变化
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

    def translate_path(self, path):
        # ⚠️ 中文名必须是 percent-encoded 的，这里要解码，否则中文图 100% 404
        return super().translate_path(unquote(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    ap.add_argument('--publish', action='store_true')
    ap.add_argument('--port', type=int, default=8899)
    a = ap.parse_args()

    site = pathlib.Path(a.site).expanduser().resolve()
    root = site / ('_publish_tmp' if a.publish else 'portfolio')
    if not (root / 'index.html').exists():
        print('!! %s 下没有 index.html —— 先跑 build.py（--publish 则先跑 sync_publish.py）' % root)
        return 1

    handler = functools.partial(Handler, directory=str(root))
    with socketserver.TCPServer(('127.0.0.1', a.port), handler) as httpd:
        url = 'http://127.0.0.1:%d/' % a.port
        print('预览：%s' % url)
        print('目录：%s' % root)
        print('Ctrl+C 停止')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n已停止')
    return 0


if __name__ == '__main__':
    sys.exit(main())
