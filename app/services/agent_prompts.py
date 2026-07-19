from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.api.chat_clients import DeepSeekAPIClient, GrokAPIClient
from app.config import AppStorageKeys, settings
from app.models import AgentPromptRecord, now_iso
from app.services import hidden_space


DEFAULT_AGENT_PROMPT_FILE = Path(__file__).resolve().parents[1] / "default_prompts" / "agent_prompt.json"


PROMPT_FIELDS = [
    ("npc1_prompt", "NPC1 Prompt"),
    ("npc2_prompt", "NPC2 Prompt"),
    ("npc3_prompt", "NPC3 Prompt"),
    ("player_parser_prompt", "玩家路由"),
    ("action_scheduler_prompt", "行动裁决"),
    ("scene_descriptor_prompt", "场景描述"),
    ("story_brain_generator_prompt", "story brain生成器"),
]


GENERATED_NPC_PROMPT_PREFIX = "你的任务是扮演以下角色，以第三人称视角输出你对what_just_happened的反应"
GENERATED_NPC_PROMPT_SUFFIX = "额外要求：根据最近的互动历史中你说话和行为的历史，让你的说话风格和行为多样化一点，不要重复说出与之前类似的话和重复做同样的行为。中文回复"


def _wrap_generated_npc_prompt(prompt: str) -> str:
    body = str(prompt or "").strip()
    prefix_variants = [
        GENERATED_NPC_PROMPT_PREFIX,
        f"“{GENERATED_NPC_PROMPT_PREFIX}”",
        f"{GENERATED_NPC_PROMPT_PREFIX}。",
        f"{GENERATED_NPC_PROMPT_PREFIX}。 ",
    ]
    suffix_variants = [
        GENERATED_NPC_PROMPT_SUFFIX,
        f"“{GENERATED_NPC_PROMPT_SUFFIX}”",
        f"{GENERATED_NPC_PROMPT_SUFFIX}。",
        f"{GENERATED_NPC_PROMPT_SUFFIX}。 ",
    ]

    changed = True
    while changed:
        changed = False
        for prefix in prefix_variants:
            if body.startswith(prefix):
                body = body[len(prefix) :].strip()
                changed = True
        for suffix in suffix_variants:
            if body.endswith(suffix):
                body = body[: -len(suffix)].strip()
                changed = True

    return "\n\n".join(part for part in [GENERATED_NPC_PROMPT_PREFIX, body, GENERATED_NPC_PROMPT_SUFFIX] if part)


DEFAULT_PLAYER_ROUTE_PROMPT = """结合story brain和最近互动历史，根据对剧情的理解决定下一轮应该哪个npc回复输出在"first_npc"中
理解用户的输入并且给你决定应该会出的NPC行动指导，输出在next_instruction部分"""


DEFAULT_ACTION_DECISION_PROMPT = """what_just_happened的部分原样输出 what_just_happened

结合story brain和最近互动历史，根据对剧情的理解决定下一轮应该哪个npc对what_just_happened进行反应，或者谁应该作出下一个行为（说话或不说话都可以）的npc在"next_npc"中。"""


DEFAULT_SCENE_DESCRIPTOR_PROMPT = """你是场景描述器。
你只负责描述，不决定角色行为，不修改 Story Brain，不输出 JSON。

你需要做的内容包括，根据输入，从第三人称描述场景，其中要包含上一轮角色的语言和行为（也就是输出要包含最近互动历史最后一个npc+玩家输入的语言和行为），还要输出包括场景中除主要角色以外其他人的行为和反应（如果场景中有其他角色存在并且你认为应该有反应时。若无反应则在输出中提到其他人没注意到或者没反应）。
规则：
- 不要揭露玩家或 NPC 不该知道的秘密。
- 不要让角色做新动作。
- 不要推进剧情，只描述当前画面。
- 输出一小段即可，保持清楚、具体。
"""


DEFAULT_STORY_BRAIN_GENERATOR_PROMPT = """我将输入过去最多x轮的记录和我现成的storybrain，我需要你根据我输入的记录，在现有的storybrain上做微调。最终只输出更新后的story brain正文，不要输出解释、标题、Markdown代码块或JSON。“未来剧情发展“部分下的情节完成一个删除一个，当全部完成时 未来剧情发展显示为“空”（例：未来剧情发展：空）"""


@dataclass
class AgentPromptState:
    hidden_space: bool
    records: List[AgentPromptRecord]
    hidden_records: List[AgentPromptRecord]
    next_index: int
    hidden_next_index: int
    selected_record_id: str


@dataclass
class GeneratedAgentPrompt:
    npc1_name: str
    npc1_prompt: str
    npc2_name: str
    npc2_prompt: str
    npc3_name: str
    npc3_prompt: str
    relationship_rules: str
    default_story_brain: str
    raw_text: str

    def to_form_values(self) -> dict:
        npc3_prompt = str(self.npc3_prompt or "").strip()
        relationship_rules = str(self.relationship_rules or "").strip()
        return {
            "npc1_name": str(self.npc1_name or "").strip(),
            "npc1_prompt": _wrap_generated_npc_prompt(self.npc1_prompt),
            "npc2_name": str(self.npc2_name or "").strip(),
            "npc2_prompt": _wrap_generated_npc_prompt(self.npc2_prompt),
            "npc3_name": str(self.npc3_name or "").strip(),
            "npc3_prompt": _wrap_generated_npc_prompt(npc3_prompt),
            "relationship_rules": relationship_rules,
            "default_story_brain": str(self.default_story_brain or "").strip(),
        }


