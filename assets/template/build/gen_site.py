# -*- coding: utf-8 -*-
"""液态玻璃作品集 · 站点生成器。

读 <站点根>/portfolio/data.json → 写 <站点根>/portfolio/index.html

站点根（BASE）解析顺序：
  1) 环境变量 SITE_BASE
  2) 本文件上两级目录（<BASE>/build/gen_site.py）
所以把本脚本放在 <任意站点>/build/ 下即可直接跑，无需改代码。
"""
import pathlib, json, html as H
import os as _os

# 主题配色（主色 → 整套色板）。和本文件同目录，建站时由 scripts/new_site.py 一起拷过来。
# 拆成独立模块的原因：后台也要用同一份预设和同一套推导（/api/palette），
# 两边各写一份必然会漂 —— 后台预览的橙色和网页上的橙色对不上，是这类功能最常见的坏味。
import palette

BASE = pathlib.Path(
    _os.environ.get('SITE_BASE')
    or pathlib.Path(__file__).resolve().parents[1]
)
# 唯一真源 = portfolio/data.json（后台直接读写它）。
_SRC = BASE / 'portfolio/data.json'
if not _SRC.exists():
    raise SystemExit('找不到 %s —— 站点还没初始化，先跑 scripts/new_site.py' % _SRC)
D = json.loads(_SRC.read_text(encoding='utf-8'))
OUT = BASE / 'portfolio/index.html'

# ---- 先体检形状，再动手渲染 ----------------------------------------------------
# 形状不对时生成器自己的报错是 `ValueError: not enough values to unpack`，
# 说不清是哪个键、第几条。validate_data.py 就在同目录，报错能指到 data.json 的具体位置。
# 留一个 SITE_SKIP_VALIDATE=1 的后门：极少数「校验误报但数据其实没错」时能强行出站。
if _os.environ.get('SITE_SKIP_VALIDATE') != '1':
    try:
        import validate_data as _vd
    except ImportError:
        _vd = None          # 老站点没拷这个文件：跳过体检，别挡着人家生成
    if _vd is not None:
        _errs, _warns = _vd.run(D, BASE)
        if _errs:
            print('data.json 有 %d 处形状错误，先改完再生成：' % len(_errs))
            print(_vd.report(_errs, _warns))
            raise SystemExit(1)
        if _warns:
            print('data.json 体检有 %d 条提醒（不影响生成）：' % len(_warns))
            print(_vd.report([], _warns))

# ---- 站点身份（可在 data.json 的 site 块里覆盖；缺省从 hero 推断，再退回通用值）----
_h = D.get('hero') or {}
SITE = D.get('site') or {}
OWNER = SITE.get('owner') or _h.get('name') or '我的'
BRAND = SITE.get('brand') or _h.get('brand') or OWNER
BRAND_EN = SITE.get('brand_en') or _h.get('brand_en') or str(_h.get('en') or '').upper()
TITLE = SITE.get('title') or '%s · %s作品集' % (BRAND, OWNER)
DESC = SITE.get('desc') or _h.get('tagline') or '个人作品集'

# 站点标识图：顶栏 mark 用 LOGO，首屏大头像用 AVATAR（两者可以不同）
LOGO = SITE.get('logo') or 'assets/hero/avatar.jpg'
AVATAR = SITE.get('avatar') or 'assets/hero/avatar.jpg'

# ---- 主题（浅色 / 深色 / 跟随系统 / 按时间）------------------------------------
# site.theme = {"mode":"system|light|dark|time", "darkAt":"19:00", "lightAt":"07:00"}
# 这里只是「访客第一次打开」的默认值。访客点顶栏那个太阳/月亮按钮可以自己覆盖，
# 覆盖结果存在他自己的 localStorage 里，不会写回 data.json。
_T = SITE.get('theme') or {}
# 缺 theme 键时的默认：**必须和 assets/data_skeleton.json、后台 themeCfg() 三处一致**。
# 以前这里是 system、骨架是 time、后台是 system —— 同一份缺数据三种答案，改一处罚处漏。
THEME_DEFAULT = {'mode': 'time', 'darkAt': '19:00', 'lightAt': '07:00',
                 'accent': palette.DEFAULT}
THEME = {
    'mode': _T.get('mode') if _T.get('mode') in ('system', 'light', 'dark', 'time') else THEME_DEFAULT['mode'],
    'darkAt': _T.get('darkAt') or THEME_DEFAULT['darkAt'],
    'lightAt': _T.get('lightAt') or THEME_DEFAULT['lightAt'],
    # 主题色：只存一个 #rrggbb，其余（深色档、柔光、透明阴影）都由 palette 推。
    # 认不出的值退回默认蓝，不在这里报错 —— 该报错的是 validate_data.py。
    'accent': palette.normalize(_T.get('accent')),
}

# ---- 页面 / 板块（两层模型）--------------------------------------------------
# site.pages 是一串页面，页面里挂板块：
#
#   {"id":"pg_work", "show":true, "nav":"影像",
#    "title":"影像作品", "titleEn":"Film & Video", "intro":"……",
#    "blocks":[{"type":"work", "title":"", "intro":""}]}
#
# · 页面 = 导航上的一项 + 一屏内容；板块 = 内容单元（影像 / 摄影 / 论文 …）
# · 一个页面挂一块：页面的标题/简介直接当这一块的大标题（= 老站点的样子）
# · 一个页面挂多块：页面出大标题，每块再出二级小节标题（.sec-head.blk）
# · 每种板块类型全站只出现一次 —— 内容仍存在 data.json 的顶层键里，不搬家，
#   所以渲染代码一行都不用改取数方式
# · 没写 site.pages 的老站：退回 site.sections（更老的站退回内置顺序）
BLOCK_TYPES = {
    'work':      ('影像作品', 'Film & Video'),
    'digital':   ('数码内容', 'Tech & Review'),
    'photo':     ('摄影', 'Photography'),
    'papers':    ('论文与研究', 'Research'),
    'opeds':     ('评论与随笔', 'Op-eds'),
    'design':    ('设计与物料', 'Design'),
    'proposals': ('问题与方案', 'Proposals'),
    'projects':  ('技术内容', 'Tech'),
    'about':     ('关于我', 'Self-Introduction'),
    'contact':   ('联系', 'Contact'),
}
# 导航短名：顶栏塞不下全称
NAV_LABEL = {
    'work': '影像', 'digital': '数码', 'photo': '摄影', 'papers': '论文',
    'opeds': '评论', 'design': '设计', 'proposals': '方案', 'projects': '图文',
    'about': '关于', 'contact': '联系',
}
_ORDER = ['work', 'digital', 'photo', 'papers', 'opeds', 'design',
          'proposals', 'projects', 'about', 'contact']
# 这几种是「有数据才出现」：data.json 里没这个键就跳过，免得导航挂空锚点
_OPTIONAL = ('digital', 'papers', 'opeds', 'design', 'proposals')


def _blk_default(key):
    return BLOCK_TYPES.get(key, ('', ''))


def _blk_title(key):
    """数据里写了 h2 就用 h2，否则用内置文案（论文这类是数据自己带的）"""
    return (D.get(key) or {}).get('h2') or _blk_default(key)[0]


def _blk_en(key):
    return (D.get(key) or {}).get('h2en') or _blk_default(key)[1]


def _blk_sub(key):
    return (D.get(key) or {}).get('sub') or ''


def _normalize_blocks(raw):
    """板块数组 → 干净的 [{type,title,intro}]。认不出的类型、重复的类型都丢掉。"""
    out, seen = [], set()
    for b in raw or []:
        t = b.get('type') if isinstance(b, dict) else b
        if t not in BLOCK_TYPES or t in seen:
            continue
        if t in _OPTIONAL and t not in D:
            continue        # 数据里没有这一块，配了也没内容
        seen.add(t)
        out.append({
            'type': t,
            'title': (b.get('title') or '').strip() if isinstance(b, dict) else '',
            'intro': (b.get('intro') or '').strip() if isinstance(b, dict) else '',
        })
    return out


def _legacy_pages():
    """老数据 migration：site.sections 一项 → 一个页面一块。"""
    raw = SITE.get('sections')
    if raw is None:
        keys = [k for k in _ORDER if not (k in _OPTIONAL and k not in D)]
        return [{'blocks': [{'type': k}], 'show': True} for k in keys]
    out, seen = [], set()
    for row in raw:
        if isinstance(row, str):
            key, show = row, True
        else:
            key, show = row.get('key'), row.get('show', True)
        if key not in BLOCK_TYPES or key in seen:
            continue
        if key in _OPTIONAL and key not in D:
            continue
        seen.add(key)
        out.append({'blocks': [{'type': key}], 'show': bool(show)})
    return out


def _resolve_pages():
    raw = SITE.get('pages')
    if not isinstance(raw, list):
        raw = _legacy_pages()
    pages = []
    for i, pg in enumerate(raw):
        if not isinstance(pg, dict):
            continue
        blocks = _normalize_blocks(pg.get('blocks'))
        if not blocks:
            # 空页面：没有内容就不该占一屏，也不该在导航上挂锚点
            continue
        head = blocks[0]['type']
        title = (pg.get('title') or '').strip() or _blk_title(head)
        pages.append({
            'id': pg.get('id') or 'pg%d' % (i + 1),
            'show': pg.get('show') is not False,
            'title': title,
            'titleEn': (pg.get('titleEn') or '').strip() or _blk_en(head),
            'nav': (pg.get('nav') or '').strip() or NAV_LABEL.get(head, title[:4]),
            'intro': pg['intro'] if pg.get('intro') is not None else pg.get('sub', _blk_sub(head)),
            'blocks': blocks,
        })
    return pages


