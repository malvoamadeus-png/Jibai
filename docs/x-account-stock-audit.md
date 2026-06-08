# X 账号股票喊单审计工具

`tools/audit/x_account_stock_audit/` 是隔离研究工具，不接入主 worker、主数据库或主前端路由，也不依赖 `Reference/`。

## 运行命令

```powershell
$env:PYTHONPATH="backend;."
python tools/audit/x_account_stock_audit/cli.py run --profile https://x.com/aleabitoreddit --days 31 --model gpt-5.4-mini
```

支持 `--start/--end` 扩展历史窗口，`--resume` 断点续跑，`--skip-ai` 只抓取，`--skip-market` 跳过行情。

## 数据口径

- FxTwitter `/2/profile/{username}/statuses` 用 `cursor.bottom` 翻页。
- 只保留目标账号本人发言；纯转发跳过，回复和带作者文字的引用保留。
- 股票抽取保留 `bull`、`bear`、`mention_only`、`mixed`。
- `mention_only` 进入矩阵和 K 线标记，但不参与喊单命中率。
- `bull/bear` 用 `+1/+5/+20` 交易日方向收益计算命中率和平均方向收益。

## 输出

- `report.html`：每只股票一张日 K，绿色上箭头为 bull，红色下箭头为 bear，灰色旗标为仅提及。
- `audit.xlsx`：
  - `stance_matrix`：股票 x 日期的态度摘要。
  - `evidence_matrix`：股票 x 日期的观点、证据和链接。
  - `raw_mentions`：逐条提及明细。
  - `score_summary`：按股票汇总方向样本和命中率。

价格是日线级近似：发言日期匹配到当日或下一个可交易日 close，不代表发言时刻逐笔价格。

