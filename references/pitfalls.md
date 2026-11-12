# 踩坑清单

全部是在真实项目里踩过、并已修掉的。新建站点时**照抄结论，别重新踩一遍**。
每条都写了「症状 → 根因 → 修法」，因为症状通常指向错误的方向。

---

## 一、生成器（`build/gen_site.py`）

### 1. 摄影分类是位置数组，不能用元组解包
- **症状**：老数据上生成直接炸。
- **根因**：`cats[i]` 是 `[key, 中文, 英文, 张数, 简介?]`，老数据只有 4 位。
- **修法**：一律按下标取；写第 5 位前先补空串。

### 2. 序号函数别叫 `cn`
- **症状**：摄影区的分类名变量被遮蔽，渲染出错。
- **修法**：用 `cnnum()`。

### 3. 数据条目的 `title` 用「位置 vs 语义」要分清
- `work.groups[i]` **没有 `title` 键**（是 `name`），`items[j]` 才有 `title`。
- `awards` 的键 = `items[].title`，**必须一字不差**。生成器收尾会打印对不上的标题，
  看到 `⚠ stars 清单里这些标题没匹配到任何卡片` 就去核对拼写。

### 4. 加了输入框却没让生成器读
- **症状**：后台能填、网页不变。
- **曾抓到两个**：`hero.vert`（从未被读，已换掉）、`about.sub`（生成器没渲染，已补）。
- **修法**：**加字段的同一轮里就去生成器确认它读这个键**。

### 5. `exec` 沙箱试生成要传一个命名空间
- **症状**：`NameError: name 'H' is not defined`。
- **根因**：`exec(code, g, l)` 传两个命名空间时，模块级赋值进 `l`，而 lambda 的
  `__globals__` 只认 `g`。
- **修法**：`exec(code, g)`，只传一个。

---

## 二、后台服务端（`admin/server.py`）

### 6. ⭐⭐ 中文文件名图片 100% 404
- **症状**：「缩略图偶发不显示」。看起来像随机，其实**按文件名命中**。
- **根因**：`do_GET` 用 `self.path.split('?')[0]` 直接拼磁盘路径，**没做 URL 解码**。
  浏览器发的是 percent-encoded：`图片(30).jpg` → `%E5%9B%BE%E7%89%87(30).jpg`。
  藏得久是因为纯 ASCII 名（`aerial_02.jpg`）不受影响。
- **修法**：
  ```python
  from urllib.parse import unquote
  def _safe(self, root, rel):
      rel = unquote(rel)                        # ① 解码
      p = (root / rel).resolve(); root = root.resolve()
      if not (p == root or root in p.parents):  # ② 越界挡住
          return None
      return p
  ```
- ⚠️ **解码和越界检查必须成对出现**：加了 `unquote` 之后 `../` 才真正能穿越
  （修之前 `/pf/../admin/server.py` 会 200 泄漏 20 KB 源码）。

### 7. 子进程输出必须钉 UTF-8
- **症状**：点「生成网页」出来的日志全是 `U+FFFD`（乱码）。
- **根因**：本机 ANSI 代码页 = 936(GBK)。Python 的 stdout 变成**管道**时按
  `locale.getpreferredencoding()` 选编码 → 子进程吐 GBK 字节，父进程按 utf-8 解。
