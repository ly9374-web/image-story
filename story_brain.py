from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STORY_BRAIN = {
    "characters": [],
    "relationships": [],
    "events": [],
}

CHARACTER_FIELDS = [
    "name",
    "speech_style",
    "behavior_style",
    "status",
    "goal",
    "secret",
    "other",
]


def _default_story_brain() -> dict:
    return {
        "characters": [],
        "relationships": [],
        "events": [],
    }


def empty_story_brain() -> dict:
    return _default_story_brain()


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _truncate(text: Any, limit: int) -> str:
    text = _safe_str(text).strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _json_text(data: dict, *, indent: int | None = None) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)


def _json_len(data: dict) -> int:
    return len(_json_text(data))


def _normalize_story_brain(data: Any) -> dict:
    if not isinstance(data, dict):
        return _default_story_brain()

    return {
        "characters": _as_list(data.get("characters")),
        "relationships": _as_list(data.get("relationships")),
        "events": _as_list(data.get("events")),
    }


def normalize_story_brain(data: Any) -> dict:
    return _normalize_story_brain(data)


def _normalize_character(character: Any, *, field_limit: int | None = None) -> dict:
    if not isinstance(character, dict):
        character = {"name": character}

    normalized = {}
    for field in CHARACTER_FIELDS:
        value = _safe_str(character.get(field, ""))
        normalized[field] = _truncate(value, field_limit) if field_limit is not None else value
    return normalized


def _constraint_content(item: Any) -> str:
    if isinstance(item, dict):
        return _safe_str(item.get("content", ""))
    return _safe_str(item)


def _normalize_memory_pack(memory_pack: Any) -> dict:
    if not isinstance(memory_pack, dict):
        memory_pack = {}

    relationships = {}
    raw_relationships = memory_pack.get("relationship", {})
    if isinstance(raw_relationships, dict):
        for key, value in raw_relationships.items():
            key_text = _safe_str(key).strip()
            if key_text:
                relationships[key_text] = _safe_str(value).strip()

    constraints = []
    for item in _as_list(memory_pack.get("generation_constraints")):
        content = _constraint_content(item).strip()
        if content:
            constraints.append(content)

    return {
        "active_characters": [
            _normalize_character(character)
            for character in _as_list(memory_pack.get("active_characters"))
        ],
        "relationship": relationships,
        "generation_constraints": constraints,
    }


def _relationship_is_between_active_characters(key: str, active_names: set[str]) -> bool:
    if "-" not in key:
        return False
    left, right = key.split("-", 1)
    return left.strip() in active_names and right.strip() in active_names


def _constraint_priority(text: str) -> int:
    if "限制" in text or "不可揭露" in text:
        return 0
    if "不能" in text or "禁止" in text or "必须" in text:
        return 1
    return 2


def _prioritize_constraints(constraints: list[str]) -> list[str]:
    indexed = list(enumerate(constraints))
    indexed.sort(key=lambda item: (_constraint_priority(item[1]), item[0]))
    return [item[1] for item in indexed]


def _relationship_value(relationship: dict) -> str:
    rel_type = _safe_str(relationship.get("type", "")).strip()
    detail = _safe_str(relationship.get("detail", "")).strip()
    if rel_type and detail:
        return f"{rel_type}：{detail}"
    return rel_type or detail


def _foreshadowing_constraint(event: dict) -> str:
    title = _safe_str(event.get("title", "")).strip()
    content = _safe_str(event.get("content", "")).strip()
    trigger = _safe_str(event.get("trigger", "")).strip()
    status = _safe_str(event.get("status", "")).strip()
    related_characters = [
        _safe_str(item).strip()
        for item in _as_list(event.get("related_characters"))
        if _safe_str(item).strip()
    ]

    parts = ["伏笔"]
    if title:
        parts.append(f"《{title}》")
    if content:
        parts.append(f"内容：{content}")
    if trigger:
        parts.append(f"触发条件：“{trigger}")
    else:
        parts.append("触发条件：未设置；不得触发该伏笔，直到补充 trigger")
    if status:
        parts.append(f"状态：{status}")
    if related_characters:
        parts.append("相关角色：" + "、".join(related_characters))

    parts.append("限制：trigger 未明确发生时，不得提到、解释、揭露、使用该伏笔，也不得让该伏笔影响情节。")
    return "；".join(parts)


def load_story_brain(path: str = "story_brain.json") -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {}
    except Exception:
        return _default_story_brain()

    return _normalize_story_brain(data)


