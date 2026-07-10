from __future__ import annotations

import json
from typing import Any, List, Optional


CHARACTER_FIELDS = [
    "id",
    "name",
    "speech_style",
    "behavior_style",
    "status",
    "goal",
    "secret",
    "other",
    "location",
    "items",
]

RELATIONSHIP_FIELDS = [
    "id",
    "from",
    "to",
    "type",
    "detail",
    "known_by",
    "hidden_from",
]

EVENT_FIELDS = [
    "id",
    "type",
    "title",
    "content",
    "status",
    "trigger",
    "related_characters",
    "known_by",
    "hidden_from",
]

SECRET_FIELDS = [
    "id",
    "from_character",
    "secret",
    "known_by",
    "hidden_from",
    "status",
]


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _text_list(value: Any) -> List[str]:
    result = []
    for item in _as_list(value):
        text = _safe_str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _truncate(text: Any, limit: int) -> str:
    text = _safe_str(text).strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _json_text(data: dict, *, indent: Optional[int] = None) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)


def _default_agent_story_brain() -> dict:
    return {
        "characters": [],
        "relationships": [],
        "events": [],
        "secrets": [],
        "scene": {
            "location": "",
            "time": "",
            "environment": "",
            "present_characters": [],
        },
    }


def empty_agent_story_brain() -> dict:
    return _default_agent_story_brain()


def _normalize_record(record: Any, fields: List[str]) -> dict:
    if not isinstance(record, dict):
        record = {}

    normalized = {}
    for field in fields:
        value = record.get(field, "")
        if field in {"known_by", "hidden_from", "related_characters", "items"}:
            normalized[field] = _text_list(value)
        else:
            normalized[field] = _safe_str(value).strip()
    return normalized


def _normalize_scene(scene: Any) -> dict:
    if not isinstance(scene, dict):
        scene = {}
    return {
        "location": _safe_str(scene.get("location", "")).strip(),
        "time": _safe_str(scene.get("time", "")).strip(),
        "environment": _safe_str(scene.get("environment", "")).strip(),
        "present_characters": _text_list(scene.get("present_characters")),
    }


def normalize_agent_story_brain(data: Any) -> dict:
    if not isinstance(data, dict):
        return _default_agent_story_brain()

    return {
        "characters": [
            _normalize_record(item, CHARACTER_FIELDS)
            for item in _as_list(data.get("characters"))
        ],
        "relationships": [
            _normalize_record(item, RELATIONSHIP_FIELDS)
            for item in _as_list(data.get("relationships"))
        ],
        "events": [
            _normalize_record(item, EVENT_FIELDS)
            for item in _as_list(data.get("events"))
        ],
        "secrets": [
            _normalize_record(item, SECRET_FIELDS)
            for item in _as_list(data.get("secrets"))
        ],
        "scene": _normalize_scene(data.get("scene")),
    }


def _copy_record(record: Any) -> Any:
    if not isinstance(record, dict):
        return record
    return dict(record)


def _collection_key(target_type: Any) -> str:
    target_type = _safe_str(target_type).strip().lower()
    if target_type == "character":
        return "characters"
    if target_type == "relationship":
        return "relationships"
    if target_type == "event":
        return "events"
    if target_type in {"secret", "inter_character_secret", "character_secret"}:
        return "secrets"
    return ""


def _fields_for_collection(collection_key: str) -> List[str]:
    if collection_key == "characters":
        return CHARACTER_FIELDS
    if collection_key == "relationships":
        return RELATIONSHIP_FIELDS
    if collection_key == "events":
        return EVENT_FIELDS
    if collection_key == "secrets":
        return SECRET_FIELDS
    return []


def _suggested_update_items(suggested_updates: Any) -> list:
    if isinstance(suggested_updates, dict):
        return _as_list(suggested_updates.get("suggested_updates"))
    if isinstance(suggested_updates, list):
        return suggested_updates
    return []


def _merge_scene(scene: dict, data: Any) -> dict:
    if not isinstance(data, dict):
        return scene
    merged = dict(scene)
    for key in ("location", "time", "environment", "present_characters"):
        if key not in data:
            continue
        if key == "present_characters":
            merged[key] = _text_list(data.get(key))
        else:
            merged[key] = _safe_str(data.get(key)).strip()
    return _normalize_scene(merged)


