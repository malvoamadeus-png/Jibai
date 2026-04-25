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
                "summary_text 是一句简洁中文概括，说明这篇内容的主判断。"
                "viewpoints 是数组，每个元素代表一条独立观点。"
                "每条观点必须包含字段："
                "entity_type, entity_name, entity_code_or_name, stance, logic, evidence, time_horizon。"
                "entity_type 只能是 stock, theme, macro, other 之一。"
                "其中："
                "stock 表示股票、上市公司或可交易证券；"
                "theme 统一涵盖行业、板块、赛道、概念，例如 CPO、光通信、AI硬件、机器人；"
                "macro 表示宏观、政策、流动性、指数、市场风格、汇率、利率等；"
                "other 表示无法归入前三类但仍是明确观点对象。"
                "stance 只能是 strong_bullish, bullish, neutral, bearish, strong_bearish, mixed, mention_only, unknown 之一。"
                "time_horizon 只能是 short_term, medium_term, long_term, unspecified 之一。"
                "如果只是提到对象但没有明确判断，用 mention_only。"
                "如果完全没有形成可投资观点，就不要硬编观点，返回空数组。"
                "logic 必须写出作者为什么这么看。"
                "evidence 必须写出能支撑该判断的原文依据，尽量贴近原文表达，但不要大段照抄。"
                "同一对象如果在文中只有一个判断，就只输出一条，不要拆碎。"
                "不要把板块/赛道/概念分成多个类型，统一用 theme。"
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
                "summary_text 要紧凑、可读、信息密度高，最好直接点出关注的股票、theme 或宏观主线。"
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
