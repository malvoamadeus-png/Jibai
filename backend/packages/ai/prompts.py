from __future__ import annotations

import json

from packages.common.models import NoteExtractRecord, RawNoteRecord


NOTE_EXTRACT_REQUIRED_KEYS = ["summary_text", "viewpoints", "events"]
CRYPTO_NOTE_EXTRACT_REQUIRED_KEYS = ["summary_text", "viewpoints"]
AUTHOR_SUMMARY_REQUIRED_KEYS = ["summary_text"]
STOCK_NARRATIVE_REQUIRED_KEYS = [
    "brief_text",
    "mainstream_narrative",
    "new_directions",
    "rare_negative_signals",
]
CRYPTO_KEYWORD_EXPANSION_REQUIRED_KEYS = ["keywords"]
CRYPTO_CA_MATCH_REQUIRED_KEYS = ["same_project", "confidence", "shared_signals", "reason"]
CRYPTO_ASSET_BRIEF_REQUIRED_KEYS = ["summary_text"]


def build_note_extract_messages(note: RawNoteRecord) -> list[dict[str, str]]:
    payload = {
        "platform": note.platform,
        "account_name": note.account_name,
        "author_nickname": note.author_nickname,
        "note_id": note.note_id,
        "title": note.title,
        "desc": note.desc,
        "publish_time": note.publish_time,
        "url": note.url,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是一个中文投研观点抽取助手。"
                "请只输出 JSON 对象，不要输出 markdown。"
                "目标不是复述帖子内容，而是拆出可以落到投研面板里的股票观点和新闻事件。"
                "JSON 顶层必须包含以下字段：summary_text, viewpoints, events。"
                "summary_text 是一句简洁中文概括；有有效股票观点时优先概括主判断；没有有效股票观点但有有效新闻事件时概括主要事件；两者都没有时写“未形成有效股票观点或新闻事件”。"
                "viewpoints 是数组，每个元素代表一条独立股票观点；没有有效股票观点时必须返回空数组。"
                "events 是数组，每个元素代表一条独立新闻事件；没有有效新闻事件时必须返回空数组。"
                "每条观点必须包含字段："
                "entity_type, entity_name, entity_code_or_name, stance, direction, signal_type, judgment_type, conviction, evidence_type, logic, evidence, time_horizon。"
                "entity_type 只能是 stock；非股票、Theme、行业、板块、赛道、宏观、指数、市场风格、纯新闻和其他对象都忽略，不要输出。"
                "股票字段必须规范：entity_name 写公司或证券名称，不要只写纯代码；entity_code_or_name 写 ticker/股票代码。"
                "美股 ticker 用普通代码，例如 NVDA、AMD、INTC；台湾上市股可写 6451.TW，A 股可写 300502.SZ。"
                "如果原文写 Shunsin (6451)，entity_name 应写 Shunsin，entity_code_or_name 应写 6451.TW 或 6451。"
                "如果原文写 Intel Foundry、Intel Foundry Services 或 IFS，且是在讨论其上市公司投资标的，应归到 Intel，entity_code_or_name 写 INTC，不要把 Intel Foundry 当成独立股票。"
                "如果对象只是上市公司里的业务部门、产品线、供应链角色，只有当作者明确把它转成该上市公司股票的买卖/看多看空结论时才输出；供应链泛叙事、生态带动、在某公司服务器中等模糊信息不要输出。"
                "stance 只能是 strong_bullish, bullish, neutral, bearish, strong_bearish, mixed, mention_only, unknown 之一。"
                "direction 表示作者本人对该股票的方向，只能是 positive, negative, neutral, mixed, unknown 之一；本任务只保留 positive 或 negative，其他方向通常不要输出。"
                "signal_type 只能是 explicit_stance 或 logic_based。"
                "explicit_stance 表示作者本人明确说看好、买入、持有、加仓、布局、继续拿，或明确说看空、卖出、减仓、不要碰、避开，但没有完整论证链；这类用于感知群众情绪和喊单聚集。"
                "logic_based 表示作者基于数据、财报、指引、管理层信号、监管、估值、订单、产品、资金流、技术面或其他证据，推出应该看多/买入/持有或看空/卖出/避开的结论。"
                "judgment_type 表示作者判断参与度，只能是 direct, implied, factual_only, quoted, mention_only, unknown 之一。"
                "direct 表示作者直接给出看多、看空、买卖、仓位、目标价等判断；logic_based 通常也应是 direct，除非作者没有直接喊但论证结论极明确才用 implied。"
                "implied 表示作者没有直接喊方向，但通过选择和组织事实构建了明确可交易结论；"
                "factual_only 表示只是行情、财报、数据、新闻等事实陈述，不能确认作者本人判断；"
                "quoted 表示主要是在转述公司管理层、机构或他人的判断；mention_only 表示仅提及。factual_only、quoted、mention_only 不应作为有效观点输出。"
                "conviction 表示判断强度，只能是 strong, medium, weak, none, unknown 之一。"
                "evidence_type 只能是 price_action, earnings, guidance, management_commentary, valuation, policy, rumor, position, capital_flow, technical, macro, other, unknown 之一。"
                "stance 是兼容旧界面的派生字段：direction 为 positive 时用 bullish/strong_bullish，negative 时用 bearish/strong_bearish。"
                "time_horizon 只能是 short_term, medium_term, long_term, unspecified 之一。"
                "不要把价格上涨、财报超预期、管理层表述自动判成作者看多；如果作者只是列出事实或转述别人观点且没有给出自己的股票结论，不要输出。"
                "如果作者转述管理层或机构信息，并明确说因此自己继续持有、看好、买入、卖出或避开，则输出 logic_based。"
                "如果只是提到股票、仅列清单、仅新闻事实、仅供应链关系、没有有效方向或没有作者本人判断，不要输出。"
                "logic 对 explicit_stance 只需简短说明作者明确表态；对 logic_based 必须写出“基于什么证据 -> 得出什么股票结论”的逻辑链。"
                "evidence 必须写出能支撑该判断的原文依据，尽量贴近原文表达，但不要大段照抄。"
                "同一对象如果在文中只有一个判断，就只输出一条，不要拆碎。"
                "events 用于承载非作者观点的客观信息，例如新闻、事件、独家报道、公告、管理层表述、分析师预期、产能/订单/产品/政策/供应链更新、业绩事实、数据播报。"
                "event 不代表作者本人立场，禁止把事件自动升级成观点。"
                "每条 event 必须包含字段：headline, event_summary, event_type, event_nature, linked_entities。"
                "headline 用一句中文短标题概括事件。"
                "event_summary 用 1 到 2 句中文说明发生了什么，不写作者态度。"
                "event_type 可使用 earnings_update, guidance_update, management_commentary, product_update, policy_update, supply_chain_update, profitability_outlook, analyst_report, exclusive_report, data_point, rumor, other。"
                "event_nature 可使用 reported, announced, exclusive, quoted, expected, rumored, other。"
                "linked_entities 是数组，每个元素必须包含 entity_type, entity_name, entity_code_or_name。"
                "linked_entities.entity_type 只能是 stock 或 theme。"
                "能明确挂到上市公司/证券主体的事件，entity_type 用 stock，并尽量写规范公司名和 ticker/股票代码。"
                "行业、主题、赛道、产业链类客观事件可用 theme，但不要把宏观市场风格、指数或纯宽泛概念塞进 theme。"
                "同一条事件可以关联多个实体；不要为了多个实体重复生成多条几乎相同的 event。"
                "如果作者既在报道事件，又明确表达自己的买卖方向，应同时输出 event 和 viewpoint。"
            ),
        },
        {
            "role": "user",
            "content": "请分析下面这篇内容并输出结构化 JSON：\n\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]


def build_crypto_asset_keyword_messages(asset_payload: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是一个 crypto 社区检索词扩展助手。"
                "只输出 JSON 对象，不要输出 markdown。"
                "必须输出字段：keywords。"
                "keywords 必须是 3 到 5 个中文或英文短词数组。"
                "每个短词只能是项目别名、赛道词、社区常用简称、机制词，不要写完整句子，不要写买卖建议。"
                "如果信息不足，也要尽量给出最稳妥的短词。"
            ),
        },
        {
            "role": "user",
            "content": "请基于下面资产信息生成 X 搜索扩展词：\n\n" + json.dumps(asset_payload, ensure_ascii=False),
        },
    ]