PAGES = _resolve_pages()
VISIBLE_PAGES = [p for p in PAGES if p['show']]

# 板块 → 所属页面（渲染时要拿页面标题/简介兜底）
BLOCK_OF, PAGE_OF = {}, {}
for _pg in PAGES:
    for _b in _pg['blocks']:
        BLOCK_OF[_b['type']] = _b
        PAGE_OF[_b['type']] = _pg

# 老逻辑里「联系」既不进导航也不占序号，走右上 CTA。
# 锚点：一块的页面指向那一块（保持 #work / #photo 这些老锚点不变）；
# 多块的页面没有「那一块」，指向页面头。
def page_anchor(pg):
    return pg['id'] if len(pg['blocks']) > 1 else pg['blocks'][0]['type']


NAV_ITEMS = [[p['nav'], '#' + page_anchor(p)]
             for p in VISIBLE_PAGES if p['blocks'][0]['type'] != 'contact']
HAS_CONTACT = any(p['blocks'][0]['type'] == 'contact' for p in VISIBLE_PAGES)
NAV_CTA = D.get('navcta') or '联系合作'

E = lambda s: H.escape(str(s or ''), quote=True)


def is_multi(key):
    """这个板块所在的页面是不是挂了多块？多块才需要「页面大标题 + 板块小标题」两层。"""
    pg = PAGE_OF.get(key)
    return bool(pg) and len(pg['blocks']) > 1


def blk_text(key, dtitle='', den='', dsub=''):
    """板块标题 / 英文 / 简介的取值顺序：
       页面挂多块 → 板块自己的覆盖值 > 数据默认（页面标题只出现在页面头上）
       页面挂一块 → 页面标题 > 数据默认（页面就是这块，不该出现两个标题）"""
    b = BLOCK_OF.get(key) or {}
    pg = PAGE_OF.get(key) or {}
    multi = is_multi(key)
    title = b.get('title') or ('' if multi else (pg.get('title') or '')) or dtitle
    en = den if multi else ((pg.get('titleEn') or '') or den)
    sub = b.get('intro') or ('' if multi else (pg.get('intro') or '')) or dsub
    return title, en, sub


def sec_head(key, dtitle='', den='', extra=''):
    """分区/板块标题。@@N@@ 是序号占位，拼接时按最终顺序换汉字。"""
    title, en, _ = blk_text(key, dtitle, den)
    cls = 'sec-head fade blk' if is_multi(key) else 'sec-head fade'
    return ('<div class="%s"><span class="num">@@N@@</span><h2>%s</h2>'
            '<span class="sec-en">%s</span>%s</div>'
            % (cls, E(title), E(en), extra))


def sec_sub(key, dsub=''):
    """简介。空字符串就整行不输出 —— 少一个空行，标题和内容贴得更紧。"""
    _, _, sub = blk_text(key, dsub=dsub)
    return '<p class="sec-sub fade">%s</p>' % E(sub) if sub else ''

# 序号一律用汉字：阿拉伯数字跟站内的英文标签挤在一起很怪。
# 分区号按**实际渲染顺序**自增，所以数码内容整块下线时不会留下断号。
CN = '一二三四五六七八九十'
_secn = [0]


def secno():
    _secn[0] += 1
    return CN[min(_secn[0] - 1, len(CN) - 1)]


def cnnum(i):
    """阿拉伯序号 → 汉字。注意别叫 cn：摄影那两处循环的分类名变量就叫 cn"""
    return CN[min(i - 1, len(CN) - 1)] if i >= 1 else str(i)


# CSS 单独放在同目录的 site.css。1100 行样式塞进 Python 字符串有三个坏处：
# 改一行要照顾缩进和转义、diff 只告诉你「这个三引号块变了」、编辑器不给 CSS 高亮。
# 生成时读回来内联进 <style>，产物照样是单文件，离线分发不受影响。
# ⚠️ site.css 必须和 gen_site.py 放在同一个目录（new_site.py 建站时会一起拷过去）。
_CSS_PATH = pathlib.Path(__file__).resolve().parent / 'site.css'
if not _CSS_PATH.exists():
    raise SystemExit('缺 %s —— 它要和 gen_site.py 同目录（建站时被漏拷了）' % _CSS_PATH)
CSS = _CSS_PATH.read_text(encoding='utf-8')

# 主题引导脚本：内联在 <head> 里、样式表之前，先定 data-theme 再加载 CSS，夜里不会白闪。
# 访客手动切过（localStorage['pf-theme']）就听他的，否则按后台配的 mode 算一次。
THEME_BOOT = (
    "(function(){var c=%s;try{"
    "var u=localStorage.getItem('pf-theme');"
    "if(u==='light'||u==='dark'){document.documentElement.dataset.theme=u;"
    "document.documentElement.dataset.manual='1';}"
    "else{var f=function(s){var p=String(s||'').split(':');"
    "return ((+p[0])||0)*60+((+p[1])||0);},"
    "n=new Date(),m=n.getHours()*60+n.getMinutes(),"
    "a=f(c.darkAt),b=f(c.lightAt),d;"
    "if(c.mode==='dark')d=true;else if(c.mode==='light')d=false;"
    "else if(c.mode==='time')d=(a<=b)?(m>=a&&m<b):(m>=a||m<b);"
    "else d=!!(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);"
    "document.documentElement.dataset.theme=d?'dark':'light';}"
    "}catch(e){}window.__TH=c;})()"
) % json.dumps(THEME)