class GeneratedPromptParseError(ValueError):
    def __init__(self, message: str, raw_text: str):
        super().__init__(message)
        self.raw_text = raw_text


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


def _extract_json_object(raw_text: str) -> dict:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("模型没有返回内容。")

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型返回内容里没有找到 JSON 对象。")
        data = json.loads(text[start : end + 1])

    if not isinstance(data, dict):
        raise ValueError("模型返回的 JSON 顶层必须是对象。")
    return data


def _require_generated_text(data: dict, key: str) -> str:
    value = data.get(key)
    text = str(value or "").strip()
    if not text:
        raise ValueError("模型返回 JSON 缺少字段：" + key)
    return text


def generate_prompt_from_story(story_description: str, model: str) -> GeneratedAgentPrompt:
    story_description = str(story_description or "").strip()
    if not story_description:
        raise ValueError("请先描述你想生成的大致故事。")

    model = str(model or "").strip().lower()
    if model not in ["grok2", "deepseek"]:
        raise ValueError("未知模型：" + str(model or ""))

    system_prompt = """
你是 Agent 模式角色 prompt 设计器。根据用户给出的故事设想，生成 3 个 NPC 的名字和角色 prompt。

要求：
1. 只输出一个合法 JSON 对象，不要输出 Markdown、解释或代码块。
2. JSON 必须包含以下 8 个字符串字段：
   npc1_name, npc1_prompt, npc2_name, npc2_prompt, npc3_name, npc3_prompt, relationship_rules, default_story_brain
3. 每个 NPC prompt 要包含：身份、性格、外形、其他 NPC 的关系(每个分类后面换个行)。每个npc的prompt需要至少超过400字，可以在包含用户输入信息的基础上再在“身份、性格、外形、其他 NPC 的关系”几个类别中自行拓展人设。禁止在prompt中使用“npc”而是以对应的姓名指代。
4. prompt 要适合放进系统提示词，让该 NPC 在故事中稳定扮演角色。
5. relationship_rules 必须严格使用下面模板（将npc1/2/3换成相应的名字），并根据故事填写每一项：
当npc们的关系为：
除正常情况外npc1会有额外反应的时机为：
除正常情况外npc2会有额外反应的时机为：
除正常情况外npc3会有额外反应的时机：
6. 生成 story brain 的背景故事，填写到 default_story_brain 字段，也就是界面里的“默认story brain”。default_story_brain 必须基于用户故事设想整理出 400 字以上的中文背景故事，包含世界观、主要角色关系、当前剧情状态、已知事实；不要把这段内容写进 NPC prompt 或 relationship_rules。default_story_brain 的结尾必须另起一行，只写“故事中所有角色超过22岁（永久保持此条字段）未来剧情发展：”。
""".strip()

    user_message = "故事设想：\n" + story_description
    if model == "deepseek":
        raw_text = DeepSeekAPIClient.send_message(
            system_prompt=system_prompt,
            context_messages=[],
            user_message=user_message,
            temperature=0.8,
        )
    else:
        raw_text = GrokAPIClient.send_message(
            system_prompt=system_prompt,
            context_messages=[],
            user_message=user_message,
            model="grok-4.3",
            temperature=0.8,
        )

    try:
        data = _extract_json_object(raw_text)
        generated = GeneratedAgentPrompt(
            npc1_name=_require_generated_text(data, "npc1_name"),
            npc1_prompt=_require_generated_text(data, "npc1_prompt"),
            npc2_name=_require_generated_text(data, "npc2_name"),
            npc2_prompt=_require_generated_text(data, "npc2_prompt"),
            npc3_name=_require_generated_text(data, "npc3_name"),
            npc3_prompt=_require_generated_text(data, "npc3_prompt"),
            relationship_rules=_require_generated_text(data, "relationship_rules"),
            default_story_brain=_require_generated_text(data, "default_story_brain"),
            raw_text=str(raw_text or ""),
        )
    except ValueError as exc:
        raise GeneratedPromptParseError(str(exc), str(raw_text or "")) from exc

    return generated


def _encode_records(records: List[AgentPromptRecord]) -> str:
    return json.dumps([r.to_dict() for r in records], ensure_ascii=False)


def _persist(state: AgentPromptState):
    settings.set(AppStorageKeys.AGENT_PROMPT_RECORDS, _encode_records(state.records))
    settings.set(AppStorageKeys.AGENT_PROMPT_RECORD_NEXT_INDEX, int(state.next_index))
    settings.set(AppStorageKeys.HIDDEN_AGENT_PROMPT_RECORDS, _encode_records(state.hidden_records))
    settings.set(AppStorageKeys.HIDDEN_AGENT_PROMPT_RECORD_NEXT_INDEX, int(state.hidden_next_index))
    settings.set(AppStorageKeys.SELECTED_AGENT_PROMPT_RECORD_ID, str(state.selected_record_id or ""))


