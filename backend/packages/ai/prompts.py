from __future__ import annotations

import json

from packages.common.models import NoteExtractRecord, RawNoteRecord


NOTE_EXTRACT_REQUIRED_KEYS = ["summary_text", "viewpoints"]
AUTHOR_SUMMARY_REQUIRED_KEYS = ["summary_text"]


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
                "目标不是复述帖子内容，而是抽取可以落到投研面板里的观点条目。"
                "JSON 顶层必须包含以下字段：summary_text, viewpoints。"
                "summary_text 是一句简洁中文概括，说明这篇内容中有效股票观点的主判断；如果没有有效股票观点，写“未形成有效股票观点”。"
                "viewpoints 是数组，每个元素代表一条独立股票观点；没有有效股票观点时必须返回空数组。"
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
