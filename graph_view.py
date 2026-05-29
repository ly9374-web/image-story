from __future__ import annotations

import html
from typing import Any

from pyvis.network import Network


GRAPH_HEIGHT_PX = 650
GRAPH_NODE_SPACING = 320
GRAPH_TRAIT_NODE_COLOR = "#6366f1"
GRAPH_CHARACTER_NODE_COLOR = "#60a5fa"
GRAPH_EVENT_NODE_COLOR = "#fde68a"
GRAPH_NODE_FONT_COLOR = "#000000"


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _clip_label(value: Any, limit: int = 28) -> str:
    text = _safe_str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _title_lines(lines: list[tuple[str, Any]]) -> str:
    rendered = []
    for label, value in lines:
        text = _safe_str(value).strip()
        if text:
            rendered.append(f"<b>{html.escape(label)}</b>: {html.escape(text)}")
    return "<br>".join(rendered) if rendered else ""


def _unique_id(base: str, used_ids: set[str]) -> str:
    node_id = base
    index = 2
    while node_id in used_ids:
        node_id = f"{base}_{index}"
        index += 1
    used_ids.add(node_id)
    return node_id


def _character_node_id(character: dict, index: int, used_ids: set[str]) -> str:
    raw_id = _safe_str(character.get("id", "")).strip()
    name = _safe_str(character.get("name", "")).strip()
    base = raw_id or f"character_{index}_{name or 'unnamed'}"
    return _unique_id("character:" + base, used_ids)


def _event_node_id(event: dict, index: int, used_ids: set[str]) -> str:
    raw_id = _safe_str(event.get("id", "")).strip()
    title = _safe_str(event.get("title", "")).strip()
    base = raw_id or f"event_{index}_{title or 'untitled'}"
    return _unique_id("event:" + base, used_ids)


def _add_trait_node(
    net: Network,
    *,
    character_id: str,
    character_name: str,
    field_key: str,
    label: str,
    value: Any,
    used_ids: set[str],
) -> None:
    node_id = _unique_id(f"trait:{character_id}:{field_key}", used_ids)
    text = _safe_str(value).strip()
    node_label = _clip_label(text or "未填写", 24)
    title = _title_lines([
        ("角色", character_name),
        (label, text or "未填写"),
    ])
    net.add_node(
        node_id,
        label=node_label,
        title=title,
        group="trait",
        size=18,
        shape="box",
        color=GRAPH_TRAIT_NODE_COLOR,
        font={"color": GRAPH_NODE_FONT_COLOR},
    )
    net.add_edge(
        character_id,
        node_id,
        label=label,
        title=title,
        color="#64748b",
    )


def _empty_graph_html() -> str:
    net = Network(
        height="650px",
        width="100%",
        bgcolor="#0b0f14",
        font_color=GRAPH_NODE_FONT_COLOR,
        directed=False,
        cdn_resources="in_line",
    )
    net.add_node(
        "empty_story_brain",
        label="暂无 Story Brain 数据",
        title="暂无 Story Brain 数据",
        group="event",
        size=28,
        shape="box",
        color="#475569",
    )
    net.set_options(
        """
        {
          "interaction": {
            "hover": true,
              "dragNodes": true,
              "dragView": true,
              "zoomView": false
          },
          "physics": {
            "enabled": true,
            "stabilization": true
          }
        }
        """
    )
    return net.generate_html()