- **修法**：跑中文脚本时 `subprocess.run(..., env=_child_env())`，
  `_child_env()` 里设 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`；
  解码用 `decode_out()`（先 utf-8 → 失败退 gbk → 再失败才 replace）。

### 8. `overwrite` 参数不能写 `bool(x)`
- **症状**：形象照换不掉（被存成 `portrait-1.jpg`）。
- **根因**：非定点上传遇重名会加序号；`bool("false")` 是 `True` 会误覆盖。
- **修法**：只认 `True` 或 `'1'/'true'/'yes'`。

### 9. 备份文件按秒命名会撞名
- **修法**：撞名时补序号（`while _b.exists()`）。

### 10. 预览必须破缓存
- **症状**：改了内容，预览窗口还是旧的。
- **修法**：`previewURL()` = `PF + 'index.html?t=' + Date.now()`；
  已开窗口用 `win.location.href = url`（比 `reload()` 稳），
  后端 `Cache-Control` 设 `no-store`。
- ⚠️ 改 `_send` / `_file` 时**别忘了 `_json`** —— 漏掉会让所有 JSON 接口抛
  `AttributeError`，症状是「端口能连、请求立刻被拒」。

### 11. 多字段文本框的分隔符：先查数据里有没有
- **症状**：角色字段被拦腰截断。
- **根因**：用全角 `｜` 分隔，而真实数据里 `role` 本身就含全角｜。
- **修法**：**先统计候选分隔符在全部数据里的出现次数**（本次全角｜冲突 1 次，
  半角 `|` / `;;` / `@@` / tab 均 0 次 → 用半角 `|`）；
  再配 `splitRow(s, n)`：优先半角、无半角才退全角（手输容错）、
  **段数超限不截断而是并回末格**。

### 12. 静态文件服务的 t/ 目录
后台所有图片类型都生成缩略图（`TH_W = {'photo2':520,'award':240,'projects':300}`，其余 260）。
老图不会自己长缩略图 → 需要一个「补缩略图」入口做 backfill。

---

## 三、发布上线

### 13. ⭐⭐ `_publish_tmp/` 是手工快照，一定会过期
- **症状**：线上 4 张图裂开。
- **根因**：`portfolio/` 改完从没同步回发布目录，而 `data.json` 引用的路径在
  `portfolio/` 下**一个不少**。
- **修法**：上线前**固定先跑 `scripts/sync_publish.py`**。

### 14. ⭐⭐ 核验必须按「页面引用清单」全量核，不能抽样
- **症状**：抽查 40 张全过、上线后仍有裂图。
- **修法**：`scripts/check_site.py` —— 从 `index.html` 抽出所有 `src` / `href` / `url()`
  逐条比对磁盘。

### 15. ⭐⭐ `assets/photo2/t/` 不能排除
- **症状**：摄影区 85 张全裂。
- **根因**：以为 `assets/*/t/` 全是后台专用，一刀切排掉。
  实际 **`photo2/t/` 就是网页正在用的资源**（`<figure><img src>` 指的它，`data-full` 才是原图）。
- **修法**：`KEEP_T = {'photo2'}`，只排除其它 kind 的 `t/`。

### 16. ⭐ 根目录下被引用的散件要一起拷
- **症状**：favicon 线上 404。
- **根因**：生成器只在 `<head>` 里**写引用、不搬文件**，而同步脚本只显式拷 `index.html`。
- **修法**：`sync_publish.py` 按引用清单把根下散件一并带上（本技能已改成这样）。

### 17. 平台域名不支持绑自有域名
平台的 Host 有硬白名单，只认 `{port}-{rid}` 格式，实测报
`invalid host subdomain: subdomain "xxx" not in {port}-{rid} format`。
即使 Cloudflare CNAME + 橙云回源过去也会被 400 拒绝。
**要绑自有域名必须把内容托管到别处**（GitHub Pages / 对象存储），不能让平台回源。

### 18. Cloudflare 橙云会注入 HTML
线上 md5 与本地不一致是正常的（注入分析脚本，约 +370 B）。
**别用 md5 比对线上/本地一致性**。
NS 切换也别信控制台显示，必须 `nslookup -type=NS <域名> <公共DNS>` 实测。

---

## 四、截图 / 量测（排查样式问题时用）

1. **探针页必须落在站点根下** —— 写在子目录会让 `assets/...` 相对路径全废，好图全报 broken。
2. `--screenshot` 只截可视区 → 要整页截 + 后切。
3. 每次换独立 `--user-data-dir`，否则被已有浏览器接管。
4. 无头浏览器**视口最小 504px**（`--window-size=390` 实测 `clientWidth=504`）
   → 移动端必须套 `<iframe width=390>`；而 `file://` 的 iframe 跨源读不到 DOM，
   量测要起本地 `http.server` 走 `127.0.0.1`。
5. iframe 的 `contentDocument` **必须在循环里重取**（导航前是 `about:blank`，抓死就永远是空）。
6. 量测前注入 `.fade{opacity:1!important;transform:none!important}`。
7. 隐藏其它 section 时写 `HIDE + '<style>'` 或插到 `</head>` 前 ——
   **别 `src.replace('<style>', hide)`**：`hide` 自带 `<style>` 标签，
   会吃掉页面 CSS 的开始标签，整份样式被当正文渲出来。

---

## 五、绝对定位（`position:absolute` 的基准）

- **改 `right`/`bottom` 数值没用**时，先看 `offsetParent` ——
  `position:absolute` 认「最近的已定位祖先」。
  奖状浮层 `.vawards` 嵌在 `.vinfo`（已定位）里时基准就是 `.vinfo`，永远贴信息区的角。
- **必须挂 `.vcard`**（与 `.vinfo` 平级），`right:24px;bottom:22px`。
  挂 `.vinfo` 内部时它脱离文档流，`.vduty` 职务标签行不知道它占位 → 同一水平带重叠。
- **中间档（681–1100px）要给奖状让位**：`.vinfo{width:min(46%,520px)}` +
  奖状 `max-width:min(230px,40%)`。不收窄的话 W ≤ 900px 时横向重叠最多 -103px。
- **≤680px 仍要绝对定位贴右下角**（`right:18px;bottom:18px`），
  **不能写 `position:static`**，否则会掉到卡片最下面。
- `bottom:34px` 的来源：`.vinfo{position:absolute;bottom:34px}`，
  而 `.vduty` 是它最后一个子元素 → 职务标签底边 = 距卡底 34px。改 `.vinfo` 的 bottom 要同步改这里。

---

## 六、后端交互（后台前端）

### 19. 跨维度下标不能直接比
`moveItem(from, to, atTop)` 里 `from` 是 **items 下标**、`to` 是 **groups 下标**，两套坐标系。
同组守卫必须写 `if (curG === to) return;`。写成 `if (from === to)` 会导致
「移到本组」时守卫失效、把作品悄悄挪到本组末尾。
**纯读 JS 看不出来，必须拿真实 data.json 跑用例**（同组移动应被忽略）才暴露。

### 20. 计数不更新
`$('#nA').textContent = ...` 只在 `init()` 里算一次 → 抽成 `refreshCounts()`，
在 `renderAll()` 开头**和 `markDirty()` 早退之前**两处调用
（`markDirty` 有 `if (dirty) return;`，放后面第二次改动就不刷新了）。

### 21. 作品移动入口要归一
列表 `⇄` 按钮 / 表单「移到分组」下拉 / 其它入口 —— **一律调同一个 `moveItem()`，别另写一份**。

### 22. ⚠️ `filter()` 返回副本，排序和删除会静默失效
- **症状**：后台「页面分块」里点 ↑↓ 没反应、点 ✕ 删不掉；但勾「显示」开关却是好的。
- **根因**：读取函数写成了 `return st.sections.filter(s => SEC_META[s.key])`，
  拿到的是**新数组**。交换 / `splice` 都作用在副本上，改完重画又按原数组渲染 → 纹丝不动。
  开关之所以正常，是因为 `arr[i].show = x` 改的是**同一个对象引用**。
- **修法**：读取函数返回**原数组**；要滤掉无效项就直接把原数组**重新赋值**。
  改完必须用真实数据跑一遍点击用例（下移 / 删除 / 加回），只看渲染看不出来。

### 23. `sections` 判空不能写真假判断
- **症状**：后台把所有分块删光、保存后，网页又变回全部分区。
- **根因**：`raw = SITE.get('sections'); if not raw:` —— `[]` 是假值，
  被当成「没配置」走了默认全开分支。
- **修法**：判 `if raw is None:`。**空数组是有效配置**（一块都不要）。

### 24. logo 走通用压缩会丢透明
- **症状**：传了带透明底的 PNG logo，顶栏上变成一块白方块（深色站点尤其难看）。
- **根因**：`compress()` 一律存 JPEG，Alpha 通道被白底合成掉。
- **修法**：logo 单独一条路（`fit_logo()`）：只缩最长边、按原扩展名存；
  svg 直接原样保留。缩略图同理 —— `thumb()` 按目标扩展名选格式，`.png` 存 PNG 并保 Alpha。

### 25. 后台保存前先建目录，会让脚手架以为目录非空
- **症状**：`setup_site.py` 第一步就报「目录非空，加 --force 才继续」。
- **根因**：脚本先写了 `_setup/profile.json`，再调 `new_site.py`，
  而 `new_site` 检查的是「目录里有东西吗」。
- **修法**：`setup_site` 只在目录里**仅剩 `_setup/`** 时自动补 `--force`，
  其余情况仍然要求用户显式给（不能因为图省事就把保护拆了）。

### 26. 抓网页拿到的是乱码 / 标题全空
- **症状**：`fetch_refs.py` 抓某些站，标题、简介、og:image 全空。
- **根因**：部分 CDN **不管请求头都塞 gzip**，按文本解码得到的是压缩字节。
- **修法**：请求头写 `Accept-Encoding: identity`，同时按魔数（`\x1f\x8b`）和
  `Content-Encoding` 双向兜底解压。判编码的顺序是 `Content-Type` 里的 charset →
  HTML 里的 `<meta charset>` → UTF-8。

### 27. 单文件打包漏内联「不在 src 里」的图
- **症状**：打包出来的单 HTML 打开是好的，但点开摄影图看大图、点奖项徽标——一片裂图。
- **根因**：内联只枚举了 `src / href / poster`。摄影墙的原图挂在 **`data-full`**、
  奖项徽标挂在 **`data-img`**，都是 JS 灯箱读取的，正则没覆盖到。
- **修法**：不要枚举属性名，改成「**值看起来就是本地媒体路径**（有媒体扩展名、
  无协议头、无 `%xx`、无 `#`）就内联」。这样新增任何 `data-*` 属性都不会再漏。
- **自检**：打包后 grep 一遍 `="assets/` 和 `assets/`，**必须是 0**。
  CSS 里的 `url(%23n)` 这类内联 SVG 噪声会被误伤，靠「有扩展名才算」这条规则挡住。

### 28. `showSaveFilePicker` 先 fetch 再要句柄 → 点了没反应
- **症状**：点「存为单文件」，按钮转了一下就复原，既不弹保存框也不报错。
- **根因**：`showSaveFilePicker()` 要求落在**用户手势**的 transient activation 窗口内。
  如果先 `await fetch(...)` 再调它，打包只要超过几秒，手势就过期了，
  Chrome 抛 `NotAllowedError`，被 `catch` 吞掉，用户看到的就是「没反应」。
- **修法**：**先要句柄，再 fetch**——
  `const h = await showSaveFilePicker(...)` → `const r = await fetch(url)` → `h.createWritable()`。
  反过来必炸。另外 `AbortError` 是用户自己取消，要静默 return，别弹「保存失败」。

### 29. 下载中文文件名乱码
- **症状**：`Content-Disposition` 只写 `filename="见山手记.html"`，Chrome 存成乱码，Safari 存成 `download`。
- **修法**：两个都给——`filename="portfolio-20261017.html"`（纯 ASCII 兜底，给不认 RFC 5987 的）
  + `filename*=UTF-8''%E8%A7%81...`（百分号编码的 UTF-8，正路）。
  兜底名别用 `name.encode('ascii','replace')`，中文会全变 `?`，丑且难认。

### 30. 后台说明文字：删过头 → 又加回来
- **症状**：第一版写满屏说明，被要求「别加解释性文字」；照做全删光，转头又被要求
  「解释性文字可以保留给用户的，不是给网站设计者的」。来回改两遍。
- **根因**：把「解释」当成了一个类别。其实是两类，混在一起判断就会一刀切：

  | 类型 | 例子 | 处理 |
  |---|---|---|
  | 给**操作者**（用这个后台的人） | 「改完点右上角『生成网页』，网页才会变」<br>「取消勾选＝先藏起来，内容还在」<br>「留空就不显示这个按钮」 | **留** |
  | 给**设计者**（看代码、维护的人） | 「生成器按 `site.sections` 顺序渲染」<br>「`show:false` 的块不进导航、不占序号」<br>「空串会落回 `DEFAULT_CTA`」 | **删** |

- **判据一句话**：说的是「你能做什么、点了会怎样」→ 留；说的是「系统内部怎么实现」→ 删。
- **做法**：卡片内说明用灰字 `.tip.plain` 写一句；整页引导用蓝框 `.tip`。
  分块行下面那行「作品分组卡片，一屏一张」属于**内容描述**，帮用户判断要不要藏，也算「给用户的」。

---

## 七、环境

- 本机 ANSI 代码页 = **936(GBK)**，任何跨进程的中文都要显式钉 UTF-8。
- 带 Pillow 的解释器：随便一个装了 `Pillow` 的 Python 3.11+ 都行，用环境变量 `SITE_PY` 指给脚本
  （`SITE_PY=/path/to/python python scripts/build.py --site ...`）。
  没装 Pillow 时生成器仍能跑，但摄影墙的宽高比会全部退回默认值、缩略图与压缩功能失效。
- 清理文件走**回收站**，不硬删。

### 31. 加了个 36px 按钮，窄屏顶栏就崩了
- **症状**：430px 下顶栏「联系合作」被挤出屏幕右侧，nav 的右圆角也看不见；
  更糟的是 body 被撑宽，首屏 `.tagline` 右侧的字被切掉。
- **根因**：顶栏是一行 flex（品牌 + 4~5 个导航 + 主题按钮 + CTA），本来就快满，
  多 36px 直接溢出。第一反应是加 `flex-wrap:wrap` —— **结果更差**：
  换行后的第二行被圆角/backdrop-filter 隐式裁掉，而且撑高 nav 顺带把页面撑宽。
- **修法**：让**导航区自己横向滚**，其余固定：
  ```css
  @media(max-width:680px){
    .navlinks{flex:1 1 auto;min-width:0;margin-left:0;flex-wrap:nowrap;overflow-x:auto;
      scrollbar-width:none;-ms-overflow-style:none;
      -webkit-mask-image:linear-gradient(90deg,#000 0,#000 calc(100% - 18px),transparent 100%);
      mask-image:linear-gradient(90deg,#000 0,#000 calc(100% - 18px),transparent 100%)}
    .navlinks a{padding:7px 10px;font-size:12.5px}
    .bid em{display:none}
    .nav-cta{margin-left:0;flex:none}
    .themebtn{flex:none;width:30px;height:30px;margin-left:0}
  }
  ```
  右端那道渐隐不是装饰 —— 它是"还能往右滑"的唯一提示，删掉用户就以为导航就这几项。
- **附带坑（真踩了两次）**：`.themebtn` 的基础样式定义在媒体查询**之后**，
  所以媒体查询里的 `width:30px` 会被后面的 `width:36px` 覆盖、静默失效。
  单文件 CSS 里「后写的赢」很容易中招，窄屏尺寸要么写在最末尾，要么加更高优先级。

### 32. headless 截图的视口 ≠ `--window-size`
- **症状**：`--window-size=430,1100` 截图，顶栏明显被切；但用 430px 宽的 iframe 量
  `getBoundingClientRect`，所有元素右边界都在 430 以内、逻辑完全正确。两边对不上。
- **根因**：headless 的截图缓冲区按 `--window-size` 出图，但**布局视口**可能更宽
  （滚动条、设备像素比都会参与），于是内容按更宽的宽度排完再裁到 430 —— 看起来像溢出。
- **修法**：验证窄屏别信这个截图。写个测试页放 `<iframe width="430">`，量
  `getBoundingClientRect()` / `scrollWidth`，或者干脆截 iframe 那张图。
  这次就是靠 iframe 测量才确认「布局其实是对的」，避免了继续瞎改 CSS。

### 33. 分段控件的联动行，别用 `style.display = ''` 显隐
- **症状**：「网站配色」选「按时间」时，两个时间输入竖着排成两行，本意是并排。
- **根因**：隐藏用 `display:none`，恢复时习惯性写 `el.style.display = ''` ——
  这一下是「清掉内联样式、回到 CSS 里的值」，而 CSS 里 `#thTime` 只有 `gap:16px`，
  默认是 `block`，于是两个 `.fld` 各占一行。
- **修法**：显隐成对写死，别留空字符串：
  ```js
  $('#thTime').style.display = mode === 'time' ? 'flex' : 'none';
  ```
  （`gap:16px` 仍旧留在样式表里，行内只设 `display`，两者互不干扰。）
- **判据**：只要一个元素有「显示/隐藏」两种状态，它的显示值就必须显式写出，
  `''` 这种「交给浏览器」的写法在联动控件里几乎一定会翻车。

## 八、后台启动（v1.7.0 集中修的一批）

### 34. `python` 在 PATH 上，但它是 Microsoft Store 的假 python
- **症状**：双击 bat，窗口闪一下就没了，或者窗口还在、提示「Admin is running」，
  但 8848 上什么都没有。用户以为程序在跑。
- **根因**：Windows 10/11 自带一个 `WindowsApps\python.exe` 的**存根**，它不解释脚本，
  而是打开应用商店然后 `exit 0`。所以「命令存在」「返回码 0」两个判断全都会通过。
- **修法**：候选路径逐个试，**最后必须真跑一次**：
  ```bat
  "%PY%" -c "import http.server" >nul 2>&1 || set "PY="
  ```
  候选顺序：`SITE_PY` → `%USERPROFILE%\.workbuddy\binaries\python\versions\*` →
  `py -3 -c "import sys;print(sys.executable)"` → `where python`（跳过含 `WindowsApps` 的）→ 全部失败就报错。
  **判据：能 import 服务端要用的模块，才算「有 python」。** 文件存在不够。

### 35. `SO_REUSEADDR` 让第二个后台也「绑定成功」
- **症状**：两个后台都显示启动成功，但请求随机落到其中一个 —— 改的是 A 站，
  刷新看到的是 B 站的内容。排查起来像灵异事件。
- **根因**：`HTTPServer.allow_reuse_address = 1` 是默认值；Windows 上 `SO_REUSEADDR`
  允许**绑定已被监听的端口**（不是时间等待期复用，是真抢占）。
- **修法**：启动前先探一次，被占就直接退出并给可操作的提示：
  ```py
  probe = socket.socket(); probe.settimeout(0.4)
  busy = probe.connect_ex(('127.0.0.1', PORT)) == 0
  if busy: print('端口已被占用…'); sys.exit(3)
  ```
  `open_admin.py` 拿到 rc=3 就换下一个端口重试；bat 则直接只开浏览器。
  另外 `/api/health` 回带 `base`（站点绝对路径），启动脚本靠它区分「同一个站已经在跑」
  和「另一个站蹲在这个端口上」。

### 36. 用 `/api/ping` 轮询「起来了没」，永远判成没起来
- **症状**：服务明明已经在听，`open_admin.py` 却等满 25 秒然后报失败；
  server.log 里刷满 `ConnectionAbortedError`。
- **根因**：`/api/ping` 会跑 `env_check()` —— 起子进程验 Pillow、验生成器，冷启动要 1~2 秒。
  轮询方设 0.4s 读超时，读到一半就断，urllib 抛超时，服务端写回时收到 `WinError 10053`。
- **修法**：单开一个**不做任何检查**的 `/api/health`，只回 `{ok, label, pid, base}`，
  轮询用它；`/api/ping` 留给前端「环境自检」按钮。
  同时 `Srv.handle_error` 吞掉 `ConnectionError` —— 浏览器切页/轮询断开都是常态，
  让它刷 traceback 只会把真正的错埋掉。

### 37. 两个后台共用 `server.log`，后起的那个连重定向都打不开
- **症状**：`start /b ... > server.log` 之后窗口闪掉，cmd 打一句
  「另一个程序正在使用此文件，进程无法访问」，然后走进失败分支，日志还是空的。
- **根因**：前一个后台的 stdout 正被重定向到同一个 `server.log`，Windows 不允许再写。
- **修法**：日志名带上端口 —— `server-8848.log`。同一个端口不可能有两个后台
  （35 那条已经拦住了），不同端口天然不冲突。

### 38. 缩略图没生成，首次 `--check` 报二三十处缺失
- **症状**：刚建完站跑 `build.py --check`，`assets/photo2/t/still_01.jpg` 之类一条条列出来，
  提示「体检不通过：28 处缺失」。看着像建站失败了。
- **根因**：摄影墙的 `data.json` 只存「分类 key + 张数」，路径由生成器拼
  `assets/photo2/<key>_NN.jpg`，缩略图同名放 `t/`。`/api/upload` 只给**新传的图**生成缩略图，
  占位图、批量导进来的图都不会自己长出来。
- **修法**：`new_site.py` 造完占位图后调一次 `admin/server.py --thumbs`（内部就是
  `backfill_thumbs()`）。顺带说明：这也意味着**批量导入图片之后必须补一次缩略图**，
  否则摄影墙会去拉原图（33M → 几百 KB 的差别）。

## 九、页面 / 板块与弹窗（v1.8.0）

### 39. ⭐⭐ 点虚线卡上的文字没反应，点边框才有反应
- **症状**：后台「页面设置」末尾那张「＋ 新增页面」虚线卡，**点文字没有跳转，点卡片边缘却正常**。
  同类问题也会出现在任何「按钮里还套了 `<span>` / `<small>` / `<em>`」的列表上。
- **根因**：事件委托里读的是 `e.target.dataset`。真正被点到的是按钮里的那个 `<span>`，
  `dataset` 长在外层 `<button>` 上，于是 `e.target.dataset.pgadd` 是 `undefined`，
  函数在第一个 `if` 就静默 `return` —— 不报错、不提示，看起来就是「点了没反应」。
- **修法**：委托一律先 `closest` 再读 dataset：
  ```js
  const el = e.target.closest('[data-pgadd],[data-pgtog],[data-pgdel],[data-blkadd]');
  if (!el) return;
  const d = el.dataset;
  ```
- **验收**：写探针分别点 `button` / `span` / `small` 三个节点，三个都要能打开弹窗。
  只点卡片本体测不出来 —— 这正是它上线后才被发现的原因。
- **顺带**：`closest` 的选择器要把**所有**带 data 属性的控件列全，漏一个就等于那个按钮失灵。

### 40. ⭐⭐ 弹窗下半截看不见、按钮被裁掉
- **症状**：新建页面弹窗在小窗口下只能看到标题和上半截模板卡，「创建标题」和底部按钮
  完全看不到，也滚不动。用户的第一反应是「点了没跳转」（其实是根本点不到）。
- **根因**：`.modal` 是 `display:flex; flex-direction:column; overflow:hidden`，
  里面正文段没给 `overflow` —— 内容超出就被父级裁掉，而且**不可滚**。
  更隐蔽的是：头部和按钮段没设 `flex:none`，空间不够时会被 flex 一起压缩，
  表现为标题文字和卡片「糊在一起」、按钮被压扁。
- **修法**：三段式，三个属性一个都不能省：
  ```css
  .mk-hd  { flex:none; }                                  /* 头：永不压缩 */
  .mk-body{ flex:1 1 auto; min-height:0; overflow-y:auto;  /* 正文：唯一滚动区 */
            overscroll-behavior:contain; }
  .mk-act { flex:none; }                                  /* 按钮：恒在视口内 */
  ```
  `min-height:0` 是必须的 —— flex 子项默认 `min-height:auto`，不给 0 它就不肯缩，滚动区撑破父级。
- **验收**：不要凭截图判断。用 620px 高的视口量三件事：
  `body.scrollHeight > body.clientHeight`（确实溢出）、`getComputedStyle(body).overflowY === 'auto'`、
  按钮的 `getBoundingClientRect().bottom <= 视口高`。三样都过才算修好。

### 41. ⭐ 宽弹窗调不宽：内联 `style="width:492px"` 压过 CSS 类
- **症状**：加了 `#mdMask.wide .modal{width:780px}`，弹窗纹丝不动还是 492px。
- **根因**：`.modal` 标签上带着 `style="width:492px"`，内联样式优先级高于任何选择器。
- **修法**：把宽度从标签上删干净，改成两条 CSS 管理（窄 / 宽），由 JS 切类名：
  `#mdMask .modal{width:492px}` + `#mdMask.wide .modal{width:780px}`。
