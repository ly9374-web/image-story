from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from app.config import AppStorageKeys, settings
from app.models import AgentPromptRecord, now_iso


PROMPT_FIELDS = [
    ("npc1_prompt", "NPC1 Prompt"),
    ("npc2_prompt", "NPC2 Prompt"),
    ("npc3_prompt", "NPC3 Prompt"),
    ("player_parser_prompt", "Prompt4 玩家输入解析器"),
    ("action_scheduler_prompt", "Prompt5 行动裁决与下一角色调度器"),
    ("scene_descriptor_prompt", "Prompt6 场景描述器"),
]


@dataclass
class AgentPromptState:
    records: List[AgentPromptRecord]
    next_index: int
    selected_record_id: str


def _decode_records(raw) -> List[AgentPromptRecord]:
    if not raw:
        return []

    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(raw)
        except Exception:
            return []

    records: List[AgentPromptRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        records.append(AgentPromptRecord.from_dict(item))
    return records


def _encode_records(records: List[AgentPromptRecord]) -> str:
    return json.dumps([r.to_dict() for r in records], ensure_ascii=False)


def _persist(state: AgentPromptState):
    settings.set(AppStorageKeys.AGENT_PROMPT_RECORDS, _encode_records(state.records))
    settings.set(AppStorageKeys.AGENT_PROMPT_RECORD_NEXT_INDEX, int(state.next_index))
    settings.set(AppStorageKeys.SELECTED_AGENT_PROMPT_RECORD_ID, str(state.selected_record_id or ""))


def load_state() -> AgentPromptState:
    records = _decode_records(settings.get(AppStorageKeys.AGENT_PROMPT_RECORDS, ""))
    selected_record_id = str(settings.get(AppStorageKeys.SELECTED_AGENT_PROMPT_RECORD_ID, "") or "")
    next_index = max(1, int(settings.get(AppStorageKeys.AGENT_PROMPT_RECORD_NEXT_INDEX, 1) or 1))

    if selected_record_id and not any(record.id == selected_record_id for record in records):
        selected_record_id = ""
        settings.set(AppStorageKeys.SELECTED_AGENT_PROMPT_RECORD_ID, "")

    return AgentPromptState(
        records=records,
        next_index=next_index,
        selected_record_id=selected_record_id,
    )


def get_record(state: AgentPromptState, record_id: str) -> Optional[AgentPromptRecord]:
    record_id = str(record_id or "").strip()
    for record in state.records:
        if record.id == record_id:
            return record
    return None


def selected_record(state: AgentPromptState) -> Optional[AgentPromptRecord]:
    if state.selected_record_id:
        record = get_record(state, state.selected_record_id)
        if record is not None:
            return record
    if state.records:
        return state.records[0]
    return None


def select_record(state: AgentPromptState, record_id: str) -> AgentPromptState:
    record = get_record(state, record_id)
    if record is None:
        return state

    state.selected_record_id = record.id
    _persist(state)
    return state


def save_prompt_record(
    state: AgentPromptState,
    *,
    record_id: str,
    title: str,
    npc1_name: str = "NPC1",
    npc2_name: str = "NPC2",
    npc3_name: str = "NPC3",
    npc1_prompt: str = "",
    npc2_prompt: str = "",
    npc3_prompt: str = "",
    player_parser_prompt: str = "",
    action_scheduler_prompt: str = "",
    scene_descriptor_prompt: str = "",
) -> AgentPromptState:
    record_id = str(record_id or "").strip()
    title = str(title or "").strip()
    values = {
        "npc1_name": str(npc1_name or "NPC1").strip() or "NPC1",
        "npc2_name": str(npc2_name or "NPC2").strip() or "NPC2",
        "npc3_name": str(npc3_name or "NPC3").strip() or "NPC3",
        "npc1_prompt": str(npc1_prompt or "").strip(),
        "npc2_prompt": str(npc2_prompt or "").strip(),
        "npc3_prompt": str(npc3_prompt or "").strip(),
        "player_parser_prompt": str(player_parser_prompt or "").strip(),
        "action_scheduler_prompt": str(action_scheduler_prompt or "").strip(),
        "scene_descriptor_prompt": str(scene_descriptor_prompt or "").strip(),
    }

    existing = get_record(state, record_id) if record_id else None
    if existing is not None:
        if title:
            existing.title = title
        for field_name, value in values.items():
            setattr(existing, field_name, value)
        existing.updated_at = now_iso()
        state.selected_record_id = existing.id
        _persist(state)
        return state

    new_title = title or f"Agent记录{state.next_index}"
    state.next_index += 1
    record = AgentPromptRecord(
        title=new_title,
        **values,
    )
    state.records.append(record)
    state.selected_record_id = record.id
    _persist(state)
    return state


def delete_record(state: AgentPromptState, record_id: str) -> AgentPromptState:
    record_id = str(record_id or "").strip()
    if not record_id:
        return state

    state.records = [record for record in state.records if record.id != record_id]
    if state.selected_record_id == record_id:
        state.selected_record_id = state.records[0].id if state.records else ""

    _persist(state)
    return state
