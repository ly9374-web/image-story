from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Optional

from app.api.chat_clients import GrokAPIClient, DeepSeekAPIClient
from app.api.media_clients import (
    CloudinaryUploader,
    DomoAIClient,
    GrokImageAPIClient,
    ReplicateImageAPIClient,
    ZhipuVideoClient,
    download_url_as_base64,
    try_download_url_as_base64,
)
from app.config import AppStorageKeys, settings
from app.models import (
    ChatRecord,
    GeneratedImageRecord,
    GeneratedMediaKind,
    Page2ConversationTurn,
    now_iso,
)
from app.storage import ChatRecordStore
from story_brain import (
    build_memory_pack,
    extract_story_brain_update_prompt,
    memory_pack_to_json,
    normalize_story_brain,
)


DEFAULT_SYSTEM_PROMPT = ""

STORY_BRAIN_SYSTEM_RULES = """
你回复中的人物和故事必须严格遵守 Story Brain Memory Pack 中的长期记忆。

规则：
1. active_characters 中的 speech_style 会决定角色说话方式。
2. active_characters 中的 behavior_style 会决定角色行动方式。
3. active_characters 中的 status 表示角色当前身体状态、受伤情况和姿势，生成时必须保持连续，不得忽略或随意恢复。
4. active_characters 中的 goal 和 secret 会影响角色动机，但 secret 不一定能被其他角色知道。
5. relationship 描述角色之间的当前关系，不能写出与之矛盾的互动。
6. generation_constraints 是硬性限制，必须遵守。
7. 当trigger在回复中出现时，让伏笔的content影响情节。
8. trigger未在回复中出现，不得提到、解释、揭露、使用该伏笔，也不得让该伏笔影响情节。
9. 伏笔一旦在正文中被明确提到、解释、揭露、使用或影响情节，就视为已触发。
10. 不要让角色 OOC。
11. 不要在respond中解释你使用了哪些记忆。
12. 不要输出分析过程。
13. 不要输出 JSON。
14. 只输出正文。
""".strip()

STORY_BRAIN_UPDATE_SYSTEM_PROMPT = """
你是 Story Brain 更新建议生成器。
你只能输出严格合法 JSON，不要输出 Markdown，不要输出代码块，不要输出解释文字。
JSON 顶层必须包含 suggested_updates 数组。
""".strip()


def _latest_assistant_message(turns: Iterable[Page2ConversationTurn]) -> str:
    for turn in reversed(list(turns)):
        if turn.assistant_message:
            return str(turn.assistant_message or "")
    return ""


def _story_brain_memory_source_text(previous_assistant_text: str, user_message: str) -> str:
    parts = [
        str(previous_assistant_text or "").strip(),
        str(user_message or "").strip(),
    ]
    return "\n\n".join(part for part in parts if part)


def _build_story_brain_memory_pack_json(
    *,
    memory_source_text: str,
    story_brain: dict,
) -> str:
    memory_pack = build_memory_pack(
        current_text=str(memory_source_text or "").strip(),
        story_brain=normalize_story_brain(story_brain),
    )
    return memory_pack_to_json(memory_pack, max_chars=1500)


def _inject_story_brain_into_prompt(
    system_prompt: str,
    user_message: str,
    *,
    memory_source_text: str,
    story_brain: dict,
) -> tuple[str, str]:
    memory_pack_json = _build_story_brain_memory_pack_json(
        memory_source_text=memory_source_text,
        story_brain=story_brain,
    )
    current_text = str(user_message or "").strip()
    base_system_prompt = str(system_prompt or "").strip()
    enhanced_system_prompt = (
        base_system_prompt + "\n\n" + STORY_BRAIN_SYSTEM_RULES
        if base_system_prompt
        else STORY_BRAIN_SYSTEM_RULES
    )
    enhanced_user_message = f"""
以下是本轮必须参考的 Story Brain Memory Pack，内容已压缩，只包含本轮最相关记忆：

{memory_pack_json}

以下是当前用户输入：

{current_text}

请基于以上内容续写下一段小说。

要求：
- 保持人物一致性
- 保持关系连续性
- 保持主线推进
- 伏笔 trigger 未明确发生时，不触发、不提到、不解释、不让伏笔影响情节
- 遵守所有constraints中的限制
""".strip()
    return enhanced_system_prompt, enhanced_user_message