- **量宽度的坑**：弹窗入场有 `transform: translateY(16px) scale(.97)`，
  **动画没走完量出来就是 757 而不是 780**（780 × .97 ≈ 757），别当成 bug 去改 CSS。
  截图/量测探针里加 `*{transition:none!important;animation:none!important}` 再量。

### 42. ⭐⭐ 骨架里缺内容键，新建页面的模板卡全是灰的
- **症状**：用 `new_site.py` 建的新站，打开「页面设置 → 新建页面」，
  「设计与物料页 / 文档展示页 / 随笔页 / 方案页」四张卡全是 `disabled`，
  卡片底下写着「这类还没有内容，建了也是空的」—— 而用户**恰恰是想建这类页**。
- **根因**：模板卡的可选性靠 `t in D` 判断（这类内容在 `data.json` 里存在过没有）。
  骨架 `data_skeleton.json` 只给了 `work/photo/projects/about/contact`，
  四类文字内容一个键都没有 → 永远判成「没有」→ 死锁：
  你没页就填不了内容，没内容就建不了页。
- **修法**：骨架里给四类**空壳**（`items: []` / `projects: []` + 头字段）。
  空壳 = 有编辑器、能建页、`blockCount` 为 0 显示「可以新建」；
  建完页再往里加条目不迟。**别用「允许建空页」绕过** —— 生成器那边
  `papers` 不在 `D` 里时整块不渲染，建出来的页会是永久空白。