JS = r"""
/* 高亮当前所在的分区。类名只管颜色，读屏软件看不见 —— 所以同时挂 aria-current，
   否则键盘/读屏用户没有任何线索知道自己在第几屏。 */
function markCur(list, cur){
  list.forEach((a, i) => {
    const on = (typeof cur === 'function') ? cur(a, i) : i === cur;
    a.classList.toggle('on', on);
    if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
  });
}

/* 分类导航：滚动高亮 + 点击居中 */
document.querySelectorAll('[data-bar]').forEach(bar => {
  const links = [...bar.querySelectorAll('.cat')];
  links.forEach(a => a.addEventListener('click', () =>
    a.scrollIntoView({inline:'center', block:'nearest', behavior:'smooth'})));
  const obs = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    markCur(links, a => a.getAttribute('href') === '#' + e.target.id);
    const on = bar.querySelector('.cat.on');
    if (on) on.scrollIntoView({inline:'center', block:'nearest', behavior:'smooth'});
  }), {rootMargin:'-160px 0px -70% 0px', threshold:0});
  bar.closest('section').querySelectorAll('.grp').forEach(g => obs.observe(g));
});

/* 只看代表作：给分组预打标记（哪些组里有被标的卡），避免依赖 :has() */
const vfil = document.getElementById('vfil');
const wsec = document.getElementById('work');
if (vfil && wsec) {
  const grps = [...wsec.querySelectorAll('.grp')];
  grps.forEach(g => g.classList.toggle('on', !!g.querySelector('.vcard.star')));
  vfil.addEventListener('click', () => {
    const on = !vfil.classList.contains('on');
    vfil.classList.toggle('on', on);
    vfil.setAttribute('aria-pressed', on ? 'true' : 'false');
    wsec.classList.toggle('star-only', on);
    /* 是用户主动要看代表作的：直接补上入场类，
       否则刚好卡在观察器 8% 阈值边缘的那张会停在全透明 */
    if (on) wsec.querySelectorAll('.vcard.star').forEach(c => c.classList.add('in'));
  });
}

/* 顶栏 */
const nav = document.querySelector('.nav');
const links = [...document.querySelectorAll('.navlinks a')];
const secs = links.map(a => document.querySelector(a.getAttribute('href')));

/* 首屏那排标签栏：进场动画跑完后接管透明度，快钻到顶栏底下就淡出，
   否则顶栏玻璃会把它透出来，看着像两排导航 */
const hnav = document.querySelector('.heronav');
let hnavOwn = false;
function hnavFade(){
  if (!hnav || !hnavOwn) return;
  const gap = hnav.getBoundingClientRect().top - nav.getBoundingClientRect().bottom;
  const k = Math.max(0, Math.min(1, gap / 120));
  hnav.style.opacity = k.toFixed(3);
  hnav.style.transform = k < 1 ? 'translateY(' + ((k - 1) * 16).toFixed(1) + 'px)' : 'none';
  hnav.style.pointerEvents = k > .5 ? '' : 'none';
}

addEventListener('scroll', () => {
  nav.classList.toggle('scrolled', scrollY > 10);
  let cur = -1;
  secs.forEach((s, i) => { if (s && s.getBoundingClientRect().top <= 200) cur = i; });
  markCur(links, cur);
  hnavFade();
}, {passive:true});
/* 等首屏入场淡入跑完（.7s）再接管，免得抢掉入场动画 */
setTimeout(() => { if (hnav) { hnavOwn = true; hnav.style.transition = 'none'; hnavFade(); } }, 900);

/* 导航横滑：项目多、宽度不够时这一排自己左右滚（滚动条隐藏）。
   两侧渐隐只在「那边还有内容」时出现 —— 一直挂着渐隐的话，宽度够时最右边那项
   看着像被裁掉了。遮罩的边距由 --fl / --fr 控制，0 就是完全不淡。 */
const navLinks = document.getElementById('navLinks');
if (navLinks){
  const nfade = () => {
    const max = navLinks.scrollWidth - navLinks.clientWidth;
    const l = navLinks.scrollLeft > 2;
    const r = max > 2 && navLinks.scrollLeft < max - 2;
    navLinks.style.setProperty('--fl', l ? '26px' : '0px');
    navLinks.style.setProperty('--fr', r ? '26px' : '0px');
  };
  navLinks.addEventListener('scroll', nfade, {passive:true});
  addEventListener('resize', nfade, {passive:true});
  addEventListener('load', nfade);
  setTimeout(nfade, 600);            // 字体换完宽度会变，再量一次
  nfade();
}

/* 正片墙：按真实宽高比分行，行高自适应 → 每张完整展示、不裁切、填满整行 */
function layoutWall(){
  const GAP = innerWidth < 680 ? 8 : 12;
  document.querySelectorAll('.pwall').forEach(wall => {
    const W = wall.clientWidth;
    if (!W) return;
    const figs = [...wall.querySelectorAll('figure')];
    if (!figs.length) return;
    const H = W > 1000 ? 235 : W > 620 ? 175 : 128;      // 目标行高
    const rows = []; let cur = [], sum = 0;
    const hOf = n => (W - GAP * (n - 1)) / sum;
    figs.forEach(f => {
      cur.push(f); sum += parseFloat(f.dataset.r) || 1.5;
      const h = hOf(cur.length);
      if (h <= H || cur.length >= 6) { rows.push({items: cur, h: Math.min(h, H)}); cur = []; sum = 0; }
    });
    if (cur.length) rows.push({items: cur, h: Math.min(hOf(cur.length), H * 1.4)});
    const frag = document.createDocumentFragment();
    rows.forEach(row => {
      const d = document.createElement('div');
      d.className = 'prowx';
      d.style.height = row.h.toFixed(1) + 'px';
      row.items.forEach(f => {
        const r = parseFloat(f.dataset.r) || 1.5;
        f.style.width = (r * row.h).toFixed(1) + 'px';
        f.style.height = row.h.toFixed(1) + 'px';
        d.appendChild(f);
      });
      frag.appendChild(d);
    });
    wall.innerHTML = '';
    wall.appendChild(frag);
  });
}
layoutWall();

let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(layoutWall, 160); });

/* 摄影筛选 */
const pills = document.getElementById('pills'), pbox = document.getElementById('photos');
if (pills) pills.addEventListener('click', e => {
  const b = e.target.closest('.pill'); if (!b) return;
  pills.querySelectorAll('.pill').forEach(p => p.classList.toggle('on', p === b));
  const k = b.dataset.k;
  pbox.querySelectorAll('.pcat').forEach(c => c.classList.toggle('hide', k !== 'all' && c.dataset.cat !== k));
});

/* 灯箱 */
const lb = document.getElementById('lb'), lbimg = document.getElementById('lbimg'),
      lbbar = document.getElementById('lbbar'), lbtxt = document.getElementById('lbtxt'),
      lbfull = document.getElementById('lbfull');
let curIdx = -1, curList = [];
/* 放大状态：论文内页是 A4 正文，铺满 86vh 也只有半页看得清 —— 所以支持滚轮/双击放大、放大后拖着看。
   每次都从 1 倍、居中开始，翻到下一张时不会顶着上一张的缩放。 */
let zoom = 1, panX = 0, panY = 0;
/* 灯箱标了 aria-modal，就得真的像个模态框：打开时把焦点收进来，关掉时还回去。
   不然 Tab 会跑到背后那层看不见的页面上，焦点在哪完全没提示。 */
let lastFocus = null;
function applyZoom(){
  if (!lbimg) return;
  lbimg.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + zoom + ')';
  lbimg.classList.toggle('zoomed', zoom > 1.01);
}
function resetZoom(){ zoom = 1; panX = panY = 0; if (lbimg) applyZoom(); }
function show(){
  const it = curList[curIdx];
  lbimg.src = it.full; lbimg.alt = it.cap;
  if (lbfull) lbfull.href = it.full;
  lbtxt.innerHTML = curList.length > 1
    ? '<b>' + (curIdx + 1) + '</b> / ' + curList.length + ' &nbsp;·&nbsp; ' + it.cap
    : it.cap;                                   /* 单张（奖状）就不显示 1/1 */
  resetZoom();
  const wasOn = lb.classList.contains('on');
  lb.classList.add('on'); lbbar.classList.add('on');
  if (!wasOn){
    /* 只在「打开」这一次记来源，翻页时别覆盖掉 —— 否则关掉后焦点回到翻页按钮上 */
    lastFocus = document.activeElement;
    const c = document.getElementById('lbclose');
    if (c) c.focus({preventScroll: true});
  }
}
function closeLB(){
  lb.classList.remove('on'); lbbar.classList.remove('on');
  lbimg.src = ''; resetZoom();
  if (lastFocus && lastFocus.focus){
    lastFocus.focus({preventScroll: true});
    lastFocus = null;
  }
}
function step(d){ if (!curList.length) return; curIdx = (curIdx + d + curList.length) % curList.length; show(); }

/* 滚轮缩放（触控板的捏合会以 ctrlKey 的 wheel 出现，一并接住） */
lb.addEventListener('wheel', e => {
  if (!lb.classList.contains('on')) return;
  e.preventDefault();
  const k = e.deltaY < 0 ? 1.15 : 0.87;
  const next = Math.min(5, Math.max(1, zoom * k));
  if (next <= 1.01){ panX = panY = 0; zoom = 1; }
  else zoom = next;
  applyZoom();
}, {passive: false});
/* 双击：1 倍 ↔ 2.4 倍 */
lbimg.addEventListener('dblclick', e => {
  e.preventDefault();
  if (zoom > 1.01){ resetZoom(); } else { zoom = 2.4; applyZoom(); }
});
/* 放大后拖动看图（pointer 事件同时覆盖鼠标和手指） */
let drag = null;
lbimg.addEventListener('pointerdown', e => {
  if (zoom <= 1.01) return;
  drag = {x: e.clientX - panX, y: e.clientY - panY};
  lbimg.classList.add('dragging');
  try { lbimg.setPointerCapture(e.pointerId); } catch (err) {}
});
lbimg.addEventListener('pointermove', e => {
  if (!drag) return;
  panX = e.clientX - drag.x; panY = e.clientY - drag.y;
  applyZoom();
});
['pointerup', 'pointercancel'].forEach(t => lbimg.addEventListener(t, () => {
  drag = null; lbimg.classList.remove('dragging');
}));
document.addEventListener('click', e => {
  const aw = e.target.closest('.vaw[data-img]');        /* 奖状：单张进灯箱 */
  if (aw) {
    curList = [{full: aw.dataset.img, cap: aw.dataset.cap}];
    curIdx = 0; show();
    return;
  }
  const pjf = e.target.closest('.pjshot');       /* 项目档案：按卡片内图集翻页 */
  if (pjf) {
    const box = pjf.closest('.pjshots');
    curList = [...box.querySelectorAll('img')].map(im => ({full: im.dataset.full, cap: im.alt}));
    curIdx = [...box.querySelectorAll('.pjshot')].indexOf(pjf);
    show(); return;
  }
  /* 论文（封面 + 内页）、设计物料（同组网格）、随笔缩略图：点开就能放大。
     图集范围按「这张图所在的那一件作品」算 —— 论文里封面和内页能顺着翻，
     设计只在本组内翻（跨组翻会让人搞不清自己在看哪一套）。
     为什么用 closest 而不是判断 e.target：点到的往往是 img 或那行 <em> 图注，
     判断 e.target 会在点文字时失效（见 pitfalls 39）。 */
  const zi = e.target.closest('.pap-cv, .pap-pi, .dz-t, .opd-th');
  if (zi) {
    const scope = zi.closest('.pap') || zi.closest('.dz-grp') || zi;
    const ims = [...scope.querySelectorAll('img')].filter(im => im.getAttribute('src'));
    const me = zi.querySelector('img');
    if (ims.length && me) {
      curList = ims.map(im => ({full: im.dataset.full || im.getAttribute('src'),
                                cap: im.alt || ''}));
      curIdx = Math.max(0, ims.indexOf(me));
      show(); return;
    }
  }
  const fig = e.target.closest('.pcat figure');   /* 主图 + 拼图格子统一走灯箱 */
  if (fig) {
    const cat = fig.closest('.pcat');
    curList = [...cat.querySelectorAll('figure img')].map(im => ({full: im.dataset.full, cap: im.alt}));
    curIdx = [...cat.querySelectorAll('figure')].indexOf(fig);
    show();
  } else if (e.target === lb || e.target.id === 'lbclose') { closeLB(); }
  /* ⚠️ 别把 e.target === lbimg 也算成「点空白关闭」：图上现在要双击放大、拖动看图，
     点一下就把灯箱关掉的话，缩放根本没法用。 */
});
addEventListener('keydown', e => {
  if (e.key === 'Escape'){
    if (zoom > 1.01) resetZoom();      /* 先退回 1 倍，再按一次才关 */
    else closeLB();
    return;
  }
  if (!lb.classList.contains('on')) return;
  if (e.key === 'ArrowRight') step(1);
  if (e.key === 'ArrowLeft') step(-1);
  /* Tab 在灯箱里打转，别漏到背后那层页面上（aria-modal 的应有之义）。
     ⚠️ #lbbar 是 #lb 的兄弟节点（一个装图、一个装工具条），所以不能从 lb 里找 ——
     一开始写成 lb.querySelectorAll 就永远查不到，陷阱静默失效。 */
  if (e.key === 'Tab'){
    const f = ['lbfull', 'lbclose'].map(id => document.getElementById(id))
                                   .filter(el => el && el.getClientRects().length);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
  }
});

/* 项目档案：模糊底复用同一张图，不给 data URI 存两遍 */
document.querySelectorAll('.pjshot').forEach(f => {
  const im = f.querySelector('img'), b = f.querySelector('.pjsbg');
  if (b && im && im.src) b.style.backgroundImage = 'url("' + im.src + '")';
});

/* 入场 */
const io = new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
}), {threshold:.08, rootMargin:'0px 0px -40px 0px'});
document.querySelectorAll('.fade').forEach((el, i) => {
  el.style.transitionDelay = (i % 3) * 70 + 'ms'; io.observe(el);
});

/* ---------- 深浅色切换 ----------
   data-theme 在 <head> 里已经算好了，这里只管「点一下」和「到点自动切」。
   访客点过之后写 localStorage，从此不再自动切（否则他刚切成浅色，一分钟又被时间拽回深色）。 */
(function(){
  const root = document.documentElement;
  const cfg = window.__TH || {mode:'time', darkAt:'19:00', lightAt:'07:00'};
  const btn = document.getElementById('thBtn');
  const mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const tmin = s => { const p = String(s || '').split(':'); return ((+p[0]) || 0) * 60 + ((+p[1]) || 0); };
  function auto(){
    if (cfg.mode === 'dark') return true;
    if (cfg.mode === 'light') return false;
    if (cfg.mode === 'time'){
      const n = new Date(), m = n.getHours() * 60 + n.getMinutes();
      const a = tmin(cfg.darkAt), b = tmin(cfg.lightAt);
      return a <= b ? (m >= a && m < b) : (m >= a || m < b);
    }
    return !!(mq && mq.matches);
  }
  function paint(){
    const d = root.dataset.theme === 'dark';
    if (btn) btn.setAttribute('aria-label', d ? '切换到浅色' : '切换到深色');
  }
  if (btn) btn.addEventListener('click', () => {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    root.dataset.manual = '1';
    try { localStorage.setItem('pf-theme', next); } catch(e){}
    paint();
  });
  // 跟随系统 / 按时间：过点了要自己换回来；访客手动选过的不动
  function tick(){
    if (root.dataset.manual === '1') return;
    const d = auto();
    if ((root.dataset.theme === 'dark') !== d){ root.dataset.theme = d ? 'dark' : 'light'; paint(); }
  }
  if (mq && mq.addEventListener) mq.addEventListener('change', tick);
  setInterval(tick, 60000);
  paint();
})();
"""