def build_crypto_ca_match_messages(name_group: dict, candidate_group: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是一个 crypto 项目同一性判断助手。"
                "目标是判断“名称搜索结果”和“候选合约地址搜索结果”是否在讨论同一个项目。"
                "只输出 JSON 对象，不要输出 markdown。"
                "必须输出字段：same_project, confidence, shared_signals, reason。"
                "same_project 必须是 true 或 false。"
                "confidence 必须是 0 到 1 之间的小数。"
                "shared_signals 必须是字符串数组，写出共同账号、共同别名、共同叙事词、共同机制词等。"
                "reason 用一句中文说明判断依据。"
                "判断时优先看社区讨论对象、项目账号、别名、机制词、赛道词是否一致，不要求文本完全重复。"
                "如果样本很少或证据冲突，应该降低 confidence。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请判断这两组 X 内容是否在说同一个 crypto 项目。\n\n"
                + json.dumps(
                    {
                        "name_group": name_group,
                        "candidate_group": candidate_group,
                    },
                    ensure_ascii=False,
                )
            ),
        },
    ]


def build_crypto_asset_brief_messages(payload: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是一个中文 crypto 叙事摘要助手。"
                "只输出 JSON 对象，不要输出 markdown。"
                "必须输出字段：summary_text。"
                "summary_text 必须是 1 到 2 句中文。"
                "第一句说明这个代币或项目是干嘛的。"
                "第二句说明 X 上当前主要叙事、社区认知或讨论焦点。"
                "不要给买卖建议，不要编造链上数据，不要输出列表。"
                "If payload.asset.identity_status is ambiguous, summary_text must explicitly say the project identity is not fully confirmed or may be mixed with same-name discussions."
                "如果样本不足，也要直说信息不足。"
            ),
        },
        {
            "role": "user",
            "content": "请基于下面材料生成 crypto 资产摘要：\n\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]


def build_crypto_note_extract_messages(note: RawNoteRecord) -> list[dict[str, str]]:
    payload = {
        "platform": note.platform,
        "account_name": note.account_name,
        "author_nickname": note.author_nickname,
        "note_id": note.note_id,
        "title": note.title,
        "desc": note.desc,
        "publish_time": note.publish_time,
        "url": note.url,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是一个中文 crypto 信息信号抽取助手。"
                "请只输出 JSON 对象，不要输出 markdown。"
                "JSON 顶层必须包含 summary_text, viewpoints。"
                "summary_text 只作为兼容字段，一句概括即可；有效数据以 viewpoints 为准。"
                "viewpoints 是数组，每个元素代表一条可落到项目或资产的 crypto 推荐实体/信息信号。"
                "不要局限标准 symbol；项目名、代币名、meme ticker、EVM 合约地址、Solana 地址、项目 X 账号、$ticker 都可以作为实体。"
                "只要作者发布、转发、提及、公告、数据播报或价格播报涉及具体 crypto 实体，就应输出；没有明确方向时保留为弱信号。"
                "每条观点必须包含字段："
                "entity_type, entity_name, entity_code_or_name, entity_identifier_type, raw_identifiers, stance, direction, "
                "signal_type, judgment_type, conviction, evidence_type, source_signal_level, logic, evidence, time_horizon。"
                "如有把握，请额外输出 entity_kind, canonical_name_hint, investable_score, specificity_score, entityness_score, is_generic_term。"
                "entity_type 固定为 crypto_entity。"
                "entity_name 写项目或资产名称，例如 Bitcoin、Ethereum、Solana、uPEG_ETH。"
                "entity_code_or_name 写原文最稳定标识，可以是 BTC、ETH、uPEG、0x...、Solana 地址或 @项目账号。"
                "entity_identifier_type 只能是 project_name, symbol, evm_contract, solana_address, project_account, meme_ticker, unknown。"
                "raw_identifiers 是数组，放原文出现过的全部关键标识。"
                "entity_kind 优先使用 project, token, org_or_fund, account, theme_or_generic, unknown。"
                "canonical_name_hint 是可选字段；当项目名和 @项目账号、symbol 或 meme ticker 明显指向同一实体时，写出你认为更稳定的规范名称。"
                "investable_score, specificity_score, entityness_score 是 0 到 1 的小数。"
                "is_generic_term 用 true 或 false；泛赛道词、泛主题词、泛项目描述应标记为 true。"
                "signal_type 只能是 explicit_stance, logic_based, informational, mention_signal。"
                "explicit_stance 表示作者明确看好/看空/买/卖/参与/避开。"
                "logic_based 表示作者基于链上、代币经济、生态、收入、流动性、解锁、融资、上所、催化等证据推出方向。"
                "informational 表示新闻、公告、数据、价格或事实播报，仍要保留。"
                "mention_signal 表示仅提及、转发或弱相关线索。"
                "direction 只能是 positive, negative, neutral, mixed, unknown；弱信号通常用 unknown。"
                "stance 使用兼容字段：positive 对应 bullish/strong_bullish，negative 对应 bearish/strong_bearish，unknown 弱信号用 mention_only 或 unknown。"
                "judgment_type 只能是 direct, implied, factual_only, quoted, mention_only, unknown；转发他人观点可用 quoted，公告/播报可用 factual_only，纯提及可用 mention_only。"
                "conviction 只能是 strong, medium, weak, none, unknown；弱信号用 none 或 weak。"
                "evidence_type 只能是 price_action, rumor, position, capital_flow, technical, macro, onchain, tokenomics, unlock, ecosystem, "
                "protocol_revenue, catalyst, listing, liquidity, funding_rate, security_incident, regulation, other, unknown。"
                "source_signal_level 只能是 strong, weak；明确观点或完整逻辑用 strong，转发/提及/播报用 weak。"
                "logic 对强信号写出证据到结论的链条；对弱信号说明它是什么信息信号。"
                "evidence 写贴近原文的短证据，不要大段照抄。"
                "time_horizon 只能是 short_term, medium_term, long_term, unspecified。"
                "同一实体在同一篇内容里可以合并为一条；多实体需要拆开。"
            ),
        },
        {
            "role": "user",
            "content": "请分析下面这篇内容并输出结构化 JSON：\n\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]


def build_author_day_summary_messages(
    account_name: str,
    date: str,
    extracts: list[NoteExtractRecord],
) -> list[dict[str, str]]:
    note_items = [
        {
            "note_id": item.note_id,
            "title": item.note_title,
            "summary_text": item.summary_text,
            "viewpoints": [view.model_dump(mode="json") for view in item.viewpoints],
        }
        for item in extracts
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是一个中文投研编辑。"
                "请基于同一作者某一天的多篇内容，写一句适合作为时间线标题的日总结。"
                "这句总结应突出作者当天最核心的观点方向，而不是流水账。"
                "只输出 JSON 对象，且只包含 summary_text 一个字段。"
                "summary_text 要紧凑、可读、信息密度高，直接点出作者关注的股票和看多/看空方向。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"作者：{account_name}\n"
                f"日期：{date}\n"
                "该作者当天的帖子结构化结果如下：\n"
                + json.dumps(note_items, ensure_ascii=False)
            ),
        },
    ]


