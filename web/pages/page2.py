from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import streamlit as st

from app.api.media_clients import CloudinaryUploader
from app.config import AppStorageKeys, settings
from app.models import GeneratedMediaKind, Page2ConversationTurn
from app.services import chat_records, page2_service, stored_urls, system_prompts
from web.nav import get_arg, goto


def _chat_scope() -> str | None:
    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    return "guest" if mode == "guest" else None


def _decode_image_base64(b64: str) -> bytes:
    return base64.b64decode(b64.encode("ascii"))


def _ensure_state():
    st.session_state.setdefault("page2_record_id", "")
    st.session_state.setdefault("page2_loaded_record_id", "")
    st.session_state.setdefault("page2_turns", [])
    st.session_state.setdefault("page2_generated_media", [])
    st.session_state.setdefault("page2_selected_media_id", "")
    st.session_state.setdefault("page2_image_prompt", "")
    st.session_state.setdefault("page2_image_prompt_mode", "normal")
    st.session_state.setdefault("page2_image_prompt_subject", "")
    st.session_state.setdefault("page2_url_hidden_space", False)


def _load_record_from_nav_if_needed():
    record_id = str(get_arg("record_id", "") or "").strip()
    if not record_id:
        return

    if st.session_state.page2_loaded_record_id == record_id:
        return

    record = chat_records.load_record_by_id(record_id, scope=_chat_scope())
    if record is None:
        st.warning("记录不存在或加载失败。")
        return

    st.session_state.page2_record_id = record.id
    st.session_state.page2_loaded_record_id = record.id
    st.session_state.page2_turns = list(record.turns or [])
    st.session_state.page2_generated_media = list(record.generated_images or [])
    st.session_state.page2_selected_media_id = ""

    if str(record.system_prompt or "").strip():
        ctx = page2_service.load_context_from_settings()
        ctx.system_prompt = record.system_prompt
        page2_service.save_context_to_settings(ctx)


def _latest_assistant_message(turns: list[Page2ConversationTurn]) -> str:
    for turn in reversed(turns):
        if turn.assistant_message:
            return turn.assistant_message
    return ""


def _upsert_record():
    ctx = page2_service.load_context_from_settings()
    st.session_state.page2_record_id = page2_service.upsert_chat_record(
        record_id=st.session_state.page2_record_id,
        turns=st.session_state.page2_turns,
        generated_media=st.session_state.page2_generated_media,
        system_prompt=ctx.system_prompt,
        scope=_chat_scope(),
    )


def _render_sidebar_context():
    with st.sidebar:
        st.subheader("会话")
        if st.button("新建会话", use_container_width=True):
            st.session_state.page2_record_id = ""
            st.session_state.page2_loaded_record_id = ""
            st.session_state.page2_turns = []
            st.session_state.page2_generated_media = []
            st.session_state.page2_selected_media_id = ""
            goto("main", push_history=False)

        if st.session_state.page2_record_id:
            st.caption("记录 ID: " + st.session_state.page2_record_id)

        st.divider()
        st.subheader("上下文设置")
        ctx = page2_service.load_context_from_settings()

        # 提供从「设置」里选择 system prompt 记录的入口
        prompt_state = system_prompts.load_state(hidden_space=False)
        prompt_records = system_prompts.visible_records(prompt_state)
        prompt_options = ["(使用当前)"] + [r.title for r in prompt_records]
        chosen = st.selectbox("选择 prompt 记录", options=prompt_options, index=0)
        if chosen != "(使用当前)":
            for record in prompt_records:
                if record.title == chosen:
                    ctx.system_prompt = record.prompt
                    settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, record.id)
                    settings.set(AppStorageKeys.SYSTEM_PROMPT, record.prompt)
                    break
            page2_service.save_context_to_settings(ctx)

        with st.form("page2_context_form", border=True):
            if _chat_scope() == "guest":
                st.text_area("system prompt（游客仅可选择）", value=ctx.system_prompt, height=180, disabled=True)
                system_prompt = ctx.system_prompt
            else:
                system_prompt = st.text_area("system prompt", value=ctx.system_prompt, height=180)
            context_turn_count = st.number_input("上下文轮数", min_value=0, max_value=50, value=int(ctx.context_turn_count))
            selected_chat_model = st.selectbox(
                "聊天模型",
                options=["grok1", "grok2", "deepseek"],
                index=["grok1", "grok2", "deepseek"].index(ctx.selected_chat_model)
                if ctx.selected_chat_model in ["grok1", "grok2", "deepseek"]
                else 0,
            )
            temperature = st.slider("temperature", min_value=0.0, max_value=2.0, value=float(ctx.temperature), step=0.05)
            video_provider = st.selectbox(
                "图生视频",
                options=["domoai", "zhipu"],
                index=["domoai", "zhipu"].index(ctx.selected_video_generation_provider)
                if ctx.selected_video_generation_provider in ["domoai", "zhipu"]
                else 0,
            )

            saved = st.form_submit_button("保存", use_container_width=True, type="primary")

        if saved:
            if _chat_scope() != "guest":
                ctx.system_prompt = system_prompt
            ctx.context_turn_count = int(context_turn_count)
            ctx.selected_chat_model = selected_chat_model
            ctx.temperature = float(temperature)
            ctx.selected_video_generation_provider = video_provider
            page2_service.save_context_to_settings(ctx)
            st.success("已保存")
            _upsert_record()
            st.rerun()