# ---------------- 摄影：真实宽高比 → 拼图格 ----------------
_pil = {}
def ratio_of(k, j):
    """读缩略图真实宽高比（缓存），决定拼图格大小。"""
    key = '%s_%s' % (k, pad(j))
    if key not in _pil:
        try:
            from PIL import Image
            im = Image.open(BASE / ('portfolio/assets/photo2/t/%s.jpg' % key))   # 括号不能省：/ 和 % 同优先级左结合
            _pil[key] = im.width / im.height
        except Exception:
            _pil[key] = 1.5
    return _pil[key]

def span_for(r):
    """格子宽高比贴近图片真实比例 → 裁切最少、尽量完整。
       基准：6 列 × 行高 120，列宽 ≈ 187；(c,r) → 宽 ≈ 187c+12(c-1)，高 ≈ 120r+12(r-1)"""
    if   r >= 1.60: return (3, 2)    # ≈2.32  宽幅
    elif r >= 1.15: return (2, 2)    # ≈1.53  横构图
    elif r >= 0.90: return (2, 3)    # ≈1.00  方构图
    elif r >= 0.62: return (1, 2)    # ≈0.74  竖构图
    else:           return (1, 3)    # ≈0.49  长竖幅

# ---------------- 获奖 ----------------
# 每条 = (等级/短标, 赛事或奖项全称, 奖状图路径)；图路径留空则只显示文字徽章。
# ⚠️ 模板默认无内置奖项 —— 全部以 data.json 的 awards 为准（键 = 作品标题）。
AWARDS = {}
# 用户改过的奖项表落到 data.json 就能覆盖（老 _awards.json 仅作兜底）
if D.get('awards'):
    AWARDS = {k: [tuple(x) for x in v] for k, v in D['awards'].items()}
else:
    _AW = BASE / 'build/_awards.json'
    if _AW.exists():
        import json as _json
        AWARDS = {k: [tuple(x) for x in v] for k, v in _json.loads(_AW.read_text(encoding='utf-8')).items()}

# 代表作清单：默认 = 挂奖的那几支；data.json 的 stars 为准（纯标题数组，可跨分类）
if D.get('stars'):
    STARS = set(D['stars'])
else:
    STARS = set(AWARDS)
_MISS = []          # 清单里对不上任何卡片的标题，收尾时报警，防止静默失效
_SEEN = set()       # 实际命中的代表作标题

# ---------------- 卡片 ----------------
def vcard(it, wide=False, ep=''):
    duty = ''
    if it['duty']:
        duty = ('<div class="vduty"><span class="dl">%s</span>%s</div>'
                % (E(it['dutylab']), ''.join('<span class="dc">%s</span>' % E(x) for x in it['duty'])))
    go  = '<span class="vgo">%s <span class="arr">↗</span></span>' % E(it['go'] or '观看') if it['href'] else ''
    hit = '<a class="vhit" href="%s" target="_blank" rel="noopener" aria-label="%s"></a>' % (E(it['href']), E(it['title'])) if it['href'] else ''
    aws = AWARDS.get(it['title'], [])
    if aws:
        # 奖状卡已挪到**卡片右下角**（见 CSS .vawards），与 .vinfo 不再抢位置，
        # 纵向实测最大占用 139px，各档卡高都容得下 → 正常情况下用完整奖状卡。
        # .mini（小圆角标）只在「多张 + 长名」叠加、确实可能顶到卡片上半部时才上，
        # 且仅 681–1100px 那档的 CSS 认这个类（≤680px 走 static 流式、>1100px 卡够高）。
        _long = sum(1 for _lv, _nm, _ in aws if len(_nm or '') > 26)
        _mini = (len(aws) >= 3) or (len(aws) >= 2 and _long >= 2)
        aw = ('<div class="vawards%s">%s</div>'
              % (' mini' if _mini else '',
                 ''.join('<span class="vaw"%s><i class="med">奖</i><span><b class="at">%s</b>%s</span></span>'
                         % (' data-img="%s" data-cap="%s" title="点击查看奖状"' % (E(img), E('%s · %s' % (lv, nm))) if img else '',
                            E(lv), '<span class="al">%s</span>' % E(nm) if nm else '')
                         for lv, nm, img in aws)))
    else:
        aw = ''
    info = ('<div class="vinfo">'
            + ('<div class="vkick">%s</div>' % E(it['kick']) if it['kick'] else '')
            + '<h3 class="vtitle">%s</h3>' % E(it['title'])
            + ('<p class="vdesc">%s</p>' % E(it['desc']) if it['desc'] else '')
            + duty + '</div>')
    cls = 'vcard fade' + (' wide' if wide else '')
    starb = ''
    if it['title'] in STARS:
        _SEEN.add(it['title'])
        cls += ' star'
        starb = '<span class="vstar">★ 代表作</span>'
    epb = '<span class="vep">%s</span>' % E(ep) if ep else ''
    if it['img']:
        inner = '<img src="%s" alt="%s" loading="lazy">' % (E(it['img']), E(it['title']))
    else:
        cls += ' nocover'
        inner = ('<div class="vbig">%s</div><div class="vtag">%s</div>'
                 % (E(it['txtbig']), E(it['txttag'])))
    # ⚠️ aw 必须放在 .vinfo **外面**、作为 .vcard 的直接子元素。
    #    放 .vinfo 里面时，position:absolute 的基准是 .vinfo（最近的已定位祖先），
    #    right/bottom 全按 .vinfo 算 → 奖状贴在信息区里，永远跑不到卡片最右侧。
    return ('<article class="%s">%s<div class="vscrim"></div>%s%s%s%s%s%s</article>'
            % (cls, inner, epb, starb, go, hit, info, aw))

def subwall(subs):
    """专项下面那几支：封面 + 标题（可选一行职务）+ 小按钮，文案不重复"""
    out = []
    for s in subs:
        duty = ('<div class="subduty">%s</div>'
                % ''.join('<span class="dc">%s</span>' % E(x) for x in s['duty'])
                ) if s.get('duty') else ''
        out.append('<a class="subitem fade" href="%s" target="_blank" rel="noopener">'
                   '<img src="%s" alt="%s" loading="lazy">'
                   '<span class="submeta"><span class="subtx"><span class="subttl">%s</span>%s</span>'
                   '<span class="subgo">%s <span class="arr">↗</span></span></span></a>'
                   % (E(s['href']), E(s['img']), E(s['title']), E(s['title']), duty,
                      E(s.get('go') or '观看')))
    return '<div class="subwall">%s</div>' % ''.join(out)

