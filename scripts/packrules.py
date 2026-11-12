# -*- coding: utf-8 -*-
"""打包规范 —— 什么算「多余的文件」。

两处打包共用这一份规则，避免各写各的：
  · 技能发行包   scripts/pack_skill.py      （发给别人装这个技能）
  · 站点交付包   scripts/deploy_site.py --pack zip（发给别人看这个网站）

规矩只有一条：**只发该发的**。运行残留、临时产物、编辑器垃圾、上一次的压缩包，
一律不进包。这类东西一旦混进去，用户解压后会看到一堆看不懂的文件，
而它们跟作品集本身没有任何关系。

判定按「路径任一层的目录名 + 文件名 + 扩展名」，不看大小：一个 0 字节的
.admin.json 也能暴露后台端口和进程号。
"""

# 目录名：整棵子树都不打包
JUNK_DIRS = {
    '__pycache__', '.git', '.idea', '.vscode', '.pytest_cache',
    '__MACOSX', 'node_modules', '.ipynb_checkpoints',
}

# 文件名完全匹配
JUNK_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini', '.admin.json'}

# 扩展名（小写比较）
JUNK_EXTS = {
    '.pyc', '.pyo',            # Python 字节码
    '.log', '.tmp', '.bak',    # 运行日志 / 临时 / 备份
    '.swp', '.orig', '.rej',   # 编辑器与补丁残留
    '.zip',                    # 上一次的包，别套娃
    '.ds_store',
}

# 文件名前缀：探针页、备份目录、macOS 资源分叉、Office 锁文件
JUNK_PREFIX = ('._', '~$', '_bak', '_selftest', '_navtest', '_dgtest', '_probe')

# 技能包允许出现在顶层的条目（白名单）。不在表里的顶层条目 = 混进了不该发的东西
SKILL_TOP = {
    'SKILL.md', 'README.md', 'LICENSE', 'CHANGELOG.md',
    'assets', 'examples', 'references', 'scripts',
}


def is_junk(rel):
    """rel 用 / 分隔的相对路径。是运行残留/临时产物就返回 True。"""
    parts = [p for p in str(rel).replace('\\', '/').split('/') if p and p != '.']
    if not parts:
        return False
    for p in parts[:-1]:                       # 中间层只看目录
        if p in JUNK_DIRS or p.startswith('_bak'):
            return True
    name = parts[-1]
    if name in JUNK_FILES:
        return True
    low = name.lower()
    if any(low.endswith(e) for e in JUNK_EXTS):
        return True
    if name.startswith(JUNK_PREFIX):
        return True
    return False


def split(files):
    """files 是相对路径列表 → (要发的, 被剔掉的)。报告里两个数都要给人看。"""
    keep, junk = [], []
    for r in files:
        (junk if is_junk(r) else keep).append(r)
    return sorted(keep), sorted(junk)
