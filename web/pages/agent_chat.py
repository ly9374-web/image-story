import base64
import html
import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

from app.api.media_clients import CloudinaryUploader
from app.config import user_facing_error_message
from app.models import GeneratedMediaKind
from app.services import agent_prompts, agent_records, agent_service, page2_service, stored_urls
from web.nav import get_arg


_story_brain_text_editor_component = components.declare_component(
    "agent_story_brain_text_editor",
    path=str(Path(__file__).resolve().parents[1] / "components" / "agent_story_brain_text_editor"),
)


def _sync_context_widgets_from_ctx(ctx):
    st.session_state.agent_evolution_rounds_input = int(ctx.evolution_rounds)
    st.session_state.agent_player_route_history_turns_input = int(ctx.player_route_history_turns)
    st.session_state.agent_npc_history_turns_input = int(ctx.npc_history_turns)
    st.session_state.agent_action_decision_history_turns_input = int(ctx.action_decision_history_turns)
    st.session_state.agent_scene_history_turns_input = int(ctx.scene_history_turns)
    st.session_state.agent_story_brain_turns_input = int(ctx.story_brain_turns)
    st.session_state.agent_selected_chat_model_input = str(ctx.selected_chat_model or "grok1")
    st.session_state.agent_temperature_input = float(ctx.temperature)