def ep_of(it, idx):
    """期数：类型行里写了「第 N 期」就用它，否则按组内顺序兜底编号"""
    import re as _re3
    kick = it.get('kick') or ''
    m = _re3.match(r'^\s*(第\s*\d+\s*[期集])\s*[·•\-]?\s*(.*)$', kick)
    if m:
        return m.group(1), m.group(2)
    return ('第 %d 期' % (idx + 1), kick)


def sercard(it, ep='', rest=''):
    """系列里的一期：等大卡片，带期数角标 + 简介 + 职务标签，不设主次"""
    tag = ''
    cls = 'sercard fade'
    if it['title'] in STARS:
        _SEEN.add(it['title'])
        cls += ' star'
        tag += '<span class="vstar">★ 代表作</span>'
    if ep:
        tag += '<span class="serep">%s</span>' % E(ep)
    duty = ('<div class="subduty">%s</div>'
            % ''.join('<span class="dc">%s</span>' % E(x) for x in it['duty'])) if it['duty'] else ''
    inner = ('<div class="serimg">%s<img src="%s" alt="%s" loading="lazy"></div>'
             '<div class="serbody">'
             + ('<div class="serkick">%s</div>' % E(rest) if rest else '')
             + '<h4 class="serttl">%s</h4>' % E(it['title'])
             + ('<p class="serdesc">%s</p>' % E(it['desc']) if it['desc'] else '')
             + duty
             + ('<span class="subgo">%s <span class="arr">↗</span></span>'
                % E(it['go'] or '观看') if it['href'] else '')
             + '</div>') % (tag, E(it['img']), E(it['title']))
    if it['href']:
        return ('<a class="%s" href="%s" target="_blank" rel="noopener">%s</a>'
                % (cls, E(it['href']), inner))
    return '<article class="%s">%s</article>' % (cls, inner)

def band(title_k, big, note, items, cls='band g fade'):
    return ('<div class="%s"><div class="bl"><div class="bk">%s</div><div class="bn">%s</div>%s</div>'
            '<div class="br">%s</div></div>'
            % (cls, E(title_k), big, '<div class="bx">%s</div>' % E(note) if note else '',
               ''.join('<div class="bi"><b>%s</b><span>%s</span></div>' % (E(a), E(b)) for a, b in items)))

def hcard(it):
    """数码内容的一张封面卡：封面 + 左上「播放量 / 年份」+ 右下时长。

    卡面不放标题（用户要求「主要展示视频多」）；标题塞进 title/aria-label，
    桌面 hover 时浮出。年份只有旧号有值（新号都是近两三年，标了没信息量）。
    """
    cover = it.get('cover') or ''
    title = it.get('title') or ''
    if it.get('year'):
        ml = ('<span class="meta-l"><span class="play">%s</span>'
              '<span class="yr">%s</span></span>' % (E(it['play']), E(it['year'])))
    else:
        ml = '<span class="meta-l"><span class="play">%s</span></span>' % E(it['play'])
    dur = '<span class="dur">%s</span>' % E(it['dur']) if it.get('dur') else ''
    img = ('<img src="%s" alt="%s" loading="lazy">' % (E(cover), E(title))) if cover \
        else '<div class="hc-nocover"></div>'
    return ('<a class="hc fade" href="%s" target="_blank" rel="noopener" title="%s" aria-label="%s">'
            '%s%s%s<span class="tp">%s</span></a>'
            % (E(it['href']), E(title), E(title), img, ml, dur, E(title)))

def group_block(g, idx):
    gid = 'g%d' % idx
    # 分类简介：标题下面一段。空着就不渲染，免得留一个带 margin 的空段
    sub = (g.get('sub') or '').strip()
    subhtml = '<p class="grp-sub">%s</p>' % E(sub) if sub else ''
    head = ('<div class="grp-t"><h3>%s</h3><span class="fl"></span><span class="n">%s</span></div>%s'
            % (E(g['name']), E(g['en']), subhtml))
    if g['type'] == 'aerial':
        n = g['n']
        big = re_big(n)
        return '<div class="grp" id="%s">%s%s</div>' % (gid, head,
            band(g['k'], big, '', g['items']))
    if g['type'] == 'net':
        return '<div class="grp" id="%s">%s</div>' % (gid, band(g['k'], re_big(g['n']), g['x'], g['items']))
    if g['type'] == 'lists':
        cols = ''
        for c in g['cols']:
            rows = ''.join('<div class="prow"><span class="no">%s</span><span class="mt">%s</span>'
                           '<span class="mv">%s%s</span></div>'
                           % (E(r[0]), E(r[1]), E(r[2]),
                              '<em>%s</em>' % E(r[3]) if r[3] else '')
                           for r in c['rows'])
            # 口径说明清空后别留一个带 margin 的空 div
            cols += ('<div class="plist g"><div class="ph"><span class="pn">%s</span><span class="pv">%s</span></div>'
                     '%s%s</div>'
                     % (E(c['pn']), E(c['pv']),
                        '<div class="pnote">%s</div>' % E(c['note']) if c.get('note') else '',
                        rows))
        return '<div class="grp" id="%s">%s<div class="plists">%s</div></div>' % (gid, head, cols)
    # 系列：每期等大横排，角标标期数，不设主次（和「专项大卡 + 封面墙」区分开）
    if g['type'] == 'series':
        return ('<div class="grp" id="%s">%s<div class="serwall">%s</div></div>'
                % (gid, head, ''.join(sercard(it, *ep_of(it, i)) for i, it in enumerate(g['items']))))
    # 竖版罗列型：封面按 9:16 竖条密排，没有首视频
    if g['type'] == 'vwall':
        return ('<div class="grp" id="%s">%s<div class="vwall">%s</div></div>'
                % (gid, head, ''.join(sercard(it, *ep_of(it, i)) for i, it in enumerate(g['items']))))
    # 横版展示型：封面按 16:9 宽卡展示，没有首视频
    if g['type'] == 'hwall':
        return ('<div class="grp" id="%s">%s<div class="hwall">%s</div></div>'
                % (gid, head, ''.join(sercard(it, *ep_of(it, i)) for i, it in enumerate(g['items']))))
    # 首视频型：第一支放大成主视觉，其余照常竖排在下面
    if g['type'] == 'lead':
        items = g['items']
        if not items:
            return '<div class="grp" id="%s">%s</div>' % (gid, head)
        parts = ['<div class="flow special">%s</div>' % vcard(items[0], wide=True,
                                                       ep=ep_of(items[0], 0)[0])]
        rest = items[1:]
        if rest:
            parts.append('<div class="flow">%s</div>'
                         % ''.join(vcard(it, ep=ep_of(it, i + 1)[0]) for i, it in enumerate(rest)))
        return '<div class="grp" id="%s">%s%s</div>' % (gid, head, ''.join(parts))
    items = g['items']
    # 专项：每段 feature（big）可带自己的 subs 封面墙；其余小卡收进 .flow
    if g['type'] == 'special':
        if any(it.get('big') for it in items):
            parts, small = [], []
            for it in items:
                if it.get('big'):
                    if small:
                        parts.append('<div class="flow">%s</div>' % ''.join(vcard(x) for x in small))
                        small = []
                    parts.append('<div class="flow special">%s</div>' % vcard(it, wide=True))
                    if it.get('subs'):
                        parts.append(subwall(it['subs']))
                else:
                    small.append(it)
            if small:
                parts.append('<div class="flow">%s</div>' % ''.join(vcard(x) for x in small))
            return '<div class="grp" id="%s">%s%s</div>' % (gid, head, ''.join(parts))
        # 旧结构（单 feature + 全局 subitems，兼容）
        head_card = vcard(items[0], wide=True)
        subs = g.get('subitems') or []
        rest = items[1:]
        if rest:                      # 没配 subitems 时退回普通流式卡，不至于丢内容
            wall = ('<div class="flow">%s</div>'
                    % ''.join(vcard(it, wide=(len(rest) == 1)) for it in rest))
        else:
            wall = ''
        return ('<div class="grp" id="%s">%s<div class="flow special">%s</div>%s%s</div>'
                % (gid, head, head_card, subwall(subs) if subs else '', wall))
    body = ''.join(vcard(it, wide=(len(items) == 1)) for it in items)
    return '<div class="grp" id="%s">%s<div class="flow">%s</div></div>' % (gid, head, body)

def re_big(s):
    """'55<span>小时</span>' 之类 → 大数字 + 小单位"""
    import re as _re
    m = _re.match(r'^(\d[\d,.]*)\s*(.*)$', s or '')
    if m and m.group(2):
        return '%s<i>%s</i>' % (E(m.group(1)), E(m.group(2)))
    return E(s)

# ---------------- 组装 ----------------
P = []
A = P.append

# 分区先分别生成到各自的缓冲里，最后按 site.pages 的页面顺序拼接（老站回退 site.sections）。
# 这样「调顺序」不用改代码，也不会因为换顺序把分区序号（一二三…）搞乱
# —— 序号在拼接时按最终顺序补（生成时先写 @@N@@ 占位）。
SEC_BUF = {}
_prev_buf = []


def begin_sec(key):
    global P, A, _prev_buf
    _prev_buf = [P, A]
    buf = []
    SEC_BUF[key] = buf
    P, A = buf, buf.append


def end_sec():
    global P, A
    P, A = _prev_buf


def _cnnum_seq(i):
    CNL = '一二三四五六七八九十'
    return CNL[min(i, len(CNL) - 1)]