def save_story_brain(story_brain: dict, path: str = "story_brain.json") -> None:
    data = _normalize_story_brain(story_brain)
    output_path = Path(path)
    if output_path.parent != Path("."):
        output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def detect_active_characters(current_text: str, story_brain: dict) -> list[str]:
    text = _safe_str(current_text)
    if not text.strip():
        return []

    data = _normalize_story_brain(story_brain)
    active_names = []
    seen = set()

    for character in data["characters"]:
        if not isinstance(character, dict):
            continue

        name = _safe_str(character.get("name", "")).strip()
        if name and name in text and name not in seen:
            active_names.append(name)
            seen.add(name)

    return active_names


def build_memory_pack(current_text: str, story_brain: dict) -> dict:
    data = _normalize_story_brain(story_brain)
    active_names = detect_active_characters(current_text, data)
    active_name_set = set(active_names)

    active_characters = []
    added_names = set()
    for character in data["characters"]:
        if not isinstance(character, dict):
            continue

        name = _safe_str(character.get("name", "")).strip()
        if name in active_name_set and name not in added_names:
            active_characters.append(_normalize_character(character))
            added_names.add(name)

    relationships = {}
    for relationship in data["relationships"]:
        if not isinstance(relationship, dict):
            continue

        from_name = _safe_str(relationship.get("from", "")).strip()
        to_name = _safe_str(relationship.get("to", "")).strip()
        if not from_name or not to_name:
            continue
        if from_name not in active_name_set or to_name not in active_name_set:
            continue

        key = f"{from_name}-{to_name}"
        value = _relationship_value(relationship)
        if not value:
            continue

        if key in relationships:
            relationships[key] = relationships[key] + "；" + value
        else:
            relationships[key] = value

    generation_constraints = []
    for event in data["events"]:
        if not isinstance(event, dict):
            continue

        event_type = _safe_str(event.get("type", "")).strip()
        content = _safe_str(event.get("content", "")).strip()

        if event_type == "限制":
            if not content:
                continue
            generation_constraints.append(content)
        elif event_type == "伏笔":
            generation_constraints.append(_foreshadowing_constraint(event))
        elif event_type == "主线":
            if not content:
                continue
            generation_constraints.append(content)

    return {
        "active_characters": active_characters,
        "relationship": relationships,
        "generation_constraints": generation_constraints,
    }


def compact_memory_pack(memory_pack: dict, max_chars: int = 1500) -> dict:
    try:
        max_chars = int(max_chars)
    except Exception:
        max_chars = 1500
    max_chars = max(200, max_chars)

    normalized = _normalize_memory_pack(memory_pack)
    if _json_len(normalized) <= max_chars:
        return normalized

    active_characters = [
        _normalize_character(character, field_limit=80)
        for character in normalized["active_characters"]
    ]
    active_names = {
        character["name"].strip()
        for character in active_characters
        if character.get("name", "").strip()
    }

    relationships = {
        _truncate(key, 120): _truncate(value, 120)
        for key, value in normalized["relationship"].items()
        if _relationship_is_between_active_characters(key, active_names)
    }

    constraints = [
        _truncate(constraint, 180)
        for constraint in _prioritize_constraints(normalized["generation_constraints"])
    ]

    compacted = {
        "active_characters": active_characters,
        "relationship": relationships,
        "generation_constraints": constraints,
    }
    if _json_len(compacted) <= max_chars:
        return compacted

    for keep_count in range(len(constraints), -1, -1):
        compacted["generation_constraints"] = constraints[:keep_count]
        if _json_len(compacted) <= max_chars:
            return compacted

    relationship_items = list(relationships.items())
    for keep_count in range(len(relationship_items), -1, -1):
        compacted["relationship"] = dict(relationship_items[:keep_count])
        if _json_len(compacted) <= max_chars:
            return compacted

    for field_limit in (60, 40, 20):
        compacted["active_characters"] = [
            _normalize_character(character, field_limit=field_limit)
            for character in compacted["active_characters"]
        ]
        if _json_len(compacted) <= max_chars:
            return compacted

    for keep_count in range(len(compacted["active_characters"]), -1, -1):
        compacted["active_characters"] = compacted["active_characters"][:keep_count]
        if _json_len(compacted) <= max_chars:
            return compacted

    return compacted


