# -*- coding: utf-8 -*-
"""data.json 体检：形状对不对，错了该改哪一行。

生成器是「边遍历边解包」的写法 —— `for a, b in it['pages']` 这种一旦写错形状，
用户看到的是 `ValueError: not enough values to unpack`，既不知道是哪个文件、也不知道改什么。
这个脚本在生成之前把形状全过一遍，用人话指出「哪个键、第几条、应该长什么样」。

两种用法：
  1. 被 gen_site.py import：生成前自动跑一遍，有错就不生成（后台点「生成网页」也走这条路）。
  2. 自己跑：python build/validate_data.py --site D:/sites/lisi [--strict]

这个文件必须和 gen_site.py 放在同一个目录（建站时一起拷过去）。
"""
import argparse
import json
import pathlib
import re
import sys

BLOCK_TYPES = ('work', 'photo', 'papers', 'opeds', 'design', 'proposals',
               'projects', 'about', 'contact', 'digital')
OPTIONAL = ('digital', 'papers', 'opeds', 'design', 'proposals')
THEME_MODES = ('system', 'light', 'dark', 'time')

# 设计物料单格的版式。**真源是 site.css 里的 `.dz-t.xxx{aspect-ratio:…}`**，
# 这里只是把它的键列出来做校验 —— 加版式要两边一起改，否则数据写了却渲染成默认比例。
# 曾经漏了 ssq / sflag 两个，真实站点的数据被判「不认识」，白跑一趟。
#   tall  不限高，按图片原比例（默认，CSS 里没有规则）
#   s16   16:9      stall 1130:1600 竖长     ssq 1:1      sflag 1445:334 横幅
DZ_SHAPES = (None, '', 'tall', 's16', 'stall', 'ssq', 'sflag')

ERR, WARN = [], []
_hhmm = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
_hex6 = re.compile(r'^#[0-9a-fA-F]{6}$')


def err(where, msg, fix=''):
    ERR.append((where, msg, fix))


def warn(where, msg, fix=''):
    WARN.append((where, msg, fix))


def kind(v):
    """给人看的类型名。"""
    if isinstance(v, dict):
        return '对象'
    if isinstance(v, list):
        return '数组'
    if isinstance(v, str):
        return '字符串'
    if isinstance(v, bool):
        return '布尔'
    if isinstance(v, (int, float)):
        return '数字'
    if v is None:
        return 'null'
    return type(v).__name__


def want_dict(d, key, where, required=False):
    if key not in d:
        if required:
            err(where, '缺 %r 这个键' % key, '补成对象，例如 "%s": {}' % key)
        return None
    v = d[key]
    if not isinstance(v, dict):
        err('%s.%s' % (where, key), '应该是对象，现在是%s' % kind(v))
        return None
    return v


def want_list(d, key, where, required=False):
    if key not in d:
        if required:
            err(where, '缺 %r 这个键' % key, '补成数组，例如 "%s": []' % key)
        return None
    v = d[key]
    if not isinstance(v, list):
        err('%s.%s' % (where, key), '应该是数组，现在是%s' % kind(v),
            '写成 [ ... ]，哪怕暂时是空的')
        return None
    return v


def want_str(d, key, where, required=False):
    if key not in d:
        if required:
            err(where, '缺 %r' % key)
        return None
    v = d[key]
    if v is None:
        return None
    if not isinstance(v, str):
        warn('%s.%s' % (where, key), '建议写字符串，现在是%s（生成器会 str() 它）' % kind(v))
    return v


def pairs(rows, where, width, item_hint, must=False):
    """校验 [值, 说明] 这类定宽数组。width 可以是 int 或 (最小, 最大)。"""
    if rows is None:
        return
    if not isinstance(rows, list):
        err(where, '应该是数组，现在是%s' % kind(rows), '每行写成 %s' % item_hint)
        return
    lo, hi = (width, width) if isinstance(width, int) else width
    for i, row in enumerate(rows):
        if not isinstance(row, (list, tuple)):
            err('%s[%d]' % (where, i), '应该是数组（%s），现在是%s' % (item_hint, kind(row)))
            continue
        if not (lo <= len(row) <= hi):
            want = ('%d 项' % lo) if lo == hi else ('%d~%d 项' % (lo, hi))
            err('%s[%d]' % (where, i), '有 %d 项，应该是 %s —— %s' % (len(row), want, item_hint))
        elif must and not str(row[0] or '').strip():
            warn('%s[%d][0]' % (where, i), '第一项是空的（一般要写标题/数值）')