A('<!DOCTYPE html><html lang="zh-CN" data-theme="%s"><head><meta charset="utf-8">'
  % ('dark' if THEME['mode'] == 'dark' else 'light'))
A('<meta name="viewport" content="width=device-width,initial-scale=1">')
A('<title>%s</title>' % H.escape(TITLE))
A('<meta name="description" content="%s">' % H.escape(DESC))
# 站点图标（头像圆形裁切，源 = assets/hero/avatar.jpg，由 scripts/make_favicon.py 生成）
A('<link rel="icon" href="favicon.ico" sizes="any">')
A('<link rel="icon" type="image/png" href="favicon-32.png" sizes="32x32">')
A('<link rel="apple-touch-icon" href="apple-touch-icon.png">')
# 主题判定必须在样式表之前跑完：晚一帧就会先画一屏浅色再跳成深色（夜里白闪一下很刺眼）。
# 顺序：访客自己选过 → 用他的；否则按后台设的 mode 算。算完把配置留在 window.__TH 给主脚本用。
A('<script>%s</script>' % THEME_BOOT)
A('<style>\n%s</style>' % CSS)   # 换行只为让产物里的 CSS 从行首开始，方便回读
# 主题配色覆盖层：紧跟在样式表后面、同优先级靠「后出现」赢过 :root 与
# html[data-theme="dark"] 里的默认蓝。生成器只换这一小段，site.css 本身不动 ——
# 单独打开样式表仍然是默认蓝，不存在「改了配色把样式表改坏」这种事。
A('<style>\n/* 主题配色（site.theme.accent） */\n%s</style></head><body>'
  % palette.css(THEME['accent']))

# 顶栏（导航项由 site.pages 推导，见上方 NAV_ITEMS）
# 自己传了 logo 就加 mark-wm：圆形容器是按头像设计的，横版字标塞进去会被裁成一条蓝块
A('<header class="nav g"><a class="brand" href="#top"><img class="mark%s" src="%s" alt="%s">'
  '<span class="bid">%s<em>%s</em></span></a><nav class="navlinks" id="navLinks">'
  % (' mark-wm' if SITE.get('logo') else '', E(LOGO), E(BRAND), E(BRAND), E(BRAND_EN)))
for txt, href in NAV_ITEMS:
    A('<a href="%s">%s</a>' % (href, E(txt)))
A('</nav>')
# 深浅色切换：两个图标都在 DOM 里，靠 html[data-theme] 显示哪个，不重画按钮
A('<button class="themebtn" id="thBtn" type="button" aria-label="切换深浅色" title="切换深浅色">'
  '<svg class="ic-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
  '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
  '<svg class="ic-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
  '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.4v2.2M12 19.4v2.2M2.4 12h2.2M19.4 12h2.2'
  'M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6"/></svg></button>')
if HAS_CONTACT:
    A('<a class="nav-cta" href="#contact">%s</a>' % E(NAV_CTA))
A('</header>')

# 首屏
h = D['hero']
A('<section class="hero" id="top">')
A('<div class="hero-bg"><img src="assets/hero/cover.jpg" alt="" fetchpriority="high">'
  '<div class="hero-scrim"></div></div>')
A('<div class="hero-in wrap">')
A('<img class="avatar fade" src="%s" alt="%s · 头像">' % (E(AVATAR), E(BRAND)))
A('<div class="kick fade">%s</div>' % E(h['kick']))
A('<h1 class="fade">%s<span class="en">%s</span></h1>' % (E(BRAND), E(BRAND_EN)))
A('<p class="tagline fade">%s</p>' % E(h['tagline']))
A('<ul class="hmeta fade">')
for k, v in h['hm']:
    A('<li><i>%s</i>%s</li>' % (E(k), E(v)))
A('</ul>')
A('<div class="stats g fade">')
for b, sp in h['stats']:
    A('<div class="stat"><b>%s</b><span>%s</span></div>' % (E(b), E(sp)))
A('</div>')
A('<nav class="heronav fade">')
for txt, href in NAV_ITEMS:
    A('<a href="%s">%s</a>' % (href, E(txt)))
if HAS_CONTACT:
    A('<a class="hn-cta" href="#contact">%s</a>' % E(NAV_CTA))
A('</nav>')
A('</div></section>')

# 首屏之前的部分（head / 顶栏 / hero）到此结束，后面按配置插入各分区
SPLIT_AT = len(P)

# 影像作品
w = D['work']

# 后台里标了 hidden 的作品不进网页（缺封面 / 待单独设计）；整组都隐藏则整组不渲染
def _vis(items):
    return [it for it in items if not it.get('hidden')]


VG = []
for g in w['groups']:
    if g.get('hidden'):      # 整组隐藏（版式实验组用这个，数据留着以后还能翻回来比）
        continue
    v = dict(g)
    v['items'] = _vis(g['items'])
    for it in v['items']:
        if it.get('subs'):
            it['subs'] = _vis(it['subs'])
    if v['items'] or g['type'] in ('aerial', 'net', 'lists'):
        VG.append(v)
_nhid = sum(len(g['items']) for g in w['groups']) - sum(len(g['items']) for g in VG)

star_n = len(STARS)
begin_sec('work')
A('<section id="work"><div class="wrap">')
A(sec_head('work', '影像作品', 'Film & Video', extra=(
    '<button class="vfil" id="vfil" type="button" aria-pressed="false">'
    '<span class="st">★</span>只看代表作<span class="cn">%d</span></button>' % star_n)))
A(sec_sub('work', w['sub']))
A('<nav class="catbar g" data-bar><div class="cat-inner">')
for i, g in enumerate(VG):
    A('<a class="cat" href="#g%d">%s</a>' % (i, E(g['name'])))
A('</div></nav>')
for i, g in enumerate(VG):
    A(group_block(g, i))
A('</div></section>')
end_sec()

if 'digital' in D:
    begin_sec('digital')
    # 数码内容：data.json 里没有 digital 键时整段不渲染（可整体下线）
    d = D['digital']
    ac = d['acct']
    A('<section id="digital"><div class="wrap">')
    A(sec_head('digital', '数码内容', 'Tech & Review'))
    A(sec_sub('digital', d['sub']))
    # 账号简介卡
    A('<div class="dacct g fade">')
    A('<img class="dava" src="%s" alt="%s">' % (E(ac['avatar']), E(ac['name'])))
    A('<div><div class="dan"><h3>%s</h3><span class="den">%s</span></div>' % (E(ac['name']), E(ac['en'])))
    A('<p class="dasub">%s</p>' % E(ac['sub']))
    if ac.get('chips'):
        A('<div class="dchips">%s</div>'
          % ''.join('<span class="dchip">%s</span>' % E(c) for c in ac['chips']))
    A('<a class="dlink" href="%s" target="_blank" rel="noopener">查看 B 站主页 <span>↗</span></a>' % E(ac['link']))
    A('</div></div>')
    # 两个分组：现频道 / 早期频道
    for g in d['groups']:
        A('<div class="grp-t fade"><h3>%s</h3><span class="fl"></span>'
          '<span class="n">%s</span></div>' % (E(g['name']), E(g['n'])))
        sub = (g.get('sub') or '').strip()
        if sub:
            A('<p class="grp-sub fade">%s</p>' % E(sub))
        A('<div class="hcards">%s</div>' % ''.join(hcard(it) for it in g['items']))
    # 更多视频
    m = d['more']
    A('<div class="dmore g fade"><div><div class="mt">%s</div><div class="ms">%s</div></div>'
      '<a href="%s" target="_blank" rel="noopener">%s <span>↗</span></a></div>'
      % (E(m['t']), E(m['s']), E(m['href']), E(m['btn'])))
    A('</div></section>')
    end_sec()

# 摄影
ph = D['photo']
pad = lambda i: ('0%d' % i) if i < 10 else str(i)
total = sum(c[3] for c in ph['cats'])
begin_sec('photo')
A('<section id="photo"><div class="wrap">')
A(sec_head('photo', '摄影', 'Photography'))
A(sec_sub('photo', ph['sub']))
A('<div class="pills g fade" id="pills">')
A('<button class="pill on" data-k="all">全部 <span class="c">%d</span></button>' % total)
# 摄影分类是位置数组 [key, 中文, 英文, 张数, 简介?]，第 5 位是可选的简介。
# 一律按下标取，别用元组解包——老数据只有 4 位，解包会直接炸。
for i, c in enumerate(ph['cats']):
    A('<button class="pill" data-k="%s">%s %s <span class="c">%d</span></button>'
      % (c[0], cnnum(i + 1), E(c[1]), c[3]))
A('</div><div id="photos">')
for i, c in enumerate(ph['cats']):
    k, cn, en, n = c[0], c[1], c[2], c[3]
    sub = ((c[4] if len(c) > 4 else '') or '').strip()
    A('<div class="pcat fade" data-cat="%s"><div class="pcat-h"><span class="pn">%s</span><h3>%s</h3>'
      '<span class="en">%s</span><span class="fl"></span><span class="n">%d 张</span></div>%s'
      % (k, cnnum(i + 1), E(cn), E(en), n,
         '<p class="grp-sub">%s</p>' % E(sub) if sub else ''))
    A('<div class="pwall">')
    for j in range(1, n + 1):
        f = 'assets/photo2/%s_%s.jpg' % (k, pad(j))
        th = 'assets/photo2/t/%s_%s.jpg' % (k, pad(j))
        cap = '%s · %s' % (cn, pad(j))
        A('<figure data-r="%.4f"><img src="%s" data-full="%s" alt="%s" loading="lazy">'
          '<figcaption>%s</figcaption></figure>'
          % (ratio_of(k, j), th, f, E(cap), E(cap)))
    A('</div></div>')
