# 设计语言：液态玻璃（Liquid Glass）

全站视觉只有一条规则：**玻璃块浮在彩色的模糊背景上**。
不要在页面上加第二种视觉语言（不要纸感、不要描边卡片、不要霓虹）。

## 设计令牌（`:root`）

```css
--ink:#0d1117; --ink-2:#4d5766; --ink-3:#8a909c;   /* 文字三级 */
--acc:#2f6bff; --acc-2:#7aa2ff; --acc-3:#5b8cff;   /* 主色三档：电光蓝（默认） */
--acc-rgb:47,107,255; /* 同上的 RGB 分量，给 rgba(var(--acc-rgb),.32) 用 */
--r-xl:34px; --r-lg:28px; --r-md:22px; --r-sm:14px;
--sh:0 8px 30px rgba(16,24,40,.10), 0 2px 8px rgba(16,24,40,.06);
--sh-hi:0 18px 50px rgba(16,24,40,.16), 0 4px 14px rgba(16,24,40,.08);
--blur:26px;
```

## 深浅色（v1.5.0）

**实现方式：只加不改。** 上面所有浅色规则一律不碰，深色全部写在 CSS 末尾的
`html[data-theme="dark"]` 覆盖块里。好处是浅色版零风险，单条也能单独回退。

切换链路：

```
<html data-theme="light|dark">
   ↑ head 内联脚本（首帧前执行，防闪白）
     localStorage['pf-theme']  >  site.theme.mode  >  light
   ↑ 顶栏 #tbTheme 点击 → 改 data-theme + 写 localStorage
   ↑ 没手选过时，system 模式跟系统变 / time 模式每分钟对表
```

`site.theme.mode` 的四种取值（后台「网站配色」可改，v1.6.0）：

| mode | 判定来源 | 页面开着时会自己变吗 |
|---|---|---|
| `system` | `matchMedia('(prefers-color-scheme: dark)')` | 会（监听 change 事件） |
| `light` | 常量 | 不会 |
| `dark` | 常量 | 不会 |
| `time` | 本地时钟 vs `darkAt` / `lightAt` | 会（`setInterval` 60s） |

`time` 的深色区间是 `[darkAt, lightAt)` 半开区间，`darkAt > lightAt` 自动按跨夜处理
（19:00 深 / 07:00 浅 → 晚上深、白天浅）；两者相等会退化成全天浅色。
用 `setInterval` 而不是 `setTimeout` 卡点，是因为**休眠/挂起后定时器会漂**，每分钟对一次表更稳。

配色原则（液态玻璃换到深色底时要守的三条）：

| 项 | 浅色 | 深色 | 为什么 |
|---|---|---|---|
| 玻璃填充 | `rgba(255,255,255,.68→.40)` | `rgba(255,255,255,.085→.032)` | 深色底上白色只能当"微光"，不能当"面" |
| 折射描边 | `.98 → .08 → .62` | `.34 → .02 → .19` | 描边仍是全片最亮的东西，但亮度砍到三成 |
| `backdrop-filter` | `saturate(185%) brightness(1.06)` | `saturate(150%) brightness(.90)` | **靠 brightness 压暗，不是靠加深 alpha** —— 加深 alpha 会让玻璃变灰泥 |
| 文字 | `--ink:#0d1117` | `--ink:#e9eef7` | 只改这三个变量，全文自动跟随 |
| 阴影 | 柔和下投影 | 更深更散（`.5` 黑） | 深色下阴影是唯一的纵深线索 |

**不要跟着变的**：`.hero` / `.heronav` / `.vmeta` / 视频卡的 `.vinfo` / `.vaw` / `#lb`。
它们本来就压在深色照片或黑色遮罩上，恒定白字。改主题时别去动这些选择器。

### 顶栏：导航常驻 + 放不下就横滑

顶栏是「品牌 + N 个导航 + 主题 + CTA」的横向竞争，`N` 最大到 10。**导航项永远在顶栏里**，
不藏进二级菜单（汉堡）—— 藏起来等于把「有几页」这个信息也一起藏了，访客得多点一次才知道站里有什么。

排布是一个 flex 行，顺序固定：品牌 → 导航（弹性）→ 主题 → CTA。

| 位置 | 规则 | 作用 |
|---|---|---|
| 品牌 | `flex:0 0 auto`，≤680 起允许缩小 + 名字省略，≤560 只留 logo | 空间不够时第一个让步（名字不是关键信息） |
| 导航 | `flex:1 1 auto; min-width:66px; overflow-x:auto` | 吃掉剩余空间；放不下就自己滚 |
| 主题 / CTA | `flex:none` | 不给压缩，凑在一起贴着右边缘 |

```css
.navlinks{display:flex;align-items:center;gap:4px;flex:1 1 auto;
  min-width:66px;overflow-x:auto;overflow-y:hidden;
  scrollbar-width:none;-ms-overflow-style:none}
.navlinks::before{content:'';flex:0 0 0;margin-left:auto}   /* 富余时右对齐，挤时自动归零 */
```