def check_hero(d):
    h = want_dict(d, 'hero', 'data', required=True)
    if not h:
        return
    for k in ('kick', 'name', 'en', 'tagline'):
        want_str(h, k, 'hero')
    pairs(h.get('stats'), 'hero.stats', 2, '[数值, 说明]')
    pairs(h.get('hm'), 'hero.hm', 2, '[标签, 内容]')


def check_work(d):
    w = want_dict(d, 'work', 'data', required=True)
    if not w:
        return
    want_str(w, 'sub', 'work')
    groups = want_list(w, 'groups', 'work')
    for gi, g in enumerate(groups or []):
        wp = 'work.groups[%d]' % gi
        if not isinstance(g, dict):
            err(wp, '应该是对象', '{"name": ..., "items": [...]}')
            continue
        for k in ('name', 'en', 'type', 'sub'):
            if k in g and not isinstance(g[k], str):
                warn('%s.%s' % (wp, k), '建议写字符串，现在是%s' % kind(g[k]))
        items = want_list(g, 'items', wp)
        for ii, it in enumerate(items or []):
            ip = '%s.items[%d]' % (wp, ii)
            if not isinstance(it, dict):
                err(ip, '应该是对象（一张作品卡）')
                continue
            if not it.get('title'):
                warn(ip, '没有 title，卡片会没有标题')
            if 'duty' in it and not isinstance(it['duty'], list):
                err(ip + '.duty', '应该是职务名数组，例如 ["策划", "摄影师"]')
            for si, sub in enumerate(it.get('subs') or []):
                if not isinstance(sub, dict):
                    err('%s.subs[%d]' % (ip, si), '应该是对象（子卡）')


def check_photo(d):
    p = want_dict(d, 'photo', 'data', required=True)
    if not p:
        return
    cats = want_list(p, 'cats', 'photo')
    seen = set()
    for i, c in enumerate(cats or []):
        cp = 'photo.cats[%d]' % i
        if not isinstance(c, (list, tuple)):
            err(cp, '应该是数组 [分类key, 中文名, 英文名, 张数, 简介?]，现在是%s' % kind(c))
            continue
        if not (4 <= len(c) <= 5):
            err(cp, '有 %d 项，应该是 4 或 5 项 —— [key, 中文名, 英文名, 张数, 简介?]' % len(c))
            continue
        key = str(c[0] or '')
        if not key:
            err(cp + '[0]', '分类 key 不能为空（它就是图片文件名前缀）')
        elif key in seen:
            err(cp + '[0]', '分类 key %r 重复了，图片会互相覆盖' % key)
        seen.add(key)
        try:
            n = int(c[3])
            if n <= 0:
                warn(cp + '[3]', '张数是 %d，这一分类不会显示' % n)
        except (TypeError, ValueError):
            err(cp + '[3]', '张数要是整数，现在是 %r' % (c[3],))

    # 摄影图的引用是拼出来的，抽一次看文件在不在（这一项只在 --site 下做，见 main）
    return seen


def check_projects(d):
    p = want_dict(d, 'projects', 'data')
    if not p:
        return
    for gi, g in enumerate(want_list(p, 'groups', 'projects') or []):
        gp = 'projects.groups[%d]' % gi
        if not isinstance(g, dict):
            err(gp, '应该是对象 {"name": ..., "items": [...]}')
            continue
        for ii, it in enumerate(want_list(g, 'items', gp) or []):
            ip = '%s.items[%d]' % (gp, ii)
            if not isinstance(it, dict):
                err(ip, '应该是对象（一个项目）')
                continue
            if not it.get('title'):
                warn(ip, '没有 title')
            pairs(it.get('metrics'), ip + '.metrics', 2, '[数值, 说明]')
            pairs(it.get('shots'), ip + '.shots', 2, '[图片路径, 图注]')