A('</div></div></section>')
end_sec()

# ---------------- 论文与研究 ----------------
# 左边整幅 A4 封面，右边要点 + 指标贴底，卡片下方横排内页。
# 封面是体量，内页是内容 —— 两样都得占位置，只放一句简介说服不了人。
if 'papers' in D:
    pap = D['papers']
    begin_sec('papers')
    A('<section id="papers"><div class="wrap">')
    A(sec_head('papers', pap.get('h2') or '论文与研究', pap.get('h2en') or 'Research'))
    A(sec_sub('papers', pap.get('sub') or ''))
    for it in pap['items']:
        A('<article class="pap g fade">')
        if it.get('cover'):
            A('<figure class="pap-cv"><img src="%s" alt="%s" loading="lazy">'
              '<span class="pap-tag">%s</span></figure>'
              % (E(it['cover']), E(it['title']), E(it.get('cover_note') or 'A4 封面')))
        else:
            # 没封面就别塞一张假图：留虚线框，作者一眼知道该补什么
            A('<figure class="pap-cv pap-empty"><span>封面待补<br>'
              '<em>A4 · 1400×1866</em></span></figure>')
        A('<div class="pap-bd">')
        A('<div class="pap-top"><span class="pap-no">%s</span>'
          '<span class="pap-kind">%s</span></div>'
          % (E(it.get('no') or ''), E(it.get('kind') or '')))
        A('<h3 class="pap-title">%s</h3>' % E(it['title']))
        A('<p class="pap-one">%s</p>' % E(it['oneline']))
        if it.get('points'):
            A('<ul class="pap-points">%s</ul>'
              % ''.join('<li>%s</li>' % E(x) for x in it['points']))
        if it.get('metrics') or it.get('href'):
            A('<div class="pap-meta">')
            for v, l in it.get('metrics') or []:
                A('<div><b>%s</b><span>%s</span></div>' % (E(v), E(l)))
            if it.get('href'):
                A('<a class="pap-read" href="%s" target="_blank" rel="noopener">读全文 ↗</a>'
                  % E(it['href']))
            A('</div>')
        A('</div>')
        if it.get('pages'):
            A('<div class="pap-pages"><div class="pap-ph"><b>内页 · 版面</b><span>%s</span></div>'
              '<div class="pap-strip" style="--pn:%d">'
              % (E(it.get('pages_note') or ''), min(len(it['pages']), 6)))
            for src, cap in it['pages']:
                if src:
                    A('<div class="pap-pi"><div class="im"><img src="%s" alt="%s" loading="lazy">'
                      '</div><span>%s</span></div>' % (E(src), E(cap), E(cap)))
                else:
                    A('<div class="pap-pi"><div class="im ph"><span>%s</span></div>'
                      '<span>待补</span></div>' % E(cap))
            A('</div></div>')
        A('</article>')
    A('</div></section>')
    end_sec()

# ---------------- 评论与随笔 ----------------
# 单篇体量轻，做成同等大卡片会显得空。时间线能长出「一直在写」这个印象。
if 'opeds' in D:
    opd = D['opeds']
    begin_sec('opeds')
    A('<section id="opeds"><div class="wrap">')
    A(sec_head('opeds', opd.get('h2') or '评论与随笔', opd.get('h2en') or 'Op-eds'))
    A(sec_sub('opeds', opd.get('sub') or ''))
    A('<div class="opd-top fade"><b>%d 篇</b><span>%s</span></div>'
      % (len(opd['items']), E(opd.get('counts') or '')))
    A('<div class="opd-list">')
    for it in opd['items']:
        A('<article class="opd fade">')
        # 有年份用年份，没有就用序号 —— 别硬编日期
        A('<div class="opd-date"><b>%s</b><span>%s</span></div>'
          % (E(it.get('year') or it.get('no') or ''), E(it.get('kind') or '')))
        A('<div class="opd-bd"><h3>%s</h3><p>%s</p>' % (E(it['title']), E(it['oneline'])))
        if it.get('quote'):
            A('<blockquote class="opd-q">%s</blockquote>' % E(it['quote']))
        A('</div>')
        if it.get('cover'):
            A('<figure class="opd-th"><img src="%s" alt="%s" loading="lazy"></figure>'
              % (E(it['cover']), E(it['title'])))
        else:
            A('<div class="opd-th opd-noth"></div>')
        A('</article>')
    A('</div></div></section>')
    end_sec()

# ---------------- 设计与物料 ----------------
# 按**物料形态**分组，不是按时间。评审想知道的是「你能不能把控不同尺寸下的信息层级」。
if 'design' in D:
    dzs = D['design']
    begin_sec('design')
    A('<section id="design"><div class="wrap">')
    A(sec_head('design', dzs.get('h2') or '设计与物料', dzs.get('h2en') or 'Design'))
    A(sec_sub('design', dzs.get('sub') or ''))
    for pj in dzs['projects']:
        A('<article class="dz g fade">')
        A('<div class="dz-h"><div>')
        if pj.get('badge'):
            A('<span class="dz-badge">%s</span>' % E(pj['badge']))
        A('<h3>%s</h3><p>%s</p></div>' % (E(pj['title']), E(pj.get('desc') or '')))
        if pj.get('specs'):
            A('<ul class="dz-spec">%s</ul>' % ''.join(
                ('<li><b>%s</b>%s</li>' % (E(v), E(l))) if v else ('<li>%s</li>' % E(l))
                for v, l in pj['specs']))
        A('</div>')
        for g in pj.get('groups') or []:
            A('<div class="dz-grp"><div class="dz-gh"><b>%s</b><span>%s</span><i></i></div>'
              % (E(g['name']), E(g.get('note') or '')))
            A('<div class="dz-grid dz-g%d">' % (g.get('cols') or 4))
            for src, cap, shape in g['items']:
                A('<figure class="dz-t %s"><img src="%s" alt="%s" loading="lazy">'
                  '<em>%s</em></figure>' % (E(shape or 's16'), E(src), E(cap), E(cap)))
            nc = g.get('note_card')
            if nc:
                # 这格不是图，是清单卡：两组方形图只占两列，第三列拿来讲清规格
                A('<div class="dz-note"><b>%s</b>' % E(nc['title']))
                for k, v in nc['rows']:
                    A('<div><span>%s</span><i>%s</i></div>' % (E(k), E(v)))
                if nc.get('foot'):
                    A('<div class="dz-note-foot">%s</div>' % E(nc['foot']))
                A('</div>')
            A('</div>')
            if g.get('wide'):
                wsrc, wcap = g['wide']
                A('<figure class="dz-t sflag"><img src="%s" alt="%s" loading="lazy">'
                  '<em>%s</em></figure>' % (E(wsrc), E(wcap), E(wcap)))
            A('</div>')
        if pj.get('foot'):
            A('<div class="dz-foot"><b>%s</b><span>%s</span></div>'
              % (E(pj['foot'][0]), E(pj['foot'][1])))
        A('</article>')
    A('</div></section>')
    end_sec()

# ---------------- 问题与方案 ----------------
# 策划案的价值在结构，不在描述。左问题右解法，两栏一对，三秒能判断想没想清楚。
if 'proposals' in D:
    prp = D['proposals']
    begin_sec('proposals')
    A('<section id="proposals"><div class="wrap">')
    A(sec_head('proposals', prp.get('h2') or '问题与方案', prp.get('h2en') or 'Proposals'))
    A(sec_sub('proposals', prp.get('sub') or ''))
    for it in prp['items']:
        A('<article class="prp g fade">')
        A('<div class="prp-h"><h3>%s</h3><span>%s</span></div>'
          % (E(it['title']), E(it.get('kind') or '')))
        A('<p class="prp-sub">%s</p>' % E(it.get('oneline') or ''))
        A('<div class="prp-flow">')
        A('<div class="prp-col"><div class="prp-ch">%s</div>' % E(it.get('left_label') or '问题'))
        for t, d in it.get('left') or []:
            A('<div class="prp-s"><b>%s</b><span>%s</span></div>' % (E(t), E(d)))
        A('</div><div class="prp-ar">%s</div>' % '→')
        A('<div class="prp-col"><div class="prp-ch">%s</div>' % E(it.get('right_label') or '方案'))
        for t, d in it.get('right') or []:
            A('<div class="prp-s"><b>%s</b><span>%s</span></div>' % (E(t), E(d)))
        A('</div></div>')
        if it.get('foot'):
            A('<div class="prp-foot">%s</div>' % E(it['foot']))
        A('</article>')
    A('</div></section>')
    end_sec()

