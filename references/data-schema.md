# data.json 数据结构（唯一真源）

一份 `portfolio/data.json` 描述整站内容。生成器 `build/gen_site.py` 读它、写 `portfolio/index.html`。
后台 `admin/server.py` 也直接读写它（`POST /api/save` 是**整份覆盖写**）。

> **改内容的唯一入口就是这个文件**（或后台界面）。不要改 `index.html` —— 它是产物，下次生成就被覆盖。

顶层键一览：

| 键 | 类型 | 必需 | 对应分区 |
|---|---|---|---|
| `site` | dict | 否 | 站点身份（站名 / 标题 / logo / **页面与分块** / 配色） |
| `hero` | dict | **是** | 首屏 |
| `navcta` | str | 否 | 顶栏右侧按钮文字 |
| `site.pages` | `Page[]` | 否 | **页面顺序、标题、导航名、每页挂哪些板块**（后台「页面设置」管的就是它） |
| `site.sections` | `{key,show}[]` | 否 | 老格式，`site.pages` 缺失时才读（后台保存时会顺手重写一份做兼容） |
| `work` | dict | **是** | 影像作品 |
| `photo` | dict | **是** | 摄影 |
| `projects` | dict | 否 | 图文 / 技术内容 |
| `papers` | dict | 否 | 论文与研究（**存在才渲染**，见下） |
| `opeds` | dict | 否 | 评论与随笔（同上） |
| `design` | dict | 否 | 设计与物料（同上） |
| `proposals` | dict | 否 | 问题与方案（同上） |
| `digital` | dict | 否 | 数码内容（**存在才渲染**，见下） |
| `about` | dict | **是** | 关于我 |
| `awards` | dict | 否 | 奖项（键 = 作品标题） |
| `stars` | str[] | 否 | 「只看代表作」清单（作品标题） |
| `contact` | dict | **是** | 联系 |
| `footer` | str | 否 | 页脚 |

---

## site —— 站点身份（新加，可省）

生成器原来是写死站名的。现在统一从 `site` 取，缺省依次退回 `hero`：

| 键 | 说明 | 缺省值 |
|---|---|---|
| `brand` | 首屏大标题 + 顶栏站名 | `hero.name` |
| `brand_en` | 大标题下方小字 | `hero.en` 转大写 |
| `owner` | 用于版权 / 图注的姓名 | `hero.name` |
| `title` | `<title>`，留空自动拼 | `「{brand} · {owner}作品集」` |
| `desc` | `<meta name="description">` | `hero.tagline` |
| `logo` | 顶栏左上角标 | `assets/hero/avatar.jpg` |
| `avatar` | 首屏圆形大头像 | `assets/hero/avatar.jpg` |
| `pages` | 页面顺序 / 标题 / 导航名 / 每页板块（见下） | 内置 5 页：影像·摄影·图文·关于·联系 |
| `sections` | 老格式分块顺序与显隐（**仅兼容**，见下） | —— |
| `theme` | 默认配色（`mode` / `darkAt` / `lightAt`，见下） | `{mode:'time', darkAt:'19:00', lightAt:'07:00'}` |

> ⚠️ 老站（`site` 块缺失）里 `brand` 会退化成 `hero.name`。

### site.logo 的两个细节

1. **传了 logo 会换一种显示方式**：`.mark` 本来是 36px 圆形 + `object-fit:cover`
   （按头像设计的）。横版字标塞进圆里只会剩下中间一块色块，所以 `site.logo` 有值时
   生成器给 img 加 `mark-wm` 类：长方形、`contain`、去掉渐变底和描边。
2. **后台传 logo 不转 JPEG**：`server.py` 的 `fit_logo()` 只缩最长边（≤512），
   png 存 png、保留透明通道。走通用压缩会把透明底压成白底，深色顶栏上就是一块白斑。

### site.pages —— 页面与板块（v1.8.0 起是唯一的顺序来源）

