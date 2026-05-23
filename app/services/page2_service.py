from __future__ import annotations

import base64
import binascii
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


DEFAULT_SYSTEM_PROMPT = ""


@dataclass
class Page2Context:
    system_prompt: str
    context_turn_count: int
    selected_chat_model: str
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
) -> str:
    context_messages = build_context_messages(turns, ctx.context_turn_count)

    if ctx.selected_chat_model == "deepseek":
        return DeepSeekAPIClient.send_message(
            system_prompt=ctx.system_prompt,
            context_messages=context_messages,
            user_message=user_message,
            temperature=ctx.temperature,
        )

    if ctx.selected_chat_model == "grok2":
        return GrokAPIClient.send_message(
            system_prompt=ctx.system_prompt,
            context_messages=context_messages,
            user_message=user_message,
            model="grok-4.20-0309-non-reasoning",
            temperature=ctx.temperature,
        )

    return GrokAPIClient.send_message(
        system_prompt=ctx.system_prompt,
        context_messages=context_messages,
        user_message=user_message,
        model="grok-4-1-fast-reasoning",
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
        raise ValueError("图片描述不能为空。")

    if provider in ["grok", "grokQuality", "grokPro"]:
        model = {
            "grok": "grok-imagine-image",
            "grokQuality": "grok-2-image",
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
            "请确认 CLOUDINARY_CLOUD_NAME、CLOUDINARY_API_KEY、CLOUDINARY_API_SECRET 已配置。原始错误："
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
        raise ValueError("视频 prompt 不能为空。")

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
    scope: str | None = None,
) -> str:
    if not turns and not generated_media:
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
        created_at=existing_created_at or now,
        updated_at=now,
    )
    ChatRecordStore.save_or_update_record(record, scope=scope)
    return record_id