def _parse_story_brain_suggested_updates(raw_text: str) -> dict:
    try:
        data = json.loads(str(raw_text or "").strip())
    except json.JSONDecodeError as exc:
        raise ValueError("Story Brain 更新建议不是合法 JSON：" + str(exc)) from exc

    if not isinstance(data, dict):
        raise ValueError("Story Brain 更新建议 JSON 顶层必须是对象。")

    suggested_updates = data.get("suggested_updates")
    if not isinstance(suggested_updates, list):
        raise ValueError("Story Brain 更新建议 JSON 必须包含 suggested_updates 数组。")

    return {"suggested_updates": suggested_updates}


def generate_story_brain_update_suggestions(
    *,
    ctx: Page2Context,
    current_text: str,
    model_reply: str,
    story_brain: dict,
) -> dict:
    update_prompt = extract_story_brain_update_prompt(
        current_text=current_text,
        model_reply=model_reply,
        story_brain=story_brain,
    )

    if ctx.story_brain_update_model == "grok":
        raw_text = GrokAPIClient.send_message(
            system_prompt=STORY_BRAIN_UPDATE_SYSTEM_PROMPT,
            context_messages=[],
            user_message=update_prompt,
            model="grok-4.3",
            temperature=ctx.temperature,
        )
    else:
        raw_text = DeepSeekAPIClient.send_message(
            system_prompt=STORY_BRAIN_UPDATE_SYSTEM_PROMPT,
            context_messages=[],
            user_message=update_prompt,
            temperature=ctx.temperature,
        )

    return _parse_story_brain_suggested_updates(raw_text)


@dataclass
class Page2Context:
    system_prompt: str
    context_turn_count: int
    selected_chat_model: str
    story_brain_update_model: str
    temperature: float
    selected_video_generation_provider: str


def load_context_from_settings() -> Page2Context:
    return Page2Context(
        system_prompt=str(settings.get(AppStorageKeys.SYSTEM_PROMPT, "") or "").strip()
        or DEFAULT_SYSTEM_PROMPT,
        context_turn_count=max(0, settings.int(AppStorageKeys.PAGE2_CONTEXT_TURN_COUNT, 8)),
        selected_chat_model=str(
            settings.get(AppStorageKeys.PAGE2_SELECTED_CHAT_MODEL, "grok1") or "grok1"
        ),
        story_brain_update_model=str(
            settings.get(AppStorageKeys.PAGE2_STORY_BRAIN_UPDATE_MODEL, "deepseek")
            or "deepseek"
        ),
        temperature=float(settings.float(AppStorageKeys.PAGE2_TEMPERATURE, 0.8)),
        selected_video_generation_provider=str(
            settings.get(AppStorageKeys.PAGE2_SELECTED_VIDEO_GENERATION_PROVIDER, "domoai")
            or "domoai"
        ),
    )


def save_context_to_settings(ctx: Page2Context):
    settings.set(AppStorageKeys.SYSTEM_PROMPT, str(ctx.system_prompt or "").strip())
    settings.set(AppStorageKeys.PAGE2_CONTEXT_TURN_COUNT, int(max(0, ctx.context_turn_count)))
    settings.set(AppStorageKeys.PAGE2_SELECTED_CHAT_MODEL, str(ctx.selected_chat_model or "grok1"))
    settings.set(
        AppStorageKeys.PAGE2_STORY_BRAIN_UPDATE_MODEL,
        str(ctx.story_brain_update_model or "deepseek"),
    )
    settings.set(AppStorageKeys.PAGE2_TEMPERATURE, float(ctx.temperature))
    settings.set(
        AppStorageKeys.PAGE2_SELECTED_VIDEO_GENERATION_PROVIDER,
        str(ctx.selected_video_generation_provider or "domoai"),
    )


def build_context_messages(
    turns: Iterable[Page2ConversationTurn],
    context_turn_count: int,
) -> list[dict]:
    turns_list = list(turns)
    slice_turns = turns_list[-max(0, int(context_turn_count)) :]
    messages: list[dict] = []

    for turn in slice_turns:
        messages.append({"role": "user", "content": turn.user_message})
        if turn.assistant_message:
            messages.append({"role": "assistant", "content": turn.assistant_message})

    return messages