def apply_agent_story_brain_updates(story_brain: dict, suggested_updates: Any) -> dict:
    updated = normalize_agent_story_brain(story_brain)
    updated = {
        "characters": [_copy_record(item) for item in updated["characters"]],
        "relationships": [_copy_record(item) for item in updated["relationships"]],
        "events": [_copy_record(item) for item in updated["events"]],
        "secrets": [_copy_record(item) for item in updated["secrets"]],
        "scene": dict(updated["scene"]),
    }

    for update in _suggested_update_items(suggested_updates):
        if not isinstance(update, dict):
            continue

        target_type = _safe_str(update.get("target_type", "")).strip().lower()
        action = _safe_str(update.get("action", "")).strip().lower()
        data = update.get("data", {})

        if target_type == "scene":
            if action in {"modify", "set", "update"}:
                updated["scene"] = _merge_scene(updated["scene"], data)
            continue

        collection_key = _collection_key(target_type)
        fields = _fields_for_collection(collection_key)
        if not collection_key or not fields:
            continue

        collection = updated[collection_key]
        target_id = _safe_str(update.get("target_id", "")).strip()

        if action == "add":
            collection.append(_normalize_record(data, fields))
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
                candidate = {**original, **(data if isinstance(data, dict) else {})}
                collection[target_index] = _normalize_record(candidate, fields)
            continue

        if action == "delete":
            del collection[target_index]

    return normalize_agent_story_brain(updated)


def _character_name(character: dict) -> str:
    return _safe_str(character.get("name", "")).strip()


def _present_character_names(story_brain: dict, present_characters: Optional[List[str]] = None) -> List[str]:
    if present_characters is not None:
        names = _text_list(present_characters)
        if names:
            return names
    return _text_list(story_brain.get("scene", {}).get("present_characters"))


def _known_by_all(known_by: list) -> bool:
    return not known_by or "*" in known_by or "all" in [item.lower() for item in known_by]


def _record_visible_to_npc(record: dict, npc_name: str) -> bool:
    npc_name = _safe_str(npc_name).strip()
    known_by = _text_list(record.get("known_by"))
    hidden_from = _text_list(record.get("hidden_from"))
    if npc_name and npc_name in hidden_from:
        return False
    if _known_by_all(known_by):
        return True
    return bool(npc_name and npc_name in known_by)


def filter_agent_story_brain_for_npc(
    story_brain: dict,
    npc_name: str,
    *,
    present_characters: Optional[List[str]] = None,
) -> dict:
    data = normalize_agent_story_brain(story_brain)
    npc_name = _safe_str(npc_name).strip()
    present_names = _present_character_names(data, present_characters)
    visible_names = set(present_names)
    if npc_name:
        visible_names.add(npc_name)

    visible_characters = []
    for character in data["characters"]:
        name = _character_name(character)
        if name not in visible_names:
            continue
        item = dict(character)
        if name != npc_name:
            item["secret"] = ""
        visible_characters.append(item)

    visible_relationships = []
    for relationship in data["relationships"]:
        left = _safe_str(relationship.get("from", "")).strip()
        right = _safe_str(relationship.get("to", "")).strip()
        if left in visible_names and right in visible_names and _record_visible_to_npc(relationship, npc_name):
            visible_relationships.append(dict(relationship))

    visible_events = []
    for event in data["events"]:
        related = _text_list(event.get("related_characters"))
        related_visible = not related or any(name in visible_names for name in related)
        if related_visible and _record_visible_to_npc(event, npc_name):
            visible_events.append(dict(event))

    visible_secrets = []
    for secret in data["secrets"]:
        owner = _safe_str(secret.get("from_character", "")).strip()
        hidden_from = _text_list(secret.get("hidden_from"))
        known_by = _text_list(secret.get("known_by"))
        if npc_name and npc_name in hidden_from:
            continue
        if npc_name and (owner == npc_name or npc_name in known_by):
            visible_secrets.append(dict(secret))

    return {
        "characters": visible_characters,
        "relationships": visible_relationships,
        "events": visible_events,
        "secrets": visible_secrets,
        "scene": {
            **data["scene"],
            "present_characters": present_names,
        },
    }


def _detect_active_characters(current_text: str, characters: list) -> List[str]:
    text = _safe_str(current_text)
    active_names = []
    for character in characters:
        if not isinstance(character, dict):
            continue
        name = _character_name(character)
        if name and name in text and name not in active_names:
            active_names.append(name)
    return active_names


def _relationship_value(relationship: dict) -> str:
    rel_type = _safe_str(relationship.get("type", "")).strip()
    detail = _safe_str(relationship.get("detail", "")).strip()
    if rel_type and detail:
        return f"{rel_type}：{detail}"
    return rel_type or detail


def _event_constraint(event: dict) -> str:
    event_type = _safe_str(event.get("type", "")).strip()
    title = _safe_str(event.get("title", "")).strip()
    content = _safe_str(event.get("content", "")).strip()
    status = _safe_str(event.get("status", "")).strip()
    trigger = _safe_str(event.get("trigger", "")).strip()
    parts = [part for part in [event_type, title, content, status] if part]
    if trigger:
        parts.append("trigger：" + trigger)
    return "；".join(parts)