- **验收**：从零建站后，弹窗里 10 张模板卡 `disabled` 全为 `false`；
  建一页「文档展示页」→ 保存 → 重生成，导航出现「论文」、`<section id="papers">` 存在。

### 43. `check_site.py` 把 JS 里的 `dataset.src = 'user'` 当成资源引用
- **症状**：体检报「缺 7 个引用」，其中一个是 `user`，磁盘上当然没有这个文件。
- **根因**：核验正则是 `(?:src|href)\s*=\s*["']([^"']+)["']`，
  `el.dataset.src = 'user'` 里 `src = 'user'` 正好命中。
- **修法**：加反向断言，别让 `.` 或标识符在前面：`(?<![.\w])(?:src|href)\s*=\s*…`。
  同时把生成器里那个值改成 `dataset.manual = '1'` —— 语义上也更对（标记「访客手选过」）。
- **教训**：**体检脚本的假阳性比漏报更费时间**，因为它会把注意力引到不存在的文件上。
  改完正则要顺手全站再跑一遍，确认引用数没有突然变化。

### 44. 论文 / 设计图点了不放大：灯箱只绑了三个入口
- **症状**：摄影墙、作品卡、项目截图点开都正常，论文封面和设计物料图块点了毫无反应。
  用户的原话是「图片可以点开放大」——他默认全站图片都能点。
- **根因**：灯箱（`#lb`）是**按选择器逐个挂**的，不是一个通用图片查看器：
  早先只挂了 `.vaw[data-img]`（奖状）、`.pjshot`（项目图）、`.pcat figure`（摄影）。
  `papers` / `design` / `opeds` 是后来才加的分区，图是普通 `<img>`，没人给它挂事件。
- **修法**：在同一个全局 click 委托里加一支，**范围按「这一件作品」算**：
  ```js
  const zi = e.target.closest('.pap-cv, .pap-pi, .dz-t, .opd-th');
  if (zi){
    const scope = zi.closest('.pap') || zi.closest('.dz-grp') || zi;   // 论文顺翻内页；设计只在本组翻
    const ims = [...scope.querySelectorAll('img')].filter(im => im.getAttribute('src'));
    const me = zi.querySelector('img');
    if (ims.length && me){ curList = ims.map(...); curIdx = ...; show(); return; }
  }
  ```
- **三个必须**：① 用 `closest`（点到的常是 `img` 或图注 `<em>`）；
  ② 空槽位（「待补」虚线框）没有 `img`，要直接不响应，别弹空灯箱；
  ③ 补 `cursor:zoom-in` + 悬停微放大，否则用户根本不会去点一张「看起来只是配图」的封面。