`::before` 那个 0 宽、`margin-left:auto` 的伪元素是关键：空间富余时它吸收全部剩余、
把导航项推到右边贴着主题按钮；一旦内容超宽，auto 边距按规范归零，导航从第一项开始排、
可以滚。**如果不这么做，改成给容器加 `justify-content:flex-end`，溢出时左边几项会被推到
滚动区外面且滚不回来。**

**两侧渐隐靠 JS 控制**（`--fl` / `--fr` 两个变量，0 就是完全不淡）：
只在「那一边真的还有内容」时淡出。一直挂着渐隐的话，宽度够时最后一项看着像被裁掉了。

**为什么不用 `flex-wrap:wrap`**：容器上要是还有 `margin-left:auto`，宽度不足时 flex 会把它
压到「最宽那一项」的宽度，wrap 就一个一项地竖着堆——7 个导航项在 570px 宽时变成一根竖线。

**媒体查询的书写顺序**：`.themebtn`、`.nav-cta` 这类基础规则写在文件靠后的位置，
而媒体查询**不提升优先级**——它只是「满足条件时也算一条普通规则」。
所以窄屏的尺寸覆盖必须写在基础声明**之后**，否则会被整条盖掉。

### 断点一览

| 宽度 | 品牌 | 导航 | CTA / 主题 |
|---|---|---|---|
| `> 1080px` | 名字 + 英文小标 | 完整，右对齐 | 原尺寸 |
| `1080 – 681px` | 同上 | 胶囊收紧（内距 `7px 10px` / 字号 `12.5px`） | 原尺寸 |
| `680 – 561px` | 名字可省略（长名字出 `…`） | 再收一档内距 | 原尺寸 |
| `≤ 560px` | **只留 logo**（名字在首屏 H1 里还有） | 继续收 | 略收 |
| `≤ 430px` | logo 32px | 剩余空间约 2~3 项，横向滚 | 内距 `7px 12px` / 字号 `12px` |

## `.g` 三件套（所有玻璃块的统一做法）

任何要「像玻璃」的元素，套 `.g` 即可。它由三部分叠出来：

1. **渐变底**：`linear-gradient(158deg, rgba(255,255,255,.68), rgba(255,255,255,.40) 52%, rgba(255,255,255,.55))`
2. **折射描边**（`::before`）：`padding:1px` + `mask-composite:exclude`，
   用一条多段浅色渐变模拟玻璃边缘的高光折射
3. **镜面高光**（`::after`）：`radial-gradient(115% 78% at 8% -14%, ...)`，从左上方打一道光

```css
.g{position:relative;border-radius:var(--r-lg);
  background:linear-gradient(158deg, rgba(255,255,255,.68), rgba(255,255,255,.40) 52%, rgba(255,255,255,.55));
  -webkit-backdrop-filter:blur(var(--blur)) saturate(185%) brightness(1.06);
  backdrop-filter:blur(var(--blur)) saturate(185%) brightness(1.06);
  box-shadow:var(--sh), inset 0 1px 0 rgba(255,255,255,.92), inset 0 -1px 0 rgba(255,255,255,.32)}
.g::before{content:'';position:absolute;inset:0;border-radius:inherit;padding:1px;pointer-events:none;
  background:linear-gradient(145deg, rgba(255,255,255,.98), rgba(255,255,255,.08) 34%,
             rgba(255,255,255,.62) 58%, rgba(255,255,255,.14) 82%, rgba(255,255,255,.8));
  -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite:xor;
  mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); mask-composite:exclude}
.g::after{content:'';position:absolute;inset:0;border-radius:inherit;pointer-events:none;
  background:radial-gradient(115% 78% at 8% -14%, rgba(255,255,255,.55), rgba(255,255,255,0) 56%)}
```

## 主题配色（v1.12.0）

**数据里只存一个值**：`site.theme.accent`（`#rrggbb`）。其余颜色由 `build/palette.py`
从一个主色推导，不存第二份 —— 存两份必然漂，改了按钮忘了阴影是这类功能最常见的坏法。

推导出来的变量（生成时作为**第二段 `<style>`** 插在样式表后面，同优先级靠「后出现」生效）：

| 变量 | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--acc` | 主色本身（亮度兜底后） | 提亮一档 | 小标题、编号、按钮底、白字底 |
| `--acc-2` | +36% 提亮 | +53% 提亮 | 渐变另一端、光晕 |
| `--acc-3` | +21% | +12% | 渐变中间色（原来写死的 `#5b8cff`） |
| `--w1..--w4` | 主色相 +0 / +114 / −47 / +174 | 同色相、压暗降饱和 | 背景四团柔光 |
| `--bg1`/`--bg2`/`--bgD` | 微染主色相的白 | 近黑 | 页底与深色底 |