def _minimal_memory_pack(compacted: dict, max_chars: int) -> dict:
    note = "Story Brain 已被压缩，只保留本轮最相关记忆"
    constraints = _prioritize_constraints(compacted.get("generation_constraints", []))
    relationship_items = list(compacted.get("relationship", {}).items())
    characters = compacted.get("active_characters", [])

    for character_count in (3, 2, 1, 0):
        for relationship_count in (3, 1, 0):
            for constraint_count in (5, 3, 1, 0):
                candidate = {
                    "active_characters": [
                        _normalize_character(character, field_limit=40)
                        for character in characters[:character_count]
                    ],
                    "relationship": {
                        key: _truncate(value, 60)
                        for key, value in relationship_items[:relationship_count]
                    },
                    "generation_constraints": [
                        _truncate(item, 80)
                        for item in constraints[:constraint_count]
                    ],
                    "note": note,
                }
                if len(_json_text(candidate, indent=2)) <= max_chars:
                    return candidate

    return {
        "active_characters": [],
        "relationship": {},
        "generation_constraints": [],
        "note": note,
    }


def memory_pack_to_json(memory_pack: dict, max_chars: int = 1500) -> str:
    try:
        max_chars = int(max_chars)
    except Exception:
        max_chars = 1500
    max_chars = max(200, max_chars)

    compacted = compact_memory_pack(memory_pack, max_chars=max_chars)
    text = _json_text(compacted, indent=2)
    if len(text) <= max_chars:
        return text

    minimal = _minimal_memory_pack(compacted, max_chars)
    return _json_text(minimal, indent=2)


def extract_story_brain_update_prompt(
    current_text: str,
    model_reply: str,
    story_brain: dict,
) -> str:
    data = _normalize_story_brain(story_brain)
    story_brain_json = _json_text(data, indent=2)
    current_text = _safe_str(current_text).strip()
    model_reply = _safe_str(model_reply).strip()

    return f"""
你是 Story Brain 长期记忆更新分析器。

你的任务：
根据“用户输入 + 模型新生成内容 + 当前 Story Brain”，判断是否出现需要更新 Story Brain 的内容，包括：
- 新角色
- 角色说话风格、行为风格、身体状态、目标、秘密或其他特征变化
- 角色关系新增或变化
- 伏笔新增、trigger 推断、状态变化或触发后删除
- 主线推进
- 小说限制新增、变化或删除

重要规则：
1. 你只能生成更新建议 suggested_updates，不能重建整个 Story Brain。
2. 更新必须基于当前 Story Brain 增量修改。
3. 不要建议删除已有记忆，除非文本中明确说明该记忆已失效、被撤销、需要删除，或已有伏笔已经触发。
4. 如果只是正文里的临时描写，不要过度记录。
5. 如果没有任何需要更新的内容，输出 {{"suggested_updates": []}}。
6. 新增数据的 id 请使用对应前缀：char_、rel_、event_。
7. modify 和 delete 必须填写已有 target_id。
8. add 的 target_id 为空字符串。
9. 输出必须是严格合法 JSON。
10. 不要输出 Markdown。
11. 不要输出代码块。
12. 不要输出解释文字。
13. 如果当前 Story Brain 为空，也要从本轮用户输入和模型新生成内容中主动抽取新角色、关系、主线、伏笔、限制，并以 add 建议输出。
14. 如果发现新的重要角色、稳定关系、主线推进、伏笔或长期限制，即使当前 Story Brain 中还没有相关节点，也应该生成 add 建议。
15. 伏笔定义：只有“之后会对剧情有影响，同时目前还未造成影响的事实”才算伏笔；如果未来不会对剧情造成影响，或在本轮已经造成影响的事实，不属于伏笔。属于伏笔的案例：某人受伤/无人注意到的警报 不属于伏笔的案例：某人吃了饭/被大家注意到的警报。 
16. 新增 type 为“伏笔”的 event 时，data.trigger 必须是非空字符串。trigger 要推断“什么时候且只有什么时候这个伏笔会对剧情产生影响”。 
17. trigger 只给 type 为“伏笔”的 event 使用；主线和限制不要使用 trigger。伏笔的content需要包含当trigger被触发时会发生什么 案例：被触发时老师会害怕/ 被触发时主角行为会受限
18. trigger至少包含两个要求：1.提到何时触发，2.触发发生什么。 trigger的范例：xx走路时/ 当主角团去到xx时
19. 对已有伏笔，如果本轮模型新生成内容中已经明确提到、解释、揭露、使用该伏笔，或让该伏笔影响情节，必须输出 action 为 delete 的 event 更新并填写已有 target_id。
20. character.status 只记录角色当前身体状态、受伤情况和当前姿势，例如流血、骨折、昏迷、站着、坐着、躺着、跪着、被束缚、行动受限等。
21. character.status 必须总结为当前最新身体状态，不要写成历史流水账。
22. character.status 不得记录心理状态、情绪、态度、服装设定或身份背景；服装设定和身份背景应写入 other。

输出 JSON 格式必须严格符合：
{{
  "suggested_updates": [
    {{
      "target_type": "character | relationship | event",
      "action": "add | modify | delete",
      "target_id": "<已有 id，如果是新增则为空>",
      "reason": "<为什么建议更新>",
      "data": {{}}
    }}
  ]
}}

如果 target_type 是 character，data 应符合：
{{
  "id": "char_<唯一id>",
  "name": "<角色名>",
  "speech_style": "<说话风格>",
  "behavior_style": "<行为风格>",
  "status": "<身体状态、受伤情况、当前姿势；不要记录心理状态、情绪、服装设定或身份背景>",
  "other": "<其他角色特点>",
  "goal": "<角色目标>",
  "secret": "<角色秘密或隐藏信息>"
}}

如果 target_type 是 relationship，data 应符合：
{{
  "id": "rel_<唯一id>",
  "from": "<角色A>",
  "to": "<角色B>",
  "type": "<关系类型>",
  "detail": "<关系详细说明>"
}}

如果 target_type 是 event，data 应符合：
{{
  "id": "event_<唯一id>",
  "type": "<伏笔 | 主线 | 限制>",
  "title": "<事件标题>",
  "content": "<事件内容>",
  "status": "<事件状态>",
  "trigger": "<仅伏笔使用，非空；什么时候且只有什么时候会触发这个伏笔>",
  "related_characters": ["<相关角色名>"]
}}

当前 Story Brain：
{story_brain_json}

用户输入 / 当前小说正文：
{current_text}

模型新生成内容：
{model_reply}
""".strip()


