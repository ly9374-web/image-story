import base64
import threading
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import filedialog, messagebox, simpledialog

from app.api.chat_clients import GrokAPIClient, DeepSeekAPIClient
from app.api.media_clients import (
    GrokImageAPIClient,
    ReplicateImageAPIClient,
    DomoAIClient,
    ZhipuVideoClient,
    CloudinaryUploader,
    download_url_as_base64,
)
from app.config import AppStorageKeys, settings
from app.models import (
    ChatRecord,
    GeneratedImageRecord,
    GeneratedMediaKind,
    Page2ConversationTurn,
    StoredImageURLRecord,
    now_iso,
)
from app.storage import ChatRecordStore
from app.ui.components import (
    PageWithCustomTopBar,
    make_button,
    make_dark_button,
    make_danger_button,
)


DEFAULT_SYSTEM_PROMPT = "你是一个有帮助的 AI 助手。"


class Page2SplitView(PageWithCustomTopBar):
    """
    对应 Swift 里的 Page2SplitView。

    这个页面负责：
    1. 左侧聊天
    2. 右侧图片 / 视频展示
    3. 聊天记录保存
    4. 图片 prompt 生成
    5. 图片生成
    6. 图生视频
    7. URL 收藏
    8. 上下文设置
    """

    def __init__(self, master, app, initial_record=None):
        super().__init__(master, app)

        self.initial_record = initial_record

        self.current_chat_record_id = None
        self.conversation_turns = []
        self.generated_image_records = []
        self.selected_generated_image_index = 0

        self.system_prompt = settings.get(AppStorageKeys.SYSTEM_PROMPT, "") or DEFAULT_SYSTEM_PROMPT

        self.is_sending = False
        self.is_generating_image_prompt = False
        self.is_generating_image = False
        self.is_generating_video = False
        self.is_uploading_cloudinary = False

        self.current_generated_image_prompt = ""
        self.last_failed_image_prompt = ""
        self.image_generation_error_message = ""

        self.stored_image_url_records = []
        self.hidden_stored_image_url_records = []
        self.is_hidden_url_space = False

        self.restore_from_initial_record()
        self.build_page()
        self.apply_selected_generated_image_to_display()

    # =========================
    # 初始化 / 页面结构
    # =========================

    def restore_from_initial_record(self):
        if self.initial_record is None:
            return

        self.current_chat_record_id = self.initial_record.id
        self.conversation_turns = list(self.initial_record.turns or [])
        self.generated_image_records = list(self.initial_record.generated_images or [])

        restored_prompt = str(self.initial_record.system_prompt or "").strip()
        if restored_prompt:
            self.system_prompt = restored_prompt

        self.selected_generated_image_index = max(
            0,
            len(self.generated_image_records) - 1,
        )

        for turn in self.conversation_turns:
            turn.is_loading = False

    def build_page(self):
        root = tk.Frame(
            self.body,
            bg=COLOR_PAGE_BG,
        )
        root.pack(
            fill=tk.BOTH,
            expand=True,
            padx=24,
            pady=22,
        )
        root.grid_columnconfigure(0, weight=1, uniform="page2_columns")
        root.grid_columnconfigure(1, weight=1, uniform="page2_columns")
        root.grid_rowconfigure(0, weight=1)

        self.left = Page2LeftCanvas(root, self)
        self.left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 14),
        )

        self.right = Page2RightBlankArea(root, self)
        self.right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(14, 0),
        )

    # =========================
    # 设置项
    # =========================

    @property
    def context_turn_count(self):
        return max(
            0,
            settings.int(AppStorageKeys.PAGE2_CONTEXT_TURN_COUNT, 8),
        )

    @property
    def selected_chat_model(self):
        return settings.get(
            AppStorageKeys.PAGE2_SELECTED_CHAT_MODEL,
            "grok1",
        ) or "grok1"

    @property
    def temperature(self):
        return settings.float(
            AppStorageKeys.PAGE2_TEMPERATURE,
            0.8,
        )

    @property
    def selected_video_generation_provider(self):
        return settings.get(
            AppStorageKeys.PAGE2_SELECTED_VIDEO_GENERATION_PROVIDER,
            "domoai",
        ) or "domoai"

    # =========================
    # 聊天逻辑
    # =========================

    def build_context_messages(self):
        turns = self.conversation_turns[-self.context_turn_count:]
        messages = []

        for turn in turns:
            messages.append(
                {
                    "role": "user",
                    "content": turn.user_message,
                }
            )

            if turn.assistant_message:
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.assistant_message,
                    }
                )

        return messages

    def send_current_message(self):
        text = self.left.input.get("1.0", tk.END).strip()

        if not text:
            return

        if self.is_sending:
            return

        turn = Page2ConversationTurn(
            user_message=text,
            assistant_message=None,
            is_loading=True,
        )

        self.conversation_turns.append(turn)
        self.left.input.delete("1.0", tk.END)

        self.is_sending = True
        self.left.refresh()
        self.upsert_current_chat_record()

        def work():
            try:
                model = self.selected_chat_model
                context_messages = self.build_context_messages()
                temperature = self.temperature

                if model == "deepseek":
                    reply = DeepSeekAPIClient.send_message(
                        system_prompt=self.system_prompt,
                        context_messages=context_messages,
                        user_message=text,
                        temperature=temperature,
                    )
                elif model == "grok2":
                    reply = GrokAPIClient.send_message(
                        system_prompt=self.system_prompt,
                        context_messages=context_messages,
                        user_message=text,
                        model="grok-4.20-0309-non-reasoning",
                        temperature=temperature,
                    )
                else:
                    reply = GrokAPIClient.send_message(
                        system_prompt=self.system_prompt,
                        context_messages=context_messages,
                        user_message=text,
                        model="grok-4-1-fast-reasoning",
                        temperature=temperature,
                    )

            except Exception as exc:
                reply = "请求失败，请稍后重试。\n" + str(exc)

            self.after(0, lambda: self.finish_reply(turn.id, reply))

        threading.Thread(target=work, daemon=True).start()

    def finish_reply(self, turn_id, reply):
        for turn in self.conversation_turns:
            if turn.id == turn_id:
                turn.assistant_message = reply
                turn.is_loading = False
                break

        self.is_sending = False
        self.left.refresh()
        self.upsert_current_chat_record()

    def rollback_last_turn(self):
        if self.is_sending:
            return

        if not self.conversation_turns:
            return

        self.conversation_turns.pop()
        self.left.refresh()
        self.upsert_current_chat_record()

    def edit_turn(self, turn_id, target):
        for turn in self.conversation_turns:
            if turn.id != turn_id:
                continue

            if target == "user":
                original = turn.user_message
                edited = text_prompt(self, "编辑用户消息", original)
                if edited is not None:
                    turn.user_message = edited.strip()
            else:
                original = turn.assistant_message or ""
                edited = text_prompt(self, "编辑助手消息", original)
                if edited is not None:
                    turn.assistant_message = edited.strip()

            self.left.refresh()
            self.upsert_current_chat_record()
            return

    # =========================
    # 图片 prompt 生成
    # =========================

    def latest_assistant_message(self):
        for turn in reversed(self.conversation_turns):
            if turn.assistant_message:
                return turn.assistant_message
        return ""

    def can_generate_image_prompt(self):
        return bool(self.latest_assistant_message()) and not self.is_generating_image_prompt

    def generate_image_prompt_from_latest_assistant_message(self, mode="normal"):
        latest = self.latest_assistant_message()

        if not latest:
            messagebox.showwarning("暂无内容", "请先生成一条助手回复。")
            return

        subject = ""

        if mode in ["first_person", "closeup"]:
            subject = simpledialog.askstring(
                "主体",
                "请输入主体：",
                parent=self,
            )

            if not subject:
                return

        self.is_generating_image_prompt = True
        self.right.set_status("正在生成图片 prompt...")

        def work():
            try:
                if mode == "first_person":
                    prompt = GrokAPIClient.generate_first_person_image_prompt(
                        latest,
                        subject,
                    )
                elif mode == "closeup":
                    prompt = GrokAPIClient.generate_character_closeup_image_prompt(
                        latest,
                        subject,
                    )
                else:
                    prompt = GrokAPIClient.generate_image_prompt(latest)

                self.after(0, lambda: self.finish_generated_image_prompt(prompt))

            except Exception as exc:
                self.after(
                    0,
                    lambda: self.fail_generated_image_prompt(str(exc)),
                )

        threading.Thread(target=work, daemon=True).start()

    def finish_generated_image_prompt(self, prompt):
        self.is_generating_image_prompt = False
        self.current_generated_image_prompt = prompt
        self.right.set_status("图片 prompt 已生成。")
        self.open_image_prompt_sheet(prompt)

    def fail_generated_image_prompt(self, error_message):
        self.is_generating_image_prompt = False
        self.right.set_status("图片 prompt 生成失败：\n" + error_message)

    def open_current_generated_image_prompt(self):
        self.open_image_prompt_sheet(self.current_generated_image_prompt or "")

    def open_image_prompt_sheet(self, prompt=None):
        if prompt is None:
            prompt = self.current_generated_image_prompt or ""

        ImagePromptEditSheet(self, prompt)

    # =========================
    # 图片生成
    # =========================

    def confirm_image_prompt_and_generate(self, prompt, provider, image_urls):
        prompt = str(prompt or "").strip()

        if not prompt:
            messagebox.showwarning("图片描述不能为空", "请输入图片描述。")
            return

        for url in image_urls:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ["http", "https"] or not parsed.netloc:
                messagebox.showwarning("URL 无效", "请输入有效的 http/https 图片 URL。")
                return

        self.current_generated_image_prompt = prompt
        self.is_generating_image = True
        self.right.set_status("正在生成图片...")

        def work():
            try:
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

                self.after(
                    0,
                    lambda: self.append_generated_image_record(
                        provider,
                        prompt,
                        image_urls,
                        result,
                    ),
                )

            except Exception as exc:
                self.after(
                    0,
                    lambda: self.fail_generate_image(prompt, str(exc)),
                )

        threading.Thread(target=work, daemon=True).start()

    def append_generated_image_record(self, provider, prompt, image_urls, result):
        self.is_generating_image = False
        self.image_generation_error_message = ""

        image_url = getattr(result, "image_url", None)
        image_base64 = getattr(result, "image_data_base64", None)

        record = GeneratedImageRecord(
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

        self.generated_image_records.append(record)
        self.selected_generated_image_index = len(self.generated_image_records) - 1

        self.apply_selected_generated_image_to_display()
        self.upsert_current_chat_record()

    def fail_generate_image(self, prompt, error_message):
        self.is_generating_image = False
        self.last_failed_image_prompt = prompt
        self.image_generation_error_message = error_message
        self.right.set_status("图片生成失败：\n" + error_message)

    def retry_generate_image_with_last_prompt(self):
        if not self.last_failed_image_prompt:
            return

        self.open_image_prompt_sheet(self.last_failed_image_prompt)

    # =========================
    # 图片 / 视频展示
    # =========================

    def current_image_record(self):
        if not self.generated_image_records:
            return None

        if self.selected_generated_image_index < 0:
            return None

        if self.selected_generated_image_index >= len(self.generated_image_records):
            return None

        return self.generated_image_records[self.selected_generated_image_index]

    def apply_selected_generated_image_to_display(self):
        record = self.current_image_record()

        if record is None:
            if hasattr(self, "right"):
                self.right.set_status("生成的图片将在这里显示")
            return

        self.current_generated_image_prompt = record.prompt

        media_kind = record.media_kind
        if hasattr(media_kind, "value"):
            media_kind = media_kind.value

        if media_kind == "video" and record.video_url_string:
            self.right.set_url(record.video_url_string, kind="video")
            return

        if record.image_url_string:
            self.right.set_url(record.image_url_string, kind="image")
            return

        if record.image_data_base64:
            self.right.set_base64_image(record.image_data_base64)
            return

        self.right.set_status("当前生成记录没有可显示内容。")

    def show_previous_generated_image(self):
        if self.selected_generated_image_index > 0:
            self.selected_generated_image_index -= 1
            self.apply_selected_generated_image_to_display()

    def show_next_generated_image(self):
        if self.selected_generated_image_index + 1 < len(self.generated_image_records):
            self.selected_generated_image_index += 1
            self.apply_selected_generated_image_to_display()

    def delete_current_generated_image(self):
        if not self.generated_image_records:
            return

        confirm = messagebox.askyesno(
            "删除",
            "确定删除当前图片或视频记录吗？",
            parent=self,
        )

        if not confirm:
            return

        self.generated_image_records.pop(self.selected_generated_image_index)

        self.selected_generated_image_index = max(
            0,
            min(
                self.selected_generated_image_index,
                len(self.generated_image_records) - 1,
            ),
        )

        self.apply_selected_generated_image_to_display()
        self.upsert_current_chat_record()

    def copy_current_video_or_image_url(self):
        record = self.current_image_record()

        if record is None:
            return

        url = record.video_url_string or record.image_url_string or ""

        if not url:
            return

        self.clipboard_clear()
        self.clipboard_append(url)

        self.right.set_footer("已复制 URL")

    # =========================
    # 图生视频
    # =========================

    def generate_video_from_current_image(self):
        record = self.current_image_record()

        if record is None:
            messagebox.showwarning("暂无图片", "请先生成或选择一张图片。")
            return

        VideoGenerationPromptSheet(self, record)

    def start_video_generation(self, source_record, prompt, seconds):
        prompt = str(prompt or "").strip()

        if not prompt:
            messagebox.showwarning("视频 prompt 不能为空", "请输入视频 prompt。")
            return

        provider = self.selected_video_generation_provider

        self.is_generating_video = True
        self.right.set_status("正在生成视频...")

        def work():
            try:
                if provider == "zhipu":
                    if not source_record.image_url_string:
                        raise RuntimeError("智谱图生视频需要 http/https 图片 URL。")

                    task_id = ZhipuVideoClient.create_image_to_video_task(
                        source_record.image_url_string,
                        prompt,
                        seconds,
                    )
                    video_url = ZhipuVideoClient.poll_video_url(task_id)

                else:
                    if source_record.image_data_base64:
                        image_base64 = source_record.image_data_base64
                    elif source_record.image_url_string:
                        image_base64 = download_url_as_base64(source_record.image_url_string)
                    else:
                        raise RuntimeError("当前记录没有可用图片。")

                    task_id = DomoAIClient.create_image_to_video_task_with_base64(
                        image_base64,
                        prompt,
                        seconds,
                    )
                    video_url = DomoAIClient.poll_task_until_video_url(task_id)

                self.after(
                    0,
                    lambda: self.append_video_record(
                        source_record,
                        provider,
                        prompt,
                        seconds,
                        video_url,
                    ),
                )

            except Exception as exc:
                self.after(
                    0,
                    lambda: self.fail_generate_video(str(exc)),
                )

        threading.Thread(target=work, daemon=True).start()

    def append_video_record(self, source_record, provider, prompt, seconds, video_url):
        self.is_generating_video = False

        record = GeneratedImageRecord(
            provider=source_record.provider,
            prompt=prompt,
            media_kind=GeneratedMediaKind.VIDEO,
            image_url_string=None,
            image_data_base64=None,
            image_input_urls=[],
            video_url_string=video_url,
            source_image_url_string=source_record.image_url_string,
            source_image_data_base64=source_record.image_data_base64,
            duration_seconds=seconds,
            video_generation_provider=provider,
        )

        self.generated_image_records.append(record)
        self.selected_generated_image_index = len(self.generated_image_records) - 1

        self.apply_selected_generated_image_to_display()
        self.upsert_current_chat_record()

    def fail_generate_video(self, error_message):
        self.is_generating_video = False
        self.right.set_status("视频生成失败：\n" + error_message)

    # =========================
    # Cloudinary 上传
    # =========================

    def upload_current_displayed_image_to_cloudinary(self):
        path = filedialog.askopenfilename(
            title="选择要上传的图片",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All", "*.*"),
            ],
        )

        if not path:
            return

        self.is_uploading_cloudinary = True
        self.right.set_status("正在上传 Cloudinary...")

        def work():
            try:
                secure_url = CloudinaryUploader.upload_image(path)
                self.after(
                    0,
                    lambda: self.finish_cloudinary_upload(secure_url),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda: self.fail_cloudinary_upload(str(exc)),
                )

        threading.Thread(target=work, daemon=True).start()

    def finish_cloudinary_upload(self, secure_url):
        self.is_uploading_cloudinary = False

        self.clipboard_clear()
        self.clipboard_append(secure_url)

        self.right.set_status("上传成功，URL 已复制：\n" + secure_url)

    def fail_cloudinary_upload(self, error_message):
        self.is_uploading_cloudinary = False
        self.right.set_status("Cloudinary 上传失败：\n" + error_message)

    # =========================
    # URL 收藏
    # =========================

    def open_image_url_store_sheet(self):
        ImageURLStoreSheet(self)

    def preview_stored_image_url(self, url):
        record = GeneratedImageRecord(
            provider="stored-image-url",
            prompt="",
            media_kind=GeneratedMediaKind.IMAGE,
            image_url_string=url,
            image_data_base64=None,
            image_input_urls=[],
            video_url_string=None,
            source_image_url_string=None,
            source_image_data_base64=None,
            duration_seconds=None,
            video_generation_provider=None,
        )

        self.generated_image_records.append(record)
        self.selected_generated_image_index = len(self.generated_image_records) - 1

        self.apply_selected_generated_image_to_display()
        self.upsert_current_chat_record()

    # =========================
    # 上下文设置
    # =========================

    def open_context_settings(self):
        Page2ContextSettingsSheet(self)

    def edit_page2_system_prompt(self):
        edited = text_prompt(
            self,
            "Page2 system prompt",
            self.system_prompt,
        )

        if edited is None:
            return

        self.system_prompt = edited.strip()
        settings.set(AppStorageKeys.SYSTEM_PROMPT, self.system_prompt)
        self.upsert_current_chat_record()

    # =========================
    # 聊天记录保存
    # =========================

    def upsert_current_chat_record(self):
        if not self.conversation_turns and not self.generated_image_records:
            return

        now = now_iso()

        if self.current_chat_record_id:
            existing = None
            for item in ChatRecordStore.load_index():
                if item.id == self.current_chat_record_id:
                    existing = item
                    break

            title = existing.title if existing else "聊天记录"
            created_at = existing.created_at if existing else now

        else:
            self.current_chat_record_id = self.make_record_id()
            title = self.make_record_title()
            created_at = now

        record = ChatRecord(
            id=self.current_chat_record_id,
            title=title,
            turns=self.conversation_turns,
            system_prompt=self.system_prompt,
            generated_images=self.generated_image_records,
            created_at=created_at,
            updated_at=now,
        )

        ChatRecordStore.save_or_update_record(record)

    def make_record_id(self):
        import uuid
        return str(uuid.uuid4())

    def make_record_title(self):
        for turn in self.conversation_turns:
            text = str(turn.user_message or "").strip()
            if text:
                return text[:24]
        return "聊天记录"