def build_story_brain_graph_html(story_brain: dict) -> str:
    data = _as_dict(story_brain)
    characters = _as_list(data.get("characters"))
    relationships = _as_list(data.get("relationships"))
    events = _as_list(data.get("events"))

    if not characters and not relationships and not events:
        return _empty_graph_html()

    net = Network(
        height="650px",
        width="100%",
        bgcolor="#0b0f14",
        font_color=GRAPH_NODE_FONT_COLOR,
        directed=False,
        cdn_resources="in_line",
    )
    net.barnes_hut(
        gravity=-2600,
        central_gravity=0.22,
        spring_length=GRAPH_NODE_SPACING,
        spring_strength=0.035,
        damping=0.12,
    )

    used_ids: set[str] = set()
    character_ids_by_name: dict[str, str] = {}

    for index, raw_character in enumerate(characters):
        character = _as_dict(raw_character)
        name = _safe_str(character.get("name", "")).strip() or f"未命名角色 {index + 1}"
        node_id = _character_node_id(character, index, used_ids)
        character_ids_by_name.setdefault(name, node_id)

        title = _title_lines([
            ("角色", name),
            ("说话风格", character.get("speech_style")),
            ("行为风格", character.get("behavior_style")),
            ("状态", character.get("status")),
            ("目标", character.get("goal")),
            ("秘密", character.get("secret")),
            ("其他", character.get("other")),
        ])
        net.add_node(
            node_id,
            label=_clip_label(name, 24),
            title=title,
            group="character",
            size=40,
            shape="circle",
            color=GRAPH_CHARACTER_NODE_COLOR,
            font={"color": GRAPH_NODE_FONT_COLOR},
        )

        _add_trait_node(
            net,
            character_id=node_id,
            character_name=name,
            field_key="speech_style",
            label="说话风格",
            value=character.get("speech_style"),
            used_ids=used_ids,
        )
        _add_trait_node(
            net,
            character_id=node_id,
            character_name=name,
            field_key="behavior_style",
            label="行为风格",
            value=character.get("behavior_style"),
            used_ids=used_ids,
        )
        _add_trait_node(
            net,
            character_id=node_id,
            character_name=name,
            field_key="status",
            label="状态",
            value=character.get("status"),
            used_ids=used_ids,
        )
        _add_trait_node(
            net,
            character_id=node_id,
            character_name=name,
            field_key="other",
            label="其他",
            value=character.get("other"),
            used_ids=used_ids,
        )

        goal = _safe_str(character.get("goal", "")).strip()
        if goal:
            _add_trait_node(
                net,
                character_id=node_id,
                character_name=name,
                field_key="goal",
                label="目标",
                value=goal,
                used_ids=used_ids,
            )

        secret = _safe_str(character.get("secret", "")).strip()
        if secret:
            _add_trait_node(
                net,
                character_id=node_id,
                character_name=name,
                field_key="secret",
                label="秘密",
                value=secret,
                used_ids=used_ids,
            )

    for raw_relationship in relationships:
        relationship = _as_dict(raw_relationship)
        from_name = _safe_str(relationship.get("from", "")).strip()
        to_name = _safe_str(relationship.get("to", "")).strip()
        from_id = character_ids_by_name.get(from_name)
        to_id = character_ids_by_name.get(to_name)
        if not from_id or not to_id:
            continue

        relationship_type = _safe_str(relationship.get("type", "")).strip()
        detail = _safe_str(relationship.get("detail", "")).strip()
        title = _title_lines([
            ("关系", relationship_type),
            ("详情", detail),
        ])
        net.add_edge(
            from_id,
            to_id,
            label=_clip_label(relationship_type, 18),
            title=title,
            group="relationship",
            width=3,
            color="#f59e0b",
        )

    for index, raw_event in enumerate(events):
        event = _as_dict(raw_event)
        event_type = _safe_str(event.get("type", "")).strip()
        title_text = _safe_str(event.get("title", "")).strip()
        content = _safe_str(event.get("content", "")).strip()
        status = _safe_str(event.get("status", "")).strip()
        trigger = _safe_str(event.get("trigger", "")).strip()
        label = title_text or content or f"事件 {index + 1}"

        event_id = _event_node_id(event, index, used_ids)
        event_title = _title_lines([
            ("类型", event_type),
            ("标题", title_text),
            ("内容", content),
            ("状态", status),
            ("触发条件", trigger if event_type == "伏笔" else ""),
            ("相关角色", "、".join(_safe_str(item) for item in _as_list(event.get("related_characters")))),
        ])
        net.add_node(
            event_id,
            label=_clip_label(label, 32),
            title=event_title,
            group="event",
            size=24,
            shape="box",
            color=GRAPH_EVENT_NODE_COLOR,
            font={"color": GRAPH_NODE_FONT_COLOR},
        )

        for related_name in _as_list(event.get("related_characters")):
            character_id = character_ids_by_name.get(_safe_str(related_name).strip())
            if character_id:
                net.add_edge(
                    event_id,
                    character_id,
                    label=event_type or "相关",
                    title=event_title,
                    color="#94a3b8",
                )

    net.set_options(
        """
        {
          "interaction": {
            "hover": true,
              "dragNodes": true,
              "dragView": true,
              "zoomView": true
          },
          "nodes": {
              "font": {
              "color": "#000000",
              "size": 18,
              "face": "Arial"
            },
            "borderWidth": 2
          },
          "edges": {
            "font": {
              "color": "#000000",
              "size": 14,
              "align": "middle"
            },
            "smooth": {
              "type": "dynamic"
            }
          },
          "physics": {
            "enabled": true,
            "stabilization": true
          }
        }
        """
    )
    return net.generate_html()