def _story_brain_collection_key(target_type: Any) -> str:
    target_type = _safe_str(target_type).strip().lower()
    if target_type == "character":
        return "characters"
    if target_type == "relationship":
        return "relationships"
    if target_type == "event":
        return "events"
    return ""


def _suggested_update_items(suggested_updates: Any) -> list:
    if isinstance(suggested_updates, dict):
        return _as_list(suggested_updates.get("suggested_updates"))
    if isinstance(suggested_updates, list):
        return suggested_updates
    return []


def _copy_story_brain_record(record: Any) -> Any:
    if not isinstance(record, dict):
        return record
    return dict(record)


def apply_story_brain_updates(
    story_brain: dict,
    suggested_updates: dict,
) -> dict:
    updated = _normalize_story_brain(story_brain)
    updated = {
        "characters": [_copy_story_brain_record(item) for item in updated["characters"]],
        "relationships": [_copy_story_brain_record(item) for item in updated["relationships"]],
        "events": [_copy_story_brain_record(item) for item in updated["events"]],
    }

    for update in _suggested_update_items(suggested_updates):
        if not isinstance(update, dict):
            continue

        collection_key = _story_brain_collection_key(update.get("target_type"))
        if not collection_key:
            continue

        action = _safe_str(update.get("action", "")).strip().lower()
        target_id = _safe_str(update.get("target_id", "")).strip()
        data = update.get("data", {})
        if not isinstance(data, dict):
            data = {}

        collection = updated[collection_key]

        if action == "add":
            if collection_key == "events":
                data = dict(data)
                event_type = _safe_str(data.get("type", "")).strip()
                trigger = _safe_str(data.get("trigger", "")).strip()
                if event_type == "伏笔" and not trigger:
                    continue
                if event_type != "伏笔":
                    data["trigger"] = ""
            collection.append(dict(data))
            continue

        if not target_id:
            continue

        target_index = None
        for index, item in enumerate(collection):
            if isinstance(item, dict) and _safe_str(item.get("id", "")).strip() == target_id:
                target_index = index
                break

        if target_index is None:
            continue

        if action == "modify":
            original = collection[target_index]
            if isinstance(original, dict):
                candidate = {
                    **original,
                    **data,
                }
                if collection_key == "events":
                    event_type = _safe_str(candidate.get("type", "")).strip()
                    trigger = _safe_str(candidate.get("trigger", "")).strip()
                    if event_type == "伏笔" and not trigger:
                        continue
                    if event_type != "伏笔":
                        candidate["trigger"] = ""
                collection[target_index] = candidate
            continue

        if action == "delete":
            del collection[target_index]

    return updated