# =========================
# Page2 UI: Left + Right
# 直接替换原来的 Page2LeftCanvas 和 Page2RightBlankArea
# =========================

COLOR_PAGE_BG = "#070a12"
COLOR_PANEL_BG = "#101722"
COLOR_PANEL_ALT = "#151e2b"
COLOR_CARD_BG = "#080d15"
COLOR_CARD_USER_BG = "#151026"
COLOR_CARD_BORDER = "#263241"
COLOR_RIGHT_BG = "#0f1722"
COLOR_CANVAS_BG = "#0a111b"
COLOR_DASH = "#3f4d62"
COLOR_TEXT = "#f7f9fc"
COLOR_MUTED = "#9aa6b8"
COLOR_INPUT_BG = "#f6f7fb"
COLOR_PURPLE = "#9b5cff"
COLOR_PURPLE_DARK = "#6424b7"
COLOR_GREEN = "#42c982"
COLOR_BLUE = "#54b5ff"
COLOR_BUTTON_DARK = "#202b3a"
COLOR_OUTLINE = "#344254"
RADIUS_PANEL = 18
RADIUS_CARD = 24
RADIUS_BUTTON = 12


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def _rounded_panel(master, bg, border="#222b38", thickness=1):
    return tk.Frame(
        master,
        bg=bg,
        highlightbackground=border,
        highlightcolor=border,
        highlightthickness=thickness,
        bd=0,
    )