**两层：页面（Page）→ 板块（Block）。** 一个页面 = 网页上的一屏 + 导航里的一项；
板块 = 这一屏放的是哪类内容（`work` / `photo` / `papers` …）。内容仍然住在顶层键里，
页面只记「谁放在哪、叫什么名、显不显示」。

```json
"pages": [
  {
    "id": "pg_work",
    "show": true,
    "nav": "影像",
    "title": "",
    "titleEn": "",
    "intro": "",
    "blocks": [{ "type": "work", "title": "", "intro": "" }]
  },
  {
    "id": "pg_pg4k2x",
    "show": true,
    "nav": "",
    "title": "论文与研究",
    "titleEn": "",
    "intro": "",
    "blocks": [{ "type": "papers" }]
  }
]
```

| 键 | 说明 | 缺省 |
|---|---|---|
| `id` | 页面 id，多块页的锚点用它（`#pg_xxxx`） | `pg1`、`pg2`… |
| `show` | `false` → 这一页不上网页、不进导航，**内容一条不删** | `true` |
| `nav` | 导航短名（2–4 字最好） | 板块的默认短名（`NAV_LABEL`） |
| `title` | 页面大标题 | 板块默认标题 |
| `titleEn` | 标题右边那行英文小字 | 板块默认英文 |
| `intro` | 页面简介，只在该页挂**多块**时单独出一屏页头 | 板块的 `sub` |
| `blocks` | 该页的板块，`type` 取 `work/photo/papers/opeds/design/proposals/projects/about/contact/digital` | —— |

规则（改数据前先看这五条）：

1. **一种内容只能挂在一页上。** 后台新建页面时如果那类内容已在别页，会**整块挪过来**
   （`data.json` 里内容一个字不删，原页空了就自动收起来）。
2. **空页面不占位。** `blocks` 全是被 `_OPTIONAL` 过滤掉的类型（没数据）时，整页跳过 ——
   不渲染、不进导航、不占分区序号。
3. **`contact` 特殊。** 它不进导航，走顶栏右上那个 CTA；关掉它 CTA 也跟着消失。
4. **页面上限 10**（后台 `PAGE_MAX`）。超了后台直接拦，不弹窗。
5. **多块页的锚点变了**：单块页锚点还是那一块（`#work`、`#photo` 不变），
   多块页锚点是页面 id（`#pg_xxxx`）——老链接不会断，新链接按页走。
6. `site.pages` 缺失 → 退回 `site.sections` 或内置默认顺序（老站不用动数据）。

### site.sections —— 老格式（仅兼容）

```json
"sections": [
  { "key": "about",    "show": true  },
  { "key": "photo",    "show": true  },
  { "key": "work",     "show": false },
  { "key": "projects", "show": true  },
  { "key": "contact",  "show": true  }
]
```

- `key` 只能取 `work / digital / photo / projects / about / contact`（老格式不认
  `papers/opeds/design/proposals`，要挂这四类必须用 `site.pages`）。
- 写成字符串数组（`["about", "photo"]`）也认，等价于全部 `show: true`。
- 只在 `site.pages` 缺失时才读。后台每次保存会顺手重写一份，纯粹给老生成器兜底。
- 判空用的是 `is None`，不是真假判断。写 `[]` 是有效配置，别被当成「没配」。

> 如果站名和本人姓名不是一个词（例如站名「见山手记」、姓名「陈屿」），**必须补 `site.brand`**，
> 否则重新生成会把首屏大标题换成人名。补上后产物可做到与旧版逐字节一致。

### site.theme —— 网站配色（v1.6.0）

```json
"theme": { "mode": "time", "darkAt": "19:00", "lightAt": "07:00" }
```

| 键 | 取值 | 说明 |
|---|---|---|
| `mode` | `system` / `light` / `dark` / `time` | 访客打开时的**默认**配色。键缺失时按 `system`；新站骨架默认写 `time`（19:00 深 / 07:00 浅） |
| `darkAt` | `"HH:MM"` | 仅 `mode: "time"` 用。几点转深色，缺省 `19:00` |
| `lightAt` | `"HH:MM"` | 仅 `mode: "time"` 用。几点转浅色，缺省 `07:00` |

