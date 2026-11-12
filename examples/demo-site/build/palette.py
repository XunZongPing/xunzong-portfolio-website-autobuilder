# -*- coding: utf-8 -*-
"""主题配色：一个主色 → 整套色板。

为什么要有这个模块
------------------
站点的强调色（--acc）在样式表里被用了 39 次，另外还有 20 来处写死的
rgba(47,107,255,α) —— 光换 --acc 会得到「按钮变红了、阴影还是蓝的」那种半拉子效果。
所以这里不存一堆颜色，只存**一个主色**，其余全部推导：

    --acc / --acc-2 / --acc-3      强调色三档（深 → 浅），用于文字、按钮底、渐变两端
    --acc-rgb 等                   同上的 RGB 分量，给 rgba(var(--acc-rgb),.32) 这种透明阴影用
    --w1..--w4                     背景那四团柔光，按主色相的四个固定偏移转
    --bg1 / --bg2 / --bgD          明暗两套底色

深色模式不是把浅色的色值调暗，而是**单独算一套**：同一个色相在深底上要提亮才看得清
（默认蓝 #2f6bff → 深色下是 #6b96ff）。两个模式各自一套，谁也不会把谁改坏。

推导系数是用默认蓝反推出来的：输入 #2f6bff，输出必须落在现在这组值附近
（#7aa2ff / #6b96ff / #9dbaff / 那四团柔光），否则老站点一升级就变色。
scripts/selftest.py 里有一条断言守着这个基准。

对比度兜底
----------
强调色会被当成「白字底」和「浅底上的文字」两种用途，所以亮度不能随便给：
选了亮黄（#ffd400）白字就没了。这里按 WCAG 相对亮度算对比度，不够就往深/往亮走，
直到对白底（浅色模式）或对深底（深色模式）达到 3.2:1。不追求 4.5 ——
强调色大多是短标签、大字号，3.2 是 AA 大字的门槛，再往上会把鲜艳色压成暗色。
"""
import colorsys

# 缺省主色：和 site.css 里 :root 的 --acc 一致
DEFAULT = '#2f6bff'

# 内置预设。色值都是手挑的：既要在白底上能当文字，又要能当「白字底」，
# 还要在深色模式下有足够亮度（推导时会再兜一层底）。
PRESETS = [
    dict(id='blue',   name='海蓝', accent='#2f6bff', note='默认，冷静、偏理性，适合影像与技术类'),
    dict(id='orange', name='暖橙', accent='#e0651c', note='暖、有活力，适合生活与商业摄影'),
    dict(id='red',    name='朱砂', accent='#cf2b3d', note='最抓眼，适合强叙事的纪录片方向'),
    dict(id='green',  name='松绿', accent='#10855f', note='沉稳，适合自然、户外、纪实'),
    dict(id='violet', name='鸢尾', accent='#6b46e8', note='偏设计感，适合视觉与品牌向'),
    dict(id='teal',   name='雾青', accent='#0e7c8c', note='清冷，适合旅行与人文'),
]

# 背景柔光四团相对主色的色相偏移。数值是从默认蓝那四团反推的：
#   220（蓝）→ 334（粉）→ 173（青）→ 34（琥珀），即 0 / +114 / -47 / +174
# 换色时整组一起转，四团的「冷暖对撞」关系不变 —— 这才是液态玻璃那层底色好看的原因。
_WASH_HUE = (0, 114, -47, 174)
_WASH_L_DAY = (0.735, 0.829, 0.755, 0.771)     # 浅色模式四团的亮度（左上一团最实）
_WASH_S_DAY = (1.0, 1.0, 0.68, 1.0)            # 第三团（青绿）本来就淡一档，全饱和会抢戏
_WASH_L_NIGHT = (0.410, 0.325, 0.227, 0.263)
_WASH_S_NIGHT = (0.58, 0.40, 0.62, 0.61)

# 三档强调色的提亮比例（相对「到 1.0 还剩多少」）。反推自默认蓝：
#   #7aa2ff 落在 +0.36、#5b8cff 落在 +0.21、深色 #6b96ff 落在 +0.29、#9dbaff 落在 +0.53
_L_DEEP = 0.0
_L_MID = 0.21
_L_SOFT = 0.36
_L_NIGHT = 0.29
_L_NIGHT_SOFT = 0.53

# 对比度门槛（AA 大字）。低于此值就往能看清的方向走。
MIN_CONTRAST = 3.2


# ---------------------------- 基础换算 ----------------------------
def normalize(v, default=DEFAULT):
    """把用户/数据里拿到的色值收敛成 `#rrggbb`。

    认这几种写法：`#2f6bff` / `2f6bff` / `#2F6BFF` / `#2bf`（三位缩写）。
    认不出来就回默认色 —— 生成器不该因为一个色值写错就整个崩掉，
    真正该报错的地方是 validate_data.py（它会在生成前指出来）。
    """
    if not isinstance(v, str):
        return default          # 数字、null、数组一律当没写：别把 123 猜成 #112233
    s = v.strip().lstrip('#')
    if len(s) == 3 and all(c in '0123456789abcdefABCDEF' for c in s):
        s = ''.join(c * 2 for c in s)
    if len(s) == 6 and all(c in '0123456789abcdefABCDEF' for c in s):
        return '#' + s.lower()
    return default


def is_hex(v):
    """是不是一个能认的色值（不替它猜，只回答是/不是）。"""
    s = str(v or '').strip().lstrip('#')
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    return len(s) == 6 and all(c in '0123456789abcdefABCDEF' for c in s)