- **验收**：点封面 → 序号是 `1 / N`，按 → 能翻到内页；点设计图块 → 分母等于**本组**图数
  （不是整节）；点随笔缩略图 → 不出现 `1 / 1`。

### 45. 同一秒里连点两次保存，中间那版备份被盖掉了
- **症状**：改错东西之后想回退，发现「历史版本」里少了一步 —— 两次保存挤在同一秒，
  只剩后一次的快照。
- **根因**：`backup()` 用 `data-%Y%m%d-%H%M%S.json` 命名，秒级精度。
  两次保存落在同一秒，`copy2` 直接覆盖同名文件。
  （同一个坑在图片备份里早踩过，那里补了序号，data.json 这头漏了。）
- **修法**：撞名就补序号 `data-…-224853-2.json`、`-3`。**排序也要跟着改**：
  - 不能按 `mtime` 排 —— `copy2` 会把源文件的 mtime 带过来，同一秒的几份时间戳一样；
  - 也不能按文件名字符串排 —— `.` 的码位比 `-` 大，`data-…-224853.json` 会排到 `-3` 后面，
    新旧正好颠倒。
  - 正解：解析成 `(日期, 时刻, 序号)` 元组再排。
- **验收**：同一秒内连点三次保存，历史版本里应有 3 条，最新那条带 `#3`。

### 46. 抽出去的文件没跟着拷：`site.css` / `validate_data.py` 缺一个就崩
- **症状**：老站点直接跑生成器报「缺 …/build/site.css」；新站点体检不生效（不报错，只是不体检）。
- **根因**：这套模板里 `gen_site.py` 不再自带 CSS 和校验逻辑 —— 它读**同目录**的
  `site.css`（样式）和 `validate_data.py`（数据体检）。`new_site.py` 拷贝清单里少一个，
  站点就是残缺的。生成器对缺 CSS 会直接 `SystemExit`，对缺校验模块则是**静默跳过**（故意的：
  老站点别被挡住），所以后者更容易漏。
- **修法**：`new_site.py` 的模板拷贝必须是这三个一起：
  `gen_site.py` + `site.css` + `validate_data.py`。批量升级已有站点时同样三个一起覆盖。
- **验收**：`scripts/selftest.py` 的 [1/6] 会逐个检查这三个文件在不在。

### 47. 校验白名单和样式表分居两个文件，必然漂移
- **症状**：真实站点的数据被体检判「版式 `'ssq'` 不认识（可用 s16 / tall / stall）」，
  可打开 `site.css` 一看，`.dz-t.ssq{aspect-ratio:1/1}` 明明写着，而且一直渲染正常。
- **根因**：设计物料的版式键由**样式表**定义（`.dz-t.xxx`），校验脚本却另抄了一份白名单。
  两个文件在 `build/` 下各占一行位置，加版式时只改了 CSS —— 校验从此把合法数据当错的。
  当时 CSS 里有四个（`s16 / stall / ssq / sflag`），白名单只写了三个还多写了个没有规则的 `tall`。
- **修法**：`validate_data.py` 里把白名单提成常量 `DZ_SHAPES`，注释写明**真源是 site.css**；
  再让 `selftest.py` 每次自己数一遍两边的差集（`\.dz-t\.([a-z0-9]+)\{` vs 白名单），
  漏一个就红。**凡是「两份配置要一致」的地方，都该有脚本替人数，别靠记性。**
- **顺带**：`tall` 在 CSS 里没有规则 = 不限高、按图片原比例，这是**默认行为**不是漏写，
  白名单里要保留它，否则用户写 `tall` 反而被警告。

### 48. 调试产物写进站点目录，会被打包和发布一起带走
- **症状**：内置 Demo 的 `build/` 里莫名多出一个 13KB 的 `_preview_sizes.png`；
  发布副本、单文件包里也跟着有。
- **根因**：`make_favicon.py` 顺手把「16/32/180 三个尺寸的真实观感」拼成一张预览图，
  存到了 `<site>/build/`。它只是给操作者肉眼确认用的，不属于站点资源，
  但 `build/` 会被整体打包。
- **修法**：写到系统临时目录（`tempfile.gettempdir()/pf_favicon_preview.png`），
  照样打印路径给人看，但不再污染站点。**判据：这个文件是不是 index.html 要引用的？
  不是就别放在站点目录里。** 后台 `server.py` 里 `fn.startswith('_')` 跳过也是同一类补丁，
  属于事后兜底，不如一开始就别写进去。

### 49. `hash()` 对字符串按进程加盐，Demo 永远无法逐字节复现
- **症状**：同一个 `make_demo.py --rebuild` 跑两遍，占位图的配色全变了，
  `index.html` 的 md5 也跟着变 —— 想「改模板前后对比产物」就没法比。
- **根因**：`seed_of()` 用 `abs(hash(rel))` 当随机种子。Python 3 对 `str` 的 `hash`
  默认带随机盐（`PYTHONHASHSEED`），**每个进程都不一样**（`int` 的 hash 才是稳定的）。
- **修法**：换成 `zlib.crc32(rel.encode())` —— 确定值、跨平台一致、够当种子。
  **凡是要「产物可复现」的地方都不能用 `hash()`**，同类雷还有 `set` 的迭代顺序、
  `dict` 里混用不同类型的键、`glob` 不排序。
- **验收**：连跑两次 `--rebuild`，`index.html` 与任意一张占位图 md5 必须相同。

### 50. 标了 `aria-modal` 却不做焦点管理，等于撒谎
- **症状**：灯箱打开后键盘 `Tab` 一走就跑到背后那层页面上（视觉上根本看不见焦点在哪），
  读屏软件也不报「你在对话框里」。关掉灯箱后焦点掉回 `<body>`，键盘用户等于被扔回页首。
- **根因**：`role="dialog" aria-modal="true"` 只是**声明**，浏览器不会替你做焦点管理。
  要么老实删掉这两个属性，要么把三件事做全：
  打开时把焦点移进对话框、`Tab` 在对话框内循环、关闭时把焦点还给打开它的元素。
- **陷阱里的陷阱**：灯箱的图在 `#lb` 里，工具条 `#lbbar` 却是 `#lb` 的**兄弟节点**。
  写成 `lb.querySelectorAll('button, a[href]')` 永远返回空数组 —— 过滤器空转，
  代码不报错、测试也「通过」，功能实际不存在。写焦点陷阱时先把 DOM 结构打印出来数一遍。
- **修法**：
  ```js
  let lastFocus = null;
  // 打开（只在第一次打开时记来源，翻页别覆盖）
  if (!wasOn){ lastFocus = document.activeElement; lbclose.focus({preventScroll:true}); }
  // 关闭
  if (lastFocus && lastFocus.focus){ lastFocus.focus({preventScroll:true}); lastFocus = null; }
  // Tab：显式列出对话框内的可聚焦元素，别从错误的父节点去查
  const f = ['lbfull', 'lbclose'].map(id => document.getElementById(id))
                                 .filter(el => el && el.getClientRects().length);
  ```
- **验收**：无头探针里点开图 → `document.activeElement.id === 'lbclose'`；
  焦点在最后一个元素上按 `Tab` → 回到第一个；`Shift+Tab` 反向同理；`Esc` 关掉后焦点不在 `body`。
- **同类**：顶栏导航只加 `.on` 类不挂 `aria-current`，读屏用户同样不知道自己在第几屏。

### 51. 空站的 `data.json` 里没有 `papers` 条目，字段根本不渲染
- **症状**：改了论文编辑器的字段，起一个新站打开后台，找不到那个控件 —— 以为代码没生效，
  翻来覆去查 JS。
- **根因**：`renderTexts()` 是「数据驱动」的：`data.json` 里没有 `papers` 这个顶层键就只画
  一句「还没有 papers 这个模块」；有键但 `items: []` 时，字段在**条目卡**里，
  一条都没有就什么都不画。新站的骨架数据正好是空数组。
- **修法**：验证字段渲染前先塞一条数据（或拿内置 Demo 试，它有两篇论文）。
  **测 UI 不能只测空站** —— 空站的「空状态」把中间所有控件都挡住了。
