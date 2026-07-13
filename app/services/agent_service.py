from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional

from app.api.chat_clients import DeepSeekAPIClient, GrokAPIClient
from app.config import AppStorageKeys, settings, user_facing_error_message
from app.models import AgentPromptRecord, now_iso
from app.services.agent_prompts import DEFAULT_STORY_BRAIN_GENERATOR_PROMPT


NPC_NAMES = ["NPC1", "NPC2", "NPC3"]
REQUIRED_OUTPUT_PREFIX = "好，我会按要求回复"
REQUIRED_OUTPUT_PREFIX_RETRIES = 4


@dataclass
class AgentContext:
    selected_chat_model: str
    temperature: float
    evolution_rounds: int
    player_route_history_turns: int = 3
    npc_history_turns: int = 5
    action_decision_history_turns: int = 3
    scene_history_turns: int = 3
    story_brain_turns: int = 6


@dataclass
class AgentRunResult:
    story_brain: str
    events: list
    completed_rounds: int
    stopped_early: bool
    error: str = ""
    debug_logs: list = None


@dataclass
class AgentRunProgress:
    phase: str
    message: str = ""
    event: Optional[dict] = None
    story_brain: str = ""
    events: list = None
    completed_rounds: int = 0
    stopped_early: bool = False
    error: str = ""
    debug_logs: list = None


def load_context_from_settings() -> AgentContext:
    model = str(settings.get(AppStorageKeys.AGENT_SELECTED_CHAT_MODEL, "grok1") or "grok1")
    if model not in ["grok1", "grok2", "deepseek"]:
        model = "grok1"

    rounds = settings.int(AppStorageKeys.AGENT_EVOLUTION_ROUNDS, 5)
    rounds = min(25, max(1, int(rounds)))

    return AgentContext(
        selected_chat_model=model,
        temperature=float(settings.float(AppStorageKeys.AGENT_TEMPERATURE, 0.8)),
        evolution_rounds=rounds,
        player_route_history_turns=max(0, settings.int(AppStorageKeys.AGENT_PLAYER_ROUTE_HISTORY_TURNS, 3)),
        npc_history_turns=max(0, settings.int(AppStorageKeys.AGENT_NPC_HISTORY_TURNS, 5)),
        action_decision_history_turns=max(0, settings.int(AppStorageKeys.AGENT_ACTION_DECISION_HISTORY_TURNS, 3)),
        scene_history_turns=max(0, settings.int(AppStorageKeys.AGENT_SCENE_HISTORY_TURNS, 3)),
        story_brain_turns=max(1, settings.int(AppStorageKeys.AGENT_STORY_BRAIN_TURNS, 6)),
    )


def default_context() -> AgentContext:
    return AgentContext(
        selected_chat_model="grok1",
        temperature=0.8,
        evolution_rounds=5,
        player_route_history_turns=3,
        npc_history_turns=5,
        action_decision_history_turns=3,
        scene_history_turns=3,
        story_brain_turns=6,
    )


def reset_context_settings():
    save_context_to_settings(default_context())


def save_context_to_settings(ctx: AgentContext):
    model = str(ctx.selected_chat_model or "grok1")
    if model not in ["grok1", "grok2", "deepseek"]:
        model = "grok1"
    settings.set(AppStorageKeys.AGENT_SELECTED_CHAT_MODEL, model)
    settings.set(AppStorageKeys.AGENT_TEMPERATURE, float(ctx.temperature))
    settings.set(AppStorageKeys.AGENT_EVOLUTION_ROUNDS, min(25, max(1, int(ctx.evolution_rounds))))
    settings.set(AppStorageKeys.AGENT_PLAYER_ROUTE_HISTORY_TURNS, max(0, int(ctx.player_route_history_turns)))
    settings.set(AppStorageKeys.AGENT_NPC_HISTORY_TURNS, max(0, int(ctx.npc_history_turns)))
    settings.set(AppStorageKeys.AGENT_ACTION_DECISION_HISTORY_TURNS, max(0, int(ctx.action_decision_history_turns)))
    settings.set(AppStorageKeys.AGENT_SCENE_HISTORY_TURNS, max(0, int(ctx.scene_history_turns)))
    settings.set(AppStorageKeys.AGENT_STORY_BRAIN_TURNS, max(1, int(ctx.story_brain_turns)))