- `time` 的深色区间是 **`[darkAt, lightAt)`**，**支持跨午夜**（19:00→07:00 即晚上深、白天浅）。
  `darkAt > lightAt` 时按「跨夜」算；两者相等会退化成**全天浅色**（半开区间取不到任何深色点），别这么配。
- 后台「网站配色」里改，落在这一层。老数据没有 `theme` 键 → 按 `system` 处理，不会报错。
- **优先级**：访客手点过顶栏按钮就按 `localStorage['pf-theme']` 来，`theme` 只是没手选时的默认值。
  也就是说站长定的是「默认」，不是「强制」。
- 生成器把这段配置写进 `<head>` 的内联脚本（`<style>` 之前），目的是首帧就定好色，避免闪白。

## hero —— 首屏

```json
{
  "kick": "Portfolio — 2026 影像 · 摄影 · 内容",
  "name": "陈屿",
  "en": "CHEN YU",
  "tagline": "一句话说清你是谁、会什么、做过什么。写事实和数字，别写形容词。",
  "stats": [["210+", "条成片产出"], ["86万+", "累计播放"]],
  "hm":    [["坐标", "杭州"], ["方向", "影像 / 内容运营"]],
  "vert":  "FILM — PHOTOGRAPHY — CONTENT"
}
```

- `stats` = 首屏那排大数字，**建议 4 条**（多了会挤）。
- `hm` = 右上角那几行小字。
- `vert` 已废弃（生成器不读，只做数据留存）。

## work —— 影像作品

```json
{
  "sub": "分区副标题，留空则整段不渲染",
  "groups": [
    {
      "name": "汽车与商业广告",
      "en": "AUTOMOTIVE",
      "type": "special",
      "sub": "分组副标题，可空",
      "hidden": false,
      "items": [ ... ]
    }
  ]
}
```

- ⚠️ `work` 是 **dict 不是数组**。`groups[i]` 的键是 `name` / `en` / `type` / `items` / `sub` —— **没有 `title`**。
- `type` 取值决定卡的形态：`special`（1 张大卡 + 封面墙）/ `cards`（普通卡阵）/
  `aerial` / `net` / `lists`（空 `items` 也会渲染）。
- 组级 `hidden: true` → 整组不渲染（版式实验组用这个，数据留着以后还能翻回来比）。

### items[j] 的字段（共 16 个）

```json
{
  "img": "assets/cover/xxx.jpg",
  "title": "海岸线以北 · 秋冬特辑",
  "kick": "汽车广告 · 山路试驾 · 2026.09",
  "desc": "",
  "badge": "",
  "txtbig": null,
  "txttag": null,
  "stat": [],
  "dutylab": "片中职务",
  "duty": ["策划", "摄影师", "剪辑师"],
  "go": "微信视频号",
  "href": "https://weixin.qq.com/sph/xxx",
  "big": false,
  "series": "单支",
  "subs": [],
  "hidden": false
}
```

- `duty` = 你在片中的职务标签（**别写「参与」，写具体动作**）。
- `go` + `href` = 右下角跳转按钮。
- `hidden: true` → 该卡不进网页（缺封面 / 待单独设计时用）。
- `subs` = 子条目（同组内的小卡），同样支持 `hidden`。

## photo —— 摄影

```json
{
  "sub": "分区副标题",
  "cats": [
    ["aerial", "航拍", "Aerial", 12, "无人机视角下的城市街区、古建与山野。"]
  ]
}
```

- ⚠️ `cats[i]` 是**位置数组**：`[key, 中文名, 英文名, 张数, 简介?]` —— **一律按下标取，别用元组解包**
  （老数据只有 4 位，解包直接炸）。写第 5 位前先补空串。