def send_message(
    *,
    ctx: Page2Context,
    turns: list[Page2ConversationTurn],
    user_message: str,
    story_brain: dict,
    story_brain_enabled: bool = True,
) -> str:
    context_messages = build_context_messages(turns, ctx.context_turn_count)
    system_prompt = ctx.system_prompt
    user_message_for_model = user_message

    if story_brain_enabled:
        memory_source_text = _story_brain_memory_source_text(
            _latest_assistant_message(turns),
            user_message,
        )
        system_prompt, user_message_for_model = _inject_story_brain_into_prompt(
            ctx.system_prompt,
            user_message,
            memory_source_text=memory_source_text,
            story_brain=story_brain,
        )

    if ctx.selected_chat_model == "deepseek":
        return DeepSeekAPIClient.send_message(
            system_prompt=system_prompt,
            context_messages=context_messages,
            user_message=user_message_for_model,
            temperature=ctx.temperature,
        )

    if ctx.selected_chat_model == "grok2":
        return GrokAPIClient.send_message(
            system_prompt=system_prompt,
            context_messages=context_messages,
            user_message=user_message_for_model,
            model="grok-4.3",
            temperature=ctx.temperature,
        )

    return GrokAPIClient.send_message(
        system_prompt=system_prompt,
        context_messages=context_messages,
        user_message=user_message_for_model,
        model="grok-4.3",
        temperature=ctx.temperature,
    )


def generate_image_prompt(latest_assistant_message: str, mode: str = "normal", subject: str = "") -> str:
    latest_assistant_message = str(latest_assistant_message or "").strip()
    if not latest_assistant_message:
        raise ValueError("暂无助手回复内容。")

    mode = str(mode or "normal").strip()
    subject = str(subject or "").strip()

    if mode == "first_person":
        if not subject:
            raise ValueError("主体不能为空。")
        return GrokAPIClient.generate_first_person_image_prompt(latest_assistant_message, subject)

    if mode == "closeup":
        if not subject:
            raise ValueError("主体不能为空。")
        return GrokAPIClient.generate_character_closeup_image_prompt(latest_assistant_message, subject)

    return GrokAPIClient.generate_image_prompt(latest_assistant_message)


def generate_image(provider: str, prompt: str, image_urls: Optional[list[str]] = None) -> GeneratedImageRecord:
    provider = str(provider or "").strip()
    prompt = str(prompt or "").strip()
    image_urls = image_urls or []
    image_urls = [str(url).strip() for url in image_urls if str(url).strip()]

    if not prompt:
        raise ValueError("你得先点“生成图片prompt”生成prompt才能点这个生图")

    if provider in ["grok", "grokQuality", "grokPro"]:
        model = {
            "grok": "grok-imagine-image",
            "grokQuality": "grok-imagine-image-quality",
            "grokPro": "grok-imagine-image",
        }.get(provider, "grok-imagine-image")

        result = GrokImageAPIClient.generate_image(
            prompt=prompt,
            image_urls=image_urls,
            model=model,
        )
    else:
        result = ReplicateImageAPIClient.generate_image(
            provider=provider,
            prompt=prompt,
            image_urls=image_urls,
        )

    image_url = getattr(result, "image_url", None)
    image_base64 = getattr(result, "image_data_base64", None)

    if image_url and not image_base64:
        image_base64 = try_download_url_as_base64(image_url)

    return GeneratedImageRecord(
        provider=provider,
        prompt=prompt,
        media_kind=GeneratedMediaKind.IMAGE,
        image_url_string=image_url,
        image_data_base64=image_base64,
        image_input_urls=image_urls,
        video_url_string=None,
        source_image_url_string=None,
        source_image_data_base64=None,
        duration_seconds=None,
        video_generation_provider=None,
    )


def _decode_image_base64(image_base64: str) -> bytes:
    text = str(image_base64 or "").strip()

    if "," in text and text.lower().startswith("data:"):
        text = text.split(",", 1)[1].strip()

    try:
        image_bytes = base64.b64decode(text, validate=True)
    except binascii.Error:
        image_bytes = base64.b64decode(text)

    if not image_bytes:
        raise ValueError("图片 base64 数据为空。")

    return image_bytes