def _ensure_context_widget_state(ctx):
    defaults = {
        "agent_evolution_rounds_input": int(ctx.evolution_rounds),
        "agent_player_route_history_turns_input": int(ctx.player_route_history_turns),
        "agent_npc_history_turns_input": int(ctx.npc_history_turns),
        "agent_action_decision_history_turns_input": int(ctx.action_decision_history_turns),
        "agent_scene_history_turns_input": int(ctx.scene_history_turns),
        "agent_story_brain_turns_input": int(ctx.story_brain_turns),
        "agent_selected_chat_model_input": str(ctx.selected_chat_model or "grok1"),
        "agent_temperature_input": float(ctx.temperature),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _chat_scope() -> Optional[str]:
    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    return "guest" if mode == "guest" else None


def _ensure_state():
    st.session_state.setdefault("agent_record_id", "")
    st.session_state.setdefault("agent_loaded_record_id", "")
    st.session_state.setdefault("agent_story_brain", "")
    st.session_state.agent_story_brain = agent_records.story_brain_to_text(
        st.session_state.get("agent_story_brain")
    )
    st.session_state.setdefault("agent_events", [])
    st.session_state.setdefault("agent_generated_media", [])
    st.session_state.setdefault("agent_debug_logs", [])
    st.session_state.setdefault("agent_selected_media_id", "")
    st.session_state.setdefault("agent_image_prompt", "")
    st.session_state.setdefault("agent_image_prompt_mode", "normal")
    st.session_state.setdefault("agent_image_prompt_subject", "")
    st.session_state.setdefault("agent_video_prompt", "动起来")
    st.session_state.setdefault("agent_url_hidden_space", False)
    st.session_state.setdefault("agent_story_brain_enabled", False)
    st.session_state.setdefault("agent_story_brain_editor_nonce", 0)
    st.session_state.setdefault("agent_last_error", "")
    st.session_state.setdefault("agent_last_save_notice", "")


def _refresh_story_brain_editor():
    st.session_state.agent_story_brain_editor_nonce = int(
        st.session_state.get("agent_story_brain_editor_nonce", 0) or 0
    ) + 1


def _current_story_brain() -> str:
    story_brain = agent_records.story_brain_to_text(st.session_state.get("agent_story_brain"))
    st.session_state.agent_story_brain = story_brain
    return story_brain


def _decode_image_base64(b64: str) -> bytes:
    return base64.b64decode(b64.encode("ascii"))


def _show_error(exc: Exception):
    st.error(user_facing_error_message(exc))


def _save_agent_story_brain(story_brain: str, prompt_record=None, ctx=None):
    st.session_state.agent_story_brain = agent_records.story_brain_to_text(story_brain)
    if prompt_record is not None and ctx is not None and str(st.session_state.get("agent_record_id", "") or ""):
        _save_current_record(prompt_record, ctx)


def _active_prompt_record():
    state = agent_prompts.load_state(hidden_space=bool(st.session_state.get("agent_prompt_hidden_space", False)))
    records = agent_prompts.visible_records(state)
    return agent_prompts.selected_record(state) or (records[0] if records else None)


def _load_record_from_nav_if_needed():
    record_id = str(get_arg("record_id", "") or "").strip()
    if not record_id:
        return

    if str(st.session_state.get("agent_loaded_record_id", "") or "") == record_id:
        return

    record = agent_records.load_record_by_id(record_id, scope=_chat_scope())
    if record is None:
        st.warning("Agent 记录不存在或加载失败。")
        return

    st.session_state.agent_record_id = record.id
    st.session_state.agent_loaded_record_id = record.id
    st.session_state.agent_events = list(record.events or [])
    st.session_state.agent_story_brain = agent_records.story_brain_to_text(record.story_brain)
    _refresh_story_brain_editor()
    st.session_state.agent_generated_media = list(record.generated_media or [])
    st.session_state.agent_debug_logs = list(getattr(record, "debug_logs", []) or [])
    st.session_state.agent_selected_media_id = ""
    st.session_state.agent_image_prompt = ""
    st.session_state.agent_last_error = ""
    st.session_state.agent_last_save_notice = ""

    ctx = agent_service.load_context_from_settings()
    ctx.selected_chat_model = record.selected_chat_model or ctx.selected_chat_model
    ctx.temperature = float(record.temperature)
    ctx.evolution_rounds = int(record.evolution_rounds)
    ctx.player_route_history_turns = int(getattr(record, "player_route_history_turns", ctx.player_route_history_turns))
    ctx.npc_history_turns = int(getattr(record, "npc_history_turns", ctx.npc_history_turns))
    ctx.action_decision_history_turns = int(getattr(record, "action_decision_history_turns", ctx.action_decision_history_turns))
    ctx.scene_history_turns = int(getattr(record, "scene_history_turns", ctx.scene_history_turns))
    ctx.story_brain_turns = int(getattr(record, "story_brain_turns", ctx.story_brain_turns))
    agent_service.save_context_to_settings(ctx)
    _sync_context_widgets_from_ctx(ctx)

    if str(record.prompt_record_id or "").strip():
        prompt_state = agent_prompts.load_state(hidden_space=True)
        if agent_prompts.record_space(prompt_state, record.prompt_record_id) == "hidden":
            st.session_state.agent_prompt_hidden_space = True
        prompt_state = agent_prompts.load_state(hidden_space=bool(st.session_state.get("agent_prompt_hidden_space", False)))
        agent_prompts.select_record(prompt_state, record.prompt_record_id)


def prepare_from_navigation():
    _ensure_state()
    _load_record_from_nav_if_needed()


def _npc_display_names(prompt_record) -> dict:
    return {
        "NPC1": str(getattr(prompt_record, "npc1_name", "NPC1") or "NPC1").strip() or "NPC1",
        "NPC2": str(getattr(prompt_record, "npc2_name", "NPC2") or "NPC2").strip() or "NPC2",
        "NPC3": str(getattr(prompt_record, "npc3_name", "NPC3") or "NPC3").strip() or "NPC3",
    }


def _latest_agent_message(events: list) -> str:
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        kind = str(event.get("kind", "") or "").strip()
        if kind in {"player", "error", "system"}:
            continue
        content = str(event.get("content", "") or "").strip()
        if content:
            return content
    return ""


def _event_label(event: dict, display_names: dict) -> str:
    speaker = str(event.get("speaker", "") or "").strip()
    kind = str(event.get("kind", "") or "").strip()
    if speaker:
        return display_names.get(speaker, speaker)
    if kind == "scene":
        return "场景"
    if kind == "judgement":
        return "裁决"
    if kind == "error":
        return "错误"
    return "系统"


def _event_class(event: dict) -> str:
    kind = str(event.get("kind", "") or "")
    speaker = str(event.get("speaker", "") or "").strip()
    if kind == "player":
        return "player"
    if speaker == "NPC1":
        return "npc1"
    if speaker == "NPC2":
        return "npc2"
    if speaker == "NPC3":
        return "npc3"
    if kind in {"scene", "judgement", "error", "system"}:
        return kind
    return "assistant"


def _html_text(text: str) -> str:
    return html.escape(str(text or "").strip()).replace("\n", "<br>")


def _render_event(event: dict, display_names: dict):
    kind = str(event.get("kind", "") or "")
    content = str(event.get("content", "") or "").strip()
    if not content:
        return

    label = _event_label(event, display_names)
    if kind == "scene":
        label = "场景描述"
    css_class = _event_class(event)
    st.markdown(
        f"""
<div class="agent-event agent-event-{css_class}">
  <div class="agent-event-avatar"></div>
  <div class="agent-event-bubble">
    <div class="agent-event-label">{html.escape(label)}</div>
    <div class="agent-event-content">{_html_text(content)}</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_event_list(events: list, display_names: dict):
    for event in events:
        if isinstance(event, dict):
            _render_event(event, display_names)


def _select_prompt_record():
    state = agent_prompts.load_state(hidden_space=bool(st.session_state.get("agent_prompt_hidden_space", False)))
    records = agent_prompts.visible_records(state)
    if not records:
        st.warning("暂无 Agent prompt 记录。请先到 Agent Prompt 页面创建一条记录。")
        return state, None

    options = [
        f"{index + 1}. {'隐藏：' if agent_prompts.record_space(state, record.id) == 'hidden' else ''}{record.title or '未命名 Agent 记录'}"
        for index, record in enumerate(records)
    ]
    selected = agent_prompts.selected_record(state) or records[0]
    selected_index = 0
    for index, record in enumerate(records):
        if record.id == selected.id:
            selected_index = index
            break

    chosen_title = st.selectbox("Agent prompt 记录", options=options, index=selected_index)
    chosen_record = records[options.index(chosen_title)]
    if chosen_record.id != state.selected_record_id:
        state = agent_prompts.select_record(state, chosen_record.id)
        _apply_prompt_default_story_brain(chosen_record)
        st.rerun()
    return state, chosen_record


def _build_record(prompt_record, ctx) -> agent_records.AgentChatRecord:
    record_id = str(st.session_state.get("agent_record_id", "") or "").strip()
    existing = agent_records.load_record_by_id(record_id, scope=_chat_scope()) if record_id else None
    record = existing if existing is not None else agent_records.empty_record()
    record.events = list(st.session_state.get("agent_events") or [])
    record.story_brain = _current_story_brain()
    record.generated_media = list(st.session_state.get("agent_generated_media") or [])
    record.debug_logs = list(st.session_state.get("agent_debug_logs") or [])
    record.prompt_record_id = prompt_record.id if prompt_record is not None else ""
    record.selected_chat_model = ctx.selected_chat_model
    record.temperature = float(ctx.temperature)
    record.evolution_rounds = int(ctx.evolution_rounds)
    record.player_route_history_turns = int(ctx.player_route_history_turns)
    record.npc_history_turns = int(ctx.npc_history_turns)
    record.action_decision_history_turns = int(ctx.action_decision_history_turns)
    record.scene_history_turns = int(ctx.scene_history_turns)
    record.story_brain_turns = int(ctx.story_brain_turns)
    record.title = agent_records.build_record_title(record.events)
    return record


def _save_current_record(prompt_record, ctx) -> str:
    record = _build_record(prompt_record, ctx)
    agent_records.save_or_update_record(record, scope=_chat_scope())
    st.session_state.agent_record_id = record.id
    return record.id


def _apply_default_story_brain_if_new(prompt_record):
    default_story_brain = str(getattr(prompt_record, "default_story_brain", "") or "").strip()
    if not default_story_brain:
        return
    if str(st.session_state.get("agent_record_id", "") or "").strip():
        return
    if list(st.session_state.get("agent_events") or []):
        return
    if str(st.session_state.get("agent_story_brain", "") or "").strip():
        return
    _apply_prompt_default_story_brain(prompt_record)


def _apply_prompt_default_story_brain(prompt_record):
    default_story_brain = agent_records.story_brain_to_text(
        getattr(prompt_record, "default_story_brain", "") if prompt_record is not None else ""
    )
    st.session_state.agent_story_brain = default_story_brain
    st.session_state.agent_story_brain_enabled = bool(default_story_brain.strip())
    _refresh_story_brain_editor()


def start_new_conversation(reset_settings: bool = False):
    _ensure_state()
    if reset_settings:
        agent_service.reset_context_settings()
        page2_ctx = page2_service.load_context_from_settings()
        page2_ctx.selected_video_generation_provider = "domoai"
        page2_service.save_context_to_settings(page2_ctx)
        agent_prompts.reset_selected_record()
        _sync_context_widgets_from_ctx(agent_service.default_context())
    st.session_state.agent_record_id = ""
    st.session_state.agent_loaded_record_id = ""
    st.session_state.agent_events = []
    st.session_state.agent_generated_media = []
    st.session_state.agent_debug_logs = []
    st.session_state.agent_selected_media_id = ""
    st.session_state.agent_image_prompt = ""
    st.session_state.agent_story_brain = ""
    st.session_state.agent_last_error = ""
    st.session_state.agent_last_save_notice = ""
    st.session_state.agent_story_brain_enabled = False
    _apply_default_story_brain_if_new(_active_prompt_record())


def _undo_last_visible_event():
    events = list(st.session_state.get("agent_events") or [])
    if not events:
        return False

    last_event = events[-1]
    if isinstance(last_event, dict):
        meta = last_event.get("meta")
        if isinstance(meta, dict) and "story_brain_before" in meta:
            st.session_state.agent_story_brain = agent_records.story_brain_to_text(
                meta.get("story_brain_before")
            )
        if isinstance(meta, dict) and isinstance(meta.get("debug_log_start_index"), int):
            st.session_state.agent_debug_logs = list(
                st.session_state.get("agent_debug_logs") or []
            )[: meta.get("debug_log_start_index")]

    st.session_state.agent_events = events[:-1]
    st.session_state.agent_last_error = ""
    return True


def _render_story_brain_text_editor(value: str) -> str:
    result = _story_brain_text_editor_component(
        value=str(value or ""),
        key=f"agent_story_brain_text_editor_component_{int(st.session_state.get('agent_story_brain_editor_nonce', 0) or 0)}",
        default=None,
    )
    if isinstance(result, str):
        return result
    return str(value or "")


def _render_agent_story_brain_panel(prompt_record, ctx):
    story_brain_enabled = bool(st.session_state.get("agent_story_brain_enabled", False))
    if st.button(
        "点击关闭story brain" if story_brain_enabled else "点击开启story brain",
        key="agent_story_brain_btn",
        use_container_width=True,
    ):
        st.session_state.agent_story_brain_enabled = not story_brain_enabled
        st.rerun()

    if not bool(st.session_state.get("agent_story_brain_enabled", False)):
        return

    story_brain = _current_story_brain()
    next_story_brain = _render_story_brain_text_editor(story_brain)
    if next_story_brain != story_brain:
        _save_agent_story_brain(next_story_brain, prompt_record, ctx)
        st.rerun()


def render_sidebar_context():
    _ensure_state()
    prompt_record = None
    ctx = agent_service.load_context_from_settings()
    _ensure_context_widget_state(ctx)

    with st.sidebar:
        if st.button("新建 Agent 对话", use_container_width=True):
            start_new_conversation()
            st.rerun()

        if st.session_state.get("agent_record_id"):
            st.caption("记录 ID: " + str(st.session_state.agent_record_id))

        st.divider()
        st.subheader("Agent 参数")
        _, selected_prompt_record = _select_prompt_record()
        if selected_prompt_record is not None:
            prompt_record = selected_prompt_record
            _apply_default_story_brain_if_new(prompt_record)

        rounds = st.number_input(
            "自动演化轮数",
            min_value=1,
            max_value=25,
            key="agent_evolution_rounds_input",
        )
        player_route_history_turns = st.number_input(
            "玩家路由带入轮数",
            step=1,
            key="agent_player_route_history_turns_input",
        )
        npc_history_turns = st.number_input(
            "NPC行动带入轮数",
            step=1,
            key="agent_npc_history_turns_input",
        )
        action_decision_history_turns = st.number_input(
            "行动裁决带入轮数",
            step=1,
            key="agent_action_decision_history_turns_input",
        )
        scene_history_turns = st.number_input(
            "场景描述带入轮数",
            step=1,
            key="agent_scene_history_turns_input",
        )
        story_brain_turns = st.number_input(
            "Story Brain 更新间隔/带入轮数",
            min_value=1,
            step=1,
            key="agent_story_brain_turns_input",
        )
        model = st.selectbox(
            "聊天模型",
            options=["grok1", "grok2", "deepseek"],
            key="agent_selected_chat_model_input",
        )
        temperature = st.slider(
            "temperature",
            min_value=0.0,
            max_value=2.0,
            step=0.05,
            key="agent_temperature_input",
        )
        ctx.selected_chat_model = model
        ctx.temperature = float(temperature)
        ctx.evolution_rounds = int(rounds)
        ctx.player_route_history_turns = int(player_route_history_turns)
        ctx.npc_history_turns = int(npc_history_turns)
        ctx.action_decision_history_turns = int(action_decision_history_turns)
        ctx.scene_history_turns = int(scene_history_turns)
        ctx.story_brain_turns = int(story_brain_turns)
        agent_service.save_context_to_settings(ctx)

        page2_ctx = page2_service.load_context_from_settings()
        video_provider = st.selectbox(
            "图生视频",
            options=["domoai", "zhipu"],
            index=["domoai", "zhipu"].index(page2_ctx.selected_video_generation_provider)
            if page2_ctx.selected_video_generation_provider in ["domoai", "zhipu"]
            else 0,
        )
        page2_ctx.selected_video_generation_provider = video_provider
        page2_service.save_context_to_settings(page2_ctx)

        st.divider()
        st.subheader("对话")
        if st.button("撤销", use_container_width=True, disabled=not bool(st.session_state.get("agent_events"))):
            if _undo_last_visible_event():
                if str(st.session_state.get("agent_record_id", "") or ""):
                    _save_current_record(prompt_record, ctx)
                st.rerun()

        save_disabled = not bool(st.session_state.get("agent_events"))
        if st.button("保存记录", type="primary", use_container_width=True, disabled=save_disabled):
            record_id = _save_current_record(prompt_record, ctx)
            st.session_state.agent_last_save_notice = "已保存 Agent 记录：" + record_id
            st.rerun()

        if st.button("清空聊天", use_container_width=True):
            st.session_state.agent_events = []
            st.session_state.agent_last_error = ""
            if str(st.session_state.get("agent_record_id", "") or ""):
                _save_current_record(prompt_record, ctx)
            st.rerun()

        notice = str(st.session_state.get("agent_last_save_notice", "") or "").strip()
        if notice:
            st.success(notice)


def _render_chat_column(prompt_record, ctx):
    display_names = _npc_display_names(prompt_record)
    with st.container(key="agent_chat_canvas"):
        history = st.container(key="agent_chat_history")
        with history:
            _render_event_list(st.session_state.agent_events, display_names)

        story_brain_enabled = bool(st.session_state.get("agent_story_brain_enabled", False))
        story_brain = _current_story_brain() if story_brain_enabled else ""
        live_history = st.empty()
        progress_notice = st.empty()
        user_text = st.chat_input("输入剧情指令、角色控制、环境变化或突发事件", key="agent_chat_input")
        if user_text:
            if prompt_record is None:
                st.session_state.agent_last_error = "暂无 Agent prompt 记录。请先到 Agent Prompt 页面创建并选择一条记录。"
                st.session_state.agent_events.append(
                    {
                        "kind": "error",
                        "speaker": "错误",
                        "content": st.session_state.agent_last_error,
                        "meta": {},
                    }
                )
                st.rerun()

            live_events = []
            final_progress = None
            for progress in agent_service.iter_agent_evolution(
                ctx=ctx,
                prompt_record=prompt_record,
                player_input=user_text,
                story_brain=story_brain,
                events=st.session_state.agent_events,
                debug_log_start_index=len(st.session_state.get("agent_debug_logs") or []),
                story_brain_enabled=story_brain_enabled,
            ):
                if progress.message:
                    if progress.phase == "complete" and not progress.error:
                        progress_notice.success(progress.message)
                    elif progress.error:
                        progress_notice.error(progress.message)
                    else:
                        progress_notice.info(progress.message)

                if progress.event is not None:
                    live_events.append(progress.event)
                    live_history.empty()
                    with live_history.container():
                        _render_event_list(live_events, display_names)

                if progress.phase == "complete":
                    final_progress = progress

            if final_progress is None:
                result = agent_service.run_agent_evolution(
                    ctx=ctx,
                    prompt_record=prompt_record,
                    player_input=user_text,
                    story_brain=story_brain,
                    events=st.session_state.agent_events,
                    debug_log_start_index=len(st.session_state.get("agent_debug_logs") or []),
                    story_brain_enabled=story_brain_enabled,
                )
            else:
                result = agent_service.AgentRunResult(
                    story_brain=final_progress.story_brain,
                    events=final_progress.events,
                    completed_rounds=final_progress.completed_rounds,
                    error=final_progress.error,
                    debug_logs=final_progress.debug_logs,
                )

            if story_brain_enabled:
                st.session_state.agent_story_brain = result.story_brain
            st.session_state.agent_events = result.events
            st.session_state.agent_debug_logs = list(st.session_state.get("agent_debug_logs") or []) + list(result.debug_logs or [])
            st.session_state.agent_last_error = result.error
            _save_current_record(prompt_record, ctx)
            st.rerun()

    _render_agent_story_brain_panel(prompt_record, ctx)


def _render_media_column(prompt_record, ctx):
    st.subheader("图片 / 视频")

    media = st.session_state.agent_generated_media
    if not media:
        st.caption("暂无媒体记录。")
    else:
        options = []
        by_id = {}
        for item in media:
            kind = item.media_kind.value if hasattr(item.media_kind, "value") else str(item.media_kind)
            label = f"{kind.upper()} • {item.provider} • {str(item.created_at or '')}"
            options.append(label)
            by_id[label] = item.id

        selected_media_id = str(st.session_state.get("agent_selected_media_id", "") or "")
        selected_index = 0
        if selected_media_id:
            for index, label in enumerate(options):
                if by_id.get(label) == selected_media_id:
                    selected_index = index
                    break

        selected_label = st.selectbox(
            "选择记录",
            options=options,
            index=selected_index,
            label_visibility="collapsed",
        )
        selected_id = by_id.get(selected_label, "")
        st.session_state.agent_selected_media_id = selected_id

        selected = None
        for item in media:
            if item.id == selected_id:
                selected = item
                break

        if selected is not None:
            kind = selected.media_kind.value if hasattr(selected.media_kind, "value") else str(selected.media_kind)
            st.caption(f"{kind} • provider={selected.provider}")
            st.text_area("prompt", value=str(selected.prompt or ""), height=120, disabled=True)

            if kind == GeneratedMediaKind.IMAGE.value:
                if selected.image_data_base64:
                    st.image(_decode_image_base64(selected.image_data_base64))
                elif selected.image_url_string:
                    st.image(selected.image_url_string)

                url = selected.image_url_string or ""
                if url:
                    st.text_input("图片 URL（可复制）", value=url)
            else:
                url = selected.video_url_string or ""
                if url:
                    st.video(url)
                    st.text_input("视频 URL（可复制）", value=url)
                else:
                    st.warning("该视频记录没有 URL。")

            if st.button("删除当前记录", use_container_width=True):
                st.session_state.agent_generated_media = [m for m in media if m.id != selected_id]
                _save_current_record(prompt_record, ctx)
                st.rerun()

    st.divider()
    st.subheader("生成图片")

    latest = _latest_agent_message(st.session_state.agent_events)
    if not latest:
        st.caption("先在左侧生成一条 Agent 回复，然后可以点击“生成图片prompt”。")

    mode = st.selectbox(
        "prompt 模式",
        options=["normal", "first_person", "closeup"],
        index=["normal", "first_person", "closeup"].index(st.session_state.agent_image_prompt_mode),
    )
    st.session_state.agent_image_prompt_mode = mode
    subject = ""
    if mode in ["first_person", "closeup"]:
        subject = st.text_input("主体", value=st.session_state.agent_image_prompt_subject)
        st.session_state.agent_image_prompt_subject = subject

    if st.button("生成图片prompt", use_container_width=True, disabled=not latest):
        with st.spinner("正在生成图片prompt..."):
            try:
                prompt = page2_service.generate_image_prompt(latest, mode=mode, subject=subject)
                st.session_state.agent_image_prompt = prompt
                st.success("图片prompt已生成")
            except Exception as exc:
                _show_error(exc)

    prompt_text = st.text_area("图片prompt（可编辑）", value=st.session_state.agent_image_prompt, height=160)
    st.session_state.agent_image_prompt = prompt_text

    provider = st.selectbox(
        "图片生成 provider",
        options=["grok", "grokQuality", "grokPro", "flux", "nanoPro", "nano"],
        index=0,
    )
    image_urls_raw = st.text_area("参考图片 URL（每行一个，可选）", value="", height=90)
    image_urls = [line.strip() for line in image_urls_raw.splitlines() if line.strip()]

    if st.button("生成图片", type="primary", use_container_width=True):
        with st.spinner("正在生成图片..."):
            try:
                record = page2_service.generate_image(provider=provider, prompt=prompt_text, image_urls=image_urls)
                st.session_state.agent_generated_media = media + [record]
                st.session_state.agent_selected_media_id = record.id
                _save_current_record(prompt_record, ctx)
                st.success("图片已生成并保存到记录")
                st.rerun()
            except Exception as exc:
                _show_error(exc)

    st.divider()
    st.subheader("图生视频")
    st.caption("从上面的媒体列表里选择一张图片作为输入。")

    image_candidates = [
        m
        for m in media
        if (m.media_kind.value if hasattr(m.media_kind, "value") else str(m.media_kind)) == GeneratedMediaKind.IMAGE.value
    ]
    if not image_candidates:
        st.caption("暂无可用图片。")
        _render_url_tools()
        return

    candidate_labels = []
    label_to_id = {}
    for item in image_candidates:
        label = f"{item.provider} • {str(item.created_at or '')} • {item.prompt[:24] if item.prompt else ''}"
        candidate_labels.append(label)
        label_to_id[label] = item.id

    selected_media_id = str(st.session_state.get("agent_selected_media_id", "") or "")
    selected_image_index = len(image_candidates) - 1
    if selected_media_id:
        for index, item in enumerate(image_candidates):
            if item.id == selected_media_id:
                selected_image_index = index
                break

    selected_label = st.selectbox(
        "选择输入图片",
        options=candidate_labels,
        index=selected_image_index,
    )
    source_id = label_to_id.get(selected_label, "")
    source = None
    for item in image_candidates:
        if item.id == source_id:
            source = item
            break
    if source is None:
        _render_url_tools()
        return

    video_prompt = st.text_input("视频 prompt", key="agent_video_prompt")
    page2_ctx = page2_service.load_context_from_settings()
    if str(page2_ctx.selected_video_generation_provider or "") == "zhipu":
        seconds = st.selectbox("时长（秒）", options=[5, 10], index=0)
    else:
        seconds = st.number_input("时长（秒）", min_value=1, max_value=10, value=5)

    if st.button("生成视频", use_container_width=True):
        with st.spinner("正在生成视频（可能需要较长时间）..."):
            try:
                video_record = page2_service.generate_video_from_image(
                    ctx=page2_ctx,
                    source_record=source,
                    prompt=video_prompt,
                    seconds=int(seconds),
                )
                st.session_state.agent_generated_media = media + [video_record]
                st.session_state.agent_selected_media_id = video_record.id
                _save_current_record(prompt_record, ctx)
                st.success("视频已生成并保存到记录")
                st.rerun()
            except Exception as exc:
                _show_error(exc)

    _render_url_tools()


def _render_url_tools():
    st.divider()
    st.subheader("URL 收藏")

    url_state = stored_urls.load_state(hidden_space=bool(st.session_state.agent_url_hidden_space))
    st.session_state.agent_url_hidden_space = url_state.hidden_space

    url_input = st.text_input("新增 URL 或输入口令解锁隐藏空间", value="")
    add_col1, add_col2 = st.columns([1, 1])
    with add_col1:
        if st.button("新增", use_container_width=True):
            try:
                url_state = stored_urls.add_url(url_state, url_input)
                st.session_state.agent_url_hidden_space = url_state.hidden_space
                st.rerun()
            except Exception as exc:
                _show_error(exc)
    with add_col2:
        uploaded = st.file_uploader("上传图片获取 URL（Cloudinary）", type=["png", "jpg", "jpeg", "webp"])
        if uploaded is not None and st.button("上传并复制 URL", use_container_width=True):
            with st.spinner("上传中..."):
                try:
                    suffix = Path(uploaded.name).suffix or ".png"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uploaded.getvalue())
                        tmp_path = tmp.name
                    secure_url = CloudinaryUploader.upload_image(tmp_path)
                    st.success("上传成功（URL 可复制）")
                    st.text_input("URL", value=secure_url)
                except Exception as exc:
                    _show_error(exc)

    visible = stored_urls.visible_records(url_state)
    if visible:
        url_labels = []
        url_by_label = {}
        for record in visible:
            prefix = "隐藏：" if record in url_state.hidden_records else ""
            label = f"{prefix}{record.title}: {record.url}"
            url_labels.append(label)
            url_by_label[label] = record
        chosen = st.selectbox("收藏列表", options=url_labels)
        record = url_by_label.get(chosen)
        if record is not None:
            st.text_input("选中 URL（可复制）", value=record.url)
            if st.button("删除选中 URL", use_container_width=True):
                stored_urls.delete_url(url_state, record.id)
                st.success("已删除")
                st.rerun()
    else:
        st.caption("暂无收藏。")


def render():
    prepare_from_navigation()
    st.markdown(
        """
<style>
/* Agent chat: match the normal chat page's top alignment. */
section[data-testid="stMain"] .block-container {
  padding-top: 16px !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    ctx = agent_service.load_context_from_settings()
    prompt_record = _active_prompt_record()

    chat_col, media_col = st.columns([1, 1])
    with chat_col:
        _render_chat_column(prompt_record, ctx)

    with media_col:
        _render_media_column(prompt_record, ctx)
