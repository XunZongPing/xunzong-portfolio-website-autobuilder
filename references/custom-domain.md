# 绑定自己的域名（一步一步指引）

> **这份文件是给人看的。** 想让网站变成 `www.你自己的名字.com` 这种网址，照这一份走。
> 带用户走的时候**一条一条来**，做完一条确认一下再下一条。
>
> 前提：网站已经发到 GitHub Pages（`https://用户名.github.io/仓库名/` 能打开）。
> 方案是「域名 + Cloudflare 免费 DNS + GitHub Pages」，除域名外 **0 费用**。

## 先准备两样东西

| 要什么 | 说明 |
|---|---|
| 一个域名 | 阿里云 / 腾讯云 / Namecheap / Cloudflare 都能买，年费几十块。最普通的 `.com` 或 `.cn` 就够 |
| GitHub 账号 | 就是网站已经发上去的那个 |

没有域名就先去买一个再回来。**买的时候不用加任何附加服务**（隐私保护、SSL、虚拟主机都不要买，
Cloudflare 免费给）。

## 全程 6 步（照抄就行）

### 第 1 步：把域名交给 Cloudflare 管

1. 打开 **dash.cloudflare.com**，注册 / 登录。
2. 点 **Add a site**（添加网站）→ 输入你买的域名 → Continue。
3. 套餐选 **Free（免费）** → Continue。
4. Cloudflare 会显示**两个 NS 地址**（长得像 `xxx.ns.cloudflare.com`）——把这个页面留着，下一步要用。

### 第 2 步：去买域名的地方换 DNS 服务器

1. 打开你买域名的那个网站（阿里云 / 腾讯云 / Namecheap…），进域名管理 →
   **DNS 服务器 / Nameserver 设置**。
2. 把原来的两条换成 Cloudflare 给你的那两条 → 保存。
3. 回 Cloudflare 点「继续」→ 等它变成「生效」（快则几分钟，慢则几小时，页面会自己刷新）。

### 第 3 步：告诉 GitHub 你要用这个域名

1. 打开你网站的 GitHub 仓库 → **Settings** → 左边 **Pages**。
2. 「Custom domain」框里填 `www.你的域名.com` → **Save**。
3. 页面会出现一行「正在检查 DNS」——先不管，继续下一步。

### 第 4 步：在 Cloudflare 加一条记录

1. Cloudflare → 你的域名 → **DNS** → **Add record**。
2. 按这样填，保存：

   | 类型 | 名称 | 目标 |
   |---|---|---|
   | `CNAME` | `www` | `你的GitHub用户名.github.io` |

3. **云朵图标选灰色（DNS only）**——先不走 Cloudflare 代理，最稳。

### 第 5 步：回 GitHub 打个勾

1. 仓库 Settings → Pages，等「DNS check」变成**绿色对勾**（几分钟）。
2. 勾上 **Enforce HTTPS**（要等 DNS 通过后才能勾；证书 GitHub 免费自动签）。

### 第 6 步：完成

浏览器打开 `https://www.你的域名.com` —— 就是你的作品集了。
以后更新网站照旧重新生成、上传，**域名不用再动**。

## 三个常见卡点

| 现象 | 真实原因 | 怎么办 |
|---|---|---|
| DNS check 一直不变绿 | NS 还没生效，或 CNAME 目标打错 | 再等十分钟；核对 `你的GitHub用户名.github.io`，一个字都不能差 |
| 打开是 404 | 刚上传还没部署完，或 Pages 没开 | 等 1 分钟刷新；仓库 Settings → Pages 看 Source 是不是 main / (root) |
| 浏览器提示「不安全」 | HTTPS 证书还在签发 | 勾了 Enforce HTTPS 后等几分钟（最多半小时）再试 |

## 进阶：想用不带 www 的域名

`www.你的域名.com` 用一条 CNAME 就行。想让 `你的域名.com`（不带 www）也能打开：

1. Cloudflare 的 DNS 里再加 **4 条 A 记录**，名称都填 `@`，内容分别是
   `185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153`
   （GitHub Pages 的官方 IP）。
2. GitHub Pages 的 Custom domain 改填 `你的域名.com`，勾 Enforce HTTPS。
3. 保留 `www` 那条 CNAME——GitHub 会自动把带 www 的跳过来。

## 其它情况

- **域名直接买在 Cloudflare**：跳过第 1、2 步（已经在它家了），从第 3 步开始。
- **网站发在 Netlify**：后台 Domain management → Add a domain，按它给的提示在
  Cloudflare 加记录（也是 CNAME），步骤几乎一样。
- **全程不想碰这些**：把域名和 GitHub 账号交给 agent，照本指引一条条做，每步截图确认即可。