def build_story_brain_graph_data(
    story_brain: dict,
    *,
    node_spacing: int = GRAPH_NODE_SPACING,
    height: int = GRAPH_HEIGHT_PX,
) -> dict:
    data = _as_dict(story_brain)
    characters = _as_list(data.get("characters"))
    relationships = _as_list(data.get("relationships"))
    events = _as_list(data.get("events"))

    if not characters and not relationships and not events:
        return {
            "height": height,
            "node_spacing": node_spacing,
            "nodes": [
                {
                    "id": "empty_story_brain",
                    "label": "暂无 Story Brain 数据",
                    "title": "暂无 Story Brain 数据",
                    "group": "event",
                    "shape": "box",
                    "size": 28,
                    "color": "#475569",
                    "font": {"color": GRAPH_NODE_FONT_COLOR},
                    "editable": False,
                }
            ],
            "edges": [],
        }

    used_ids: set[str] = set()
    used_edge_ids: set[str] = set()
    character_ids_by_name: dict[str, str] = {}
    nodes = []
    edges = []

    for index, raw_character in enumerate(characters):
        character = _as_dict(raw_character)
        name = _safe_str(character.get("name", "")).strip() or f"未命名角色 {index + 1}"
        node_id = _character_node_id(character, index, used_ids)
        raw_id = _safe_str(character.get("id", "")).strip()
        character_ids_by_name.setdefault(name, node_id)

        title = _title_lines([
            ("角色", name),
            ("说话风格", character.get("speech_style")),
            ("行为风格", character.get("behavior_style")),
            ("状态", character.get("status")),
            ("目标", character.get("goal")),
            ("秘密", character.get("secret")),
            ("其他", character.get("other")),
        ])
        nodes.append(
            {
                "id": node_id,
                "label": _clip_label(name, 24),
                "title": title,
                "group": "character",
                "shape": "circle",
                "size": 40,
                "color": GRAPH_CHARACTER_NODE_COLOR,
                "font": {"color": GRAPH_NODE_FONT_COLOR},
                "nodeType": "character",
                "targetType": "character",
                "recordId": raw_id,
                "recordIndex": index,
                "data": {
                    "id": raw_id,
                    "name": name,
                    "speech_style": _safe_str(character.get("speech_style", "")),
                    "behavior_style": _safe_str(character.get("behavior_style", "")),
                    "status": _safe_str(character.get("status", "")),
                    "other": _safe_str(character.get("other", "")),
                    "goal": _safe_str(character.get("goal", "")),
                    "secret": _safe_str(character.get("secret", "")),
                },
            }
        )

        for field_key, field_label in [
            ("speech_style", "说话风格"),
            ("behavior_style", "行为风格"),
            ("status", "状态"),
            ("other", "其他"),
            ("goal", "目标"),
            ("secret", "秘密"),
        ]:
            value = _safe_str(character.get(field_key, "")).strip()
            if field_key in {"goal", "secret"} and not value:
                continue

            trait_id = _unique_id(f"trait:{node_id}:{field_key}", used_ids)
            node_label = _clip_label(value or "未填写", 24)
            trait_title = _title_lines([
                ("角色", name),
                (field_label, value or "未填写"),
            ])
            nodes.append(
                {
                    "id": trait_id,
                    "label": node_label,
                    "title": trait_title,
                    "group": "trait",
                    "shape": "box",
                    "size": 18,
                    "color": GRAPH_TRAIT_NODE_COLOR,
                    "font": {"color": GRAPH_NODE_FONT_COLOR},
                    "nodeType": "trait",
                    "targetType": "character",
                    "recordId": raw_id,
                    "recordIndex": index,
                    "fieldKey": field_key,
                    "fieldLabel": field_label,
                    "data": {field_key: value},
                }
            )
            edges.append(
                {
                    "id": _unique_id(f"edge:{node_id}:{trait_id}", used_edge_ids),
                    "from": node_id,
                    "to": trait_id,
                    "label": field_label,
                    "title": trait_title,
                    "color": "#64748b",
                }
            )

    for index, raw_relationship in enumerate(relationships):
        relationship = _as_dict(raw_relationship)
        from_name = _safe_str(relationship.get("from", "")).strip()
        to_name = _safe_str(relationship.get("to", "")).strip()
        from_id = character_ids_by_name.get(from_name)
        to_id = character_ids_by_name.get(to_name)
        if not from_id or not to_id:
            continue

        relationship_type = _safe_str(relationship.get("type", "")).strip()
        detail = _safe_str(relationship.get("detail", "")).strip()
        title = _title_lines([
            ("关系", relationship_type),
            ("详情", detail),
        ])
        edges.append(
            {
                "id": _unique_id(
                    "edge:relationship:" + (_safe_str(relationship.get("id", "")).strip() or str(index)),
                    used_edge_ids,
                ),
                "from": from_id,
                "to": to_id,
                "label": _clip_label(relationship_type, 18),
                "title": title,
                "group": "relationship",
                "width": 3,
                "color": "#f59e0b",
                "edgeType": "relationship",
                "targetType": "relationship",
                "recordId": _safe_str(relationship.get("id", "")).strip(),
                "recordIndex": index,
                "data": {
                    "id": _safe_str(relationship.get("id", "")).strip(),
                    "from": from_name,
                    "to": to_name,
                    "type": relationship_type,
                    "detail": detail,
                },
            }
        )

    for index, raw_event in enumerate(events):
        event = _as_dict(raw_event)
        event_type = _safe_str(event.get("type", "")).strip()
        title_text = _safe_str(event.get("title", "")).strip()
        content = _safe_str(event.get("content", "")).strip()
        status = _safe_str(event.get("status", "")).strip()
        trigger = _safe_str(event.get("trigger", "")).strip()
        label = title_text or content or f"事件 {index + 1}"

        event_id = _event_node_id(event, index, used_ids)
        event_title = _title_lines([
            ("类型", event_type),
            ("标题", title_text),
            ("内容", content),
            ("状态", status),
            ("触发条件", trigger if event_type == "伏笔" else ""),
            ("相关角色", "、".join(_safe_str(item) for item in _as_list(event.get("related_characters")))),
        ])
        nodes.append(
            {
                "id": event_id,
                "label": _clip_label(label, 32),
                "title": event_title,
                "group": "event",
                "shape": "box",
                "size": 28,
                "color": GRAPH_EVENT_NODE_COLOR,
                "font": {"color": GRAPH_NODE_FONT_COLOR},
                "nodeType": "event",
                "targetType": "event",
                "recordId": _safe_str(event.get("id", "")).strip(),
                "recordIndex": index,
                "data": {
                    "id": _safe_str(event.get("id", "")).strip(),
                    "type": event_type,
                    "title": title_text,
                    "content": content,
                    "status": status,
                    "trigger": trigger,
                    "related_characters": [
                        _safe_str(item).strip()
                        for item in _as_list(event.get("related_characters"))
                        if _safe_str(item).strip()
                    ],
                },
            }
        )

        for related_name in _as_list(event.get("related_characters")):
            character_id = character_ids_by_name.get(_safe_str(related_name).strip())
            if character_id:
                edges.append(
                    {
                        "id": _unique_id(f"edge:{event_id}:{character_id}", used_edge_ids),
                        "from": event_id,
                        "to": character_id,
                        "label": event_type or "相关",
                        "title": event_title,
                        "color": "#94a3b8",
                    }
                )

    return {
        "height": height,
        "node_spacing": node_spacing,
        "nodes": nodes,
        "edges": edges,
    }
