from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from agent_story_brain import empty_agent_story_brain, normalize_agent_story_brain
from app.config import AGENT_CHAT_RECORDS_DIR, AppStorageKeys, debug_log, settings
from app.models import GeneratedImageRecord, new_id, now_iso


@dataclass
class AgentChatRecord:
    title: str
    events: list
    story_brain: dict
    generated_media: list = field(default_factory=list)
    debug_logs: list = field(default_factory=list)
    prompt_record_id: str = ""
    selected_chat_model: str = "grok1"
    temperature: float = 0.8
    evolution_rounds: int = 5
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @staticmethod
    def from_dict(data):
        if not isinstance(data, dict):
            data = {}
        return AgentChatRecord(
            id=data.get("id") or new_id(),
            title=data.get("title", "Agent 聊天记录"),
            events=data.get("events") if isinstance(data.get("events"), list) else [],
            story_brain=normalize_agent_story_brain(data.get("story_brain") or data.get("storyBrain")),
            generated_media=[
                GeneratedImageRecord.from_dict(item)
                for item in (
                    data.get("generated_media")
                    or data.get("generatedMedia")
                    or data.get("generated_images")
                    or data.get("generatedImages")
                    or []
                )
                if isinstance(item, dict)
            ],
            debug_logs=data.get("debug_logs") if isinstance(data.get("debug_logs"), list) else data.get("debugLogs") if isinstance(data.get("debugLogs"), list) else [],
            prompt_record_id=data.get("prompt_record_id") or data.get("promptRecordID") or "",
            selected_chat_model=data.get("selected_chat_model") or data.get("selectedChatModel") or "grok1",
            temperature=float(data.get("temperature", 0.8) or 0.8),
            evolution_rounds=int(data.get("evolution_rounds", 5) or 5),
            created_at=data.get("created_at") or data.get("createdAt") or now_iso(),
            updated_at=data.get("updated_at") or data.get("updatedAt") or now_iso(),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "events": self.events,
            "story_brain": normalize_agent_story_brain(self.story_brain),
            "generated_media": [
                item.to_dict() if hasattr(item, "to_dict") else item
                for item in self.generated_media
            ],
            "debug_logs": self.debug_logs,
            "prompt_record_id": self.prompt_record_id,
            "selected_chat_model": self.selected_chat_model,
            "temperature": self.temperature,
            "evolution_rounds": self.evolution_rounds,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AgentChatRecordIndexItem:
    id: str
    title: str
    created_at: str
    updated_at: str
    file_name: str

    @staticmethod
    def from_dict(data):
        if not isinstance(data, dict):
            data = {}
        return AgentChatRecordIndexItem(
            id=data.get("id", ""),
            title=data.get("title", "Agent 聊天记录"),
            created_at=data.get("created_at") or data.get("createdAt") or now_iso(),
            updated_at=data.get("updated_at") or data.get("updatedAt") or now_iso(),
            file_name=data.get("file_name") or data.get("fileName") or "",
        )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "file_name": self.file_name,
        }


def _scope_index_key(scope: Optional[str]) -> str:
    if str(scope or "").strip() == "guest":
        return AppStorageKeys.GUEST_AGENT_CHAT_RECORD_INDEX
    return AppStorageKeys.AGENT_CHAT_RECORD_INDEX


def _scope_dir(scope: Optional[str]):
    if str(scope or "").strip() == "guest":
        return AGENT_CHAT_RECORDS_DIR / "guest"
    return AGENT_CHAT_RECORDS_DIR


def _record_file_name(record_id: str) -> str:
    return "agent-record-" + str(record_id) + ".json"


def _record_file_path(file_name: str, scope: Optional[str] = None):
    base_dir = _scope_dir(scope)
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / file_name


def load_index(scope: Optional[str] = None) -> list:
    raw = settings.get(_scope_index_key(scope), "")
    if not raw:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(raw)
        except Exception:
            return []

    result = []
    for item in items:
        try:
            result.append(AgentChatRecordIndexItem.from_dict(item))
        except Exception as exc:
            debug_log("[AgentChatRecordStore] Bad index item:", exc)
    return result


def load_index_sorted(scope: Optional[str] = None) -> list:
    return sorted(
        load_index(scope=scope),
        key=lambda item: (item.updated_at, item.created_at),
        reverse=True,
    )


def _persist_index(items: list, scope: Optional[str] = None):
    settings.set(
        _scope_index_key(scope),
        json.dumps([item.to_dict() for item in items], ensure_ascii=False),
    )


def _upsert_index_item(item: AgentChatRecordIndexItem, scope: Optional[str] = None):
    index = load_index(scope=scope)
    for idx, existing in enumerate(index):
        if existing.id == item.id:
            index[idx] = item
            _persist_index(index, scope=scope)
            return
    index.append(item)
    _persist_index(index, scope=scope)


def load_record_by_id(record_id: str, scope: Optional[str] = None) -> Optional[AgentChatRecord]:
    record_id = str(record_id or "").strip()
    if not record_id:
        return None

    for item in load_index(scope=scope):
        if item.id != record_id:
            continue
        try:
            data = json.loads(_record_file_path(item.file_name, scope=scope).read_text(encoding="utf-8"))
            return AgentChatRecord.from_dict(data)
        except Exception as exc:
            debug_log("[AgentChatRecordStore] Load failed:", exc)
            return None
    return None


def save_or_update_record(record: AgentChatRecord, scope: Optional[str] = None):
    record.updated_at = now_iso()
    if not record.created_at:
        record.created_at = record.updated_at
    file_name = _record_file_name(record.id)
    _record_file_path(file_name, scope=scope).write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _upsert_index_item(
        AgentChatRecordIndexItem(
            id=record.id,
            title=record.title,
            created_at=record.created_at,
            updated_at=record.updated_at,
            file_name=file_name,
        ),
        scope=scope,
    )


def rename_record(record_id: str, new_title: str, scope: Optional[str] = None):
    record = load_record_by_id(record_id, scope=scope)
    if record is None:
        return
    record.title = str(new_title or "").strip() or "Agent 聊天记录"
    save_or_update_record(record, scope=scope)


def delete_record(record_id: str, scope: Optional[str] = None):
    record_id = str(record_id or "").strip()
    kept = []
    for item in load_index(scope=scope):
        if item.id == record_id:
            try:
                path = _record_file_path(item.file_name, scope=scope)
                if path.exists():
                    path.unlink()
            except Exception as exc:
                debug_log("[AgentChatRecordStore] Delete failed:", exc)
        else:
            kept.append(item)
    _persist_index(kept, scope=scope)


def build_record_title(events: list) -> str:
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("kind", "") or "") != "player":
            continue
        content = str(event.get("content", "") or "").strip()
        if content:
            return content[:24]
    return "Agent 聊天记录"


def empty_record() -> AgentChatRecord:
    return AgentChatRecord(
        title="Agent 聊天记录",
        events=[],
        story_brain=empty_agent_story_brain(),
        generated_media=[],
        debug_logs=[],
    )