def _hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix_hex(start, end, ratio):
    sr, sg, sb = _hex_to_rgb(start)
    er, eg, eb = _hex_to_rgb(end)
    return _rgb_to_hex(
        (
            int(sr + (er - sr) * ratio),
            int(sg + (eg - sg) * ratio),
            int(sb + (eb - sb) * ratio),
        )
    )


def _rounded_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = min(radius, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedCanvasButton(tk.Canvas):
    def __init__(
        self,
        master,
        text,
        command,
        width=48,
        height=44,
        bg=COLOR_BUTTON_DARK,
        fg=COLOR_TEXT,
        active_bg="#2b384a",
        radius=RADIUS_BUTTON,
        font=("Arial", 14, "bold"),
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            bg=master.cget("bg"),
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.text = text
        self.command = command
        self.button_bg = bg
        self.active_bg = active_bg
        self.fg = fg
        self.radius = radius
        self.font = font
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _event: self._draw(self.active_bg))
        self.bind("<Leave>", lambda _event: self._draw(self.button_bg))
        self._draw(self.button_bg)

    def _draw(self, fill):
        self.delete("all")
        width = int(self.cget("width"))
        height = int(self.cget("height"))
        _rounded_rectangle(
            self,
            1,
            1,
            width - 2,
            height - 2,
            self.radius,
            fill=fill,
            outline=COLOR_OUTLINE,
            width=1,
        )
        self.create_text(
            width / 2,
            height / 2,
            text=self.text,
            fill=self.fg,
            font=self.font,
        )

    def _click(self, _event=None):
        if self.command:
            self.command()


def _style_toplevel(window, title, geometry):
    window.title(title)
    window.geometry(geometry)
    window.configure(bg=COLOR_PANEL_BG)
    window.transient(window.master)


def _make_sheet_label(master, text, size=12, color=COLOR_TEXT):
    return tk.Label(
        master,
        text=text,
        fg=color,
        bg=COLOR_PANEL_BG,
        font=("Arial", size, "bold" if size >= 14 else "normal"),
    )


def _make_sheet_button(master, text, command, kind="secondary", width=None):
    palette = {
        "primary": (COLOR_PURPLE, "#ffffff", COLOR_PURPLE_DARK),
        "success": (COLOR_GREEN, "#06120c", "#6ee7a4"),
        "danger": ("#7a3030", "#ffffff", "#923a3a"),
        "secondary": (COLOR_BUTTON_DARK, "#e5ebf5", "#2b384a"),
    }
    bg, fg, active = palette.get(kind, palette["secondary"])

    return tk.Button(
        master,
        text=text,
        command=command,
        width=width,
        bg=bg,
        fg=fg,
        activebackground=active,
        activeforeground=fg,
        bd=0,
        relief=tk.FLAT,
        padx=14,
        pady=6,
        font=("Arial", 11, "bold"),
        cursor="hand2",
        takefocus=False,
    )


def _draw_gradient_avatar(canvas, x, y, size, colors):
    """
    用两个颜色做径向渐变头像。
    """
    start = colors[0]
    end = colors[-1]
    steps = 18
    for i in range(steps, 0, -1):
        ratio = i / steps
        pad = (1 - ratio) * size / 2
        color = _mix_hex(start, end, 1 - ratio)
        canvas.create_oval(
            x + pad,
            y + pad,
            x + size - pad,
            y + size - pad,
            fill=color,
            outline="",
        )


def _make_icon_button(master, text, command, width=3, bg="#e7e7e7", fg="#222222"):
    return RoundedCanvasButton(
        master,
        text=text,
        command=command,
        width=48 if width <= 4 else width * 12,
        height=38,
        bg=bg,
        fg=fg,
        active_bg="#ffffff" if bg == COLOR_INPUT_BG else _mix_hex(bg, "#ffffff", 0.1),
        radius=11,
        font=("Arial", 14, "bold"),
    )


def _make_footer_button(master, text, command, width=3):
    return RoundedCanvasButton(
        master,
        text=text,
        command=command,
        width=54 if width <= 3 else width * 16,
        height=54,
        bg=COLOR_BUTTON_DARK,
        fg="#d8dbe0",
        active_bg="#303743",
        radius=12,
        font=("Arial", 13, "bold"),
    )


class Page2LeftCanvas(tk.Frame):
    """
    左侧聊天区。
    对齐你截图里的样式：
    - 深色左侧面板
    - 黑色消息卡片
    - 左侧 AI 渐变头像
    - 右侧用户紫色头像
    - 底部白色输入框
    - 图片 / 人物 / 人物特写 / 回退 / 发送按钮
    """

    def __init__(self, master, controller):
        super().__init__(
            master,
            bg=COLOR_PANEL_BG,
            highlightbackground=COLOR_OUTLINE,
            highlightcolor=COLOR_OUTLINE,
            highlightthickness=1,
            bd=0,
        )

        self.controller = controller
        self._cards = []

        chat_shell = tk.Frame(self, bg=COLOR_PANEL_BG)
        chat_shell.pack(
            side=tk.TOP,
            fill=tk.BOTH,
            expand=True,
            padx=22,
            pady=(22, 10),
        )

        self.chat_canvas = tk.Canvas(
            chat_shell,
            bg=COLOR_PANEL_BG,
            bd=0,
            highlightthickness=0,
        )
        self.chat_canvas.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True,
        )

        self.scroll_frame = tk.Frame(
            self.chat_canvas,
            bg=COLOR_PANEL_BG,
        )

        self.chat_window = self.chat_canvas.create_window(
            0,
            0,
            anchor="nw",
            window=self.scroll_frame,
        )

        self.scroll_frame.bind("<Configure>", self._on_scroll_frame_configure)
        self.chat_canvas.bind("<Configure>", self._on_canvas_configure)
        self.chat_canvas.bind_all("<MouseWheel>", self._on_mouse_wheel)

        self._build_input_bar()
        self.refresh()

    # =========================
    # Layout
    # =========================

    def _on_scroll_frame_configure(self, _event=None):
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.chat_canvas.itemconfig(self.chat_window, width=event.width)

        for card in self._cards:
            _safe_call(card.update_wraplength, max(280, event.width - 150))

    def _on_mouse_wheel(self, event):
        try:
            self.chat_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _build_input_bar(self):
        self.input_outer = tk.Canvas(
            self,
            height=138,
            bg=COLOR_PANEL_BG,
            bd=0,
            highlightthickness=0,
        )
        self.input_outer.pack(
            side=tk.BOTTOM,
            fill=tk.X,
            padx=22,
            pady=(0, 22),
        )
        self.input_outer.bind("<Configure>", self._draw_input_shell)

        self.input = tk.Text(
            self.input_outer,
            height=2,
            wrap=tk.WORD,
            bg=COLOR_PANEL_BG,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            bd=0,
            relief=tk.FLAT,
            font=("Arial", 14),
            padx=4,
            pady=4,
        )
        self.input_window = self.input_outer.create_window(
            18,
            20,
            anchor="nw",
            window=self.input,
        )
        self.input.bind("<Return>", self.submit_on_enter)

        bar = tk.Frame(
            self.input_outer,
            bg=COLOR_PANEL_BG,
        )
        self.input_bar_window = self.input_outer.create_window(
            18,
            82,
            anchor="nw",
            window=bar,
        )

        _make_icon_button(
            bar,
            "▧",
            lambda: self.controller.generate_image_prompt_from_latest_assistant_message("normal"),
            width=4,
            bg="#121a25",
            fg="#d7dce5",
        ).pack(side=tk.LEFT, padx=(0, 8))

        _make_icon_button(
            bar,
            "●",
            lambda: self.controller.generate_image_prompt_from_latest_assistant_message("first_person"),
            width=4,
            bg=COLOR_GREEN,
            fg="#ffffff",
        ).pack(side=tk.LEFT, padx=(0, 8))

        RoundedCanvasButton(
            bar,
            text="人物特写",
            command=lambda: self.controller.generate_image_prompt_from_latest_assistant_message("closeup"),
            width=118,
            height=38,
            bg=COLOR_GREEN,
            fg="#ffffff",
            active_bg="#35b875",
            radius=12,
            font=("Arial", 11, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))

        _make_icon_button(
            bar,
            "↩",
            self.controller.rollback_last_turn,
            width=4,
            bg="#121a25",
            fg="#d7dce5",
        ).pack(side=tk.LEFT, padx=(0, 8))

        _make_icon_button(
            bar,
            "↑",
            self.controller.send_current_message,
            width=4,
            bg="#121a25",
            fg="#ffffff",
        ).pack(side=tk.RIGHT)

    def _draw_input_shell(self, _event=None):
        width = self.input_outer.winfo_width()
        if width <= 20:
            return

        self.input_outer.delete("shell")
        _rounded_rectangle(
            self.input_outer,
            1,
            1,
            width - 2,
            136,
            14,
            fill=COLOR_PANEL_BG,
            outline=COLOR_OUTLINE,
            width=1,
            tags="shell",
        )
        self.input_outer.create_line(
            18,
            72,
            width - 18,
            72,
            fill="#2b3544",
            width=1,
            tags="shell",
        )
        self.input_outer.tag_lower("shell")
        self.input_outer.itemconfig(self.input_window, width=max(120, width - 36))
        self.input_outer.itemconfig(self.input_bar_window, width=max(120, width - 36))

    # =========================
    # Events
    # =========================

    def submit_on_enter(self, event):
        # Shift + Enter 换行；Enter 发送
        if event.state & 0x0001:
            return None

        self.controller.send_current_message()
        return "break"

    # =========================
    # Refresh
    # =========================

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        self._cards = []

        for turn in self.controller.conversation_turns:
            self._add_user_card(turn.user_message, turn)

            if turn.is_loading:
                reply = "正在回复..."
            else:
                reply = turn.assistant_message or ""

            if reply:
                self._add_assistant_card(reply, turn)

        self.after(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        self.chat_canvas.update_idletasks()
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
        self.chat_canvas.yview_moveto(1.0)

    def _add_user_card(self, text, turn):
        card = Page2MessageCard(
            self.scroll_frame,
            text=text,
            role="user",
            on_edit=lambda t=turn: self.controller.edit_turn(t.id, "user"),
        )
        card.pack(fill=tk.X, pady=(0, 10))
        self._cards.append(card)

    def _add_assistant_card(self, text, turn):
        card = Page2MessageCard(
            self.scroll_frame,
            text=text,
            role="assistant",
            on_edit=lambda t=turn: self.controller.edit_turn(t.id, "assistant"),
        )
        card.pack(fill=tk.X, pady=(0, 16))
        self._cards.append(card)


class Page2MessageCard(tk.Frame):
    """
    单条消息卡片。
    """

    def __init__(self, master, text, role, on_edit=None):
        super().__init__(
            master,
            bg=COLOR_PANEL_BG,
        )

        self.text = text or ""
        self.role = role
        self.on_edit = on_edit
        self.canvas = None
        self.wraplength = 470

        self._build()

    def _build(self):
        self.canvas = tk.Canvas(
            self,
            height=112,
            bg=COLOR_PANEL_BG,
            bd=0,
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.X, padx=10)
        self.canvas.bind("<Configure>", lambda _event: self._redraw())
        self.canvas.bind("<Double-Button-1>", lambda _event: self.on_edit() if self.on_edit else None)

    def _redraw(self):
        if self.canvas is None:
            return

        self.canvas.delete("all")
        is_user = self.role == "user"
        width = max(320, self.canvas.winfo_width())
        text_width = max(180, width - 150)
        line_count = max(1, int(len(self.text) / max(16, text_width / 13)) + self.text.count("\n"))
        height = max(112, min(260, 74 + line_count * 22))
        self.canvas.config(height=height)

        card_bg = COLOR_CARD_USER_BG if is_user else COLOR_CARD_BG
        border = "#29154d" if is_user else "#1f2b38"
        shadow = "#2b1453" if is_user else "#123830"

        _rounded_rectangle(
            self.canvas,
            1,
            4,
            width - 2,
            height - 8,
            RADIUS_CARD,
            fill=card_bg,
            outline="#05080d",
            width=1,
        )
        _rounded_rectangle(
            self.canvas,
            2,
            2,
            width - 3,
            height - 11,
            RADIUS_CARD,
            fill="",
            outline=border,
            width=1,
        )
        self.canvas.create_line(
            24,
            height - 8,
            width - 24,
            height - 8,
            fill=shadow,
            width=2,
        )

        avatar_size = 56
        avatar_x = width - 74 if is_user else 28
        avatar_y = 22
        _draw_gradient_avatar(
            self.canvas,
            avatar_x,
            avatar_y,
            avatar_size,
            ["#7f3bd7", "#14051f"] if is_user else ["#f3a4ff", "#20d2df"],
        )

        text_x = 38 if is_user else 102
        if is_user:
            text_width = max(120, width - 138)
        else:
            text_width = max(120, width - 130)

        self.canvas.create_text(
            text_x,
            34,
            text=self.text,
            fill=COLOR_TEXT,
            width=text_width,
            justify=tk.LEFT,
            anchor="nw",
            font=("Arial", 14, "bold"),
        )

        if self.on_edit:
            self.canvas.create_text(
                width - 26 if not is_user else 26,
                height - 31,
                text="✎",
                fill=COLOR_MUTED,
                font=("Arial", 11, "bold"),
            )

    def update_wraplength(self, wraplength):
        self.wraplength = wraplength
        self._redraw()


class Page2RightBlankArea(tk.Frame):
    """
    右侧画布区。
    对齐截图里的：
    - 深色大画布
    - 虚线空画布
    - 中间空状态图标
    - 底部设置、URL、上一张、下一张按钮
    """

    def __init__(self, master, controller):
        super().__init__(
            master,
            bg=COLOR_RIGHT_BG,
            highlightbackground="#263141",
            highlightcolor="#263141",
            highlightthickness=1,
            bd=0,
        )

        self.controller = controller
        self.current_url = ""
        self.current_photo = None
        self.current_status = "生成的图像将显示在这里"

        self.canvas_meta = tk.Label(self, text="", bg=COLOR_RIGHT_BG)

        self.display_canvas = tk.Canvas(
            self,
            bg=COLOR_CANVAS_BG,
            bd=0,
            highlightthickness=0,
        )
        self.display_canvas.pack(
            side=tk.TOP,
            fill=tk.BOTH,
            expand=True,
            padx=20,
            pady=(20, 8),
        )
        self.display_canvas.bind("<Configure>", lambda _event: self._redraw())

        top_tools = tk.Frame(self, bg=COLOR_RIGHT_BG)
        top_tools.place(relx=1.0, y=42, x=-58, anchor="ne")

        _make_footer_button(
            top_tools,
            "☁",
            controller.upload_current_displayed_image_to_cloudinary,
        ).pack(side=tk.TOP, pady=(0, 10))

        _make_footer_button(
            top_tools,
            "▣",
            lambda: controller.open_image_prompt_sheet(),
        ).pack(side=tk.TOP, pady=(0, 10))

        _make_footer_button(
            top_tools,
            "⌫",
            controller.delete_current_generated_image,
        ).pack(side=tk.TOP)

        footer = tk.Frame(
            self,
            bg=COLOR_RIGHT_BG,
        )
        footer.pack(
            side=tk.BOTTOM,
            fill=tk.X,
            padx=20,
            pady=(0, 18),
        )

        _make_footer_button(
            footer,
            "⚙",
            controller.open_context_settings,
        ).pack(side=tk.LEFT)

        self.footer_label = tk.Label(
            footer,
            text="",
            fg="#b8beca",
            bg=COLOR_RIGHT_BG,
            font=("Arial", 11),
        )
        self.footer_label.pack(side=tk.LEFT, padx=8)

        _make_footer_button(
            footer,
            "›",
            controller.show_next_generated_image,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        _make_footer_button(
            footer,
            "‹",
            controller.show_previous_generated_image,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        _make_footer_button(
            footer,
            "≡",
            controller.open_image_url_store_sheet,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        _make_footer_button(
            footer,
            "↗",
            controller.copy_current_video_or_image_url,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        _make_footer_button(
            footer,
            "⌘",
            controller.generate_video_from_current_image,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        self._redraw()

    # =========================
    # Public API used by controller
    # =========================

    def set_status(self, text):
        self.current_url = ""
        self.current_photo = None
        self.current_status = text or "生成的图像将显示在这里"
        self.canvas_meta.config(text="等待生成")
        self.display_canvas.unbind("<Button-1>")
        self._redraw()

    def set_footer(self, text):
        self.footer_label.config(text=text or "")
        self.after(
            1200,
            lambda: self.footer_label.config(text=""),
        )

    def set_url(self, url, kind="image"):
        self.current_url = url or ""
        self.current_photo = None

        label = "视频" if kind == "video" else "图片"
        self.current_status = "{} URL：\n{}\n\n点击打开".format(label, self.current_url)
        self.canvas_meta.config(text="{} URL".format(label))

        self.display_canvas.bind(
            "<Button-1>",
            lambda _event: webbrowser.open(self.current_url) if self.current_url else None,
        )

        self._redraw()

    def set_base64_image(self, image_base64):
        """
        显示 base64 图片。
        注意：
        - Tkinter 原生 PhotoImage 通常支持 PNG / GIF。
        - 如果你的 base64 是 JPG/WebP，建议后续接 PIL/Pillow 做转换。
        """
        try:
            clean = str(image_base64 or "").strip()

            if clean.startswith("data:image"):
                clean = clean.split(",", 1)[1]

            # 真正使用 import base64：先校验，再交给 PhotoImage
            base64.b64decode(clean, validate=False)

            self.current_photo = tk.PhotoImage(data=clean)
            self.current_url = ""
            self.current_status = ""
            self.canvas_meta.config(text="本地预览")
            self.display_canvas.unbind("<Button-1>")
            self._redraw()

        except Exception as exc:
            self.current_photo = None
            self.set_status("base64 图片显示失败：\n{}".format(exc))

    # =========================
    # Drawing
    # =========================

    def _redraw(self):
        self.display_canvas.delete("all")

        w = self.display_canvas.winfo_width()
        h = self.display_canvas.winfo_height()

        if w <= 20 or h <= 20:
            return

        pad = 0
        inner_pad = 22

        self.display_canvas.create_rectangle(
            pad,
            pad,
            w - pad,
            h - pad,
            fill=COLOR_CANVAS_BG,
            outline="",
        )

        self.display_canvas.create_rectangle(
            1,
            1,
            w - 2,
            h - 2,
            fill="",
            outline="#1d2a3b",
            width=1,
        )

        self.display_canvas.create_rectangle(
            inner_pad,
            inner_pad,
            w - inner_pad,
            h - inner_pad,
            outline=COLOR_DASH,
            width=1,
            dash=(7, 7),
        )

        _rounded_rectangle(
            self.display_canvas,
            inner_pad,
            inner_pad,
            w - inner_pad,
            h - inner_pad,
            16,
            fill="",
            outline=COLOR_DASH,
            width=1,
        )

        if self.current_photo is not None:
            self._draw_photo(w, h, inner_pad)
            return

        if self.current_url:
            self._draw_url_state(w, h)
            return

        self._draw_empty_state(w, h)

    def _draw_photo(self, w, h, inner_pad):
        img_w = self.current_photo.width()
        img_h = self.current_photo.height()

        max_w = max(100, w - inner_pad * 4)
        max_h = max(100, h - inner_pad * 4)

        # Tkinter PhotoImage 只能整数倍 subsample，做一个基础缩小
        photo = self.current_photo
        scale = max(img_w / max_w, img_h / max_h, 1)

        if scale > 1:
            factor = int(scale) + 1
            photo = self.current_photo.subsample(factor, factor)

        self.display_canvas.create_image(
            w / 2,
            h / 2,
            image=photo,
            anchor="center",
        )

        # 防止局部变量 photo 被 GC
        self._shown_photo = photo

    def _draw_url_state(self, w, h):
        cx = w / 2
        cy = h / 2

        self.display_canvas.create_rectangle(
            cx - 72,
            cy - 110,
            cx + 72,
            cy - 18,
            fill="#111b28",
            outline="#2b3a50",
            width=1,
        )
        self.display_canvas.create_line(
            cx - 42,
            cy - 64,
            cx - 10,
            cy - 64,
            fill=COLOR_BLUE,
            width=3,
        )
        self.display_canvas.create_line(
            cx + 10,
            cy - 64,
            cx + 42,
            cy - 64,
            fill=COLOR_PURPLE,
            width=3,
        )

        self.display_canvas.create_text(
            cx,
            cy + 24,
            text=self.current_status,
            fill="#d6d8dc",
            width=max(260, w - 110),
            justify=tk.CENTER,
            font=("Arial", 14, "bold"),
        )

        self.display_canvas.create_text(
            cx,
            cy + 122,
            text="点击打开",
            fill=COLOR_MUTED,
            font=("Arial", 12),
        )

    def _draw_empty_state(self, w, h):
        cx = w / 2
        cy = h / 2 - 30

        self.display_canvas.create_rectangle(
            cx - 58,
            cy - 44,
            cx + 58,
            cy + 44,
            fill="#111b28",
            outline="#2b3a50",
            width=1,
        )
        self.display_canvas.create_rectangle(
            cx - 34,
            cy - 18,
            cx + 34,
            cy + 24,
            fill="#172335",
            outline="#3f4d62",
            width=1,
        )
        self.display_canvas.create_polygon(
            cx - 31,
            cy + 22,
            cx - 8,
            cy - 2,
            cx + 10,
            cy + 16,
            cx + 24,
            cy + 4,
            cx + 32,
            cy + 22,
            fill="#27384f",
            outline="",
        )
        self.display_canvas.create_oval(
            cx + 16,
            cy - 12,
            cx + 25,
            cy - 3,
            fill=COLOR_GREEN,
            outline="",
        )

        self.display_canvas.create_text(
            cx,
            cy - 62,
            text="IMAGE",
            fill="#526174",
            font=("Arial", 9, "bold"),
        )

        self.display_canvas.create_text(
            cx,
            cy + 70,
            text="画布为空",
            fill="#d6d8dc",
            font=("Arial", 15, "bold"),
        )

        self.display_canvas.create_text(
            cx,
            cy + 98,
            text=self.current_status or "生成的图像将显示在这里",
            fill=COLOR_MUTED,
            width=max(260, w - 130),
            justify=tk.CENTER,
            font=("Arial", 13),
        )

class ImagePromptEditSheet(tk.Toplevel):
    """
    对应 Swift 里的 ImagePromptEditSheet。
    """

    def __init__(self, controller, prompt):
        super().__init__(controller)

        self.controller = controller

        _style_toplevel(self, "确认图片提示词", "760x640")

        _make_sheet_label(
            self,
            text="图片 prompt",
            size=16,
        ).pack(anchor="w", padx=18, pady=(18, 8))

        self.prompt = tk.Text(
            self,
            height=13,
            wrap=tk.WORD,
            bg="#f7f9fc",
            fg="#101319",
            insertbackground="#101319",
            relief=tk.FLAT,
            padx=12,
            pady=12,
            font=("Arial", 14),
        )
        self.prompt.pack(
            fill=tk.BOTH,
            expand=True,
            padx=18,
        )
        self.prompt.insert("1.0", prompt)

        _make_sheet_label(
            self,
            text="参考图 URL（一行一个，可为空）",
            color=COLOR_MUTED,
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.urls = tk.Text(
            self,
            height=5,
            wrap=tk.WORD,
            bg="#f7f9fc",
            fg="#101319",
            insertbackground="#101319",
            relief=tk.FLAT,
            padx=10,
            pady=8,
        )
        self.urls.pack(
            fill=tk.X,
            padx=18,
        )

        bar = tk.Frame(
            self,
            bg=COLOR_PANEL_BG,
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        _make_sheet_button(
            bar,
            text="取消",
            command=self.destroy,
        ).pack(side=tk.LEFT)

        providers = [
            ("Grok", "grok"),
            ("Grok Quality", "grokQuality"),
            ("Grok Pro", "grokPro"),
            ("Flux", "flux"),
            ("Nano Pro", "nanoPro"),
            ("Nano", "nano"),
        ]

        for name, provider in providers:
            _make_sheet_button(
                bar,
                text=name,
                command=lambda p=provider: self.confirm(p),
                kind="primary" if provider == "grok" else "secondary",
            ).pack(side=tk.RIGHT, padx=3)

    def confirm(self, provider):
        prompt = self.prompt.get("1.0", tk.END).strip()

        urls = [
            line.strip()
            for line in self.urls.get("1.0", tk.END).splitlines()
            if line.strip()
        ]

        for url in urls:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ["http", "https"] or not parsed.netloc:
                messagebox.showwarning(
                    "URL 无效",
                    "请输入有效的 http/https 图片 URL。",
                    parent=self,
                )
                return

        self.destroy()
        self.controller.confirm_image_prompt_and_generate(
            prompt,
            provider,
            urls,
        )


class Page2ContextSettingsSheet(tk.Toplevel):
    """
    对应 Swift 里的 Page2ContextSettingsSheet。
    """

    def __init__(self, controller):
        super().__init__(controller)

        self.controller = controller

        _style_toplevel(self, "页面二设置", "480x460")

        _make_sheet_label(
            self,
            text="上下文轮数",
        ).pack(anchor="w", padx=18, pady=(18, 4))

        self.context_entry = tk.Entry(
            self,
            bg="#f7f9fc",
            fg="#101319",
            insertbackground="#101319",
            relief=tk.FLAT,
            font=("Arial", 13),
        )
        self.context_entry.insert(0, str(controller.context_turn_count))
        self.context_entry.pack(fill=tk.X, padx=18)

        _make_sheet_label(
            self,
            text="Temperature",
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.temp_entry = tk.Entry(
            self,
            bg="#f7f9fc",
            fg="#101319",
            insertbackground="#101319",
            relief=tk.FLAT,
            font=("Arial", 13),
        )
        self.temp_entry.insert(0, str(controller.temperature))
        self.temp_entry.pack(fill=tk.X, padx=18)

        _make_sheet_label(
            self,
            text="模型",
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.model_var = tk.StringVar(value=controller.selected_chat_model)

        for title, value in [
            ("grok", "grok1"),
            ("grok2", "grok2"),
            ("deepseek", "deepseek"),
        ]:
            tk.Radiobutton(
                self,
                text=title,
                variable=self.model_var,
                value=value,
                bg=COLOR_PANEL_BG,
                fg=COLOR_TEXT,
                activebackground=COLOR_PANEL_BG,
                activeforeground=COLOR_TEXT,
                selectcolor=COLOR_PANEL_ALT,
            ).pack(anchor="w", padx=18)

        _make_sheet_label(
            self,
            text="视频服务",
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.video_var = tk.StringVar(
            value=controller.selected_video_generation_provider
        )

        for title, value in [
            ("DomoAI", "domoai"),
            ("智谱", "zhipu"),
        ]:
            tk.Radiobutton(
                self,
                text=title,
                variable=self.video_var,
                value=value,
                bg=COLOR_PANEL_BG,
                fg=COLOR_TEXT,
                activebackground=COLOR_PANEL_BG,
                activeforeground=COLOR_TEXT,
                selectcolor=COLOR_PANEL_ALT,
            ).pack(anchor="w", padx=18)

        bar = tk.Frame(
            self,
            bg=COLOR_PANEL_BG,
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        _make_sheet_button(
            bar,
            text="修改 systemprompt",
            command=controller.edit_page2_system_prompt,
        ).pack(side=tk.LEFT)

        _make_sheet_button(
            bar,
            text="取消",
            command=self.destroy,
        ).pack(side=tk.RIGHT)

        _make_sheet_button(
            bar,
            text="保存",
            command=self.save,
            kind="primary",
        ).pack(side=tk.RIGHT, padx=6)

    def save(self):
        try:
            count = max(0, int(self.context_entry.get().strip()))
        except Exception:
            count = 8

        try:
            temperature = float(self.temp_entry.get().strip())
        except Exception:
            temperature = 0.8

        settings.set(AppStorageKeys.PAGE2_CONTEXT_TURN_COUNT, count)
        settings.set(AppStorageKeys.PAGE2_TEMPERATURE, temperature)
        settings.set(AppStorageKeys.PAGE2_SELECTED_CHAT_MODEL, self.model_var.get())
        settings.set(
            AppStorageKeys.PAGE2_SELECTED_VIDEO_GENERATION_PROVIDER,
            self.video_var.get(),
        )

        self.destroy()


class ImageURLStoreSheet(tk.Toplevel):
    """
    对应 Swift 里的 ImageURLStoreSheet。
    用于收藏、预览、复制、删除图片 URL。
    """

    HIDDEN_PASSCODE = "ly123"

    def __init__(self, controller):
        super().__init__(controller)

        self.controller = controller

        _style_toplevel(self, "URL 收藏", "660x600")

        self.records = self.load_records(AppStorageKeys.STORED_IMAGE_URL_RECORDS)
        self.hidden_records = self.load_records(AppStorageKeys.HIDDEN_URL_RECORDS)
        self.hidden_space = False

        self.listbox = tk.Listbox(
            self,
            bg=COLOR_CANVAS_BG,
            fg=COLOR_TEXT,
            selectbackground=COLOR_PURPLE_DARK,
            selectforeground="#ffffff",
            highlightbackground=COLOR_CARD_BORDER,
            highlightcolor=COLOR_CARD_BORDER,
            relief=tk.FLAT,
            font=("Arial", 14),
        )
        self.listbox.pack(
            fill=tk.BOTH,
            expand=True,
            padx=18,
            pady=18,
        )
        self.listbox.bind("<Double-Button-1>", self.preview_selected)

        input_row = tk.Frame(
            self,
            bg=COLOR_PANEL_BG,
        )
        input_row.pack(
            fill=tk.X,
            padx=18,
        )

        self.entry = tk.Entry(
            input_row,
            bg="#f7f9fc",
            fg="#101319",
            insertbackground="#101319",
            relief=tk.FLAT,
            font=("Arial", 13),
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        _make_sheet_button(
            input_row,
            text="新增",
            command=self.add,
            kind="primary",
        ).pack(side=tk.LEFT, padx=6)

        _make_sheet_button(
            input_row,
            text="上传获取 URL",
            command=self.upload,
        ).pack(side=tk.LEFT)

        bar = tk.Frame(
            self,
            bg=COLOR_PANEL_BG,
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        _make_sheet_button(
            bar,
            text="预览",
            command=self.preview_selected,
            kind="primary",
        ).pack(side=tk.LEFT)

        _make_sheet_button(
            bar,
            text="复制",
            command=self.copy_selected,
        ).pack(side=tk.LEFT, padx=6)

        _make_sheet_button(
            bar,
            text="删除",
            command=self.delete_selected,
            kind="danger",
        ).pack(side=tk.LEFT)

        _make_sheet_button(
            bar,
            text="确定",
            command=self.destroy,
        ).pack(side=tk.RIGHT)

        self.refresh()

    def visible_records(self):
        if self.hidden_space:
            return self.records + self.hidden_records
        return self.records

    def refresh(self):
        self.listbox.delete(0, tk.END)

        for record in self.visible_records():
            prefix = "隐藏：" if record in self.hidden_records else ""
            self.listbox.insert(
                tk.END,
                "{}{}: {}".format(prefix, record.title, record.url),
            )

    def selected_record(self):
        selection = self.listbox.curselection()

        if not selection:
            return None

        index = selection[0]
        visible = self.visible_records()

        if index >= len(visible):
            return None

        return visible[index]

    def add(self):
        url = self.entry.get().strip()

        if not url:
            return

        if url == self.HIDDEN_PASSCODE:
            self.hidden_space = True
            self.entry.delete(0, tk.END)
            self.refresh()
            return

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ["http", "https"] or not parsed.netloc:
            messagebox.showwarning(
                "URL 无效",
                "请输入有效的 http/https URL。",
                parent=self,
            )
            return

        if self.hidden_space:
            next_key = AppStorageKeys.HIDDEN_URL_RECORD_NEXT_INDEX
            index = max(1, settings.int(next_key, 1))
            title = "隐藏url{}".format(index)
            settings.set(next_key, index + 1)
        else:
            next_key = AppStorageKeys.STORED_IMAGE_URL_RECORD_NEXT_INDEX
            index = max(1, settings.int(next_key, 1))
            title = "url{}".format(index)
            settings.set(next_key, index + 1)

        record = StoredImageURLRecord(
            title=title,
            url=url,
            created_at=now_iso(),
            updated_at=now_iso(),
        )

        if self.hidden_space:
            self.hidden_records.append(record)
        else:
            self.records.append(record)

        self.entry.delete(0, tk.END)
        self.persist()
        self.refresh()

    def preview_selected(self, _event=None):
        record = self.selected_record()

        if record is None:
            return

        self.controller.preview_stored_image_url(record.url)

    def copy_selected(self):
        record = self.selected_record()

        if record is None:
            return

        self.clipboard_clear()
        self.clipboard_append(record.url)

    def delete_selected(self):
        record = self.selected_record()

        if record is None:
            return

        self.records = [item for item in self.records if item.id != record.id]
        self.hidden_records = [item for item in self.hidden_records if item.id != record.id]

        self.persist()
        self.refresh()

    def upload(self):
        path = filedialog.askopenfilename(
            title="选择图片上传",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All", "*.*"),
            ],
        )

        if not path:
            return

        try:
            secure_url = CloudinaryUploader.upload_image(path)
            self.entry.delete(0, tk.END)
            self.entry.insert(0, secure_url)
            self.clipboard_clear()
            self.clipboard_append(secure_url)
            messagebox.showinfo("上传成功", "URL 已复制：\n" + secure_url, parent=self)
        except Exception as exc:
            messagebox.showerror("上传失败", str(exc), parent=self)

    def persist(self):
        settings.set(
            AppStorageKeys.STORED_IMAGE_URL_RECORDS,
            self.encode_records(self.records),
        )
        settings.set(
            AppStorageKeys.HIDDEN_URL_RECORDS,
            self.encode_records(self.hidden_records),
        )

    def load_records(self, key):
        import json

        raw = settings.get(key, "")

        if not raw:
            return []

        if isinstance(raw, list):
            items = raw
        else:
            try:
                items = json.loads(raw)
            except Exception:
                return []

        records = []

        for item in items:
            if not isinstance(item, dict):
                continue

            records.append(
                StoredImageURLRecord(
                    id=item.get("id"),
                    title=item.get("title", "url"),
                    url=item.get("url", ""),
                    created_at=item.get("created_at") or item.get("createdAt") or now_iso(),
                    updated_at=item.get("updated_at") or item.get("updatedAt") or now_iso(),
                )
            )

        return records

    def encode_records(self, records):
        import json

        payload = []

        for record in records:
            payload.append(
                {
                    "id": record.id,
                    "title": record.title,
                    "url": record.url,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
            )

        return json.dumps(payload, ensure_ascii=False)


class VideoGenerationPromptSheet(tk.Toplevel):
    """
    对应 Swift 里的 VideoGenerationPromptSheet。
    """

    def __init__(self, controller, source_record):
        super().__init__(controller)

        self.controller = controller
        self.source_record = source_record

        _style_toplevel(self, "生成视频", "560x400")

        _make_sheet_label(
            self,
            text="视频 prompt",
            size=15,
        ).pack(anchor="w", padx=18, pady=(18, 8))

        self.prompt = tk.Text(
            self,
            height=8,
            wrap=tk.WORD,
            bg="#f7f9fc",
            fg="#101319",
            insertbackground="#101319",
            relief=tk.FLAT,
            padx=12,
            pady=12,
            font=("Arial", 13),
        )
        self.prompt.pack(
            fill=tk.BOTH,
            expand=True,
            padx=18,
        )

        _make_sheet_label(
            self,
            text="视频时长",
            color=COLOR_MUTED,
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.seconds_var = tk.StringVar(value="5")

        seconds_row = tk.Frame(
            self,
            bg=COLOR_PANEL_BG,
        )
        seconds_row.pack(fill=tk.X, padx=18)

        for value in ["1", "3", "5", "10"]:
            tk.Radiobutton(
                seconds_row,
                text=value + " 秒",
                variable=self.seconds_var,
                value=value,
                bg=COLOR_PANEL_BG,
                fg=COLOR_TEXT,
                activebackground=COLOR_PANEL_BG,
                activeforeground=COLOR_TEXT,
                selectcolor=COLOR_PANEL_ALT,
            ).pack(side=tk.LEFT)

        bar = tk.Frame(
            self,
            bg=COLOR_PANEL_BG,
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        _make_sheet_button(
            bar,
            text="取消",
            command=self.destroy,
        ).pack(side=tk.LEFT)

        _make_sheet_button(
            bar,
            text="生成",
            command=self.confirm,
            kind="primary",
        ).pack(side=tk.RIGHT)

    def confirm(self):
        prompt = self.prompt.get("1.0", tk.END).strip()

        try:
            seconds = int(self.seconds_var.get())
        except Exception:
            seconds = 5

        provider = self.controller.selected_video_generation_provider

        if provider == "zhipu" and seconds not in [5, 10]:
            messagebox.showwarning(
                "时长错误",
                "智谱请选择 5 秒或 10 秒。",
                parent=self,
            )
            return

        if provider == "domoai" and not (1 <= seconds <= 10):
            messagebox.showwarning(
                "时长错误",
                "DomoAI 请选择 1 到 10 秒。",
                parent=self,
            )
            return

        self.destroy()
        self.controller.start_video_generation(
            self.source_record,
            prompt,
            seconds,
        )


def text_prompt(parent, title, initial_text):
    """
    多行文本编辑弹窗。
    用来替代 Swift 的编辑消息 / 编辑 system prompt sheet。
    """

    dialog = tk.Toplevel(parent)
    _style_toplevel(dialog, title, "660x460")

    result = {
        "value": None,
    }

    text = tk.Text(
        dialog,
        wrap=tk.WORD,
        bg="#f7f9fc",
        fg="#101319",
        insertbackground="#101319",
        relief=tk.FLAT,
        padx=12,
        pady=12,
        font=("Arial", 14),
    )
    text.pack(
        fill=tk.BOTH,
        expand=True,
        padx=18,
        pady=18,
    )
    text.insert("1.0", initial_text or "")

    bar = tk.Frame(
        dialog,
        bg=COLOR_PANEL_BG,
    )
    bar.pack(
        fill=tk.X,
        padx=18,
        pady=(0, 18),
    )

    def cancel():
        result["value"] = None
        dialog.destroy()

    def save():
        result["value"] = text.get("1.0", tk.END).strip()
        dialog.destroy()

    _make_sheet_button(
        bar,
        text="取消",
        command=cancel,
    ).pack(side=tk.LEFT)

    _make_sheet_button(
        bar,
        text="保存",
        command=save,
        kind="primary",
    ).pack(side=tk.RIGHT)

    dialog.grab_set()
    parent.wait_window(dialog)

    return result["value"]