# 项目档案
# 数据来自 data.json 的 projects 键；图在 assets/projects/ 下，走主页自己的灯箱（一张一浏览）
pj = D['projects']
begin_sec('projects')
A('<section id="projects"><div class="wrap">')
A(sec_head('projects', pj.get('h2') or 'AI 与编程实践', pj.get('h2en') or 'AI & Coding'))
A(sec_sub('projects', pj['sub']))
for gi, g in enumerate(pj['groups']):
    A('<div class="pjgroup">')
    A('<div class="pjgroup-h fade"><span class="pn">%s</span><h3>%s</h3><span class="en">%s</span>'
      '<span class="fl"></span><span class="n">%d 个项目</span></div>%s'
      % (cnnum(gi + 1), E(g['name']), E(g['en']), len(g['items']),
         '<p class="grp-sub">%s</p>' % E((g.get('sub') or '').strip()) if (g.get('sub') or '').strip() else ''))
    A('<div class="pjcards">')
    for it in g['items']:
        A('<article class="pj g fade">')
        # 行尾定性标签（如「开源项目优化改进」），没有就不占位
        tag = '<span class="pjtag">%s</span>' % E(it['tag']) if it.get('tag') else ''
        A('<div class="pjhead"><span class="pjno">%s</span><span class="pjkind">%s</span>%s</div>'
          % (E(it['no']), E(it['kind']), tag))
        A('<h4 class="pjtitle">%s</h4>' % E(it['title']))
        A('<p class="pjoneline">%s</p>' % E(it['oneline']))
        if it.get('metrics'):
            A('<div class="pjmetrics">')
            for v, l in it['metrics']:
                A('<div class="pjmetric"><b>%s</b><span>%s</span></div>' % (E(v), E(l)))
            A('</div>')
        A('<div class="pjbody"><p class="pjdesc">%s</p>'
          '<div><div class="pjlab">%s</div><div class="pjstack">%s</div></div></div>'
          % (E(it['desc']), E(it.get('stack_label') or '技术栈'),
             ''.join('<i>%s</i>' % E(x) for x in it.get('stack', []))))
        # 结论 / 迭代记录，标题可用 notes_label 自定义
        if it.get('notes'):
            A('<div class="pjblock"><div class="pjlab">%s</div><ul class="pjnotes">%s</ul></div>'
              % (E(it.get('notes_label') or '搭建与迭代'),
                 ''.join('<li>%s</li>' % E(x) for x in it['notes'])))
        if it.get('shots'):
            A('<div class="pjshots">')
            for src, cap in it['shots']:
                A('<figure class="pjshot"><span class="pjsbg"></span>'
                  '<img src="%s" data-full="%s" alt="%s" loading="lazy">'
                  '<figcaption>%s</figcaption></figure>' % (E(src), E(src), E(cap), E(cap)))
            A('</div>')
        A('</article>')
    A('</div></div>')
A('</div></section>')
end_sec()

# 关于
ab = D['about']
begin_sec('about')
A('<section id="about"><div class="wrap">')
A(sec_head('about', '关于我', 'Self-Introduction'))
# 分区简介：留空就整段不渲染（sec_sub 自己会判空）
A(sec_sub('about', ab.get('sub') or ''))
A('<div class="resume"><aside class="rcard g fade">')
A('<img class="rphoto" src="assets/about/portrait.jpg" alt="%s">' % E(OWNER))
A('<div class="rhead"><div class="rname">%s</div><div class="ren">%s</div></div>'
  '<div style="height:18px"></div>' % (E(h['name']), E(h['en'])))
for k, v in ab['facts']:
    A('<div class="rline"><span class="k">%s</span><span class="v">%s</span></div>' % (E(k), E(v)))
for k, v in h['hm']:
    if k in ('方向', '状态'):
        A('<div class="rline"><span class="k">%s</span><span class="v">%s</span></div>' % (E(k), E(v)))
A('<div style="height:14px"></div>')
for txt, href in ab['contact']:
    A('<div class="rline"><span class="k">联系</span><span class="v"><a href="%s" style="color:inherit;text-decoration:none">%s</a></span></div>' % (E(href), E(txt)))
A('</aside><div>')
for b in ab['blocks']:
    A('<div class="abt-blk fade"><div class="abt-h">%s</div>' % E(b['h']))
    for p in b['ps']:
        A('<p>%s</p>' % E(p))
    # 逐条经历（按简历搬运时用）：左列时间，右列「单位 / 头衔 / 角色」三行，再跟要点。
    # 把单位与角色拆成两行 —— 挤在一行时「某某大学融媒体中心视频部 · 编辑」
    # 这种长头衔会把右侧 1fr 撑爆。
    for r in (b.get('rows') or []):
        A('<div class="jrow"><div class="jt">%s</div><div>'
          '<div class="jh">%s</div><div class="jr">%s</div>'
          % (E(r['t']), E(r['org']), E(r.get('role') or '')))
        if r.get('notes'):
            A('<ul class="jl">')
            for x in r['notes']:
                A('<li>%s</li>' % E(x))
            A('</ul>')
        A('</div></div>')
    # 数据能力：前面项目的四字摘要，一行一个项目
    # 摘要里要用 <b> 标项目名，所以**不能整段 E() 转义**：改成先转义再放行 <b></b>。
    if b.get('dsum'):
        A('<ul class="dsum">')
        for dn, dt in b['dsum']:
            A('<li><span class="dn">%s</span><span class="dt">%s</span></li>'
              % (E(dn), E(dt).replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')))
        A('</ul>')
    if b['ds']:
        A('<div class="dgrid">')
        for no, t5, pp in b['ds']:
            A('<div class="dcard g"><div class="no">%s</div><h5>%s</h5><p>%s</p></div>' % (E(no), E(t5), E(pp)))
        A('</div>')
    if b['awards']:
        A('<ul class="awards">')
        for lvl, name in b['awards']:
            A('<li><b>%s</b><span>%s</span></li>' % (E(lvl), E(name)))
        A('</ul>')
    A('</div>')
A('</div></div></div></section>')
end_sec()

# 联系
c = D['contact']
begin_sec('contact')
A('<section id="contact"><div class="wrap"><div class="contact-c g fade">')
A('<div class="kick">%s</div><h2>%s</h2><p class="sub">%s</p>' % (E(c['kick']), E(c['h2']), E(c['sub'])))
A('<div class="big-links">')
for txt, href in c['big']:
    A('<a class="big-link" href="%s">%s</a>' % (E(href), E(txt.replace(' ↗', ''))))
A('</div><div class="plinks">')
for txt, href in c['plinks']:
    A('<a class="plink" href="%s" target="_blank" rel="noopener">%s</a>' % (E(href), E(txt)))
A('</div>')
A('</div></div></section>')
end_sec()

A('<footer><div class="wrap"><span class="g">%s</span></div></footer>' % E(D['footer']))
A('<div id="lb" role="dialog" aria-modal="true" aria-label="图片预览">'
  '<img id="lbimg" src="" alt=""></div>'
  '<div id="lbbar"><span class="lt" id="lbtxt"></span>'
  '<span class="lbacts"><a id="lbfull" href="#" target="_blank" rel="noopener">原图 ↗</a>'
  '<button id="lbclose" aria-label="关闭预览">关闭 ✕</button></span></div>')
A('<script>%s</script></body></html>' % JS)

# ---------------- 按 site.pages 拼接 ----------------
# 分区序号（一二三四…）在这里按**最终顺序**补，所以调顺序不会出现断号/重号。
FINAL = P[:SPLIT_AT]
_ord = 0
for _pg in VISIBLE_PAGES:
    _keys = [b['type'] for b in _pg['blocks']]
    _bufs = [(k, SEC_BUF.get(k)) for k in _keys if SEC_BUF.get(k)]
    if not _bufs:
        continue        # 这一页的块都没内容，整页跳过（导航已经先跳过了）
    # 页面挂了多块：先单独出一屏页面大标题 + 页面简介，块标题在下面降级成小节
    if len(_keys) > 1:
        FINAL.append('<section id="%s" class="pghead"><div class="wrap">'
                     '<div class="sec-head fade"><h2>%s</h2><span class="sec-en">%s</span></div>%s'
                     '</div></section>'
                     % (E(page_anchor(_pg)), E(_pg['title']), E(_pg['titleEn']),
                        ('<p class="sec-sub fade">%s</p>' % E(_pg['intro'])) if _pg['intro'] else ''))
    for _k, _buf in _bufs:
        for _i, _line in enumerate(_buf):
            if '@@N@@' in _line:
                _buf[_i] = _line.replace('@@N@@', _cnnum_seq(_ord))
                _ord += 1
                break
        FINAL.extend(_buf)
FINAL.extend(P[SPLIT_AT:])
P = FINAL

OUT.write_text('\n'.join(P), encoding='utf-8')
print('写入', OUT, '%.1f KB' % (OUT.stat().st_size / 1024))
_dg = D['digital']['groups'] if 'digital' in D else []
ncards = sum(len(g['items']) for g in VG if g.get('type') == 'cards')
# 「视频卡」只数 cards 型分组；special/series/vwall 是别的版式，也占 items，
# 不注明的话读者会以为条数对不上、丢了数据
_nother = sum(len(g['items']) for g in VG if g.get('type') != 'cards')
_dgtot = sum(len(g['items']) for g in _dg)
print('视频卡 %d%s ｜ 分组 %d ｜ 隐藏 %d ｜ 摄影 %d 张 ｜ 数码 %d 条'
      % (ncards, ('（另有 special/series/vwall %d 条）' % _nother) if _nother else '',
         len(VG), _nhid, total, _dgtot))
print('代表作 %d 支：%s' % (len(_SEEN), '、'.join(sorted(_SEEN))))
_miss = STARS - _SEEN
if _miss:
    print('⚠ stars 清单里这些标题没匹配到任何卡片（拼写要一字不差）：%s' % '、'.join(sorted(_miss)))