def _send_model(
    *,
    ctx: AgentContext,
    system_prompt: str,
    user_message: str,
    context_messages: Optional[list] = None,
) -> str:
    system_prompt = str(system_prompt or "").strip()
    user_message = str(user_message or "").strip()
    context_messages = context_messages or []

    if not system_prompt:
        raise ValueError("Agent prompt 为空，请先到 Agent Prompt 页面填写并保存。")
    if not user_message:
        raise ValueError("Agent 本轮输入为空。")

    if ctx.selected_chat_model == "deepseek":
        return DeepSeekAPIClient.send_message(
            system_prompt=system_prompt,
            context_messages=context_messages,
            user_message=user_message,
            temperature=ctx.temperature,
        )

    return GrokAPIClient.send_message(
        system_prompt=system_prompt,
        context_messages=context_messages,
        user_message=user_message,
        model="grok-4.3",
        temperature=ctx.temperature,
    )


def _debug_model_name(ctx: AgentContext) -> str:
    return "deepseek-v4-pro" if ctx.selected_chat_model == "deepseek" else "grok-4.3"


def _with_required_output_prefix_instruction(user_message: str) -> str:
    message = str(user_message or "").strip()
    prefix_instruction = f"""
输出格式要求：
- 本次回复开头必须是 "{REQUIRED_OUTPUT_PREFIX}"，然后再回复剩下内容
""".strip()
    return f"{message}\n\n{prefix_instruction}".strip()


def _has_required_output_prefix(output: str) -> bool:
    return str(output or "").strip().startswith(REQUIRED_OUTPUT_PREFIX)


def _strip_required_output_prefix(output: str) -> str:
    text = str(output or "").strip()
    if text.startswith(REQUIRED_OUTPUT_PREFIX):
        return text[len(REQUIRED_OUTPUT_PREFIX) :].lstrip()
    return text


def _send_model_with_debug(
    *,
    ctx: AgentContext,
    debug_logs: list,
    label: str,
    system_prompt: str,
    user_message: str,
    context_messages: Optional[list] = None,
    round_number: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> str:
    context_messages = context_messages or []
    raw_user_message = str(user_message or "").strip()
    user_message_with_prefix_instruction = _with_required_output_prefix_instruction(raw_user_message)
    entry = {
        "at": now_iso(),
        "label": str(label or "").strip(),
        "round": round_number,
        "model": _debug_model_name(ctx),
        "selected_chat_model": ctx.selected_chat_model,
        "temperature": ctx.temperature,
        "system_prompt": str(system_prompt or "").strip(),
        "context_messages": context_messages,
        "user_prompt": user_message_with_prefix_instruction,
        "output": "",
        "error": "",
        "metadata": {
            **(metadata or {}),
            "required_output_prefix": REQUIRED_OUTPUT_PREFIX,
            "required_output_prefix_retries": REQUIRED_OUTPUT_PREFIX_RETRIES,
        },
    }
    try:
        attempts = []
        output = ""
        for attempt_number in range(1, REQUIRED_OUTPUT_PREFIX_RETRIES + 2):
            output = _send_model(
                ctx=ctx,
                system_prompt=system_prompt,
                user_message=user_message_with_prefix_instruction,
                context_messages=context_messages,
            )
            raw_output = str(output or "")
            passed = _has_required_output_prefix(raw_output)
            attempts.append(
                {
                    "attempt": attempt_number,
                    "passed_prefix_check": passed,
                    "raw_output": raw_output,
                }
            )
            if passed:
                break

        entry["output"] = _strip_required_output_prefix(output)
        entry["raw_output"] = str(output or "")
        entry["prefix_check_passed"] = _has_required_output_prefix(output)
        entry["prefix_retry_count"] = max(0, len(attempts) - 1)
        entry["prefix_attempts"] = attempts
        debug_logs.append(entry)
        return entry["output"]
    except Exception as exc:
        entry["error"] = user_facing_error_message(exc)
        debug_logs.append(entry)
        raise


def _strip_json_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1].strip()
    return text