def check_text_blocks(d):
    """papers / opeds / design / proposals —— 这四类的形状最容易写错。"""
    pap = want_dict(d, 'papers', 'data')
    if pap:
        for i, it in enumerate(want_list(pap, 'items', 'papers') or []):
            ip = 'papers.items[%d]' % i
            if not isinstance(it, dict):
                err(ip, '应该是对象（一篇论文）')
                continue
            if not it.get('title'):
                err(ip, '缺 title（卡片标题）', '补 "title": "论文标题"')
            pairs(it.get('pages'), ip + '.pages', 2, '[图片路径, 说明]')
            pairs(it.get('metrics'), ip + '.metrics', 2, '[数值, 说明]')
            if 'points' in it and not isinstance(it['points'], list):
                err(ip + '.points', '应该是字符串数组（每行一条要点）')

    opd = want_dict(d, 'opeds', 'data')
    if opd:
        for i, it in enumerate(want_list(opd, 'items', 'opeds') or []):
            ip = 'opeds.items[%d]' % i
            if not isinstance(it, dict):
                err(ip, '应该是对象（一篇评论）')
                continue
            if not it.get('title'):
                err(ip, '缺 title')

    dz = want_dict(d, 'design', 'data')
    if dz:
        for i, pj in enumerate(want_list(dz, 'projects', 'design') or []):
            pp = 'design.projects[%d]' % i
            if not isinstance(pj, dict):
                err(pp, '应该是对象（一套物料）')
                continue
            if not pj.get('title'):
                warn(pp, '没有 title')
            pairs(pj.get('specs'), pp + '.specs', 2, '[数值, 说明]')
            if 'groups' in pj and not isinstance(pj['groups'], list):
                err(pp + '.groups', '应该是数组（每组一套网格）')
                continue
            for gi, g in enumerate(pj.get('groups') or []):
                gp = '%s.groups[%d]' % (pp, gi)
                if not isinstance(g, dict):
                    err(gp, '应该是对象 {"name": ..., "items": [[图, 图注, 版式], ...]}')
                    continue
                for ii, row in enumerate(g.get('items') or []):
                    rp = '%s.items[%d]' % (gp, ii)
                    if not isinstance(row, (list, tuple)):
                        err(rp, '应该是数组 [图片路径, 图注, 版式]，现在是%s' % kind(row))
                        continue
                    if len(row) != 3:
                        err(rp, '有 %d 项，应该是 3 项 —— [图片路径, 图注, 版式]' % len(row))
                    elif row[2] not in DZ_SHAPES:
                        warn(rp + '[2]', '版式 %r 不认识（可用 %s / 留空）'
                             % (row[2], ' / '.join(x for x in DZ_SHAPES if x)))
                if g.get('wide'):
                    pairs([g['wide']], gp + '.wide', 2, '[图片路径, 图注]')

    prp = want_dict(d, 'proposals', 'data')
    if prp:
        for i, it in enumerate(want_list(prp, 'items', 'proposals') or []):
            ip = 'proposals.items[%d]' % i
            if not isinstance(it, dict):
                err(ip, '应该是对象（一个提案）')
                continue
            if not it.get('title'):
                warn(ip, '没有 title')
            pairs(it.get('left'), ip + '.left', 2, '[标题, 说明]')
            pairs(it.get('right'), ip + '.right', 2, '[标题, 说明]')


def check_about(d):
    a = want_dict(d, 'about', 'data', required=True)
    if not a:
        return
    pairs(a.get('facts'), 'about.facts', 2, '[标签, 内容]')
    for i, b in enumerate(want_list(a, 'blocks', 'about') or []):
        bp = 'about.blocks[%d]' % i
        if not isinstance(b, dict):
            err(bp, '应该是对象（一个内容块）')
            continue
        for k in ('ps', 'ds', 'awards', 'dsum', 'rows'):
            if k in b and not isinstance(b[k], list):
                err('%s.%s' % (bp, k), '应该是数组（现在%s）' % kind(b[k]))