def build_agent_memory_pack(
    *,
    npc_name: str,
    current_text: str,
    story_brain: dict,
    present_characters: Optional[List[str]] = None,
) -> dict:
    visible = filter_agent_story_brain_for_npc(
        story_brain,
        npc_name,
        present_characters=present_characters,
    )

    active_names = _detect_active_characters(current_text, visible["characters"])
    if not active_names:
        active_names = _text_list(visible["scene"].get("present_characters"))
    if npc_name and npc_name not in active_names:
        active_names.append(npc_name)
    active_name_set = set(active_names)

    active_characters = [
        character
        for character in visible["characters"]
        if _character_name(character) in active_name_set
    ]

    relationships = {}
    for relationship in visible["relationships"]:
        left = _safe_str(relationship.get("from", "")).strip()
        right = _safe_str(relationship.get("to", "")).strip()
        if left not in active_name_set or right not in active_name_set:
            continue
        value = _relationship_value(relationship)
        if not value:
            continue
        key = f"{left}-{right}"
        relationships[key] = relationships[key] + "；" + value if key in relationships else value

    return {
        "npc_name": _safe_str(npc_name).strip(),
        "scene": visible["scene"],
        "active_characters": active_characters,
        "relationship": relationships,
        "visible_secrets": visible["secrets"],
        "generation_constraints": [
            item
            for item in (_event_constraint(event) for event in visible["events"])
            if item
        ],
    }


def compact_agent_memory_pack(memory_pack: dict, max_chars: int = 2000) -> dict:
    try:
        max_chars = int(max_chars)
    except Exception:
        max_chars = 2000
    max_chars = max(300, max_chars)

    compacted = {
        "npc_name": _safe_str(memory_pack.get("npc_name", "")).strip(),
        "scene": memory_pack.get("scene") if isinstance(memory_pack.get("scene"), dict) else {},
        "active_characters": list(_as_list(memory_pack.get("active_characters"))),
        "relationship": memory_pack.get("relationship") if isinstance(memory_pack.get("relationship"), dict) else {},
        "visible_secrets": list(_as_list(memory_pack.get("visible_secrets"))),
        "generation_constraints": list(_as_list(memory_pack.get("generation_constraints"))),
    }
    if len(_json_text(compacted, indent=2)) <= max_chars:
        return compacted

    compacted["generation_constraints"] = [
        _truncate(item, 160)
        for item in compacted["generation_constraints"]
    ][:8]
    compacted["visible_secrets"] = [
        {
            **secret,
            "secret": _truncate(secret.get("secret", ""), 140),
        }
        for secret in compacted["visible_secrets"][:5]
        if isinstance(secret, dict)
    ]
    if len(_json_text(compacted, indent=2)) <= max_chars:
        return compacted

    compacted["active_characters"] = [
        {
            **character,
            "other": _truncate(character.get("other", ""), 100),
            "goal": _truncate(character.get("goal", ""), 100),
            "secret": _truncate(character.get("secret", ""), 100),
        }
        for character in compacted["active_characters"][:6]
        if isinstance(character, dict)
    ]
    if len(_json_text(compacted, indent=2)) <= max_chars:
        return compacted

    compacted["relationship"] = dict(list(compacted["relationship"].items())[:6])
    compacted["generation_constraints"] = compacted["generation_constraints"][:4]
    compacted["visible_secrets"] = compacted["visible_secrets"][:3]
    return compacted


def agent_memory_pack_to_json(memory_pack: dict, max_chars: int = 2000) -> str:
    compacted = compact_agent_memory_pack(memory_pack, max_chars=max_chars)
    text = _json_text(compacted, indent=2)
    if len(text) <= max_chars:
        return text

    minimal = {
        "npc_name": compacted.get("npc_name", ""),
        "scene": compacted.get("scene", {}),
        "active_characters": compacted.get("active_characters", [])[:3],
        "relationship": dict(list(compacted.get("relationship", {}).items())[:3]),
        "visible_secrets": compacted.get("visible_secrets", [])[:1],
        "generation_constraints": compacted.get("generation_constraints", [])[:2],
        "note": "Agent Story Brain 已压缩，只保留该 NPC 可见的最相关信息",
    }
    return _json_text(minimal, indent=2)