def _prepare_zhipu_cloudinary_image_url(source_record: GeneratedImageRecord) -> str:
    if source_record.image_data_base64:
        try:
            image_bytes = _decode_image_base64(source_record.image_data_base64)
        except Exception as exc:
            raise RuntimeError("解析输入图片 base64 失败，无法上传到 Cloudinary。原始错误：" + str(exc))
    elif source_record.image_url_string:
        try:
            image_base64 = download_url_as_base64(source_record.image_url_string)
            image_bytes = _decode_image_base64(image_base64)
        except Exception as exc:
            raise RuntimeError(
                "输入图片 URL 已无法访问或无法下载，无法上传到 Cloudinary。"
                "请重新生成图片，或使用仍可访问的图片作为输入。原始错误："
                + str(exc)
            )
    else:
        raise RuntimeError("智谱图生视频需要可用的图片 URL 或 base64 图片数据。")

    try:
        return CloudinaryUploader.upload_image_bytes(image_bytes)
    except Exception as exc:
        raise RuntimeError(
            "上传图片到 Cloudinary 失败，无法生成智谱视频。"
            "请确认 Cloudinary API Key 已在 APIkey 页面或 Streamlit Secrets 配置，"
            "并确认 Cloudinary API Secret 已在 APIkey 页面或 Streamlit Secrets 配置。原始错误："
            + str(exc)
        )


def generate_video_from_image(
    *,
    ctx: Page2Context,
    source_record: GeneratedImageRecord,
    prompt: str,
    seconds: int,
) -> GeneratedImageRecord:
    prompt = str(prompt or "").strip()
    if not prompt:
        prompt = "动起来"

    provider = str(ctx.selected_video_generation_provider or "domoai").strip()

    if provider == "zhipu":
        image_reference = _prepare_zhipu_cloudinary_image_url(source_record)
        task_id = ZhipuVideoClient.create_image_to_video_task(
            image_reference,
            prompt,
            seconds,
        )
        video_url = ZhipuVideoClient.poll_video_url(task_id)
    else:
        if source_record.image_data_base64:
            image_base64 = source_record.image_data_base64
        elif source_record.image_url_string:
            try:
                image_base64 = download_url_as_base64(source_record.image_url_string)
            except Exception as exc:
                raise RuntimeError(
                    "输入图片 URL 已无法访问，图生视频需要原图数据。"
                    "请重新生成图片，或使用仍可访问的图片作为输入。原始错误："
                    + str(exc)
                )
        else:
            raise RuntimeError("当前记录没有可用图片。")

        task_id = DomoAIClient.create_image_to_video_task_with_base64(
            image_base64,
            prompt,
            seconds,
        )
        video_url = DomoAIClient.poll_task_until_video_url(task_id)

    return GeneratedImageRecord(
        provider=source_record.provider,
        prompt=prompt,
        media_kind=GeneratedMediaKind.VIDEO,
        image_url_string=None,
        image_data_base64=None,
        image_input_urls=[],
        video_url_string=video_url,
        source_image_url_string=source_record.image_url_string,
        source_image_data_base64=source_record.image_data_base64,
        duration_seconds=int(seconds),
        video_generation_provider=provider,
    )


def ensure_record_id(existing: Optional[str]) -> str:
    existing = str(existing or "").strip()
    return existing or str(uuid.uuid4())


def make_record_title(turns: list[Page2ConversationTurn]) -> str:
    for turn in turns:
        text = str(turn.user_message or "").strip()
        if text:
            return text[:24]
    return "聊天记录"


def upsert_chat_record(
    *,
    record_id: Optional[str],
    turns: list[Page2ConversationTurn],
    generated_media: list[GeneratedImageRecord],
    system_prompt: str,
    story_brain: dict,
    scope: str | None = None,
) -> str:
    normalized_story_brain = normalize_story_brain(story_brain)
    has_story_brain = any(normalized_story_brain.get(key) for key in ("characters", "relationships", "events"))
    if not turns and not generated_media and not has_story_brain:
        return str(record_id or "").strip()

    now = now_iso()
    record_id = ensure_record_id(record_id)

    existing_title = None
    existing_created_at = None
    for item in ChatRecordStore.load_index(scope=scope):
        if item.id == record_id:
            existing_title = item.title
            existing_created_at = item.created_at
            break

    record = ChatRecord(
        id=record_id,
        title=existing_title or make_record_title(turns),
        turns=turns,
        system_prompt=system_prompt,
        generated_images=generated_media,
        story_brain=normalized_story_brain,
        created_at=existing_created_at or now,
        updated_at=now,
    )
    ChatRecordStore.save_or_update_record(record, scope=scope)
    return record_id