def _strip_plain_text_output(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_json_object(raw_text: str, *, label: str) -> dict:
    text = _strip_json_text(raw_text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 返回的内容不是合法 JSON：{exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{label} 返回 JSON 顶层必须是对象。")
    return data


def _story_brain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value or "").strip()


def _npc_name(value: Any) -> str:
    text = str(value or "").strip()
    aliases = {
        "1": "NPC1",
        "2": "NPC2",
        "3": "NPC3",
        "npc1": "NPC1",
        "npc2": "NPC2",
        "npc3": "NPC3",
        "NPC1": "NPC1",
        "NPC2": "NPC2",
        "NPC3": "NPC3",
    }
    return aliases.get(text, "")


def _history_text(events: list, limit: int = 16) -> str:
    limit = max(0, int(limit))
    if limit == 0:
        return ""

    visible_events = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        content = str(event.get("content", "") or "").strip()
        if content:
            visible_events.append(event)

    recent = visible_events[-limit:]
    lines = []
    for event in recent:
        kind = str(event.get("kind", "") or "")
        speaker = str(event.get("speaker", "") or "")
        content = str(event.get("content", "") or "").strip()
        prefix = speaker or kind or "event"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


def _prompt4_user_message(
    *,
    player_input: str,
    story_brain: str,
    events: list,
    history_turns: int,
    story_brain_enabled: bool = True,
) -> str:
    story_brain_section = ""
    if story_brain_enabled:
        story_brain_section = f"""
当前 Story Brain：
{_story_brain_text(story_brain) or "暂无"}
"""

    return f"""
你必须只输出严格合法 JSON，不要输出 Markdown、代码块或解释。first_npc输出NPC代号而不是NPC名字

返回JSON 格式示例：
{{
  "first_npc": "NPC1 / NPC2 / NPC3",
  "npc_instruction": ""
}}
{story_brain_section}

最近互动历史：
{_history_text(events, limit=history_turns) or "暂无"}

玩家输入：
{player_input}
""".strip()


def _prompt5_user_message(
    *,
    npc_name: str,
    npc_output: str,
    story_brain: str,
    events: list,
    acted_npcs: List[str],
    history_turns: int,
    story_brain_enabled: bool = True,
) -> str:
    story_brain_section = ""
    if story_brain_enabled:
        story_brain_section = f"""
当前 Story Brain：
{_story_brain_text(story_brain) or "暂无"}
"""

    return f"""
你必须只输出严格合法 JSON，不要输出 Markdown、代码块或解释。next_npc输出NPC代号而不是NPC名字


JSON 格式：
{{
  "next_npc": "NPC1 | NPC2 | NPC3",
  "what_just_happened": "",
}}

刚刚行动的 NPC：
{npc_name or "玩家"}

what_just_happened:
{npc_output}

{story_brain_section}

最近互动历史：
{_history_text(events, limit=history_turns) or "暂无"}
""".strip()


def _npc_user_message(
    *,
    npc_name: str,
    what_just_happened: str,
    story_brain: str,
    events: list,
    history_turns: int,
    story_brain_enabled: bool = True,
) -> str:
    story_brain_section = ""
    if story_brain_enabled:
        story_brain_section = f"""
当前 Story Brain：
{_story_brain_text(story_brain) or "暂无"}
"""

    return f"""

要求：
- 输出应用自然语言自然格式输出，包含角色说的话和行为
{story_brain_section}

最近互动历史：
{_history_text(events, limit=history_turns) or "暂无"}

what_just_happened:
{what_just_happened}
""".strip()


def _scene_user_message(
    *,
    story_brain: str,
    events: list,
    history_turns: int,
    player_input: str = "",
    story_brain_enabled: bool = True,
) -> str:
    story_brain_section = ""
    player_input_section = ""
    if str(player_input or "").strip():
        player_input_section = f"""
玩家输入：
{str(player_input or "").strip()}
"""

    story_brain_rule = "不要决定角色行为，不要输出 JSON。"
    if story_brain_enabled:
        story_brain_rule = "不要决定角色行为，不要修改 Story Brain，不要输出 JSON。"
        story_brain_section = f"""
当前 Story Brain：
{_story_brain_text(story_brain) or "暂无"}
"""

    return f"""
请基于最近互动历史生成一段面向玩家的场景描述。
{story_brain_rule}
{story_brain_section}
{player_input_section}

最近互动历史：
{_history_text(events, limit=history_turns) or "暂无"}
""".strip()


def _story_brain_generator_user_message(*, story_brain: str, events: list, history_turns: int) -> str:
    return f"""
过去的记录：
{_history_text(events, limit=history_turns) or "暂无"}

现有 Story Brain：
{_story_brain_text(story_brain) or "暂无"}
""".strip()


def _npc_prompt_for(record: AgentPromptRecord, npc_name: str) -> str:
    if npc_name == "NPC1":
        return record.npc1_prompt
    if npc_name == "NPC2":
        return record.npc2_prompt
    if npc_name == "NPC3":
        return record.npc3_prompt
    return ""


def _event(kind: str, content: str, *, speaker: str = "", meta: Optional[dict] = None) -> dict:
    return {
        "kind": kind,
        "speaker": speaker,
        "content": str(content or "").strip(),
        "meta": meta or {},
    }


def _absolute_debug_log_index(start_index: int, debug_logs: list) -> int:
    return int(start_index) + len(debug_logs or [])


def _generate_story_brain(
    *,
    ctx: AgentContext,
    prompt_record: AgentPromptRecord,
    story_brain: str,
    events: list,
    debug_logs: list,
    completed_rounds: int,
    metadata: Optional[dict] = None,
) -> str:
    history_turns = max(1, int(ctx.story_brain_turns))
    generator_user_message = _story_brain_generator_user_message(
        story_brain=story_brain,
        events=events,
        history_turns=history_turns,
    )
    generator_raw = _send_model_with_debug(
        ctx=ctx,
        debug_logs=debug_logs,
        label="story brain生成器",
        system_prompt=str(getattr(prompt_record, "story_brain_generator_prompt", "") or DEFAULT_STORY_BRAIN_GENERATOR_PROMPT),
        user_message=generator_user_message,
        round_number=completed_rounds,
        metadata={
            "history_turns": history_turns,
            **(metadata or {}),
        },
    )
    updated_story_brain = _strip_plain_text_output(generator_raw)
    return updated_story_brain or story_brain


def iter_agent_evolution(
    *,
    ctx: AgentContext,
    prompt_record: AgentPromptRecord,
    player_input: str,
    story_brain: str,
    events: list,
    debug_log_start_index: int = 0,
    story_brain_enabled: bool = True,
) -> Iterator[AgentRunProgress]:
    original_story_brain = _story_brain_text(story_brain)
    story_brain = original_story_brain if story_brain_enabled else ""
    story_brain_turns = max(1, int(ctx.story_brain_turns))
    previous_events = list(events or [])
    new_events = list(previous_events)
    debug_logs: list = []
    player_input = str(player_input or "").strip()
    completed_rounds = 0
    stopped_early = False
    if not player_input:
        yield AgentRunProgress(
            phase="complete",
            story_brain=story_brain if story_brain_enabled else original_story_brain,
            events=new_events,
            completed_rounds=0,
            stopped_early=False,
            debug_logs=debug_logs,
        )
        return

    try:
        player_meta = {"debug_log_start_index": int(debug_log_start_index)}
        if story_brain_enabled:
            player_meta["story_brain_before"] = story_brain
        player_event = _event(
            "player",
            player_input,
            speaker="玩家",
            meta=player_meta,
        )
        new_events.append(player_event)
        yield AgentRunProgress(
            phase="event",
            message="玩家输入已加入。",
            event=player_event,
            story_brain=story_brain,
            events=list(new_events),
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            debug_logs=list(debug_logs),
        )

        yield AgentRunProgress(
            phase="status",
            message="正在生成场景描述...",
            story_brain=story_brain,
            events=list(new_events),
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            debug_logs=list(debug_logs),
        )
        initial_scene_user_message = _scene_user_message(
            story_brain=story_brain,
            events=previous_events,
            history_turns=ctx.scene_history_turns,
            player_input=player_input,
            story_brain_enabled=story_brain_enabled,
        )
        initial_scene_debug_log_start_index = _absolute_debug_log_index(debug_log_start_index, debug_logs)
        initial_scene_story_brain_before = story_brain
        initial_scene_text = _send_model_with_debug(
            ctx=ctx,
            debug_logs=debug_logs,
            label="场景描述器",
            system_prompt=prompt_record.scene_descriptor_prompt,
            user_message=initial_scene_user_message,
            round_number=0,
            metadata={
                "player_input": player_input,
                "story_brain_enabled": story_brain_enabled,
                "trigger": "player_input",
            },
        ).strip()
        if not initial_scene_text:
            raise ValueError("场景描述器没有产生有效输出。")

        initial_scene_meta = {
            "round": 0,
            "debug_log_start_index": initial_scene_debug_log_start_index,
        }
        if story_brain_enabled:
            initial_scene_meta["story_brain_before"] = initial_scene_story_brain_before
        initial_scene_event = _event("scene", initial_scene_text, speaker="场景", meta=initial_scene_meta)
        new_events.append(initial_scene_event)
        yield AgentRunProgress(
            phase="event",
            message="场景描述完成。",
            event=initial_scene_event,
            story_brain=story_brain,
            events=list(new_events),
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            debug_logs=list(debug_logs),
        )

        if story_brain_enabled and not previous_events:
            yield AgentRunProgress(
                phase="status",
                message="正在初始化 Story Brain...",
                story_brain=story_brain,
                events=list(new_events),
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=list(debug_logs),
            )
            story_brain = _generate_story_brain(
                ctx=ctx,
                prompt_record=prompt_record,
                story_brain=story_brain,
                events=new_events,
                debug_logs=debug_logs,
                completed_rounds=0,
                metadata={"trigger": "first_player_input"},
            )

        yield AgentRunProgress(
            phase="status",
            message="正在裁决并选择首位角色...",
            story_brain=story_brain,
            events=list(new_events),
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            debug_logs=list(debug_logs),
        )
        initial_scheduler_user_message = _prompt5_user_message(
            npc_name="玩家",
            npc_output=initial_scene_text,
            story_brain=story_brain,
            events=previous_events,
            acted_npcs=[],
            history_turns=ctx.action_decision_history_turns,
            story_brain_enabled=story_brain_enabled,
        )
        initial_scheduler_debug_log_start_index = _absolute_debug_log_index(debug_log_start_index, debug_logs)
        initial_scheduler_story_brain_before = story_brain
        initial_scheduler_raw = _send_model_with_debug(
            ctx=ctx,
            debug_logs=debug_logs,
            label="行动裁决",
            system_prompt=prompt_record.action_scheduler_prompt,
            user_message=initial_scheduler_user_message,
            round_number=0,
            metadata={
                "player_input": player_input,
                "npc": "玩家",
                "acted_npcs": [],
                "trigger": "initial_scene",
                "story_brain_enabled": story_brain_enabled,
            },
        )
        initial_scheduler_data = _parse_json_object(initial_scheduler_raw, label="行动裁决")

        if bool(initial_scheduler_data.get("stop_evolution")):
            stopped_early = True
            reason = str(initial_scheduler_data.get("stop_reason") or "NPC 已不在同一场景，自动演化提前停止。").strip()
            stop_meta = {
                "round": 0,
                "debug_log_start_index": initial_scheduler_debug_log_start_index,
            }
            if story_brain_enabled:
                stop_meta["story_brain_before"] = initial_scheduler_story_brain_before
            stop_event = _event("system", reason, speaker="系统", meta=stop_meta)
            new_events.append(stop_event)
            yield AgentRunProgress(
                phase="event",
                message="自动演化提前停止。",
                event=stop_event,
                story_brain=story_brain,
                events=list(new_events),
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=list(debug_logs),
            )
            yield AgentRunProgress(
                phase="complete",
                message="Agent 自动演化完成。",
                story_brain=story_brain if story_brain_enabled else original_story_brain,
                events=new_events,
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=debug_logs,
            )
            return

        current_npc = _npc_name(initial_scheduler_data.get("next_npc"))
        if not current_npc:
            raise ValueError("行动裁决必须返回 next_npc，且值必须是 NPC1、NPC2 或 NPC3。")
        what_just_happened = (
            str(initial_scheduler_data.get("what_just_happened") or "").strip()
            or str(initial_scheduler_data.get("next_instruction") or "").strip()
            or initial_scene_text
        )

        acted_npcs: List[str] = []

        while completed_rounds < ctx.evolution_rounds:
            npc_prompt = _npc_prompt_for(prompt_record, current_npc)
            yield AgentRunProgress(
                phase="status",
                message=f"第 {completed_rounds + 1} 轮：{current_npc} 正在行动...",
                story_brain=story_brain,
                events=list(new_events),
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=list(debug_logs),
            )
            npc_user_message = _npc_user_message(
                npc_name=current_npc,
                what_just_happened=what_just_happened,
                story_brain=story_brain,
                events=new_events,
                history_turns=ctx.npc_history_turns,
                story_brain_enabled=story_brain_enabled,
            )
            npc_debug_log_start_index = _absolute_debug_log_index(debug_log_start_index, debug_logs)
            npc_story_brain_before = story_brain
            npc_output = _send_model_with_debug(
                ctx=ctx,
                debug_logs=debug_logs,
                label=f"{current_npc} 行动",
                system_prompt=npc_prompt,
                user_message=npc_user_message,
                round_number=completed_rounds + 1,
                metadata={
                    "npc": current_npc,
                    "what_just_happened": what_just_happened,
                    "story_brain_enabled": story_brain_enabled,
                },
            ).strip()
            if not npc_output:
                raise ValueError(f"{current_npc} 没有产生有效输出。")

            completed_rounds += 1
            acted_npcs.append(current_npc)
            npc_meta = {
                "round": completed_rounds,
                "debug_log_start_index": npc_debug_log_start_index,
            }
            if story_brain_enabled:
                npc_meta["story_brain_before"] = npc_story_brain_before
            npc_event = _event("npc", npc_output, speaker=current_npc, meta=npc_meta)
            new_events.append(npc_event)
            yield AgentRunProgress(
                phase="event",
                message=f"第 {completed_rounds} 轮：{current_npc} 已输出。",
                event=npc_event,
                story_brain=story_brain,
                events=list(new_events),
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=list(debug_logs),
            )

            if story_brain_enabled and completed_rounds % story_brain_turns == 0:
                yield AgentRunProgress(
                    phase="status",
                    message=f"第 {completed_rounds} 轮：正在更新 Story Brain...",
                    story_brain=story_brain,
                    events=list(new_events),
                    completed_rounds=completed_rounds,
                    stopped_early=stopped_early,
                    debug_logs=list(debug_logs),
                )
                story_brain = _generate_story_brain(
                    ctx=ctx,
                    prompt_record=prompt_record,
                    story_brain=story_brain,
                    events=new_events,
                    debug_logs=debug_logs,
                    completed_rounds=completed_rounds,
                    metadata={"trigger": "npc_round_interval"},
                )

            yield AgentRunProgress(
                phase="status",
                message=f"第 {completed_rounds} 轮：正在裁决并选择下一位角色...",
                story_brain=story_brain,
                events=list(new_events),
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=list(debug_logs),
            )
            scheduler_user_message = _prompt5_user_message(
                npc_name=current_npc,
                npc_output=npc_output,
                story_brain=story_brain,
                events=new_events[:-1],
                acted_npcs=acted_npcs,
                history_turns=ctx.action_decision_history_turns,
                story_brain_enabled=story_brain_enabled,
            )
            scheduler_debug_log_start_index = _absolute_debug_log_index(debug_log_start_index, debug_logs)
            scheduler_story_brain_before = story_brain
            scheduler_raw = _send_model_with_debug(
                ctx=ctx,
                debug_logs=debug_logs,
                label="行动裁决",
                system_prompt=prompt_record.action_scheduler_prompt,
                user_message=scheduler_user_message,
                round_number=completed_rounds,
                metadata={
                    "npc": current_npc,
                    "acted_npcs": list(acted_npcs),
                    "story_brain_enabled": story_brain_enabled,
                },
            )
            scheduler_data = _parse_json_object(scheduler_raw, label="行动裁决")

            if completed_rounds % 3 == 0:
                yield AgentRunProgress(
                    phase="status",
                    message=f"第 {completed_rounds} 轮：正在生成场景描述...",
                    story_brain=story_brain,
                    events=list(new_events),
                    completed_rounds=completed_rounds,
                    stopped_early=stopped_early,
                    debug_logs=list(debug_logs),
                )
                scene_user_message = _scene_user_message(
                    story_brain=story_brain,
                    events=new_events,
                    history_turns=ctx.scene_history_turns,
                    story_brain_enabled=story_brain_enabled,
                )
                scene_debug_log_start_index = _absolute_debug_log_index(debug_log_start_index, debug_logs)
                scene_story_brain_before = story_brain
                scene_text = _send_model_with_debug(
                    ctx=ctx,
                    debug_logs=debug_logs,
                    label="场景描述器",
                    system_prompt=prompt_record.scene_descriptor_prompt,
                    user_message=scene_user_message,
                    round_number=completed_rounds,
                    metadata={"story_brain_enabled": story_brain_enabled},
                ).strip()
                if scene_text:
                    scene_meta = {
                        "round": completed_rounds,
                        "debug_log_start_index": scene_debug_log_start_index,
                    }
                    if story_brain_enabled:
                        scene_meta["story_brain_before"] = scene_story_brain_before
                    scene_event = _event("scene", scene_text, speaker="场景", meta=scene_meta)
                    new_events.append(scene_event)
                    yield AgentRunProgress(
                        phase="event",
                        message=f"第 {completed_rounds} 轮：场景描述完成。",
                        event=scene_event,
                        story_brain=story_brain,
                        events=list(new_events),
                        completed_rounds=completed_rounds,
                        stopped_early=stopped_early,
                        debug_logs=list(debug_logs),
                    )

            if bool(scheduler_data.get("stop_evolution")):
                stopped_early = True
                reason = str(scheduler_data.get("stop_reason") or "NPC 已不在同一场景，自动演化提前停止。").strip()
                stop_meta = {
                    "round": completed_rounds,
                    "debug_log_start_index": scheduler_debug_log_start_index,
                }
                if story_brain_enabled:
                    stop_meta["story_brain_before"] = scheduler_story_brain_before
                stop_event = _event("system", reason, speaker="系统", meta=stop_meta)
                new_events.append(stop_event)
                yield AgentRunProgress(
                    phase="event",
                    message="自动演化提前停止。",
                    event=stop_event,
                    story_brain=story_brain,
                    events=list(new_events),
                    completed_rounds=completed_rounds,
                    stopped_early=stopped_early,
                    debug_logs=list(debug_logs),
                )
                break

            if completed_rounds >= ctx.evolution_rounds:
                break

            next_npc = _npc_name(scheduler_data.get("next_npc"))
            if not next_npc:
                raise ValueError("行动裁决必须返回 next_npc，且值必须是 NPC1、NPC2 或 NPC3。")
            current_npc = next_npc
            what_just_happened = (
                str(scheduler_data.get("what_just_happened") or "").strip()
                or str(scheduler_data.get("next_instruction") or "").strip()
                or "根据当前局势作出一次有效行为。"
            )

        yield AgentRunProgress(
            phase="complete",
            message="Agent 自动演化完成。",
            story_brain=story_brain if story_brain_enabled else original_story_brain,
            events=new_events,
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            debug_logs=debug_logs,
        )
    except Exception as exc:
        message = user_facing_error_message(exc)
        error_event = _event("error", message, speaker="错误")
        new_events.append(error_event)
        yield AgentRunProgress(
            phase="event",
            message=message,
            event=error_event,
            story_brain=story_brain if story_brain_enabled else original_story_brain,
            events=list(new_events),
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            error=message,
            debug_logs=list(debug_logs),
        )
        yield AgentRunProgress(
            phase="complete",
            message=message,
            story_brain=story_brain if story_brain_enabled else original_story_brain,
            events=new_events,
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            error=message,
            debug_logs=debug_logs,
        )


def run_agent_evolution(
    *,
    ctx: AgentContext,
    prompt_record: AgentPromptRecord,
    player_input: str,
    story_brain: str,
    events: list,
    debug_log_start_index: int = 0,
    story_brain_enabled: bool = True,
) -> AgentRunResult:
    final_progress: Optional[AgentRunProgress] = None
    for progress in iter_agent_evolution(
        ctx=ctx,
        prompt_record=prompt_record,
        player_input=player_input,
        story_brain=story_brain,
        events=events,
        debug_log_start_index=debug_log_start_index,
        story_brain_enabled=story_brain_enabled,
    ):
        if progress.phase == "complete":
            final_progress = progress

    if final_progress is None:
        return AgentRunResult(
            story_brain=_story_brain_text(story_brain),
            events=list(events or []),
            completed_rounds=0,
            stopped_early=False,
            debug_logs=[],
        )

    return AgentRunResult(
        story_brain=final_progress.story_brain,
        events=final_progress.events,
        completed_rounds=final_progress.completed_rounds,
        stopped_early=final_progress.stopped_early,
        error=final_progress.error,
        debug_logs=final_progress.debug_logs,
    )
