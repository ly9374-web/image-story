from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional

from agent_story_brain import (
    agent_memory_pack_to_json,
    apply_agent_story_brain_updates,
    build_agent_memory_pack,
    normalize_agent_story_brain,
)
from app.api.chat_clients import DeepSeekAPIClient, GrokAPIClient
from app.config import AppStorageKeys, settings, user_facing_error_message
from app.models import AgentPromptRecord


NPC_NAMES = ["NPC1", "NPC2", "NPC3"]


@dataclass
class AgentContext:
    selected_chat_model: str
    temperature: float
    evolution_rounds: int


@dataclass
class AgentRunResult:
    story_brain: dict
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
    story_brain: dict = None
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
    )


def save_context_to_settings(ctx: AgentContext):
    model = str(ctx.selected_chat_model or "grok1")
    if model not in ["grok1", "grok2", "deepseek"]:
        model = "grok1"
    settings.set(AppStorageKeys.AGENT_SELECTED_CHAT_MODEL, model)
    settings.set(AppStorageKeys.AGENT_TEMPERATURE, float(ctx.temperature))
    settings.set(AppStorageKeys.AGENT_EVOLUTION_ROUNDS, min(25, max(1, int(ctx.evolution_rounds))))


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


def _parse_json_object(raw_text: str, *, label: str) -> dict:
    text = _strip_json_text(raw_text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 返回的内容不是合法 JSON：{exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{label} 返回 JSON 顶层必须是对象。")
    return data


def _updates_from(data: dict) -> dict:
    updates = data.get("story_brain_updates")
    if updates is None:
        updates = data.get("suggested_updates")
    if updates is None:
        updates = []
    if not isinstance(updates, list):
        raise ValueError("story_brain_updates 必须是数组。")
    return {"suggested_updates": updates}


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
    recent = events[-max(1, limit) :]
    lines = []
    for event in recent:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("kind", "") or "")
        speaker = str(event.get("speaker", "") or "")
        content = str(event.get("content", "") or "").strip()
        if not content:
            continue
        prefix = speaker or kind or "event"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


def _json_block(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _prompt4_user_message(*, player_input: str, story_brain: dict, events: list) -> str:
    return f"""
你必须只输出严格合法 JSON，不要输出 Markdown、代码块或解释。first_npc输出NPC代号而不是NPC名字

返回JSON 格式示例：
{{
  "story_brain_updates": [],
  "first_npc": "NPC1 / NPC2 / NPC3",
  "npc_instruction": "复制",
  "present_characters": ["NPC1", "NPC2", "NPC3"]
}}

当前 Agent Story Brain：
{_json_block(story_brain)}

最近互动历史：
{_history_text(events) or "暂无"}

玩家输入：
{player_input}
""".strip()


def _prompt5_user_message(
    *,
    npc_name: str,
    npc_output: str,
    story_brain: dict,
    events: list,
    acted_npcs: List[str],
) -> str:
    return f"""
你必须只输出严格合法 JSON，不要输出 Markdown、代码块或解释。

JSON 格式：
{{
  "story_brain_updates": [],
  "stop_evolution": false,
  "stop_reason": "",
  "next_npc": "NPC1 | NPC2 | NPC3",
  "next_instruction": "给下一位 NPC 的行为提示",
  "present_characters": ["NPC1", "NPC2", "NPC3"],
  "judgement_summary": "对刚才行动结果的简短裁决"
}}

规则：
- next_npc 必须从另外两个 NPC 中选择一个，不能选择刚刚行动的 NPC。
- 如果 3 个 NPC 已不在同一场景，stop_evolution 必须为 true，并说明 stop_reason。

刚刚行动的 NPC：
{npc_name}

刚刚的 NPC 输出：
{npc_output}

本次自动演化中已经行动过的角色：
{", ".join(acted_npcs) or "暂无"}

当前 Agent Story Brain：
{_json_block(story_brain)}

最近互动历史：
{_history_text(events) or "暂无"}
""".strip()


def _npc_user_message(
    *,
    npc_name: str,
    instruction: str,
    memory_pack_json: str,
    events: list,
) -> str:
    return f"""
你现在作为 {npc_name} 行动。

要求：
- 必须产生一次有效行为，不能输出“无需作出反应”。
- 输出应包含角色台词、角色动作、建议的角色状态变化、建议的持有物品变化。
- 不要输出分析过程。
- 如果你输出 JSON，也必须同时让玩家能读懂台词和动作。

该 NPC 可见的 Agent Story Brain Memory Pack：
{memory_pack_json}

最近互动历史：
{_history_text(events) or "暂无"}

本轮行为指令：
{instruction}
""".strip()


def _scene_user_message(*, story_brain: dict, events: list) -> str:
    return f"""
请基于最近互动历史和当前 Agent Story Brain，生成一段面向玩家的场景描述。
只描述环境、氛围、角色位置、角色外在状态、明显变化、玩家可观察信息。
不要决定角色行为，不要修改 Story Brain，不要输出 JSON。

当前 Agent Story Brain：
{_json_block(story_brain)}

最近互动历史：
{_history_text(events, limit=12) or "暂无"}
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


def iter_agent_evolution(
    *,
    ctx: AgentContext,
    prompt_record: AgentPromptRecord,
    player_input: str,
    story_brain: dict,
    events: list,
    debug_log_start_index: int = 0,
) -> Iterator[AgentRunProgress]:
    story_brain = normalize_agent_story_brain(story_brain)
    new_events = list(events or [])
    debug_logs: list = []
    player_input = str(player_input or "").strip()
    completed_rounds = 0
    stopped_early = False
    if not player_input:
        yield AgentRunProgress(
            phase="complete",
            story_brain=story_brain,
            events=new_events,
            completed_rounds=0,
            stopped_early=False,
            debug_logs=debug_logs,
        )
        return

    try:
        story_brain_before_player_input = normalize_agent_story_brain(story_brain)
        player_event = _event(
            "player",
            player_input,
            speaker="玩家",
            meta={
                "story_brain_before": story_brain_before_player_input,
                "debug_log_start_index": int(debug_log_start_index),
            },
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
            message="正在解析玩家输入...",
            story_brain=story_brain,
            events=list(new_events),
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            debug_logs=list(debug_logs),
        )
        parser_raw = _send_model(
            ctx=ctx,
            system_prompt=prompt_record.player_parser_prompt,
            user_message=_prompt4_user_message(
                player_input=player_input,
                story_brain=story_brain,
                events=new_events,
            ),
        )
        parser_data = _parse_json_object(parser_raw, label="Prompt4 玩家输入解析器")
        story_brain = apply_agent_story_brain_updates(story_brain, _updates_from(parser_data))

        present_characters = parser_data.get("present_characters")
        if isinstance(present_characters, list):
            story_brain = apply_agent_story_brain_updates(
                story_brain,
                {
                    "suggested_updates": [
                        {
                            "target_type": "scene",
                            "action": "modify",
                            "data": {"present_characters": present_characters},
                        }
                    ]
                },
            )

        current_npc = _npc_name(parser_data.get("first_npc"))
        if not current_npc:
            raise ValueError("Prompt4 必须返回 first_npc，且值必须是 NPC1、NPC2 或 NPC3。")
        next_instruction = str(parser_data.get("npc_instruction") or "").strip() or "根据玩家输入和当前局势作出一次有效行为。"

        acted_npcs: List[str] = []

        while completed_rounds < ctx.evolution_rounds:
            npc_prompt = _npc_prompt_for(prompt_record, current_npc)
            memory_pack = build_agent_memory_pack(
                npc_name=current_npc,
                current_text=next_instruction,
                story_brain=story_brain,
            )
            yield AgentRunProgress(
                phase="status",
                message=f"第 {completed_rounds + 1} 轮：{current_npc} 正在行动...",
                story_brain=story_brain,
                events=list(new_events),
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=list(debug_logs),
            )
            npc_output = _send_model(
                ctx=ctx,
                system_prompt=npc_prompt,
                user_message=_npc_user_message(
                    npc_name=current_npc,
                    instruction=next_instruction,
                    memory_pack_json=agent_memory_pack_to_json(memory_pack),
                    events=new_events,
                ),
            ).strip()
            if not npc_output:
                raise ValueError(f"{current_npc} 没有产生有效输出。")

            completed_rounds += 1
            acted_npcs.append(current_npc)
            npc_event = _event("npc", npc_output, speaker=current_npc, meta={"round": completed_rounds})
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

            yield AgentRunProgress(
                phase="status",
                message=f"第 {completed_rounds} 轮：正在裁决并更新 Story Brain...",
                story_brain=story_brain,
                events=list(new_events),
                completed_rounds=completed_rounds,
                stopped_early=stopped_early,
                debug_logs=list(debug_logs),
            )
            scheduler_raw = _send_model(
                ctx=ctx,
                system_prompt=prompt_record.action_scheduler_prompt,
                user_message=_prompt5_user_message(
                    npc_name=current_npc,
                    npc_output=npc_output,
                    story_brain=story_brain,
                    events=new_events,
                    acted_npcs=acted_npcs,
                ),
            )
            scheduler_data = _parse_json_object(scheduler_raw, label="Prompt5 行动裁决与下一角色调度器")
            story_brain = apply_agent_story_brain_updates(story_brain, _updates_from(scheduler_data))

            judgement_summary = str(scheduler_data.get("judgement_summary") or "").strip()
            if judgement_summary:
                judgement_event = _event(
                    "judgement",
                    judgement_summary,
                    speaker="裁决",
                    meta={"round": completed_rounds},
                )
                new_events.append(judgement_event)
                yield AgentRunProgress(
                    phase="event",
                    message=f"第 {completed_rounds} 轮：裁决完成。",
                    event=judgement_event,
                    story_brain=story_brain,
                    events=list(new_events),
                    completed_rounds=completed_rounds,
                    stopped_early=stopped_early,
                    debug_logs=list(debug_logs),
                )

            present_characters = scheduler_data.get("present_characters")
            if isinstance(present_characters, list):
                story_brain = apply_agent_story_brain_updates(
                    story_brain,
                    {
                        "suggested_updates": [
                            {
                                "target_type": "scene",
                                "action": "modify",
                                "data": {"present_characters": present_characters},
                            }
                        ]
                    },
                )

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
                scene_text = _send_model(
                    ctx=ctx,
                    system_prompt=prompt_record.scene_descriptor_prompt,
                    user_message=_scene_user_message(story_brain=story_brain, events=new_events),
                ).strip()
                if scene_text:
                    scene_event = _event("scene", scene_text, speaker="场景", meta={"round": completed_rounds})
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
                stop_event = _event("system", reason, speaker="系统", meta={"round": completed_rounds})
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
                raise ValueError("Prompt5 必须返回 next_npc，且值必须是 NPC1、NPC2 或 NPC3。")
            if next_npc == current_npc:
                raise ValueError("Prompt5 返回的 next_npc 不能等于刚刚行动的 NPC。")
            current_npc = next_npc
            next_instruction = str(scheduler_data.get("next_instruction") or "").strip() or "根据当前局势作出一次有效行为。"

        yield AgentRunProgress(
            phase="complete",
            message="Agent 自动演化完成。",
            story_brain=story_brain,
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
            story_brain=story_brain,
            events=list(new_events),
            completed_rounds=completed_rounds,
            stopped_early=stopped_early,
            error=message,
            debug_logs=list(debug_logs),
        )
        yield AgentRunProgress(
            phase="complete",
            message=message,
            story_brain=story_brain,
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
    story_brain: dict,
    events: list,
    debug_log_start_index: int = 0,
) -> AgentRunResult:
    final_progress: Optional[AgentRunProgress] = None
    for progress in iter_agent_evolution(
        ctx=ctx,
        prompt_record=prompt_record,
        player_input=player_input,
        story_brain=story_brain,
        events=events,
        debug_log_start_index=debug_log_start_index,
    ):
        if progress.phase == "complete":
            final_progress = progress

    if final_progress is None:
        normalized_story_brain = normalize_agent_story_brain(story_brain)
        return AgentRunResult(
            story_brain=normalized_story_brain,
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
