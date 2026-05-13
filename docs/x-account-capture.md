# X 账号内容抓取

## 模块边界

本模块只负责按配置抓取特定 X 账号的公开内容，并把新内容转换成统一的 `RawNoteRecord`。它不负责 AI 分析、观点聚合、页面展示或美股顶部风险计算。

现有入口：

```bash
python backend/src/main.py run-once-x --config data/config/x_watchlist.json
```

相关代码：

- `backend/packages/x/config.py`
- `backend/packages/x/service.py`
- `backend/packages/x/fxtwitter.py`
- `backend/packages/x/browser.py`
- `backend/src/jobs.py`

## 配置

配置文件为 `data/config/x_watchlist.json`，示例来自 `data/config/x_watchlist.example.json`。

核心字段：

| 字段 | 含义 |
| --- | --- |
| `enabled` | 是否启用 X 抓取 |
| `headless` | Nitter/Playwright 兜底抓取是否无头运行 |
| `page_wait_sec` | 浏览器页面等待时间 |
| `inter_account_delay_sec` | 账号之间的基础间隔 |
| `inter_account_delay_jitter_sec` | 账号之间的随机抖动 |
| `exclude_old_posts` | 是否过滤旧帖 |
| `max_post_age_days` | 旧帖过滤天数 |
| `nitter_instances` | Nitter/XCancel 兜底镜像列表 |
| `accounts[].name` | 本地显示账号名 |
| `accounts[].profile_url` | X/Twitter 账号主页 |
| `accounts[].limit` | 单次希望新增的内容条数 |

`profile_url` 会被归一化为 `https://x.com/{username}`。用户名必须满足 X 用户名规则，且不能是 `home`、`search`、`settings` 等保留路径。

## 数据源顺序

抓取按轻量优先：

1. FXTwitter JSON
   - 用户信息：`https://api.fxtwitter.com/{username}`
   - 时间线：`https://api.fxtwitter.com/2/profile/{username}/statuses`
   - 详情：`https://api.fxtwitter.com/{username}/status/{tweet_id}`
2. Nitter/XCancel 页面兜底
   - 按 `nitter_instances` 顺序尝试
   - 使用 Playwright 打开公开页面并解析 timeline item
   - 失败时记录 debug HTML 到运行态目录

FXTwitter 能返回结果时直接使用，不再进入 Nitter 兜底。FXTwitter 失败或没有可用候选时，才尝试 Nitter/Playwright。

## 抓取流程

1. 读取 `x_watchlist.json` 并校验账号配置。
2. 读取运行态文件中的已见内容 ID。
3. 对每个账号抓取候选 tweet，扫描量为目标条数的 3 倍，最低不少于目标条数。
4. 过滤非目标作者、重复 tweet、旧帖和旧置顶帖。
5. 对候选 tweet 调用详情接口补齐正文、作者、互动数、媒体 URL 和发布时间。
6. 转换为 `RawNoteRecord`。
7. 将新内容写入 SQLite 的 `content_items`，并记录 `crawl_account_runs`。
8. 更新 X 抓取状态文件，避免下次重复处理已见 tweet。

## 输出数据

抓取模块输出两类对象：

| 对象 | 用途 |
| --- | --- |
| `CrawlAccountResult` | 记录账号级运行结果，包括候选数、新增数、错误信息 |
| `RawNoteRecord` | 统一内容记录，供后续 AI 分析和 SQLite 入库 |

X 内容入库时主要字段包括：

- `platform = "x"`
- `account_name`
- `profile_url`
- `note_id = tweet_id`
- `url`
- `title`
- `desc`
- `publish_time`
- `like_count`
- `collect_count`
- `comment_count`
- `share_count`
- `metadata_json`

## 失败分类

抓取失败会尽量给出可诊断错误，而不是只返回空列表。

主要类型：

| 类型 | 含义 |
| --- | --- |
| `X_RUNTIME_FAILED` | Playwright/Chromium 环境异常 |
| `X_FETCH_FAILED` | 请求失败、镜像不可用、被安全验证或反机器人拦截 |
| `X_PARSE_EMPTY` | 页面或接口返回成功，但没有解析到可用 tweet |
| `X_OTHER` | 未归类异常 |

## 运行态文件

运行态数据不提交 Git。

| 路径 | 用途 |
| --- | --- |
| `data/runtime/state/x_monitor_state.json` | X 抓取已见 ID、上次运行时间、上次错误 |
| `data/runtime/x/debug/` | Nitter/Playwright 失败时的调试材料 |
| `data/runtime/insight.db` | SQLite 主数据库 |

## 设计约束

- 默认只抓公开账号内容。
- 不在代码或日志中保存账号私密凭证。
- JSON 接口优先，浏览器抓取只做兜底。
- 单账号失败不应阻断其他账号。
- 旧帖过滤是抓取阶段职责，避免历史内容反复触发后续分析。
