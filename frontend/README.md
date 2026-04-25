# Frontend

Next.js 本地前端，负责：

- 浏览 SQLite 中的作者 / 股票 / 主题时间线
- 在 `/control` 管理抓取配置、调度时间和 AI 设置

## 依赖与启动

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://localhost:3000`

## 本地数据来源

- 默认读取 `../data/runtime/insight.db`
- 如需覆盖，可设置 `INSIGHT_DB_PATH`

## 控制台

`/control` 页面支持：

- 小红书 / X 抓取配置
- 每日调度时间
- 手动运行
- AI provider / model / API key 管理

AI key 不会通过浏览器接口明文回传，只会以“已配置 / 脱敏提示”的形式展示。