- **同类**：`opeds` / `design` / `proposals` 完全一样。

### 52. 删不掉的文件：多半是后台还开着
- **症状**：`--rebuild`、`shutil.rmtree`、`os.remove` 全报
  `Error during a trash operation: Unknown { description: "Some operations were aborted" }`，
  连删一个 0 字节的日志都不行。
- **根因**：**不是回收站本身坏了，是那个文件还被进程占着** —— 最常见的是本地后台
  （`admin/server.py`）还开着，`admin/server-<port>.log` 正被它写。安全删除走的是回收站，
  被占用的文件搬不进去，整批操作就 aborted。
- **修法**：先 `netstat -ano | findstr :8848` 找到 PID 结束掉，再删。
  `make_demo.py` 里 `wipe()` / `_unlink()` 仍保留「rmtree/unlink 失败就直删」的兜底
  （只作用于它自己生成的 Demo 目录），但**兜底也删不掉被占用的文件**，先关后台是正道。
- **顺带**：清完记得别把 `*.log` 和 `portfolio/_bak/` 打进发行物 ——
  `make_demo.py` 现在收尾会自动清这两样。

### 53. 传文件别急着上 multipart
- **取舍**：后台是标准库 `http.server`，解析 `multipart/form-data` 要自己写边界切分、
  处理 filename 转义和各种容错，几十行还容易出错。
  改成前端 `FileReader.readAsDataURL()` → base64 → 一个普通 JSON POST：
  **传输体积多 33%，后端零解析依赖**。论文 PDF 通常几 MB，这点膨胀无所谓。
- **配套两条**：
  1. 后端要卡大小（现设 48MB），否则一个误传的 200MB 扫描件会把内存吃掉；
  2. 前端选完文件要 `input.value = ''` 清空，否则**同一个文件改完再选一次不触发 change**，
     用户会以为没反应。

### 54. `flex-wrap:wrap` + `margin-left:auto` = 子项竖排
- **症状**：导航项在宽屏是一行，一窄就变成一根竖线——7 个链接一个一行往下堆，
  整条顶栏被拉得跟手机下拉菜单一样。看起来像"换了布局"，其实是塌了。
- **根因**：`.navlinks{display:flex; flex-wrap:wrap; margin-left:auto}`。宽度不够时，
  flex 分配剩余空间会把它压到 **「最宽那一项」的宽度**，wrap 于是每行只放得下一项。
  `margin-left:auto` 是诱因：它要求这个元素吃掉所有剩余空间，压到极限后就开始逐项换行。
- **修法**：`flex-wrap:nowrap; min-width:0; overflow-x:auto`（配合 `scrollbar-width:none`）。
  放得下是一行，放不下是整行横向滚——**宁可滚动，也不让它变形**。
  真要按窄屏换形态，用媒体查询整块收进面板，别指望 wrap 自己排好看。
- **别只看一个宽度**：570px 难看、760px 又正常，很容易以为"某处样式冲突"。
  断点问题要按 320 / 390 / 570 / 760 / 900 / 1100 成组扫。

### 55. 媒体查询写在基础规则前面，等于没写
- **症状**：给窄屏加了一段 `@media(max-width:430px){ .nav-cta{padding:7px 12px} }`，
  重建、刷新、截图——完全没变化，还是原来的 `8px 16px`。
- **根因**：**媒体查询不提升优先级**，它只是「条件成立时也算一条普通规则」。
  同优先级下看的是**谁在后面**。基础规则 `.nav-cta{padding:8px 16px}` 写在文件后面，
  就把前面媒体查询里的声明整条盖掉了。
- **修法**：断点覆盖统一写在**基础声明之后**（按组件分区放：顶栏的覆盖跟着顶栏那一段走，
  别全塞文件末尾，否则下次看不出它管谁）。写的时候顺手确认一下：被覆盖的选择器
  在文件里的位置是不是在这段之后。
- **同源**：`.themebtn` 也踩过一次（36px 盖掉 30px）。

### 56. headless 截图别用 `--window-size` 量窄屏
- **症状**：`--window-size=390,760 --screenshot` 截出来的图，顶栏右边被切、CTA 一半在框外，
  看着像窄屏布局崩了。照着这张图去改 CSS，改完再截——还是那样。
- **根因**：**Windows 上 Chrome 窗口有最小宽度（实测约 504 CSS px）**，
  你传 390 它照样按 504 布局，而截图只截了左边 390*DPR 那一块。
  于是「内容被切」是截图裁的，不是布局坏的。
- **修法**：要量窄屏就用 **iframe 定宽**——外层页面把 iframe `width` 设成目标 px，
  媒体查询按 iframe 视口算，`getBoundingClientRect()` 也准；截图时同一份 DOM 顺手拍。
  只想要一张窄屏效果图，也可以用 iframe 套一层再截外层页面。
- **顺手记**：`--force-device-scale-factor=2` 时，截图尺寸是 CSS 尺寸 × 2，别拿图片宽度当视口宽度。
- **同一类假象**：用脚本切主题（`data-theme`）后立刻截图，会遇到**过渡动画不推进**——
  `--virtual-time-budget` 下 CSS transition 的时钟不走，元素还停在旧颜色上，
  截出来像"浅色主题下文字发灰几乎看不见"。判断办法：读 `getComputedStyle(root)`
  的变量值（对）但元素颜色不对，就是过渡卡住了；临时插一条
  `*{transition:none!important}` 再量，颜色立刻正确。

### 57. 浏览器「装坏了」的表现是静默零输出
- **症状**：`chrome --version` 返回码 0、标准输出**空**；`--dump-dom` 也是空；
  同样的命令半小时前还好好的。Edge 表现一模一样。
- **根因**：Chrome 自动更新失败留下的残局 —— `Application\chrome.exe` 这个壳还在，
  但版本目录（`Application\156.0.8078.73\`）里的真身 `chrome.exe` 没了，
  只剩 `chrome.exe.sig`。壳启动后找不到真身，直接退出。
  所以**「文件存在」不等于「能用」**。Edge 的壳同理。
- **修法**：重装 / 等更新补回。要立刻干活就先找替代内核：
  `~/AppData/Local/ms-playwright/chromium_headless_shell-*/chrome-win/headless_shell.exe`
  （Playwright 缓存，接受 `--headless=new`、`--dump-dom`、`--screenshot`，够跑探针）。
  `scripts/selftest.py` 的 `find_chrome()` 现在会先跑一句 `--version` 验活，
  失败就自动退到这份 Chromium。

### 58. 别让生图模型画中文文字
- **症状**：Demo 的论文板块要「看起来像真论文」，提示词写了「a Chinese academic paper page,
  title, abstract, two-column body」，出来的图排版结构对、字全是鬼画符，放大一看没有一个能认的字，
  缩略图里更明显是一团糊。
- **根因**：图像模型画的是**像字形的纹理**，不是字。中文笔画密度高、字库大，
  它连"像"都做不到——英文短标题偶尔能蒙对几个字母，成段中文必然崩。
- **修法**：**要真字就别用生图**。改走「排版引擎造页 → 导入管线」这条现成链路：
  `scripts/demo_paper.py` 用 Pillow 按 1080×1440（3:4，匹配站点 `aspect-ratio:3/4`
  + `object-position:top center`）排标题/作者/摘要框/正文/表格/条形图，
  拼成 PDF 再调 `admin/doc_import.py` 的 `convert()` 渲染成内页图。
  顺带要处理中文避头尾（`，。、）` 不落行首、`（「《` 不落行尾），否则整页看就是业余排版。
- **同理**：logo / 二维码 / 截图 / 仪表盘，凡是要"能被读"的元素，都不要交给生图模型。

### 59. 生图成品图下方那条水印会跟着上线
- **症状**：生成的 1024×1024 里，最底下约 96px 是工具水印条；直接内接裁成 16:9 之后，
  水印还在画面里，只是变小了，而且在深色底上格外扎眼。
- **修法**：先切掉底部 `WATERMARK = 96` 再用剩下的部分裁比例（`scripts/demo_ai_images.py`
  已内置）。不同工具的水印高度不一样，换工具时要先量一遍，别照抄 96。

### 60. 换了主色，阴影还是蓝的
- **症状**：把 `--acc` 从蓝改成橙，按钮、标签、小标题都变了，但按钮底下那圈阴影、
  聚焦外环、玻璃片的光晕还是蓝的 —— 整块看着像没擦干净的旧图。
- **根因**：这些地方写的是 `rgba(47,107,255,.32)`：蓝色是**拆开的分量**，不是 `var(--acc)`。
  改主色只影响 `var(--acc)`，写死分量的地方一个都不会动（全站 21 处）。
- **修法**：拆出 `--acc-rgb:47,107,255`，把所有半透明引用改成 `rgba(var(--acc-rgb),.32)`。
  `rgb()` 的现代写法 `rgb(var(--acc-rgb) / .32)` 也能用，但 `rgba(var(--acc-rgb),.32)`
  兼容性更好，也更好搜。
- **同理**：`#5b8cff` 这种「主色的中间调」也要提成变量（`--acc-3`），
  否则渐变里会留一条不变的蓝。

