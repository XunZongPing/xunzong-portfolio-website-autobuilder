# -*- coding: utf-8 -*-
"""起后台，并且确认它真的起来了。

    python scripts/open_admin.py --site D:/sites/lisi
    python scripts/open_admin.py --site D:/sites/lisi --port 8850 --no-browser
    python scripts/open_admin.py --site D:/sites/lisi --foreground   # agent / 托管会话用
    python scripts/open_admin.py --site D:/sites/lisi --stop         # 收掉自己起的那个

两种启动方式，按环境选：

  * **默认（detach）**：新开一个控制台跑服务，脚本立刻返回。给「人坐在电脑前」用 ——
    用户能看见那个黑窗口，关掉窗口就是停服务。
  * **`--foreground`**：不脱离，脚本本身变成服务、阻塞到被停。给 **agent / 托管会话** 用。
    这类环境里父命令一结束就会级联回收子进程，detach 出去的后台会静默死亡
    （退出码 0x40010004，日志 0 字节），用户只看到「网页打不开」。

为什么需要这个脚本（而不是让用户双击启动脚本 bat / command）：
  * bat 是给「用户自己在资源管理器里点」的场景写的，agent/CLI 里点不了；
  * 双击之后失败了，用户只能看到一个闪掉的窗口，不知道错在哪；
  * 建站流程的最后一步本来就是「改内容」，把后台直接拉起来才叫跑完。

它和 bat 做同一件事，但多两点：
  1. 找不到解释器时**报清楚**，不静默失败；
  2. 起来之后**轮询端口直到真能连上**，再开浏览器 —— 固定 sleep 一定会偶发失败。
"""
import argparse
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

sys.stdout.reconfigure(encoding='utf-8')

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_PORT = 8848


def ping(port, timeout=1.2):
    """能连上就返回 /api/health 的 JSON，连不上返回 None。

    用 /api/health 而不是 /api/ping：后者要跑 env_check（起子进程验 Pillow 和生成器），
    冷启动时一两秒才回，短超时轮询会把它当成「没起来」。
    """
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/health' % port,
                                    timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception:
        return None


def port_open(port, timeout=0.35):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


def free_port(start, tries=20):
    for p in range(start, start + tries):
        if not port_open(p):
            return p
    return None


def read_state(admin):
    f = admin / '.admin.json'
    if f.exists():
        try:
            return json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def pid_cmdline(pid):
    """拿进程命令行，用来确认「这个 pid 到底是不是我们的 server.py」。

    Windows 的 pid 会复用，而 `.admin.json` 是持久文件、跨会话保留 ——
    直接 taskkill 一个旧 pid，可能杀掉一个完全无关的进程（还带 /T 连坐子进程）。
    wmic 在新版 Windows 已被移除，所以先用 PowerShell 的 CIM，再退回 wmic。
    """
    if os.name != 'nt':
        try:
            return pathlib.Path('/proc/%d/cmdline' % pid).read_bytes().decode('utf-8', 'replace')
        except Exception:
            return None
    probes = [
        ['powershell', '-NoProfile', '-NonInteractive', '-Command',
         "(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine" % pid],
        ['wmic', 'process', 'where', 'processid=%d' % pid, 'get', 'commandline'],
    ]
    for cmd in probes:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=15)
        except Exception:
            continue
        lines = [ln.strip() for ln in (r.stdout or '').splitlines() if ln.strip()]
        lines = [ln for ln in lines if ln.lower() != 'commandline']   # 去掉 wmic 的表头
        if lines:
            return ' '.join(lines)
    return None


def stop(site):
    admin = site / 'admin'
    st = read_state(admin)
    pid = st.get('pid')
    port = st.get('port') or DEFAULT_PORT

    # 先看端口上跑的还是不是本站 —— 这是「服务真在这儿」的活证据
    info = ping(port)
    mine = False
    if info and info.get('ok'):
        try:
            mine = pathlib.Path(info.get('base') or '').resolve() == site
        except Exception:
            mine = False
        # 服务重启过：health 里的 pid 才是现行 pid，state 里的是旧的
        if mine and info.get('pid') and info.get('pid') != pid:
            pid = info.get('pid')
        # 记录丢了（换电脑 / 手动删过）但服务确实在跑，用 health 的 pid 兜底
        if mine and not pid:
            pid = info.get('pid')

    if not pid:
        print('没有本脚本启动过的后台记录（admin/.admin.json 不存在或没写 pid）。')
        print('如果是双击启动脚本（bat / command）起的，关掉那个窗口即可。')
        return 0

    # pid 可能已被系统分配给别的程序 —— 杀之前必须验身份
    if not mine:
        cmd = pid_cmdline(pid) or ''
        if 'server.py' not in cmd:
            print('记录的 pid %s 已不属于本站后台，跳过杀进程。' % pid)
            if cmd:
                print('  它现在是：%s' % cmd[:120])
            else:
                print('  查不到这个 pid 的命令行（进程可能已退出）。')
            (admin / '.admin.json').unlink(missing_ok=True)
            return 1

    if os.name == 'nt':
        # taskkill 的中文提示是 GBK，用 text=True 会按 UTF-8 解码炸掉 —— 直接丢掉输出
        r = subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                           capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        ok = r.returncode == 0
    else:
        try:
            os.kill(pid, 15)
            ok = True
        except Exception:
            ok = False
    (admin / '.admin.json').unlink(missing_ok=True)
    print(('已停止 pid %s' % pid) if ok else ('pid %s 可能已经不在了' % pid))
    return 0