def _render_chat_column():
    turns = st.session_state.page2_turns

    with st.container(key="page2_chat_canvas"):
        history = st.container(key="page2_chat_history")
        with history:
            for turn in turns:
                with st.chat_message("user"):
                    st.markdown(turn.user_message or "")
                if turn.assistant_message is not None:
                    with st.chat_message("assistant"):
                        st.markdown(turn.assistant_message or "")

        user_text = st.chat_input("输入消息并回车发送", key="page2_chat_input")

    undo_clicked = st.button(
        "",
        key="page2_chat_undo_btn",
        help=None,
        icon=":material/undo:",
        type="tertiary",
        disabled=not bool(turns),
        use_container_width=True,
    )
    if undo_clicked and turns:
        st.session_state.page2_turns = turns[:-1]
        _upsert_record()
        st.rerun()

    if not user_text:
        return

    ctx = page2_service.load_context_from_settings()

    new_turn = Page2ConversationTurn(
        user_message=str(user_text).strip(),
        assistant_message=None,
        is_loading=True,
    )
    st.session_state.page2_turns = turns + [new_turn]
    _upsert_record()

    with st.spinner("正在请求模型..."):
        try:
            reply = page2_service.send_message(ctx=ctx, turns=st.session_state.page2_turns, user_message=new_turn.user_message)
        except Exception as exc:
            reply = "请求失败，请稍后重试。\n" + str(exc)

    # 写回最后一条
    last = st.session_state.page2_turns[-1]
    last.assistant_message = reply
    last.is_loading = False
    _upsert_record()
    st.rerun()