### 61. 后台的自定义控件被 `.fld input[type=text]` 压掉
- **症状**：给后台加了配色选择器，颜色块和「恢复默认」按钮正常，但十六进制输入框撑满整行、
  把按钮挤到下一行；`<label>` 也莫名变成块级、和输入框上下堆着。
- **根因**：卡片里有两条**更具体**的通用规则：
  `.fld input[type=text]{width:100%}`（0,2,1）和 `.fld label{display:block}`（0,2,0）。
  新控件只写 `.acchex{width:104px}`（0,1,0）根本压不过它们。
- **修法**：选择器带上容器并补全属性：`.accrow .acchex[type=text]`（0,3,0）。
  另外**样式块的位置也要挪到通用规则之后** —— 同权重时后写的赢，写在 `.fld` 前面等于没写
  （这是第 55 条的同一个坑，换了个地方踩）。

### 62. 16:9 的图塞进 4.33:1 的通栏格，被横切成一条
- **症状**：设计板块的通栏图（`design.groups[].wide`）是张 1600×900 的「展厅实景」，
  上线后只看见中间一条横切：易拉宝的上半截和整块地面都没了，左右各留一大片墙，
  看着像图片没加载全。
- **根因**：这一格的样式是 `.dz-t.sflag{aspect-ratio:1445/334}`（≈4.33:1），
  `img{object-fit:cover}` 会把 16:9 的图竖着裁掉约 2/3 —— 全文只保留中间那条 37%。
- **修法**：**按容器比例出图**，不是按「觉得好看的比例」出图。做任何 `wide` 位图前，
  先去 `site.css` 抄一次 `aspect-ratio`：`s16`=16/9、`stall`=1130/1600、`ssq`=1/1、
  `sflag`=1445/334。生成脚本里把这个比例写成常量并注释来源。
- **顺带**：4.33:1 太扁，装不下「实景」—— 实景要讲真实比例，A1 海报和 90×50 的门票
  按比例缩下来，门票只有 130px 宽、糊成色块。这一格改做**「一套物料排开」的对照页**
  更成立：四件都放大到能看清，代价是比例不真，但通栏要的是「看得见」。

### 63. 通栏图左下角会被图注压住
- **症状**：`.dz-t em` 的图注钉在 `left:7px;bottom:7px`，做对照页时左边第一件物料
  紧贴画布左缘，深色图注就贴在深色海报上，位置很尴尬。
- **修法**：出图时**左边预留约 15% 空纸**（1600 宽留 230px）给图注，物料从 230px 起排。
  这条对 `wide` 和单格图都适用：图注是覆盖在图片上的，设计图时要把它当成一个占位元素。

### 64. `shade()` 一刀切矩形，在山脊上留一道横线
- **症状**：给山景照片底部压暗好放白字，用的是「盖一个半透明矩形」，
  结果山脊上出现一条水平的明暗台阶，越通透的照片越明显。
- **修法**：用竖向渐变（`shade_grad(im, y0, y1, amax)`：y0 透明 → y1 到最大不透明度），
  逐行算 alpha 再 `putalpha` 合成。**只要背景里有连贯的形（山脉、水面、天空），
  压暗就必须是渐变**；纯色矩形只适合本来就有的硬边（比如图片边框内）。

### 65. 系统 Chrome 没坏透，但截图静默失败
- **症状**：`chrome --headless=new --screenshot=x.png` 退出码 **0**、stderr 空、文件不生成。
  从 Bash 里调还会立刻返回 —— 看起来像命令跑完了，其实进程早已退出。
- **根因**：Chrome 自动更新失败后，`Program Files/.../Application/chrome.exe` 这个入口还在，
  但版本目录里的真身没了。`--version` 打不出任何东西就是铁证（`selftest._alive()` 正是查这个）。
- **修法**：不要硬编码路径。`scripts/shot_site.py` 里直接 `from selftest import find_chrome`，
  它会逐个 `--version` 实测，然后回退到 Playwright 缓存的
  `AppData/Local/ms-playwright/chromium_headless_shell-*/chrome-win/headless_shell.exe`。
- **旁证**：只用 `pathlib.Path(exe).exists()` 判断“浏览器可用”是错的 —— 入口在、真身没了，
  是这台机器上最常见的形态。

## 十、CDP 探针（验证后台前端时用）

> 共同症状：**静默返回 None、不报错** —— 探针读到的永远是空，很容易误判成「页面没渲染」，
> 其实是连接方式不对。三条都来自真实站点的后台验证实测。

### 66. CDP 必须连 page 级目标，不能连 browser 级 WebSocket
- **症状**：连上 `DevToolsActivePort` 第二行那个 WebSocket（browser 级），`Runtime.evaluate`
  一律返回 `None`，无异常、无错误。
- **修法**：browser 级连接不挂页面上下文。先 `GET http://127.0.0.1:<port>/json/list`，
  从结果里挑 `type == 'page'` 的目标，用它的 `webSocketDebuggerUrl` 连 —— evaluate 才有返回值。

### 67. headless_shell 跑不了探针，要用正式 Chrome 的 `--headless=new`
- **症状**：换了个连法 evaluate 还是恒 `None`。
- **根因**：Playwright 的 `headless_shell.exe` 走旧 headless 模式，`Runtime.evaluate` 同样
  静默返回 `None`。截图能用（它只需要渲染），探针不行（它要读 DOM）。
- **修法**：用正式 `chrome.exe --headless=new`。找不到正式 Chrome 时参考 `selftest.find_chrome`
  的逐个实测逻辑，别硬编码路径（第 65 条）。

### 68. 无头 Chrome 视口最小 504px，file:// 里的 iframe 跨源读不到 DOM
- **症状**：`--window-size=390` 想量移动端布局，实测 `clientWidth = 504`；
  套 `<iframe width=390>` 量时，`file://` 下访问 iframe 内部直接被拦。
- **修法**：视口下限 504px 是硬的。移动端量测走 `<iframe width=390>` + 起一个
  `http.server` 用 `http://127.0.0.1/` 访问 —— 同源了才能读 iframe 的 DOM。

## 十一、后台表单：窄列与多行框

### 69. CSS 变量拼错不会报错，只会静默继承
- **症状**：「影像作品」分组卡底部的说明文字，颜色跟正文一样黑，看着不像提示。
- **根因**：写的是 `var(--ink-3)`，而变量定义叫 `--ink3`（`--ink / --ink2 / --ink3`）。
  `var()` 取不到值又没有兜底时会走「继承」，于是拿到祖先的正文色 —— 不报错、不告警。
- **修法**：改配色前先核对定义（`grep -- "--ink3:"`）。要防手滑就写兜底：
  `var(--ink3,#8a909c)`。同类变量还有 `--acc/--acc-s/--line/--panel/--danger`。

### 70. 三栏里塞两列表单 + `rows=2` 文本框
- **症状**（真实反馈截图）：分组卡里「英文」输入框只剩 90px，显示成 `COMMERCI…`；
  简介框 90px 高，第三行结束就切掉，框里露着一根系统默认粗滚动条。