def run_foreground(site, admin, server_py, a):
    """前台起服务：不 detach，一直阻塞到被外部停止。

    为什么必须有这个模式 —— agent / 托管会话里，父命令一结束，运行环境会**级联回收**
    子进程：默认 detach 出去的后台会悄无声息地死掉（典型退出码 0x40010004，
    即 DBG_TERMINATE_PROCESS；日志还是 0 字节），用户只看到「网页打不开」。
    这种环境只能由调用方持有进程，所以这里不退场，把 server.py 跑在当前进程里。
    """
    port = a.port
    if port_open(port):
        info = ping(port)
        same = False
        if info and info.get('ok'):
            try:
                same = pathlib.Path(info.get('base') or '').resolve() == site
            except Exception:
                same = False
        if same:
            print('后台已经在跑了：http://127.0.0.1:%d/（pid %s）' % (port, info.get('pid')))
            if not a.no_browser:
                webbrowser.open('http://127.0.0.1:%d/' % port)
            return 0
        port = free_port(port + 1)
        if port is None:
            print('✗ %d 起连续 20 个端口都被占用，没法启动' % a.port)
            return 2
        print('端口 %d 被别的程序占着，前台改用 %d' % (a.port, port))

    os.environ['SITE_PORT'] = str(port)
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    (admin / '.admin.json').write_text(
        json.dumps({'pid': os.getpid(), 'port': port, 'mode': 'foreground',
                    'at': time.strftime('%Y-%m-%d %H:%M:%S')},
                   ensure_ascii=False, indent=1), encoding='utf-8')

    url = 'http://127.0.0.1:%d/' % port
    print('后台前台运行中 → %s' % url)
    print('  pid %s ｜ 这个进程要由调用方持有，停了后台就没了' % os.getpid())
    print('  收工：Ctrl+C，或另开一个终端 open_admin.py --stop')
    sys.stdout.flush()
    if not a.no_browser:
        webbrowser.open(url)

    os.chdir(str(admin))
    import runpy
    try:
        runpy.run_path(str(server_py), run_name='__main__')
    except KeyboardInterrupt:
        pass
    finally:
        (admin / '.admin.json').unlink(missing_ok=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True, help='站点根目录（含 admin/ portfolio/）')
    ap.add_argument('--port', type=int, default=int(os.environ.get('SITE_PORT') or DEFAULT_PORT))
    ap.add_argument('--python', default=os.environ.get('SITE_PY') or sys.executable,
                    help='跑 server.py 的解释器，缺省用当前解释器')
    ap.add_argument('--no-browser', action='store_true', help='只起服务，不开浏览器')
    ap.add_argument('--hidden', action='store_true',
                    help='Windows 下不开独立控制台窗口（后台进程脱离终端）')
    ap.add_argument('--timeout', type=float, default=25.0, help='等端口监听的上限秒数')
    ap.add_argument('--stop', action='store_true', help='停掉本脚本之前起的后台')
    ap.add_argument('--foreground', action='store_true',
                    help='前台运行，不脱离父进程（agent / 托管会话用：进程由调用方持有）')
    a = ap.parse_args()

    site = pathlib.Path(a.site).expanduser().resolve()
    admin = site / 'admin'
    server_py = admin / 'server.py'
    if not server_py.exists():
        print('✗ 找不到 %s —— 站点还没建？先跑 setup_site.py' % server_py)
        return 2

    if a.stop:
        return stop(site)

    if a.foreground:
        return run_foreground(site, admin, server_py, a)

    # ---------- 1. 已经在跑了吗 ----------
    # 只看「有没有响应」不够：另一个站点的后台也可能蹲在 8848 上。
    # /api/health 带了 base，比一比路径才知道是不是同一个站。
    info = ping(a.port)
    same = False
    if info and info.get('ok'):
        try:
            same = pathlib.Path(info.get('base') or '').resolve() == site
        except Exception:
            same = False
        if same:
            print('后台已经在跑了：http://127.0.0.1:%d/（pid %s）' % (a.port, info.get('pid')))
            (admin / '.admin.json').write_text(
                json.dumps({'pid': info.get('pid'), 'port': a.port,
                            'at': time.strftime('%Y-%m-%d %H:%M:%S')},
                           ensure_ascii=False, indent=1), encoding='utf-8')
            if not a.no_browser:
                webbrowser.open('http://127.0.0.1:%d/' % a.port)
            return 0
        print('端口 %d 上跑的是别的站（%s），换一个端口起本站在后台'
              % (a.port, info.get('label') or info.get('base') or '未知'))

    # 端口被别的东西占了（不是我们的后台）→ 换一个，别去抢
    port = a.port
    if port_open(port):
        port = free_port(port + 1)
        if port is None:
            print('✗ %d 起连续 20 个端口都被占用，没法启动' % a.port)
            return 2
        print('端口 %d 被别的程序占着，改用 %d' % (a.port, port))

    # ---------- 2. 解释器自检 ----------
    py = a.python
    if not py or not pathlib.Path(py).exists():
        py = sys.executable
    chk = subprocess.run([py, '-c', 'import http.server'], capture_output=True)
    if chk.returncode != 0:
        print('✗ 这个解释器跑不了 http.server：%s' % py)
        print('  用 --python 指定一个真的 python.exe，或设 SITE_PY')
        return 2

    # ---------- 3. 起进程 ----------
    # 日志名带端口：同站两个后台（不同端口）共用 server.log 会互相锁住，
    # 后起的那个连重定向都打不开，表现就是「起了但立刻没了」。
    log = admin / ('server-%d.log' % port)
    env = dict(os.environ)
    env['SITE_PORT'] = str(port)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'

    kwargs = dict(cwd=str(admin), env=env, stdin=subprocess.DEVNULL)
    logf = open(log, 'w', encoding='utf-8', errors='replace')
    kwargs['stdout'] = logf
    kwargs['stderr'] = subprocess.STDOUT
    if os.name == 'nt':
        # CREATE_NEW_CONSOLE：用户能看见那个黑窗口，关掉窗口=停止后台（和 bat 一致）。
        # CREATE_NO_WINDOW 则完全没窗口，用户找不到怎么停，所以不做默认。
        flags = 0x00000010 if not a.hidden else 0x00000008
        flags |= 0x00000200  # CREATE_NEW_PROCESS_GROUP
        kwargs['creationflags'] = flags
    else:
        kwargs['start_new_session'] = True

    proc = subprocess.Popen([py, str(server_py)], **kwargs)

    # ---------- 4. 等它真的在听 ----------
    t0 = time.time()
    ready = False
    while time.time() - t0 < a.timeout:
        if proc.poll() is not None:
            break
        if ping(port, timeout=0.8):
            ready = True
            break
        time.sleep(0.25)
    logf.close()

    url = 'http://127.0.0.1:%d/' % port
    if not ready:
        print('✗ 后台没起来（等了 %.0fs）。' % (time.time() - t0))
        rc = proc.poll()
        if rc not in (None, 0):
            print('  进程已退出，返回码 %s。server.log 最后几行：' % rc)
            try:
                tail = log.read_text(encoding='utf-8', errors='replace').strip().splitlines()
                for ln in tail[-12:]:
                    print('  | ' + ln)
            except Exception:
                pass
            if rc == 3:
                print('  返回码 3 = 端口被占用。换端口：--port %d' % (port + 1))
        else:
            print('  进程还活着但端口没监听 —— 多半是卡在启动自检。看 %s' % log)
        return 1

    (admin / '.admin.json').write_text(
        json.dumps({'pid': proc.pid, 'port': port, 'at': time.strftime('%Y-%m-%d %H:%M:%S')},
                   ensure_ascii=False, indent=1), encoding='utf-8')

    print('后台已启动 → %s' % url)
    print('  pid %s ｜ 日志 %s' % (proc.pid, log.name))
    print('  改完内容点「生成网页」；要停掉：--stop 或关掉那个黑窗口')

    if not a.no_browser:
        webbrowser.open(url)
    return 0


if __name__ == '__main__':
    sys.exit(main())