- `key` 对应图片文件名前缀：`assets/photo2/<key>_01.jpg … _<张数>.jpg`。
- 缩略图在 `assets/photo2/t/<key>_01.jpg` —— **网页引用的是缩略图**（`data-full` 才指原图），
  所以发布时 **`photo2/t/` 不能排除**（见 `references/pitfalls.md`）。
- 图片真实宽高比决定拼图格大小（生成器用 Pillow 读 `t/` 下的图算）。

## projects —— AI 与编程实践

```json
{
  "sub": "分区副标题",
  "groups": [
    {
      "name": "内容生产工具", "en": "CONTENT TOOLS",
      "items": [{
        "no": "01",
        "kind": "单文件网站 · 可离线分发",
        "title": "项目名",
        "oneline": "一句话说明，卡片收起时显示",
        "desc": "展开后的完整说明",
        "stack": ["HTML", "Python"],
        "metrics": [["97", "张影像作品收录"]],
        "shots": [["assets/projects/a.jpg", "图注"]]
      }]
    }
  ]
}
```

## papers / opeds / design / proposals —— 四类文字内容

四类都是 **`site.pages` 里挂一块就多一页**（老 `sections` 格式不认它们）。
数据缺失时整块跳过；数据在但 `items` / `projects` 为空时，页面会渲染出一个只有标题的空分区 ——
所以「建了页还没填内容」是允许的中间状态，不是 bug。

```json
"papers": {
  "h2": "论文与研究", "h2en": "Research", "sub": "分区副标题",
  "items": [{
    "no": "01", "kind": "课程论文 · 未发表",
    "title": "标题", "cover": "assets/papers/x.jpg", "cover_note": "A4 · 封面",
    "oneline": "一句话结论",
    "points": ["要点一", "要点二"],
    "metrics": [["10 类", "CNews 分类"]],
    "pages": [["assets/papers/x_p2.jpg", "第二页"]],
    "pages_note": "内页说明"
  }]
}
```

| 键 | 列表键 | 每条字段 | 适合 |
|---|---|---|---|
| `papers` | `items` | `no / kind / title / cover / cover_note / oneline / points[] / metrics[] / pages[] / pages_note` | 论文、调研报告（大封面 + 内页） |
| `opeds` | `items` | `no / kind / title / cover / oneline / quote` | 新闻评论、随笔（一行一条） |
| `design` | `projects` | `title / badge / desc / foot / specs[] / groups[]` | 平面设计、海报、物料（分组网格） |
| `proposals` | `items` | `title / kind / left_label / right_label / oneline / left[] / right[] / foot` | 策划案、提案（左问题右方案） |

- 共有的头字段：`h2`（分区标题）、`h2en`（英文小标）、`sub`（一句话说明）；
  `opeds` 还多一个 `counts`（小字统计）。
- `design.projects[].groups` 是**分组对象数组**：一组一套网格，键是
  `{name, note, cols, items:[], wide:[], note_card:{}}`。后台用**表单**编辑它
  （组 → 图两层，图能选、能排序、版式走下拉），不再是裸 JSON 文本框；
  `metrics` / `specs` / `pages` / `left` / `right` 都是 `[值, 说明]` 二元组数组。
- **`papers.items[].pages` 通常不用手写**：后台每一条论文的**卡片最前面**有
  「从 PDF / Word 导入」+「第 1 页当封面」勾选，选文件就自动把前 4 页渲染成
  `assets/papers/<文件名>_pN.jpg`，回填成 `[["assets/papers/论文_p1.jpg", "P1"], …]`，
  第 1 页同时写进 `cover`。手填仍然支持（路径留空 = 网页上显示「待补」虚线框），
  两条路的数据形状完全一样 —— 导入只是替你把截图、命名、抄路径这几步做掉。
