# -*- coding: utf-8 -*-
"""建站最后一步：出发布物 + 体检 + 打包（单文件 HTML / zip）+ GitHub Pages 目录。

    python scripts/deploy_site.py --site D:/sites/lisi              # 交互问你要哪种打包
    python scripts/deploy_site.py --site D:/sites/lisi --pack html  # 单个 HTML，双击就开
    python scripts/deploy_site.py --site D:/sites/lisi --pack zip   # 压缩包，可部署可解压
    python scripts/deploy_site.py --site D:/sites/lisi --pack both
    python scripts/deploy_site.py --site D:/sites/lisi --github     # 额外备好 gh-pages 仓库

⚠️ 默认**不上线**。准备发布物和真正发布是两件事：
   这个脚本只出文件、只在 --push 且已配好 remote 时才碰远程。
"""
import argparse
import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

sys.stdout.reconfigure(encoding='utf-8')

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from packrules import is_junk        # 打包规范：和技能发行包共用同一份判定  # noqa: E402


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', **kw)


def slugify(s):
    s = re.sub(r'[^\w\u4e00-\u9fa5-]+', '-', (s or 'portfolio')).strip('-')
    return s.lower() or 'portfolio'


def site_name(site):
    try:
        d = json.loads((site / 'portfolio' / 'data.json').read_text(encoding='utf-8'))
        return ((d.get('site') or {}).get('brand') or
                (d.get('hero') or {}).get('name') or site.name)
    except Exception:
        return site.name


def make_zip(src, dst):
    """打包发布副本。

    按 `packrules.py` 的规范剔掉「多余的文件」：`_bak/`、探针页（`_selftest` 等）、
    `*.log`、`.admin.json`、`__pycache__`、`.DS_Store`… 这些是运行留下的，跟网站无关，
    跟着包发给别人只会让人看不懂。剔掉的数量会打出来，不作静默处理。
    """
    n, skipped = 0, []
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(src.rglob('*')):
            if not f.is_file():
                continue
            rel = f.relative_to(src).as_posix()
            if is_junk(rel):
                skipped.append(rel)
                continue
            z.write(f, rel)
            n += 1
    if skipped:
        print('      跳过 %d 个运行残留（不进交付包）：%s'
              % (len(skipped), '、'.join(skipped[:4]) + ('…' if len(skipped) > 4 else '')))
    return n, dst.stat().st_size


def choose_pack():
    """交互选打包方式。非交互（被 agent 调用）时默认两个都给，用户自己挑。"""
    if not sys.stdin.isatty():
        return 'both'
    print()
    print('  产出什么？')
    print('    1) 单个 HTML  —— 所有图片内联，双击就开，适合发微信 / 邮件')
    print('    2) 压缩包     —— 解压或直接拖去托管平台，适合部署')
    print('    3) 两个都要')
    try:
        s = (input('  选 [默认 3]: ') or '3').strip()
    except EOFError:
        print('  （没有输入环境，两个都出；要指定用 --pack html|zip）')
        return 'both'
    return {'1': 'html', '2': 'zip', '3': 'both'}.get(s, 'both')