def _to_hls(hexs):
    r, g, b = (int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, l, s


def _to_hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return '#%02x%02x%02x' % (round(r * 255), round(g * 255), round(b * 255))


def _rgb(hexs):
    return '%d,%d,%d' % tuple(int(hexs[i:i + 2], 16) for i in (1, 3, 5))


def _lum(hexs):
    """WCAG 相对亮度（注意：不是 HLS 里的 L，两者差很远）。"""
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexs[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _fit(h, l, s, bg, step):
    """把亮度调到「和 bg 对比度够」为止。step > 0 往亮走，< 0 往深走。

    只调亮度不动色相/饱和度 —— 用户选的是那个颜色，我们能动的只有明暗。
    走到 0.06/0.94 还不行就停手（纯黑/纯白已经没得调了）。
    """
    for _ in range(60):
        if contrast(_to_hex(h, l, s), bg) >= MIN_CONTRAST:
            break
        l += step
        if l <= 0.06 or l >= 0.94:
            l = max(0.06, min(0.94, l))
            break
    return l


def resolve(accent):
    """主色 → 整套色板（浅色 + 深色两套）。返回 dict，值都是能直接塞进 CSS 的字符串。"""
    hexs = normalize(accent)
    h, l, s = _to_hls(hexs)

    # 浅色模式：强调色要压得住白底（也就能当白字底），亮度先兜一次
    light_l = _fit(h, min(l, 0.70), s, '#ffffff', -0.015)
    # 深色模式：同一色相在深底上必须提亮，先按系数提一档再兜底
    night_l = _fit(h, light_l + (1 - light_l) * _L_NIGHT, s, '#070a11', +0.015)

    def tone(l0, factor):
        return _to_hex(h, min(0.96, l0 + (1 - l0) * factor), s)

    light = {
        'acc': _to_hex(h, light_l, s),
        'acc-2': tone(light_l, _L_SOFT),
        'acc-3': tone(light_l, _L_MID),
        'bg1': _to_hex(h, 0.976, 0.50),
        'bg2': _to_hex(h, 0.947, 0.52),
        'bgD': _to_hex(h, 0.066, 0.55),
    }
    night = {
        'acc': _to_hex(h, night_l, s),
        'acc-2': tone(light_l, _L_NIGHT_SOFT),
        'acc-3': tone(night_l, 0.12),
        'bg1': _to_hex(h, 0.070, 0.45),
        'bg2': _to_hex(h, 0.048, 0.45),
        'bgD': _to_hex(h, 0.066, 0.55),
    }

    deg = h * 360
    for name, base_l, sat, pal in (
        ('light', _WASH_L_DAY, _WASH_S_DAY, light),
        ('night', _WASH_L_NIGHT, None, night),
    ):
        for i, off in enumerate(_WASH_HUE):
            wl = base_l[i]
            ws = sat[i] if isinstance(sat, tuple) else _WASH_S_NIGHT[i]
            pal['w%d' % (i + 1)] = _rgb(_to_hex((deg + off) / 360, wl, ws))

    # RGB 分量：给 rgba(var(--acc-rgb),α) 用，透明阴影才不会永远是蓝的
    for pal in (light, night):
        for k in ('acc', 'acc-2', 'acc-3'):
            pal[k + '-rgb'] = _rgb(pal[k])
    return {'light': light, 'dark': night, 'accent': hexs}


# 柔光层的几何与透明度。⚠️ 和 site.css 里 body::before / 暗色 body::before 两条规则
# **必须一致** —— 那里管"真网页"，这里只给后台的预览小样用。改一处记得改另一处，
# 否则后台预览的底色和实际网页差一档，属于"看着对、上线不对"的坑。
_WASH_GEO = ((46, 40, 10, 4, 62), (38, 36, 90, 10, 60),
             (52, 44, 80, 84, 62), (42, 38, 16, 90, 60))
_WASH_ALPHA_DAY = (0.62, 0.48, 0.55, 0.45)
_WASH_ALPHA_NIGHT = (0.40, 0.30, 0.30, 0.26)


def wash_css(pal, night=False):
    """把四团柔光拼成可直接塞进 style.background 的字符串（后台预览用）。"""
    a = _WASH_ALPHA_NIGHT if night else _WASH_ALPHA_DAY
    parts = ['radial-gradient(%d%% %d%% at %d%% %d%%, rgba(%s,%.2f), transparent %d%%)'
             % (w, h, x, y, pal['w%d' % (i + 1)], a[i], end)
             for i, (w, h, x, y, end) in enumerate(_WASH_GEO)]
    parts.append('linear-gradient(180deg,%s,%s)' % (pal['bg1'], pal['bg2']))
    return ','.join(parts)


def css(accent):
    """生成要插在样式表后面那段 <style>。

    为什么是「后面再插一段」而不是改 :root：
    site.css 保持能单独打开就有效果（默认蓝），这段是覆盖层。
    两段同优先级（:root / html[data-theme]），后出现的赢。
    """
    r = resolve(accent)
    keys = ['acc', 'acc-2', 'acc-3', 'acc-rgb', 'acc-2-rgb', 'acc-3-rgb',
            'w1', 'w2', 'w3', 'w4', 'bg1', 'bg2', 'bgD']
    light = ';'.join('--%s:%s' % (k, r['light'][k]) for k in keys)
    night = ';'.join('--%s:%s' % (k, r['dark'][k]) for k in keys)
    return (':root{%s}\nhtml[data-theme="dark"]{%s}' % (light, night))


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    for p in PRESETS:
        r = resolve(p['accent'])
        print('%-7s %-8s %s  深色 %s  白字对比 %.2f / 深底 %.2f'
              % (p['id'], p['name'], r['light']['acc'], r['dark']['acc'],
                 contrast(r['light']['acc'], '#ffffff'),
                 contrast(r['dark']['acc'], '#070a11')))