三点是踩出来的：

1. **深色不是浅色调暗，是单独算一套。** 同一个色相在 `#070a11` 上要提亮才看得清
   （默认蓝 `#2f6bff` → 深色 `#6b96ff`）。只改浅色会让夜间版一眼看出「还是蓝的」。
2. **半透明色必须拆成分量。** 全站有 21 处 `rgba(47,107,255,α)` 的阴影和光晕，
   只换 `--acc` 会出现「按钮变红了、阴影还是蓝的」。现在都写成 `rgba(var(--acc-rgb),α)`。
3. **柔光的色相偏移是四个固定值**（0 / +114 / −47 / +174，从默认蓝那四团反推的）。
   整组一起转，四团之间的冷暖对撞关系不变 —— 这才是那层底色好看的原因；
   让每套预设各写一份柔光，就成了「换色 = 换滤镜」，做不出统一风格。

**对比度兜底**：`--acc` 同时要当「白字底」和「浅底上的文字」，亮度不能随便给。
推导时按 WCAG 相对亮度算，对白底（浅色）或深底（深色）不够 3.2:1 就自动往能看清的方向走。
选了 `#ffd400` 这种亮黄，实际会压深 —— 后台会明说「实际压深成 #xxxxxx」，不让人以为取色器没生效。

**加一套预设只改一处**：`build/palette.py` 的 `PRESETS`。后台的色块列表是
`GET /api/palettes` 拉下来的，前端没有写死任何颜色。

## 背景（`body::before`）

四团径向渐变 + 一条纵向线性渐变，颜色刻意拉开色相（蓝 / 粉 / 青 / 橙），玻璃才有东西可以折射：

```css
background:
  radial-gradient(46% 40% at 10% 4%,  rgba(120,170,255,.62), transparent 62%),
  radial-gradient(38% 36% at 90% 10%, rgba(255,168,205,.48), transparent 60%),
  radial-gradient(52% 44% at 80% 84%, rgba(150,235,225,.55), transparent 62%),
  radial-gradient(42% 38% at 16% 90%, rgba(255,204,138,.45), transparent 60%),
  linear-gradient(180deg,#f4f7fc,#eaeff8);
```

`body::after` 再叠一层 **2.8% 透明度的 SVG 噪点**（`feTurbulence` data URI），
防止大面积渐变出现色带。

## 顶栏要「够实」

首屏是满幅照片，图片会从顶栏底下穿过 → 顶栏玻璃必须比其它块更厚，否则深色照片透上来吃字：
`--blur:32px` + 底色不透明度提到 `.86/.66/.76`，阴影用 `--sh-hi`。

## 分区与序号

- 分区顺序（实际渲染顺序）：**影像作品 → 摄影 → AI 与编程实践 → 关于我 → 联系**。
- 序号**一律汉字**（`一二三四五…`），且**按实际渲染顺序自增**：
  ```python
  CN = '一二三四五六七八九十'
  def secno(): _secn[0] += 1; return CN[_secn[0]-1]
  ```
  这样下线某一整块时不会留断号。
- ⚠️ 转换函数**不能叫 `cn`** —— 摄影那两处循环的分类名变量就叫 `cn`，会被遮蔽。
- 序号字号与标题**同号同重**（`clamp(24px,3vw,34px)` / `600+`），只靠颜色区分。
  「小号 + 大 letter-spacing」那套是配英文标签的，配中文不搭。

## 对齐要用「文字基线」，不是盒子底边

`align-items:flex-end` 只对齐盒子底边。`.num` 是 `line-height:1`（盒高 = 字号），
`h2` 继承正文行高（盒高 = 字号 × 1.6）→ 底边齐了**基线差半个行距**（实测 10.4px）。
所以 `.sec-head` 用 `align-items:baseline`。

同理，同一视频的多张奖状卡要等宽 → `.vawards` 用 `align-items:stretch`；
移动端横排时只在**两张及以上**拉齐：`.vawards:has(.vaw:nth-child(2)) .vaw{flex:1 1 auto}`。

## 动画

统一用 `.fade`（进入视口时 `opacity 0→1` + `translateY` 上浮）。
量测间距前记得注入 `.fade{opacity:1!important;transform:none!important}`，
否则未触发的 `translateY` 会把间距量歪。

## 三处标题的下边距不同，必须补差值

`.grp-t` 20 / `.pcat-h` 14 / `.pjgroup-h` 18 → 用相邻选择器补到视觉 12–14px：

```css
.grp-t + .grp-sub{margin-top:-6px}
.pcat-h + .grp-sub{margin-top:-2px}
.pjgroup-h + .grp-sub{margin-top:-6px}
```

## 灯箱

`#lb`（大图）+ `#lbbar`（角标文字 + 关闭按钮）成对，关闭时机：点背景 / Esc。
摄影墙的 `img` 里 `src` 指缩略图、`data-full` 指原图 —— **别只换 `src`**。
