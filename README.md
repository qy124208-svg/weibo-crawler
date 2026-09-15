# 微博城市用户采集工具 v4.2

按城市筛选微博用户，采集2015年历史微博内容。

## 功能

| 模块 | 功能 | API |
|------|------|-----|
| ① 搜索+验证 | 关键词搜索 → 验证所在地 | PC 端 |
| ② 社交扩散 | 从关注列表扩展同城用户 | PC 端(Playwright) |
| ③ 2015微博采集 | 采集指定年份微博内容 | 移动端 m.weibo.cn |

## 环境要求

- **Python 3.8+**
- 任意现代浏览器（系统默认即可，Edge / Chrome / Firefox 都行）
- Windows / macOS 均可

## 快速开始

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装 Playwright 浏览器驱动（仅社交扩散需要）
playwright install chromium

# 3. 登录微博（获取Cookie）
python playwright_login.py
# → Chrome 弹出 → 扫码登录 m.weibo.cn
# → 等待打印 "登录成功(MLOGIN=1)！"

# 4. 启动采集
python weibo_city_crawl_gui.py
```

### 之后每次使用

直接启动 GUI 即可（Cookie 会自动刷新）：

```bash
python weibo_city_crawl_gui.py
```

如果提示 Cookie 过期，再跑一遍 `python playwright_login.py`。

## 文件说明

```
爬虫工具/
├── weibo_city_crawl.py          # 核心引擎 v4.2（纯requests，零Playwright）
├── weibo_city_crawl_gui.py      # GUI 界面 v3.1
├── playwright_login.py          # 扫码登录（刷新Cookie）
├── refresh_cookie.py            # 后台自动刷新Cookie
├── collect_2015_browser.py      # 浏览器辅助采集（备选方案）
├── social_expand.py             # Playwright社交扩散
├── get_cookie.py                # 从Chrome本地数据库读取Cookie
├── auto_cdp_refresh.py          # CDP自动刷新Cookie
├── refresh_cookie_cdp.py        # CDP方式刷新Cookie
├── migrate_data.py              # 数据迁移工具
│
├── cookie.txt                   # 自动生成：PC端Cookie（模板）
├── cookie_mobile.txt            # 自动生成：移动端Cookie（模板）
│
├── requirements.txt             # Python依赖
├── README.md                    # 本文件
├── 使用说明.txt                  # 中文使用说明
│
└── city_output/                 # 自动生成：采集结果
    ├── state.json               # 断点续传进度
    ├── 南京_用户.csv             # 14字段用户信息
    ├── 南京_2015微博.csv         # 11字段微博内容
    └── ...                      # 其他城市同理
```

## GUI 操作

```
① 搜索+验证 → 选城市 → ▶ 开始     # 从零发现用户
② 社交扩散 → 选城市 → ▶ 开始       # 从已有用户扩展
③ 2015微博采集 → 选城市 → ▶ 开始   # 采集历史微博
```

| 参数 | 建议值 | 说明 |
|------|:--:|------|
| 每城目标 | 10000 | 每个城市采集多少用户 |
| 请求间隔 | 3-5秒 | 越小越快，但可能触发限流 |
| 搜索线程 | 3-5 | 搜索并发数 |

## 命令行版本

```bash
# 自动串行执行全部阶段（搜索→扩散→2015采集）
python weibo_city_crawl.py
```

## 技术架构 (v4.2)

### 核心原则：纯requests，采集期间绝不调Playwright

```
启动:     纯文件重载cookie + requests预热（不调playwright）
采集:     requests.get() 2.5-3.5s延迟 + 自适应降速
验证码:   webbrowser.open()系统浏览器 + GUI回调 + 文件重载cookie
限流:     ok=-100 → 等90s + 重载cookie文件
```

### 关键API

- ✅ `m.weibo.cn/api/container/getIndex?containerid=107603{uid}` — **唯一**能拿2015完整内容
- ❌ `weibo.com/ajax/statuses/searchProfile` — 2015帖显示"客户端查看"占位符
- ❌ `weibo.com/ajax/statuses/mymblog` — 仅近半年

### 2015采集四大优化

1. **注册时间预过滤** — 零API跳过，秒级判断，过滤30-40%无效用户
2. **小profile直扫** — total<100帖不跳页不二分
3. **减冷却** — 二分后冷却从5-10s减至1-3s
4. **快速末页确认** — first_year>2020时末页确认，避免无效二分

### v4.2 修复

| 修复 | 说明 |
|------|------|
| 静默跳过补日志 | 三处跳过路径（注册时间/API失败/无可见帖子）现在有明确日志 |
| ok=0 误判修复 | 隐私账号不再触发"连续3页失败→中断扫描" |
| 异常日志补齐 | ok非标准值、请求异常、cookie为空均有诊断日志 |
| IP选择决策 | 国内IP远优于翻墙，混在正常流量中不触发异常检测 |

## 数据格式

### 用户 CSV（14字段）

uid, 昵称, 性别, 所在地, IP属地, 认证类型, 认证信息, 简介, 粉丝数, 关注数, 微博数, 注册时间, 用户主页链接, 质量标记

### 微博 CSV（11字段）

uid, 用户昵称, 微博id, 微博链接, 发布时间, 微博内容, 转发数, 评论数, 点赞数, 发布于, 话题标签

## 常见问题

**Q: Cookie 过期怎么办？**
A: 运行 `python playwright_login.py` 重新扫码登录。

**Q: 触发验证码？**
A: 系统浏览器自动弹出验证页面，人工完成滑块后点GUI"恢复"按钮即可继续。

**Q: 能同时跑多个模块吗？**
A: ①② 可以同时跑（都用 PC API），③ 也可以同时跑（用移动端 API）。

**Q: 数据显示乱码？**
A: CSV 文件是 UTF-8 编码，用 Excel 打开时选"数据→从文本导入→UTF-8"。

## 免责声明

本工具仅供学术交流和个人学习使用，禁止用于任何商业用途或大规模爬取。使用者需遵守微博平台的相关规定和法律法规。