def _load_default_records() -> tuple[List[AgentPromptRecord], str]:
    try:
        data = json.loads(DEFAULT_AGENT_PROMPT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return [], ""

    if isinstance(data, list):
        items = data
        selected_title = ""
    elif isinstance(data, dict):
        items = data.get("records") or []
        selected_title = str(data.get("selected_title", "") or "").strip()
    else:
        return [], ""

    records = [
        AgentPromptRecord.from_dict(item)
        for item in items
        if isinstance(item, dict)
    ]
    return records, selected_title


def _seed_default_records(state: AgentPromptState) -> AgentPromptState:
    records, selected_title = _load_default_records()
    if not records:
        return state

    state.records = records
    state.next_index = max(state.next_index, len(records) + 1)

    selected_record = None
    if selected_title:
        selected_record = next((record for record in records if record.title == selected_title), None)
    selected_record = selected_record or records[0]

    state.selected_record_id = selected_record.id
    _persist(state)
    return state


def load_state(hidden_space: bool = False) -> AgentPromptState:
    records = _decode_records(settings.get(AppStorageKeys.AGENT_PROMPT_RECORDS, ""))
    hidden_records = _decode_records(settings.get(AppStorageKeys.HIDDEN_AGENT_PROMPT_RECORDS, ""))
    selected_record_id = str(settings.get(AppStorageKeys.SELECTED_AGENT_PROMPT_RECORD_ID, "") or "")
    next_index = max(1, int(settings.get(AppStorageKeys.AGENT_PROMPT_RECORD_NEXT_INDEX, 1) or 1))
    hidden_next_index = max(1, int(settings.get(AppStorageKeys.HIDDEN_AGENT_PROMPT_RECORD_NEXT_INDEX, 1) or 1))

    if selected_record_id and not any(record.id == selected_record_id for record in records + hidden_records):
        selected_record_id = ""
        settings.set(AppStorageKeys.SELECTED_AGENT_PROMPT_RECORD_ID, "")

    state = AgentPromptState(
        hidden_space=bool(hidden_space),
        records=records,
        hidden_records=hidden_records,
        next_index=next_index,
        hidden_next_index=hidden_next_index,
        selected_record_id=selected_record_id,
    )

    if not state.records:
        state = _seed_default_records(state)

    return state


def visible_records(state: AgentPromptState) -> List[AgentPromptRecord]:
    if state.hidden_space:
        return state.records + state.hidden_records
    return state.records


def record_space(state: AgentPromptState, record_id: str) -> Optional[str]:
    for record in state.hidden_records:
        if record.id == record_id:
            return "hidden"
    for record in state.records:
        if record.id == record_id:
            return "normal"
    return None


def unlock_hidden_space(state: AgentPromptState, passcode: str) -> AgentPromptState:
    if hidden_space.is_valid_passcode(passcode):
        state.hidden_space = True
    return state


def get_record(state: AgentPromptState, record_id: str) -> Optional[AgentPromptRecord]:
    record_id = str(record_id or "").strip()
    for record in state.records + state.hidden_records:
        if record.id == record_id:
            return record
    return None


def selected_record(state: AgentPromptState) -> Optional[AgentPromptRecord]:
    if state.selected_record_id:
        record = next((item for item in visible_records(state) if item.id == state.selected_record_id), None)
        if record is not None:
            return record
    records = visible_records(state)
    if records:
        return records[0]
    return None


def select_record(state: AgentPromptState, record_id: str) -> AgentPromptState:
    record = next((item for item in visible_records(state) if item.id == str(record_id or "").strip()), None)
    if record is None:
        return state

    state.selected_record_id = record.id
    _persist(state)
    return state


def reset_selected_record():
    settings.set(AppStorageKeys.SELECTED_AGENT_PROMPT_RECORD_ID, "")


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
    story_brain_generator_prompt: str = "",
    default_story_brain: str = "",
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
        "story_brain_generator_prompt": str(story_brain_generator_prompt or "").strip(),
        "default_story_brain": str(default_story_brain or "").strip(),
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

    if state.hidden_space:
        new_title = title or f"隐藏Agent记录{state.hidden_next_index}"
        state.hidden_next_index += 1
    else:
        new_title = title or f"Agent记录{state.next_index}"
        state.next_index += 1
    record = AgentPromptRecord(
        title=new_title,
        **values,
    )
    if state.hidden_space:
        state.hidden_records.append(record)
    else:
        state.records.append(record)
    state.selected_record_id = record.id
    _persist(state)
    return state


def delete_record(state: AgentPromptState, record_id: str) -> AgentPromptState:
    record_id = str(record_id or "").strip()
    if not record_id:
        return state

    state.records = [record for record in state.records if record.id != record_id]
    state.hidden_records = [record for record in state.hidden_records if record.id != record_id]
    if state.selected_record_id == record_id:
        records = visible_records(state)
        state.selected_record_id = records[0].id if records else ""

    _persist(state)
    return state