- 设计物料的单格是 `[图片路径, 图注, 版式]` 三元组，**版式决定格子高宽比**：

  | 版式 | 高宽比 | 适合 |
  |---|---|---|
  | 留空 或 `tall` | 按图片原比例 | 竖版海报、长图（默认） |
  | `s16` | 16:9 | 横版 banner、屏幕物料 |
  | `stall` | 1130:1600 | A 系列竖版（展板、易拉宝） |
  | `ssq` | 1:1 | 社媒方图、商品主图、门票 |
  | `sflag` | 1445:334 | 超宽横幅（展台围挡、门头） |

  ⚠️ 版式的**真源是 `build/site.css` 里的 `.dz-t.xxx{aspect-ratio:…}`**。
  加新版式要两边一起改（CSS 加规则 + `validate_data.py` 的 `DZ_SHAPES` 加键）。
- ⚠️ 用后台「新建页面」建这四类页时，**先建页再填内容**：页建好后编辑器从「未分配」搬进该页签，
  才能点「+ 新建一篇」。反过来先手工在 `data.json` 里造数据也行，但字段名要对上上表。

## about —— 关于我（简历）

```json
{
  "sub": "分区副标题",
  "facts": [["求职意向", "内容运营"], ["学校", "江州传媒学院"]],
  "contact": [["微信 xxx", "#"]],
  "blocks": [ ... ]
}
```

`blocks[i]` 支持 **6 类**内容，按顺序渲染：

| 键 | 说明 |
|---|---|
| `h` | 小标题 |
| `ps` | 段落数组 |
| `rows` | 经历条目 `{t, org, role, notes[]}` |
| `dsum` | 数据能力摘要 `[名称, 说明]`（说明里可含 `<b>`） |
| `ds` | 简表 |
| `awards` | 奖项 |

> ⚠️ 后台原先只能编辑其中 4 类，`rows` / `dsum` / 形象照曾长期没有入口（2026-10-08 已补齐）。
> 加了新字段后**务必确认生成器真的读它**，否则是摆设。

形象照固定路径 `assets/about/portrait.jpg`（后台走 `overwrite` 定点覆盖，不会存成 `portrait-1.jpg`）。

## awards —— 奖项

```json
{ "作品标题（必须与 items[].title 一字不差）": [["国家级银奖", "2025 外研社·国才杯", "assets/award/x.jpg"]] }
```

- 靠 **标题** 挂到对应的视频卡上，所以跨组移动卡片不会掉。
- 第三条是奖状图路径，**留空则只显示文字徽章**。
- 标题对不上的老奖项：后台会标黄提示，不会静默消失。

## stars —— 「只看代表作」

纯标题数组，可跨分类。生成器跟实际卡片比对，对不上的会在控制台报警。
留空则默认 = 挂了奖的那几支。

## digital —— 数码内容（可选整块，**只对老数据保留**）

**只有 `data.json` 里有 `digital` 键时才会渲染**，顶栏也会多一个「数码」入口。
不想要这块就整块删掉（整块下线时不会留断号，因为分区序号是按实际渲染顺序自增的）。

⚠️ **后台不给它建页，也没有编辑器** —— 新建页面的 10 张模板卡里没有「数码」，
这是刻意的（`admin/index.html` 的 `BLOCK_EDITOR` 里没有登记它：
没数据、没界面，建出来只会是空页）。它存在的意义是**渲染早期站点留下的 `digital` 数据**，
让老站升级模板后那块内容不至于凭空消失。要改这类内容只有两条路：
直接编辑 `data.json`，或者把它迁移成 `work` / `projects`（后台有编辑器）。

## contact / footer

```json
{
  "contact": {
    "kick": "Contact", "h2": "谢谢观看", "sub": "合作、约拍、写稿，微信最快。",
    "big":    [["13800000000", "tel:13800000000"], ["a@b.com ↗", "mailto:a@b.com"]],
    "plinks": [["作品主页", "https://..."]]
  },
  "footer": "© 2026 陈屿 杭州 · 影像 / 内容运营"
}
```

`big` = 大号联系按钮（电话 / 邮箱），`plinks` = 平台链接。
`big` 里的 ` ↗` 后缀会被生成器自动剥掉（图标另外加）。