def extract_agent_story_brain_update_prompt(
    *,
    player_input: str,
    npc_name: str,
    npc_instruction: str,
    npc_output: str,
    story_brain: dict,
    recent_history: str,
) -> str:
    data = normalize_agent_story_brain(story_brain)
    story_brain_json = _json_text(data, indent=2)
    player_input = _safe_str(player_input).strip()
    npc_name = _safe_str(npc_name).strip()
    npc_instruction = _safe_str(npc_instruction).strip()
    npc_output = _safe_str(npc_output).strip()
    recent_history = _safe_str(recent_history).strip()

    return f"""
你是 Agent Story Brain 长期记忆更新分析器。

你的任务：
根据“玩家输入 + NPC 本轮指令 + NPC 新输出 + 当前 Agent Story Brain + 最近互动历史”，判断是否出现需要更新 Agent Story Brain 的内容，包括：
- 新角色，或已有角色的说话风格、行为风格、身体状态、目标、秘密、位置、持有物品、其他稳定特征变化
- 角色关系新增或变化
- 主线推进、伏笔新增/触发/删除、长期限制新增或变化
- 内部秘密新增、变化、公开状态变化
- 当前场景的位置、时间、环境、在场角色变化

重要规则：
1. 你只能生成更新建议 suggested_updates，不能重建整个 Agent Story Brain。
2. 更新必须基于当前 Agent Story Brain 增量修改。
3. 不要建议删除已有记忆，除非文本中明确说明该记忆已失效、被撤销、需要删除，或已有伏笔已经触发。
4. 如果只是一次性动作、临时情绪、普通台词，不要过度记录。
5. 如果没有任何需要更新的内容，输出 {{"suggested_updates": []}}。
6. 新增数据的 id 请使用对应前缀：char_、rel_、event_、secret_。
7. modify 和 delete 必须填写已有 target_id；add 的 target_id 为空字符串。
8. 输出必须是严格合法 JSON，不要输出 Markdown、代码块或解释文字。
9. 如果当前 Agent Story Brain 为空，也要从本轮内容中主动抽取重要角色、关系、主线、伏笔、限制、场景和秘密。
10. character.status 只记录当前身体状态、受伤情况、当前姿势或行动限制，不记录心理状态、情绪、服装设定或身份背景。
11. character.location 只记录角色当前位置。
12. character.items 只记录角色当前持有的重要物品，必须是字符串数组。
13. character.secret 只记录该角色自己的隐藏设定；角色之间的独立秘密优先写入 secret 类型。
14. known_by 为空数组表示公开可见；hidden_from 表示明确不能知道该信息的角色。
15. 伏笔必须有非空 trigger，trigger 要说明何时触发以及触发后发生什么。
16. 如果本轮内容已经明确使用、揭露或让伏笔影响情节，应该 delete 对应 event 伏笔。

输出 JSON 格式必须严格符合：
{{
  "suggested_updates": [
    {{
      "target_type": "character | relationship | event | secret | scene",
      "action": "add | modify | delete",
      "target_id": "<已有 id，如果是新增或 scene 则为空>",
      "reason": "<为什么建议更新>",
      "data": {{}}
    }}
  ]
}}

如果 target_type 是 character，data 应符合：
{{
  "id": "char_<唯一id>",
  "name": "<NPC1 | NPC2 | NPC3 或角色名>",
  "speech_style": "<说话风格>",
  "behavior_style": "<行为风格>",
  "status": "<身体状态、受伤情况、当前姿势或行动限制>",
  "goal": "<角色目标>",
  "secret": "<角色自己的秘密或隐藏信息>",
  "other": "<其他稳定角色特点、服装、身份背景等>",
  "location": "<角色当前位置>",
  "items": ["<重要持有物品>"]
}}

如果 target_type 是 relationship，data 应符合：
{{
  "id": "rel_<唯一id>",
  "from": "<角色A>",
  "to": "<角色B>",
  "type": "<关系类型>",
  "detail": "<关系详细说明>",
  "known_by": ["<知道该关系的角色名>"],
  "hidden_from": ["<不知道该关系的角色名>"]
}}

如果 target_type 是 event，data 应符合：
{{
  "id": "event_<唯一id>",
  "type": "<伏笔 | 主线 | 限制>",
  "title": "<事件标题>",
  "content": "<事件内容>",
  "status": "<事件状态>",
  "trigger": "<仅伏笔使用，非空；主线和限制为空字符串>",
  "related_characters": ["<相关角色名>"],
  "known_by": ["<知道该事件的角色名>"],
  "hidden_from": ["<不知道该事件的角色名>"]
}}

如果 target_type 是 secret，data 应符合：
{{
  "id": "secret_<唯一id>",
  "from_character": "<秘密所属角色>",
  "secret": "<秘密内容>",
  "known_by": ["<知道该秘密的角色名>"],
  "hidden_from": ["<不知道该秘密的角色名>"],
  "status": "<未公开 | 部分公开 | 已公开>"
}}

如果 target_type 是 scene，data 应符合：
{{
  "location": "<当前场景地点>",
  "time": "<当前场景时间>",
  "environment": "<当前环境>",
  "present_characters": ["<当前同一场景内的角色名>"]
}}

当前 Agent Story Brain：
{story_brain_json}

玩家输入：
{player_input}

刚刚行动的 NPC：
{npc_name}

本轮给该 NPC 的行为指令：
{npc_instruction}

NPC 新输出：
{npc_output}

最近互动历史：
{recent_history or "暂无"}
""".strip()