def check_awards(d):
    aw = want_dict(d, 'awards', 'data')
    if not aw:
        return
    for title, rows in aw.items():
        wp = 'awards[%r]' % title
        if not isinstance(rows, (list, tuple)):
            err(wp, '应该是数组，每项 [奖项, 年份/说明, 奖状图路径?]')
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, (list, tuple)):
                err('%s[%d]' % (wp, i), '应该是数组')
            elif len(row) not in (2, 3):
                err('%s[%d]' % (wp, i), '有 %d 项，应该是 2 或 3 项' % len(row))


def check_contact(d):
    c = want_dict(d, 'contact', 'data', required=True)
    if not c:
        return
    for k in ('kick', 'h2', 'sub'):
        want_str(c, k, 'contact')
    pairs(c.get('big'), 'contact.big', 2, '[显示文字, 链接 tel:/mailto:]')
    pairs(c.get('plinks'), 'contact.plinks', 2, '[平台名, 链接]')


def check_site(d):
    s = want_dict(d, 'site', 'data')
    if not s:
        return
    for k in ('brand', 'brand_en', 'owner', 'title', 'desc', 'logo', 'avatar'):
        want_str(s, k, 'site')

    th = want_dict(s, 'theme', 'site')
    if th:
        mode = th.get('mode')
        if mode is not None and mode not in THEME_MODES:
            err('site.theme.mode', '%r 不认识（可用 %s）' % (mode, ' / '.join(THEME_MODES)))
        for k in ('darkAt', 'lightAt'):
            v = th.get(k)
            if v is None:
                continue
            if not isinstance(v, str) or not _hhmm.match(v):
                err('site.theme.' + k, '%r 不是 HH:MM（例如 "19:00"）' % (v,))
        # 主题色会被原样拼进 CSS 变量（--acc:#xxxxxx）。写错一个字符不是「颜色不对」，
        # 是整段变量声明失效 —— 按钮、阴影、背景柔光一起掉回浏览器默认，看不出是哪儿出的问题。
        acc = th.get('accent')
        if acc is not None:
            if not isinstance(acc, str) or not _hex6.match(acc):
                err('site.theme.accent',
                    '%r 不是 #rrggbb 颜色（例如 "#e0651c"，也可以写成 "e0651c"）' % (acc,),
                    '留空则用默认蓝 #2f6bff；后台「网站配色 → 主题色」里点一个色块就会写进这一项')

    pages = want_list(s, 'pages', 'site')
    if pages is None:
        return
    seen_block, seen_id = {}, set()
    for i, pg in enumerate(pages):
        pp = 'site.pages[%d]' % i
        if not isinstance(pg, dict):
            err(pp, '应该是对象（一个页面）')
            continue
        pid = pg.get('id')
        if pid:
            if pid in seen_id:
                err(pp + '.id', '页面 id %r 重复了，锚点会撞车' % pid)
            seen_id.add(pid)
        for k in ('nav', 'title', 'titleEn', 'intro'):
            if k in pg and pg[k] is not None and not isinstance(pg[k], str):
                warn('%s.%s' % (pp, k), '建议写字符串，现在是%s' % kind(pg[k]))
        blocks = want_list(pg, 'blocks', pp)
        for bi, b in enumerate(blocks or []):
            bp = '%s.blocks[%d]' % (pp, bi)
            if not isinstance(b, dict):
                err(bp, '应该是对象 {"type": "work"}')
                continue
            t = b.get('type')
            if t not in BLOCK_TYPES:
                err(bp + '.type', '%r 不是已知板块（可用 %s）' % (t, ' / '.join(BLOCK_TYPES)))
                continue
            if t in seen_block:
                err(bp + '.type', '「%s」已经挂在 %s 了 —— 一种内容只能挂在一页上' % (t, seen_block[t]),
                    '把这里删掉，或者把那一页的那块挪过来')
            else:
                seen_block[t] = pp
            if t in OPTIONAL and t not in d:
                warn(bp + '.type', 'data.json 里没有 %r 键，这一块不会渲染（整页会被跳过）' % t)


def check_types(d):
    for k in ('site', 'hero', 'work', 'photo', 'about', 'contact'):
        if k in d and not isinstance(d[k], dict):
            err('data.' + k, '应该是对象，现在是%s' % kind(d[k]))
    for k in ('footer', 'navcta'):
        if k in d and not isinstance(d[k], str):
            warn('data.' + k, '建议写字符串，现在是%s' % kind(d[k]))
    if 'stars' in d and not isinstance(d['stars'], list):
        err('data.stars', '应该是标题数组，例如 ["作品标题", ...]')