- **根因**：`.cols` 是 `230px 320px 1fr`，前两栏既是列表又是**就地表单**；表单被塞进
  230px 里还要 `row2` 拆两列，每列 ~90px。文本框 `rows=2` + `min-height:64px`，
  内容一长就只能在小框里滚。
- **修法**：
  1. 列宽给下限（`270 / 300 / 1fr`），编辑卡吃剩下的；中屏（≤1150）**改成两行**而不是
     继续压三栏（`grid-template-columns:1fr 1fr` + 编辑卡 `1/-1`）。
  2. 窄列里的两列表单退单列（`.row2.stack`）—— 下拉里的「专项（大卡 + 封面墙）」这类长选项
     在 120px 里只看得到前半句。
  3. 多行框 `min-height:96px` + `field-sizing:content` + `max-height:340px`：随内容长高，
     到上限才出滚动条；`@supports (field-sizing:content)` 里把 resize 手柄关掉（高度由内容定，
     拖了也会被盖回去）。不支持的浏览器退回 96px 固定高。
  4. 文本域滚动条单独做细（9px 圆角浅灰、透明槽），别用系统默认那根 —— 它比正文还抢眼。

### 71. bat 里写中文：`chcp 65001` 救不了，第二行就崩
- **症状**：`start-admin.bat` 里加中文提示，第一行 `echo` 正常显示，第二行开始报
  `'掉就等于停掉后台。' 不是内部或外部命令` —— 后面的行从句子中间开始执行。
  括号块（`if ... ( echo 中文 )`）里的中文更糟，因为整块在执行前就按旧码页解码了。
- **根因**：cmd 按 OEM 码页（简中 936）解析 .bat。UTF-8 一个汉字 3 字节 ≠ 1 个字符，
  解析器按「已消费的字节数」推进文件指针，遇到多字节字符就错位。`chcp 65001` 改的是
  **输出**码页，不会重算已经读进来的行偏移 —— 所以它只对紧跟着的一两行有效。
- **修法**：bat 全文 ASCII（文件名也 ASCII，中文名经 zip 分发会乱码），中文提示全部交给
  Python 打印 —— Windows 上 Python 3.6+ 走 `WriteConsoleW`，与控制台码页无关，
  `PYTHONIOENCODING=utf-8` 只影响重定向到文件的情况。必须由 bat 自己说的地方，宁可写英文。
- **旁证**：LF 换行的 .bat 在 cmd 下会出**一模一样**的错位症状。用 Python 生成 bat 时必须
  显式写 `\r\n`（`newline=''` + 手写 CRLF），否则测试环境看着对、真机一闪就没。
- **mac 对应物**：`.command` 走 UTF-8 终端没这个解析问题，但同一套脚本为分发一致也保持纯 ASCII；
  它的坑在**执行位**——zip 解压会丢 `+x`，双击没反应，`sh 文件名` 照样能跑（脚本顶部写清了）。
- **反面教材**：`打不开就 chcp 一下` 是网上最常见的建议，实测只在最简单的一行 echo 成立。

### 72. 后台探针缓存的节点，会被 `innerHTML` 重画换掉
- **症状**：断言「点『+ 加一张图』后 DOM 也 +1」失败，可同一时刻数据明明是 5 条。
- **根因**：`renderTexts()` 用的是 `box.innerHTML = …` —— 容器还在，**子节点全换新**。
  探针里写的 `const card = q('#txDesign .txi')` 拿到的是旧节点，`card.querySelectorAll()`
  查的是一棵已经脱离文档的旧树，所以数字永远停在重画前。
- **修法**：作用域写成函数，每次重查：`const card = () => q('#txDesign .txi')`。
  同理，`#txDesign`（外层容器）可以缓存，它里面的东西不能。
- **同类**：`let D` 不在 `window` 上（`let/const` 不挂全局对象），探针读数据得走
  `w.eval('(D.design.projects[0].groups)')`，写 `w.D` 只会拿到 `undefined`。

### 73. `--virtual-time-budget` 开太大，`--dump-dom` 反而挂住
- **症状**：`chrome --headless=new --dump-dom` 配 `--virtual-time-budget=30000`，
  90 秒不返回（超时 rc=124，输出只有几行 `ANOMALY: meaningless REX prefix used` 噪声）；
  改成 3000~10000 立刻出结果。
- **根因**：页面里跑着长驻定时器（自动保存、计数轮询）。虚拟时间要「没有 pending 任务」
  才结算并 dump，budget 越大越容易卡在等结算那一步 —— 这是反直觉的：想多等一会儿，
  结果等到的是不返回。
- **修法**：探针自己控节奏（几次 `await sleep(200)`，总共几秒），budget 给 10000 就够；
  真要跑长流程，就在探针里把长驻定时器清掉，别指望加大 budget。
- **旁注**：Windows 上 Chrome 还不认 Git Bash 的 `/tmp` 路径，`--screenshot` 要传 Windows
  绝对路径；localhost 被系统代理拦时要加 `--no-proxy-server`。

## 十一、文件命名

### 74. 导入的照片沿用原文件名，括号一路坑到底
- **症状**：单 HTML 里个别封面是空的，站内预览却正常；换台机器解压 zip 中文名还乱。
- **根因**：上传时把用户的原文件名（`图片(30).jpg`、`微信图片_20260421120512_3653_331.jpg`）
  直接当文件名。三处连锁：① 内联白名单只认字母数字和汉字，括号被跳过 →
  单文件裂图（而且不报 missing，静默）；② 括号在 URL 里要转义，手写 `src` 时容易漏；
  ③ 中文名经 zip 分发、换个工具解压就乱码（#71）。
- **修法**：导入一律重命名，原文件名只用来取扩展名 —— 后台上传落成
  `<目录短名>-<YYYYMMDD>-<两位序号>.<ext>`，文档导入落成 `<目录名>-<日期>-<序号>_p<页号>.jpg`。
  序号按天递增、永不覆盖（重传同一张图得到新文件，旧图仍有效）。
  例外：靠同名覆盖换图的固定名（`cover.jpg` / `avatar.jpg` / `portrait.jpg` / logo）
  和摄影墙 `分类_NN.jpg`（生成器按名字分组）。
- **旁证**：见 1.21.1 那条「单文件缺图」——同一个坑的另一面。

## 十二、读简历（docx 文本抽取）

### 75. 带浮动头像的简历，姓名被抽成「影像制作」
- **症状**：`setup_site.py --resume 简历.docx` 抽出的 `name` 不是人名，而是「影像制作」「内容运营」
  这类职位词。学校、专业、电话都好，唯独姓名错。
- **根因**：`docx_text()` 是「document.xml 去标签」的粗暴做法。浮动图片的 XML 里含
  `<wp:align>right</wp:align>` 和 `<wp:posOffset>0</wp:posOffset>` —— 这两个值是**文本节点**，
  去标签后原样留在正文里，首行变成 `right0陈屿`。`guess_name` 要求「2–4 个纯汉字」，
  匹配不上就跳过，于是抓到下一行「影像制作 / 内容运营 · 杭州」里的 `影像制作`。
- **为什么一定会踩**：国内简历基本都带头像，而且为了排版都做成**浮动**图
  （inline 图会把所在行撑高，姓名后面拖一大块空白）。
- **修法**：去标签**之前**先把图形块整棵删掉，四类都要删 —— `w:drawing` / `w:pict` /
  `mc:AlternateContent` / `w:txbxContent`：`re.sub(r'<tag\b[^>]*>.*?</tag>', '', xml, flags=re.S)`。
  顺手把 `<w:tab/>` 换成两个空格，否则「2022—2026　江州传媒学院　本科」会粘成一行，
  `guess_major` 的分栏兜底也跟着失效。
- **别做的事**：① 别去给 `guess_name` 加职位词黑名单 —— 黑名单永远列不全，根因在解析这一层；
  ② 别靠「让用户简历不要带头像」绕过 —— 那是用户的文件，不是我们能规定的。
- **验证**：修完 `python scripts/selftest.py` 41 项仍全绿；抽字段 8/8（name/city/school/
  major/years/email/phone/tagline），`clean_lines()[0] == '陈屿'`。
