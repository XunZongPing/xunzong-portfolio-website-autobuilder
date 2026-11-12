# -*- coding: utf-8 -*-
"""液态玻璃作品集 · 建站第一步：读简历 → 生成站点骨架 + 初始 data.json + 起后台。

    python scripts/setup_site.py --out D:/sites/lisi --resume D:/简历.docx
    python scripts/setup_site.py --out D:/sites/lisi --resume 简历.txt --brand "四时记录" --brand-en SISHI
    python scripts/setup_site.py --out D:/sites/lisi --resume 简历.docx --dry-run
    python scripts/setup_site.py --out D:/sites/lisi --demo          # 先看版式，内容以后换
    python scripts/setup_site.py --out D:/sites/lisi --demo --no-admin   # 只建站，不起后台

它只干三件事：把简历读成纯文本、抽出能自动认出来的字段、把站点建起来，
**最后直接把后台拉起来**（`open_admin.py`，起来并确认端口真在听才开浏览器）。
**不编造内容** —— 认不出来的（一句话介绍、经历、作品）一律留空，交给后面用后台填。

产出：
    <out>/portfolio/data.json        唯一真源
    <out>/_setup/resume.txt          简历抽出来的纯文本（方便对着填）
    <out>/_setup/profile.json        自动认出来的字段（可手改后重跑 --profile）
    <out>/admin/.admin.json          后台进程 pid / 端口（`open_admin.py --stop` 用）
"""
import argparse
import html
import json
import os
import pathlib
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
DEMO_DATA = SKILL / 'examples' / 'demo-data.json'

EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
PHONE = re.compile(r'(?<!\d)(1[3-9]\d{9})(?!\d)')
NAME_KV = re.compile(r'(?:姓\s*名|Name)\s*[:：]\s*([^\s,，。;；|]{2,12})')
SCHOOL = re.compile(r'([\u4e00-\u9fa5]{2,18}(?:大学|学院|学校|中学))|([A-Z][A-Za-z. ]{3,40}(?:University|College))')
MAJOR = re.compile(r'(?:专\s*业|主\s修|Major)\s*[:：]\s*([^\s,，。;；|]{2,20})')
YEAR = re.compile(r'(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)')
# 「起—止」成对才算时间跨度。只认单个年份会把出生年（1998）当成入学年。
SPAN = re.compile(r'(19[89]\d|20[0-4]\d)\s*[-—–~至]{1,2}\s*'
                  r'(19[89]\d|20[0-4]\d|至今|现在|今|present)', re.I)

CITIES = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '南京', '西安', '重庆',
          '苏州', '长沙', '厦门', '青岛', '天津', '郑州', '合肥', '福州', '昆明', '大连',
          '宁波', '无锡', '佛山', '东莞', '济南', '沈阳', '哈尔滨', '长春', '石家庄',
          '南昌', '贵阳', '南宁', '太原', '兰州', '海口', '乌鲁木齐', '呼和浩特', '银川', '西宁']


# ---------- 读文件 ----------
def docx_text(p):
    """docx 就是 zip + xml，标准库足够，不必装 python-docx。

    ⚠️ 去标签之前必须先把图形块**整块删掉**：`<wp:align>right</wp:align>`、
    `<wp:posOffset>0</wp:posOffset>` 这些值都是**文本节点**，去标签法会把它原样留在正文里 ——
    带浮动头像的简历首行会变成「right0张三」，姓名就抽不出来了（会误抓到下一行的「影像制作」）。
    国内简历基本都带头像，所以这条不是边角情况。
    """
    import zipfile
    with zipfile.ZipFile(p) as z:
        xml = z.read('word/document.xml').decode('utf-8', 'ignore')
    for tag in ('w:drawing', 'w:pict', 'mc:AlternateContent', 'w:txbxContent'):
        xml = re.sub(r'<%s\b[^>]*>.*?</%s>' % (tag, tag), '', xml, flags=re.S)
    xml = xml.replace('</w:p>', '\n').replace('<w:br/>', '\n')
    xml = re.sub(r'<w:tab/>', '  ', xml)      # 制表符 → 两个空格，别让「2022—2026江州传媒学院」粘成一行
    return html.unescape(re.sub(r'<[^>]+>', '', xml))


