# 链上埋伏分析方案

## 状态

链上钱包持仓追踪已经下线。`/onchain`、`/onchain/tokens`、
`/onchain/wallets`、`/onchain/admin` 和 `/onchain/gmgn-labels` 前端页面已
移除，后端不再调度 OKX 钱包持仓抓取，也不再保留 `public.onchain_*`
钱包追踪表。

下线 migration：

- `supabase/migrations/041_remove_onchain_tracking_and_slim_public_rpc.sql`

保留能力：

- `backend/packages/onchain/okx_client.py`
- `backend/packages/onchain/gmgn_labels.py`
- `backend/packages/public_app/api.py` 中的 `POST /api/onchain/gmgn-labels`
- crypto asset brief / identity resolution 中的 OKX Onchain OS token search

这些保留能力只用于服务端 token 查询，不写入 `onchain_balance_snapshots`
或其他已下线的钱包持仓表。