def build_stock_narrative_messages(input_digest: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是一个中文投研叙事编辑。"
                "请只输出 JSON 对象，不要输出 markdown。"
                "任务是基于一批已结构化的股票观点，写一篇偏中立的中文叙事简报。"
                "必须输出字段：brief_text, mainstream_narrative, new_directions, rare_negative_signals。"
                "brief_text 是完整小作文，语气中立，不给买卖指令、目标价或新股票推荐。"
                "mainstream_narrative、new_directions、rare_negative_signals 都必须是中文句子数组。"
                "主流叙事只能写多名作者或多条证据共同支持的东西，不要把单个作者的一条观点写成大家都认可。"
                "新风向要优先比较当前 7 个有效观点日、上一非重叠周期简报和 14/30 日主题基线；"
                "请区分真正新出现、明显升温、单点早期信号。"
                "昨日或上一条简报只用于连续性，不要把它当成唯一历史事实。"
                "少见负面声音要保留样本里的反向观点或风险提示，并说明它目前是少数声音还是正在增多。"
                "不要为输入里没有证据的主题补行业背景。"
                "输入中的 current_viewpoints 故意不单独提供股票对象字段；请从 logic 和 evidence 里自然归纳主题，"
                "但不要臆造输入没有出现过的公司、题材或结论。"
                "如果样本不足，就在 brief_text 和对应数组里直接说明不足，不要硬写结论。"
            ),
        },
        {
            "role": "user",
            "content": "请基于下面的输入生成股票叙事简报 JSON：\n\n" + json.dumps(input_digest, ensure_ascii=False),
        },
    ]