def pdf_text(p):
    for mod in ('pypdf', 'PyPDF2'):
        try:
            M = __import__(mod)
            Reader = getattr(M, 'PdfReader')
            return '\n'.join((pg.extract_text() or '') for pg in Reader(str(p)).pages)
        except ImportError:
            continue
        except Exception as e:
            raise SystemExit('PDF 解析失败（%s）。建议先在 Word 里另存为 .docx 再试' % e)
    raise SystemExit('读 PDF 需要 pypdf：pip install pypdf\n'
                     '懒得装就把简历另存成 .docx 或 .txt，格式一样能读')


def read_any(p):
    p = pathlib.Path(p).expanduser().resolve()
    if not p.exists():
        raise SystemExit('找不到简历：%s' % p)
    s = p.suffix.lower()
    if s == '.docx':
        t = docx_text(p)
    elif s == '.pdf':
        t = pdf_text(p)
    elif s in ('.txt', '.md', '.markdown', '.json'):
        raw = p.read_bytes()
        for enc in ('utf-8-sig', 'utf-8', 'utf-16', 'gbk'):
            try:
                t = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise SystemExit('这个文件编码认不出来，另存成 UTF-8 再试')
        if s == '.json':
            try:
                d = json.loads(t)
                # 已经是 profile 就直接用，别再猜
                return t, d
            except Exception:
                pass
    elif s == '.doc':
        raise SystemExit('旧版 .doc 读不了，用 Word 另存为 .docx')
    else:
        raise SystemExit('不支持的文件类型：%s（要 .docx / .pdf / .txt / .md / .json）' % s)
    return t, None


# ---------- 抽字段 ----------
def clean_lines(text):
    out = []
    for ln in text.splitlines():
        ln = re.sub(r'[\u3000\xa0]+', ' ', ln).strip(' ·•-—|')
        if ln:
            out.append(ln)
    return out


def guess_name(lines, text):
    m = NAME_KV.search(text)
    if m:
        return m.group(1).strip()
    # 简历第一屏通常是「张三」或「张三 | 男 | 1999」，取最靠前的纯中文短行
    for ln in lines[:12]:
        cand = re.split(r'\s*[|｜/·,，]\s*', ln)[0].strip()
        if re.fullmatch(r'[\u4e00-\u9fa5]{2,4}', cand) and cand not in CITIES:
            return cand
    return ''


def guess_region(text):
    for c in CITIES:
        if c in text:
            return c
    return ''


def guess_years(lines, school=''):
    """只认成对的时间段，且优先取院校那一行的（多个时间段混在一起会把工作时间算进「在校」）。"""
    def span_of(ls):
        spans = SPAN.findall('\n'.join(ls))
        if not spans:
            return ''
        starts = [int(s) for s, _ in spans]
        ends = [int(e) for _, e in spans if e.isdigit()]
        return '%d—%d' % (min(starts), max(ends)) if ends else '%d—至今' % min(starts)

    edu = [ln for ln in lines if school and school in ln]
    return span_of(edu) or span_of(lines)


def guess_major(lines, school):
    """「专业」经常没写标签，而是跟在院校名后面同一行：2016—2020  浙大  广播电视学  本科"""
    m = MAJOR.search('\n'.join(lines))
    if m:
        return m.group(1).strip()
    for ln in lines:
        if school and school in ln:
            parts = [x.strip() for x in re.split(r'\s{2,}|\t|｜|\|', ln) if x.strip()]
            if len(parts) >= 2:
                for p in parts[parts.index(school) + 1:]:
                    if re.fullmatch(r'[\u4e00-\u9fa5]{2,10}', p) and '本科' not in p and '硕士' not in p:
                        return p
    return ''


def guess_tagline(lines):
    """找「自我评价 / 个人简介 / 关于我」那一段的第一句，找不到就留空。"""
    keys = ('自我评价', '个人简介', '自我介绍', '关于我', '个人陈述')
    for i, ln in enumerate(lines):
        if any(k in ln for k in keys):
            for nxt in lines[i + 1:i + 4]:
                if len(nxt) >= 12 and not nxt.endswith('：'):
                    return nxt[:120]
    return ''


