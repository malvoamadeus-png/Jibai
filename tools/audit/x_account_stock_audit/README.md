# X Account Stock Audit

隔离研究工具，用来抓取单个 X 账号的历史发言，抽取股票提及/态度，拉取日 K，并生成 HTML 与 Excel 审计报告。

## Run

```powershell
$env:PYTHONPATH="backend;."
python tools/audit/x_account_stock_audit/cli.py run --profile https://x.com/aleabitoreddit --days 31 --model gpt-5.4-mini
```

常用参数：

- `--start YYYY-MM-DD --end YYYY-MM-DD`：指定日期窗口。
- `--max-pages 300`：FxTwitter cursor 最大翻页数。
- `--resume`：复用已有 `normalized_posts.jsonl` 或 `stock_mentions.jsonl`。
- `--skip-ai`：只抓取并基于已有 mentions 生成空/旧报告。
- `--skip-market`：不请求行情，只生成观点矩阵。
- `--output-dir PATH`：改写默认 `runs/` 输出目录。

## Outputs

每次运行写入独立目录：

- `raw_statuses.jsonl`：FxTwitter 原始 status。
- `normalized_posts.jsonl`：标准化后的目标账号发言。
- `stock_mentions.jsonl`：AI 抽取的股票提及。
- `report.html`：自包含 K 线与观点标记报告。
- `audit.xlsx`：`stance_matrix`、`evidence_matrix`、`raw_mentions`、`score_summary`。
- `run_manifest.json`：运行参数、统计和输出路径。

价格为日线级近似：发言日期匹配到当日或下一个可交易日 close，不代表发言瞬间价格。