def _render_media_column():
    st.subheader("图片 / 视频")

    media = st.session_state.page2_generated_media
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

        selected_label = st.selectbox("选择记录", options=options, label_visibility="collapsed")
        selected_id = by_id.get(selected_label, "")
        st.session_state.page2_selected_media_id = selected_id

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
                st.session_state.page2_generated_media = [m for m in media if m.id != selected_id]
                _upsert_record()
                st.rerun()

    st.divider()
    st.subheader("生成图片")

    latest = _latest_assistant_message(st.session_state.page2_turns)
    if not latest:
        st.caption("先在左侧生成一条助手回复，然后可以从最近回复生成图片 prompt。")

    mode = st.selectbox(
        "prompt 模式",
        options=["normal", "first_person", "closeup"],
        index=["normal", "first_person", "closeup"].index(st.session_state.page2_image_prompt_mode),
    )
    st.session_state.page2_image_prompt_mode = mode
    subject = ""
    if mode in ["first_person", "closeup"]:
        subject = st.text_input("主体", value=st.session_state.page2_image_prompt_subject)
        st.session_state.page2_image_prompt_subject = subject

    if st.button("从最近助手回复生成图片 prompt", use_container_width=True, disabled=not latest):
        with st.spinner("正在生成图片 prompt..."):
            try:
                prompt = page2_service.generate_image_prompt(latest, mode=mode, subject=subject)
                st.session_state.page2_image_prompt = prompt
                st.success("图片 prompt 已生成")
            except Exception as exc:
                st.error(str(exc))

    prompt_text = st.text_area("图片 prompt（可编辑）", value=st.session_state.page2_image_prompt, height=160)
    st.session_state.page2_image_prompt = prompt_text

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
                st.session_state.page2_generated_media = media + [record]
                _upsert_record()
                st.success("图片已生成并保存到记录")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("图生视频")
    st.caption("从上面的媒体列表里选择一张图片作为输入。")

    image_candidates = [m for m in media if (m.media_kind.value if hasattr(m.media_kind, "value") else str(m.media_kind)) == GeneratedMediaKind.IMAGE.value]
    if not image_candidates:
        st.caption("暂无可用图片。")
        return

    candidate_labels = []
    label_to_id = {}
    for item in image_candidates:
        label = f"{item.provider} • {str(item.created_at or '')} • {item.prompt[:24] if item.prompt else ''}"
        candidate_labels.append(label)
        label_to_id[label] = item.id

    selected_label = st.selectbox("选择输入图片", options=candidate_labels)
    source_id = label_to_id.get(selected_label, "")
    source = None
    for item in image_candidates:
        if item.id == source_id:
            source = item
            break
    if source is None:
        return

    video_prompt = st.text_input("视频 prompt", value="")
    seconds = st.number_input("时长（秒）", min_value=1, max_value=10, value=5)

    if st.button("生成视频", use_container_width=True):
        ctx = page2_service.load_context_from_settings()
        with st.spinner("正在生成视频（可能需要较长时间）..."):
            try:
                video_record = page2_service.generate_video_from_image(
                    ctx=ctx,
                    source_record=source,
                    prompt=video_prompt,
                    seconds=int(seconds),
                )
                st.session_state.page2_generated_media = media + [video_record]
                _upsert_record()
                st.success("视频已生成并保存到记录")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("URL 收藏")

    url_state = stored_urls.load_state(hidden_space=bool(st.session_state.page2_url_hidden_space))
    st.session_state.page2_url_hidden_space = url_state.hidden_space

    url_input = st.text_input("新增 URL 或输入口令解锁隐藏空间", value="")
    add_col1, add_col2 = st.columns([1, 1])
    with add_col1:
        if st.button("新增", use_container_width=True):
            try:
                url_state = stored_urls.add_url(url_state, url_input)
                st.session_state.page2_url_hidden_space = url_state.hidden_space
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
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
                    st.error(str(exc))

    visible = stored_urls.visible_records(url_state)
    if visible:
        url_labels = []
        url_by_label = {}
        for r in visible:
            prefix = "隐藏：" if r in url_state.hidden_records else ""
            label = f"{prefix}{r.title}: {r.url}"
            url_labels.append(label)
            url_by_label[label] = r
        chosen = st.selectbox("收藏列表", options=url_labels)
        r = url_by_label.get(chosen)
        if r is not None:
            st.text_input("选中 URL（可复制）", value=r.url)
            if st.button("删除选中 URL", use_container_width=True):
                stored_urls.delete_url(url_state, r.id)
                st.success("已删除")
                st.rerun()
    else:
        st.caption("暂无收藏。")


def render():
    _ensure_state()
    _load_record_from_nav_if_needed()
    st.markdown(
        """
<style>
/* Page2: move content to top (remove Streamlit's default top padding) */
section[data-testid="stMain"] .block-container {
  padding-top: 16px !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    _render_sidebar_context()

    left, right = st.columns([1, 1])
    with left:
        _render_chat_column()
    with right:
        _render_media_column()