def build_profile(text):
    lines = clean_lines(text)
    name = guess_name(lines, text)
    email = (EMAIL.search(text).group(0) if EMAIL.search(text) else '')
    phone = (PHONE.search(text).group(1) if PHONE.search(text) else '')
    school_m = SCHOOL.search(text)
    school = (school_m.group(1) or school_m.group(2)) if school_m else ''
    major = guess_major(lines, school)
    city = guess_region(text)
    years = guess_years(lines, school)
    tagline = guess_tagline(lines)

    facts = [['姓名', name], ['坐标', city], ['学校', school], ['专业', major]]
    facts = [f for f in facts if f[1]]
    if years:
        facts.append(['在校时间', years])

    contact = []
    if email:
        contact.append([email, 'mailto:' + email])
    if phone:
        contact.append([phone, 'tel:' + phone])

    return {
        'name': name, 'email': email, 'phone': phone, 'city': city,
        'school': school, 'major': major, 'years': years, 'tagline': tagline,
        'facts': facts, 'contact': contact,
        'lines': len(lines),
    }


def to_site_profile(g):
    """抽出来的字段 → new_site.py 认的 profile 结构（只放非空值，别把骨架默认值冲掉）。"""
    prof = {'hero': {}, 'about': {}, 'site': {}}
    if g['name']:
        prof['hero']['name'] = g['name']
        prof['site']['owner'] = g['name']
    if g['tagline']:
        prof['hero']['tagline'] = g['tagline']
    if g['facts']:
        prof['about']['facts'] = g['facts']
    if g['contact']:
        prof['about']['contact'] = g['contact']
        # 联系那一屏是大号链接，显示文本用值本身；about 里那一行是「标签 | 链接」的表格
        prof['contact'] = {'big': [[t + ' ↗', h] for t, h in g['contact']]}
    return {k: v for k, v in prof.items() if v}


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='站点根目录')
    ap.add_argument('--resume', help='简历文件（.docx / .pdf / .txt / .md / .json）')
    ap.add_argument('--demo', action='store_true',
                    help='先用虚构 Demo 数据建站，只看版式；内容以后在后台换')
    ap.add_argument('--name', help='本人姓名（简历里认不出来时手动给）')
    ap.add_argument('--brand', help='站名 / 首屏大标题，留空用姓名')
    ap.add_argument('--brand-en', dest='brand_en', help='站名英文')
    ap.add_argument('--tagline', help='一句话介绍，覆盖从简历里抽到的那句')
    ap.add_argument('--dry-run', action='store_true', help='只打印抽到的字段，不建站')
    ap.add_argument('--no-build', action='store_true', help='只建骨架，不生成网页')
    ap.add_argument('--no-admin', action='store_true',
                    help='不自动起后台（默认建完就起来，省得用户再去找 bat）')
    ap.add_argument('--no-browser', action='store_true', help='起后台但不开浏览器')
    ap.add_argument('--port', type=int, default=0, help='后台端口，缺省 8848 起自动找空位')
    ap.add_argument('--force', action='store_true', help='允许写进非空目录')
    a = ap.parse_args()

    out = pathlib.Path(a.out).expanduser().resolve()
    setup_dir = out / '_setup'

    # ---------- 1. 简历 ----------
    print('[1/5] 读简历')
    guess = None
    raw_text = ''
    if a.demo:
        if not DEMO_DATA.exists():
            raise SystemExit('找不到 Demo 数据：%s' % DEMO_DATA)
        print('      跳过简历（--demo）：用虚构人物「陈屿」的数据先把版式立起来')
    elif a.resume:
        raw_text, pre = read_any(a.resume)
        if pre is not None:
            guess = None
            print('      %s 本身就是 profile，直接用' % pathlib.Path(a.resume).name)
        else:
            guess = build_profile(raw_text)
            print('      %s → %d 行，认出 %s'
                  % (pathlib.Path(a.resume).name, guess['lines'],
                     '、'.join(k for k in ('name', 'email', 'phone', 'city', 'school', 'major', 'years')
                               if guess.get(k)) or '（没认出结构化字段）'))
        if raw_text and not a.dry_run:
            setup_dir.mkdir(parents=True, exist_ok=True)
            (setup_dir / 'resume.txt').write_text(raw_text, encoding='utf-8')
    else:
        print('      没给 --resume，按空白骨架建站（内容后面在后台填）')

    if guess:
        print('      姓名 %s ｜ 城市 %s ｜ 学校 %s ｜ 专业 %s ｜ 时间 %s'
              % (guess['name'] or '—', guess['city'] or '—', guess['school'] or '—',
                 guess['major'] or '—', guess['years'] or '—'))

    # ---------- 2. 组装 profile ----------
    prof = to_site_profile(guess) if guess else {}
    if a.name:
        prof.setdefault('hero', {})['name'] = a.name
        prof.setdefault('site', {})['owner'] = a.name
    if a.tagline:
        prof.setdefault('hero', {})['tagline'] = a.tagline
    if a.brand:
        prof.setdefault('site', {})['brand'] = a.brand
    if a.brand_en:
        prof.setdefault('site', {})['brand_en'] = a.brand_en

    if a.dry_run:
        print()
        print(json.dumps(prof, ensure_ascii=False, indent=2))
        print('\n（--dry-run：没有写任何文件）')
        return 0

    # ---------- 3. 建站 ----------
    print('[2/5] 建站目录')
    cmd = [sys.executable, str(HERE / 'new_site.py'), '--out', str(out)]
    if a.demo:
        cmd += ['--data', str(DEMO_DATA)]
    else:
        setup_dir.mkdir(parents=True, exist_ok=True)
        pf = setup_dir / 'profile.json'
        pf.write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding='utf-8')
        cmd += ['--profile', str(pf)]
        print('      初始字段：%s' % pf)
    if a.force:
        cmd.append('--force')
    elif out.is_dir() and [p.name for p in out.iterdir()] == ['_setup']:
        # 目录里只有我们自己刚写的 _setup/，不算「用户的东西」，放行
        cmd.append('--force')
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print((r.stdout or '') + (r.stderr or ''))
        raise SystemExit('建站失败')
    for ln in (r.stdout or '').strip().splitlines():
        print('      ' + ln)

    # ---------- 4. 首次生成 ----------
    print('[3/5] 首次生成网页')
    if a.no_build:
        print('      跳过（--no-build）')
    else:
        r = subprocess.run([sys.executable, str(HERE / 'build.py'), '--site', str(out), '--check'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        tail = (r.stdout or '').strip().splitlines()[-6:]
        for ln in tail:
            print('      ' + ln)
        if r.returncode != 0:
            print((r.stderr or '').strip()[:600])
            print('      ! 生成没过，但站点骨架已经在了，改完内容再跑一次 build.py')

    # ---------- 5. 直接把后台拉起来 ----------
    # 建站流程到这里，用户唯一要做的事就是「改内容」，所以后台必须已经在跑。
    # 让他再去找启动脚本双击，等于把「跑完」的活儿又推回给他。
    print('[4/5] 启动后台')
    url = 'http://127.0.0.1:8848/'
    launcher = out / 'admin' / ('start-admin.bat' if os.name == 'nt' else 'start-admin.command')
    if a.no_admin:
        print('      跳过（--no-admin）。需要时双击 %s' % launcher)
    else:
        cmd = [sys.executable, str(HERE / 'open_admin.py'), '--site', str(out),
               '--python', sys.executable]
        if a.port:
            cmd += ['--port', str(a.port)]
        if a.no_browser:
            cmd.append('--no-browser')
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        for ln in (r.stdout or '').strip().splitlines():
            print('      ' + ln)
        if r.returncode != 0:
            print('      ! 后台没起来，但站点已经建好了 —— 双击 %s 手动开' % launcher)
        else:
            for ln in (r.stdout or '').splitlines():
                if 'http://127.0.0.1:' in ln:
                    url = ln.split('http://')[1].split()[0]
                    url = 'http://' + url
                    break

    # [5/5] 是脚本内部的最后一步，不是工作流的最后一步。脚本只管到「后台已经在跑」，
    # 后面的改内容 / 补图 / 打包得由调用方接着走 —— 所以这里必须把下一步指向工作流的编号，
    # 否则读到 [5/5] 就会以为「齐活了」，把占位图和没打包的目录直接交付出去。
    print('[5/5] 后台已在跑 —— 脚本到这里结束，工作流还剩三步')
    print('      ③ 改内容：%s  → 第一页是「总设置」' % url)
    print('        预览：%s' % (out / 'portfolio' / 'index.html'))
    print('        验收：把 portfolio/index.html 发给用户看（不要用截图代替）')
    print('      ④ 补图片：assets 下小于 45KB 的基本都是占位图，按 SKILL.md「④」的顺序补')
    print('      ⑤ 打包：python scripts/deploy_site.py --site "%s" --pack ask' % out)
    if guess and not guess['tagline']:
        print()
        print('  提示：简历里没找到「一句话介绍」，首屏那句现在是骨架里的占位文案，')
        print('        在后台「封面」里改掉，或重跑时加 --tagline "……"')
    return 0


if __name__ == '__main__':
    sys.exit(main())