def prep_github(src, dst, name):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    # .nojekyll 必须加：GitHub Pages 默认跑 Jekyll，会把下划线开头的目录吞掉
    (dst / '.nojekyll').write_text('', encoding='utf-8')
    (dst / 'README.md').write_text(
        '# %s\n\n个人作品集（静态站，无构建依赖）。\n\n'
        '## 发布\n\n'
        '### A. 全程浏览器（不用装 git）\n\n'
        '1. 在 https://github.com/new 新建一个空仓库（不要勾 README / .gitignore）。\n'
        '2. 点 `Add file → Upload files`，把**本目录**整个文件夹拖进上传区\n'
        '   （网页上传会保留目录结构；`.nojekyll` 不能漏）。\n'
        '3. 仓库 Settings → Pages → Source 选 `Deploy from a branch`，\n'
        '   分支 `main`、目录 `/ (root)`，Save。\n'
        '4. 等约 1 分钟，地址是 `https://<用户名>.github.io/<仓库名>/`。\n\n'
        '### B. 命令行（会用 git 时更快）\n\n'
        '1. 在 GitHub 新建一个空仓库（不要勾选 README / .gitignore）。\n'
        '2. 本目录下执行：\n\n'
        '   ```\n'
        '   git init -b main\n'
        '   git add -A\n'
        '   git commit -m "site: first publish"\n'
        '   git remote add origin https://github.com/<用户名>/<仓库名>.git\n'
        '   git push -u origin main\n'
        '   ```\n\n'
        '3. 仓库 Settings → Pages → Source 选 `Deploy from a branch`，\n'
        '   分支 `main`、目录 `/ (root)`，Save。\n'
        '4. 等约 1 分钟，地址是 `https://<用户名>.github.io/<仓库名>/`。\n\n'
        '> 更新内容：回到站点目录重新生成，再按 A（网页拖新文件覆盖）或\n'
        '> B（`deploy_site.py --github --push`）更新一次。\n'
        '> 想绑自己的域名（www.你的域名.com）：技能包 `references/custom-domain.md`\n'
        '> 有一步一步指引（Cloudflare + GitHub Pages，域名成本之外零费用）。\n'
        % name, encoding='utf-8')
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    ap.add_argument('--pack', choices=['ask', 'html', 'zip', 'both'], default='ask',
                    help='产出形式：单文件 HTML / zip / 都要（默认 ask＝交互问）')
    ap.add_argument('--github', action='store_true', help='额外备好可 push 的 gh-pages 仓库目录')
    ap.add_argument('--push', action='store_true', help='真的推送到 origin（需要已配好 git 身份与 remote）')
    ap.add_argument('--out', help='产物放哪（默认 <site>/_deploy）')
    a = ap.parse_args()

    site = pathlib.Path(a.site).expanduser().resolve()
    if not (site / 'portfolio' / 'index.html').exists():
        raise SystemExit('还没有 index.html，先跑 scripts/build.py --site "%s"' % site)

    out = pathlib.Path(a.out).expanduser().resolve() if a.out else site / '_deploy'
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d')
    name = site_name(site)
    slug = slugify(name)
    made = []

    # ---------- 1. 发布副本 ----------
    print('[1/4] 同步发布副本')
    r = run([sys.executable, str(HERE / 'sync_publish.py'), '--site', str(site)])
    print('\n'.join('      ' + x for x in (r.stdout or '').strip().splitlines()[-4:]))
    if r.returncode != 0:
        print((r.stderr or '')[:600])
        raise SystemExit('同步失败')

    # ---------- 2. 体检 ----------
    print('[2/4] 体检（按引用清单全量核）')
    r = run([sys.executable, str(HERE / 'check_site.py'), '--site', str(site), '--publish'])
    print('\n'.join('      ' + x for x in (r.stdout or '').strip().splitlines()[-4:]))
    if r.returncode != 0:
        print('      ! 体检没过，先修缺失，别急着发')
        raise SystemExit('体检未通过')

    pub = site / '_publish_tmp'
    files = [f for f in pub.rglob('*') if f.is_file()]
    print('      %d 个文件，%.1f MB'
          % (len(files), sum(f.stat().st_size for f in files) / 1024.0 / 1024.0))

    # ---------- 3. 打包 ----------
    pack = choose_pack() if a.pack == 'ask' else a.pack
    print('[3/4] 打包（%s）' % {'html': '单文件 HTML', 'zip': '压缩包',
                                'both': '单文件 + 压缩包'}[pack])
    if pack in ('html', 'both'):
        import importlib.util
        spec = importlib.util.spec_from_file_location('pack_single', str(HERE / 'pack_single.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        f, n, miss = mod.bundle(site, out / ('%s-%s.html' % (slug, stamp)), quiet=True)
        print('      %d 个资源内联，%.1f MB%s'
              % (n, f.stat().st_size / 1024.0 / 1024.0, '' if not miss else '，%d 个引用缺失' % len(miss)))
        made.append(('单文件 HTML', f))
    if pack in ('zip', 'both'):
        dst = out / ('%s-%s.zip' % (slug, stamp))
        n, b = make_zip(pub, dst)
        print('      %d 个文件，%.1f MB' % (n, b / 1024.0 / 1024.0))
        made.append(('压缩包', dst))

    # ---------- 4. GitHub Pages ----------
    if a.github:
        print('[4/4] 备好 GitHub Pages 目录')
        gh = prep_github(pub, out / 'gh-pages', name)
        print('      %s' % gh)
        if a.push:
            if not run(['git', 'remote', '-v'], cwd=str(gh)).stdout.strip():
                print('      ! 没有 origin，先按下面的第 3 步配一下远程')
                a.push = False
            else:
                steps = [['git', 'add', '-A'],
                         ['git', 'commit', '-m', 'site: publish %s' % stamp]]
                if not (gh / '.git').exists():
                    steps.insert(0, ['git', 'init', '-b', 'main'])
                for cmd in steps:
                    q = run(cmd, cwd=str(gh))
                    if q.returncode != 0 and 'nothing to commit' not in (q.stdout + q.stderr):
                        print('      ! %s 失败：%s' % (' '.join(cmd), (q.stderr or q.stdout)[:200]))
                        a.push = False
                        break
                if a.push:
                    q = run(['git', 'push', '-u', 'origin', 'main'], cwd=str(gh))
                    print('      推送%s' % ('成功' if q.returncode == 0
                                          else '失败：' + (q.stderr or q.stdout)[:200]))
        made.append(('gh-pages 目录', gh))
    else:
        print('[4/4] 跳过 GitHub Pages（加 --github 才生成）')

    # ---------- 交付清单 ----------
    print()
    print('=' * 58)
    print('产物')
    print('=' * 58)
    for label, p in made:
        print('  · %-13s %s' % (label, p))

    fmt = {
        'html': '把 `%s` 发给用户：双击就能开，图片全在里面，不用解压也不用起服务。' % (
            made[0][1].name if made else ''),
        'zip':  '把 zip 发给用户：解压后双击 index.html 也能看；要放到托管平台就直接拖这个包。',
        'both': '单文件发给「只想看看」的人；zip 留给「要部署 / 要自己改」的人。',
    }[pack]
    print()
    print(fmt)

    # ---------- GitHub 流程（把「我能自动」和「你要手动」分开写） ----------
    print()
    print('=' * 58)
    print('GitHub Pages 发布流程（git 命令版）')
    print('=' * 58)
    print('[自动] ① 生成发布目录（本脚本已做）：%s' % (out / 'gh-pages'))
    print('[自动] ② 写 .nojekyll（不加的话下划线目录会被 Jekyll 吞掉）')
    print('[手动] ③ 在 https://github.com/new 建一个空仓库')
    print('         不要勾 README / .gitignore / license，名字随意')
    print('[自动] ④ git init / add / commit —— 我能直接跑')
    print('[自动] ⑤ git remote add origin <仓库地址> —— 把地址给我，我来加')
    print('[自动] ⑥ git push -u origin main —— 首次推公开仓库需要你的 GitHub 授权')
    print('[手动] ⑦ 仓库 Settings → Pages → Source: Deploy from a branch')
    print('         分支选 main，目录选 / (root)，点 Save')
    print('[等待] ⑧ 约 1 分钟，地址 https://<用户名>.github.io/<仓库名>/')
    print('[手动] ⑨ 想绑自己的域名：见 references/custom-domain.md（一步一步指引）')
    print()
    print('  不想碰命令行？GitHub 网页版做同样的事（全程浏览器）：')
    print('[手动] a. https://github.com/new 建空仓库（不勾 README）')
    print('[手动] b. Add file → Upload files，把 gh-pages/ 文件夹整个拖进上传区')
    print('[手动] c. Settings → Pages → Deploy from a branch，main / (root) → Save')
    print('[等待] d. 约 1 分钟 → https://<用户名>.github.io/<仓库名>/')
    print('         更新：重新生成后把新文件拖上去覆盖，或用 --github --push')
    print()
    print('  也就是说：网页版全程你点；git 版只有 ③⑦⑨ 只能你做，其余我都能代劳。')
    print('  把仓库地址发我，`--github --push` 一次就能推上去。')
    print()
    print('  其它几条路：')
    print('  · WorkBuddy 网页端：在 WorkBuddy 对话里说「发布上线」，平台托管、给在线链接，最省事')
    print('  · Netlify Drop：把 zip 或 `_publish_tmp` 拖到 https://app.netlify.com/drop，零配置')
    print('  · 自有服务器：`_publish_tmp` 里的文件全量覆盖上去，纯静态、无后端')
    print()
    print('  想用自己的域名（www.你的域名.com）：Cloudflare + GitHub Pages 零成本方案，')
    print('  跟着 references/custom-domain.md 一步步来。')
    print()
    print('注意：到这里为止只是**备好了发布物**，域名和仓库都还没动。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