def check_photo_files(d, site):
    """只有拿到站点目录才能核文件：摄影图路径是拼出来的，最常见的一类「裂图」来源。"""
    p = d.get('photo') or {}
    pf = site / 'portfolio'
    for i, c in enumerate(p.get('cats') or []):
        if not isinstance(c, (list, tuple)) or len(c) < 4:
            continue
        key = str(c[0] or '')
        try:
            n = int(c[3])
        except (TypeError, ValueError):
            continue
        missing = []
        for j in range(1, n + 1):
            f = pf / 'assets' / 'photo2' / ('%s_%02d.jpg' % (key, j))
            if not f.exists():
                missing.append(f.name)
        if missing:
            warn('photo.cats[%d]' % i,
                 '%d 张图不存在（%s%s）' % (len(missing), '、'.join(missing[:3]),
                                        '…' if len(missing) > 3 else ''),
                 '把图放进 assets/photo2/，文件名必须是 <分类key>_01.jpg … _%02d.jpg；'
                 '或者把张数改成实际张数' % n)


def run(d, site=None):
    """跑全套检查，返回 (错误, 提醒)。每次调用都重置，可以反复用。"""
    global ERR, WARN
    ERR, WARN = [], []
    if not isinstance(d, dict):
        err('data', '顶层应该是对象 {}，现在是%s' % kind(d))
        return ERR, WARN
    check_types(d)
    check_site(d)
    check_hero(d)
    check_work(d)
    check_photo(d)
    check_projects(d)
    check_text_blocks(d)
    check_about(d)
    check_awards(d)
    check_contact(d)
    if site is not None:
        check_photo_files(d, pathlib.Path(site))
    return ERR, WARN


def report(errs, warns, prefix='  '):
    """把结果拼成人话（生成器和 CLI 共用同一套措辞）。"""
    lines = []
    for where, msg, fix in warns:
        lines.append('%s[提醒] %s：%s' % (prefix, where, msg))
        if fix:
            lines.append('%s       → %s' % (prefix, fix))
    for where, msg, fix in errs:
        lines.append('%s[错误] %s：%s' % (prefix, where, msg))
        if fix:
            lines.append('%s       → %s' % (prefix, fix))
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', help='站点根目录（读 <site>/portfolio/data.json）')
    ap.add_argument('--data', help='直接给 data.json 的路径')
    ap.add_argument('--strict', action='store_true', help='警告也算不通过')
    a = ap.parse_args()

    site = None
    if a.site:
        site = pathlib.Path(a.site).expanduser().resolve()
        path = site / 'portfolio' / 'data.json'
    elif a.data:
        path = pathlib.Path(a.data).expanduser().resolve()
        site = path.parent.parent if path.parent.name == 'portfolio' else None
    else:
        ap.error('要么 --site，要么 --data')

    if not path.exists():
        print('读不到 %s' % path)
        return 2
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print('data.json 不是合法 JSON：第 %d 行第 %d 列 —— %s' % (e.lineno, e.colno, e.msg))
        print('多半是少了个逗号 / 多了个逗号 / 字符串没闭合。改完再跑一次。')
        return 2
    if not isinstance(d, dict):
        print('data.json 顶层应该是对象 {}，现在是%s' % kind(d))
        return 1

    errs, warns = run(d, site)

    print('检查 %s' % path)
    for where, msg, fix in warns:
        print('  [提醒] %s：%s%s' % (where, msg, ('\n         → ' + fix) if fix else ''))
    for where, msg, fix in errs:
        print('  [错误] %s：%s%s' % (where, msg, ('\n         → ' + fix) if fix else ''))
    if errs:
        print('\n%d 个错误 —— 先改这些，生成器才能跑通。' % len(errs))
        return 1
    if a.strict and warns:
        print('\n%d 个提醒（--strict 当错误处理）。' % len(warns))
        return 1
    print('\n通过：%d 个提醒，0 个错误。' % len(warns))
    return 0


if __name__ == '__main__':
    sys.exit(main())
