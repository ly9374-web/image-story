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
            bg="#05070d",
        )
        root.pack(
            fill=tk.BOTH,
            expand=True,
            padx=20,
            pady=20,
        )

        self.left = Page2LeftCanvas(root, self)
        self.left.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=False,
            padx=(0, 22),
        )
        self.left.config(width=655)

        self.right = Page2RightBlankArea(root, self)
        self.right.pack(
            side=tk.RIGHT,
            fill=tk.BOTH,
            expand=True,
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
            self.right.set_status("已生成 base64 图片。可继续生成视频或保存记录。")
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


class Page2LeftCanvas(tk.Frame):
    """
    对应 Swift 里的 Page2LeftCanvas。
    左侧：聊天历史 + 输入框 + 图片按钮。
    """

    def __init__(self, master, controller):
        super().__init__(
            master,
            bg="#0b1017",
            highlightbackground="#222b38",
            highlightthickness=1,
        )

        self.controller = controller

        self.messages = tk.Text(
            self,
            wrap=tk.WORD,
            bg="#0b1017",
            fg="white",
            bd=0,
            state=tk.DISABLED,
            font=("Arial", 14),
        )
        self.messages.pack(
            fill=tk.BOTH,
            expand=True,
            padx=16,
            pady=16,
        )

        self.messages.tag_config(
            "user",
            foreground="#ffffff",
            spacing1=8,
            spacing3=8,
        )
        self.messages.tag_config(
            "assistant",
            foreground="#d4fff9",
            spacing1=8,
            spacing3=8,
        )

        input_frame = tk.Frame(
            self,
            bg="#f5f5f5",
        )
        input_frame.pack(
            fill=tk.X,
            padx=18,
            pady=(0, 14),
        )

        self.input = tk.Text(
            input_frame,
            height=3,
            wrap=tk.WORD,
            bg="white",
            fg="black",
            bd=0,
            font=("Arial", 14),
        )
        self.input.pack(
            fill=tk.X,
            padx=10,
            pady=(8, 0),
        )
        self.input.bind("<Return>", self.submit_on_enter)

        bar = tk.Frame(
            input_frame,
            bg="#f5f5f5",
        )
        bar.pack(fill=tk.X)

        tk.Button(
            bar,
            text="🖼",
            command=lambda: controller.generate_image_prompt_from_latest_assistant_message("normal"),
            bd=0,
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            bar,
            text="我",
            command=lambda: controller.generate_image_prompt_from_latest_assistant_message("first_person"),
            bd=0,
        ).pack(side=tk.LEFT)

        tk.Button(
            bar,
            text="人物特写",
            command=lambda: controller.generate_image_prompt_from_latest_assistant_message("closeup"),
            bd=0,
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            bar,
            text="↶",
            command=controller.rollback_last_turn,
            bd=0,
        ).pack(side=tk.LEFT)

        tk.Button(
            bar,
            text="↑",
            command=controller.send_current_message,
            bd=0,
        ).pack(side=tk.RIGHT, padx=12, pady=6)

        self.refresh()

    def submit_on_enter(self, event):
        # Shift + Enter 换行；Enter 发送
        if event.state & 0x0001:
            return None

        self.controller.send_current_message()
        return "break"

    def refresh(self):
        self.messages.config(state=tk.NORMAL)
        self.messages.delete("1.0", tk.END)

        for turn in self.controller.conversation_turns:
            self.messages.insert(
                tk.END,
                "用户：{}\n".format(turn.user_message),
                "user",
            )

            if turn.is_loading:
                reply = "正在回复..."
            else:
                reply = turn.assistant_message or ""

            self.messages.insert(
                tk.END,
                "助手：{}\n\n".format(reply),
                "assistant",
            )

        self.messages.config(state=tk.DISABLED)
        self.messages.see(tk.END)


class Page2RightBlankArea(tk.Frame):
    """
    对应 Swift 里的 Page2RightBlankArea。
    右侧：图片 / 视频 URL 展示 + 操作栏。
    """

    def __init__(self, master, controller):
        super().__init__(
            master,
            bg="#0e141d",
            highlightbackground="#222b38",
            highlightthickness=1,
        )

        self.controller = controller
        self.current_url = ""

        self.display = tk.Message(
            self,
            text="生成的图片将在这里显示",
            fg="#98a2b3",
            bg="#0e141d",
            width=620,
            font=("Arial", 16),
        )
        self.display.pack(
            fill=tk.BOTH,
            expand=True,
            padx=20,
            pady=20,
        )

        footer = tk.Frame(
            self,
            bg="#0e141d",
        )
        footer.pack(
            fill=tk.X,
            padx=20,
            pady=(0, 20),
        )

        tk.Button(
            footer,
            text="⚙",
            command=controller.open_context_settings,
            width=3,
        ).pack(side=tk.LEFT)

        self.footer_label = tk.Label(
            footer,
            text="",
            fg="#b8beca",
            bg="#0e141d",
        )
        self.footer_label.pack(side=tk.LEFT, padx=8)

        tk.Button(
            footer,
            text="URL+",
            command=controller.open_image_url_store_sheet,
        ).pack(side=tk.RIGHT, padx=4)

        tk.Button(
            footer,
            text="复制",
            command=controller.copy_current_video_or_image_url,
        ).pack(side=tk.RIGHT, padx=4)

        tk.Button(
            footer,
            text="prompt",
            command=lambda: controller.open_image_prompt_sheet(),
        ).pack(side=tk.RIGHT, padx=4)

        tk.Button(
            footer,
            text="‹",
            command=controller.show_previous_generated_image,
        ).pack(side=tk.RIGHT, padx=4)

        tk.Button(
            footer,
            text="›",
            command=controller.show_next_generated_image,
        ).pack(side=tk.RIGHT, padx=4)

        tk.Button(
            footer,
            text="video",
            command=controller.generate_video_from_current_image,
        ).pack(side=tk.RIGHT, padx=4)

        tk.Button(
            footer,
            text="upload",
            command=controller.upload_current_displayed_image_to_cloudinary,
        ).pack(side=tk.RIGHT, padx=4)

        tk.Button(
            footer,
            text="delete",
            command=controller.delete_current_generated_image,
        ).pack(side=tk.RIGHT, padx=4)

    def set_status(self, text):
        self.current_url = ""
        self.display.config(text=text)
        self.display.unbind("<Button-1>")

    def set_footer(self, text):
        self.footer_label.config(text=text)
        self.after(
            1200,
            lambda: self.footer_label.config(text=""),
        )

    def set_url(self, url, kind="image"):
        self.current_url = url

        label = "视频" if kind == "video" else "图片"

        self.display.config(
            text="{} URL：\n{}\n\n点击打开".format(label, url)
        )
        self.display.bind(
            "<Button-1>",
            lambda _event: webbrowser.open(url),
        )


class ImagePromptEditSheet(tk.Toplevel):
    """
    对应 Swift 里的 ImagePromptEditSheet。
    """

    def __init__(self, controller, prompt):
        super().__init__(controller)

        self.controller = controller

        self.title("确认图片提示词")
        self.geometry("720x600")
        self.configure(bg="#202020")

        tk.Label(
            self,
            text="图片 prompt",
            fg="white",
            bg="#202020",
            font=("Arial", 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))

        self.prompt = tk.Text(
            self,
            height=13,
            wrap=tk.WORD,
            bg="white",
            fg="black",
            font=("Arial", 14),
        )
        self.prompt.pack(
            fill=tk.BOTH,
            expand=True,
            padx=18,
        )
        self.prompt.insert("1.0", prompt)

        tk.Label(
            self,
            text="参考图 URL（一行一个，可为空）",
            fg="#d0d0d0",
            bg="#202020",
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.urls = tk.Text(
            self,
            height=5,
            wrap=tk.WORD,
            bg="white",
            fg="black",
        )
        self.urls.pack(
            fill=tk.X,
            padx=18,
        )

        bar = tk.Frame(
            self,
            bg="#202020",
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        tk.Button(
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
            tk.Button(
                bar,
                text=name,
                command=lambda p=provider: self.confirm(p),
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

        self.title("页面二设置")
        self.geometry("440x420")
        self.configure(bg="#202020")

        tk.Label(
            self,
            text="上下文轮数",
            fg="white",
            bg="#202020",
        ).pack(anchor="w", padx=18, pady=(18, 4))

        self.context_entry = tk.Entry(self)
        self.context_entry.insert(0, str(controller.context_turn_count))
        self.context_entry.pack(fill=tk.X, padx=18)

        tk.Label(
            self,
            text="Temperature",
            fg="white",
            bg="#202020",
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.temp_entry = tk.Entry(self)
        self.temp_entry.insert(0, str(controller.temperature))
        self.temp_entry.pack(fill=tk.X, padx=18)

        tk.Label(
            self,
            text="模型",
            fg="white",
            bg="#202020",
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
                bg="#202020",
                fg="white",
                selectcolor="#303030",
            ).pack(anchor="w", padx=18)

        tk.Label(
            self,
            text="视频服务",
            fg="white",
            bg="#202020",
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
                bg="#202020",
                fg="white",
                selectcolor="#303030",
            ).pack(anchor="w", padx=18)

        bar = tk.Frame(
            self,
            bg="#202020",
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        tk.Button(
            bar,
            text="修改 systemprompt",
            command=controller.edit_page2_system_prompt,
        ).pack(side=tk.LEFT)

        tk.Button(
            bar,
            text="取消",
            command=self.destroy,
        ).pack(side=tk.RIGHT)

        tk.Button(
            bar,
            text="保存",
            command=self.save,
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

        self.title("URL 收藏")
        self.geometry("620x560")
        self.configure(bg="#202020")

        self.records = self.load_records(AppStorageKeys.STORED_IMAGE_URL_RECORDS)
        self.hidden_records = self.load_records(AppStorageKeys.HIDDEN_URL_RECORDS)
        self.hidden_space = False

        self.listbox = tk.Listbox(
            self,
            bg="#111722",
            fg="white",
            selectbackground="#293447",
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
            bg="#202020",
        )
        input_row.pack(
            fill=tk.X,
            padx=18,
        )

        self.entry = tk.Entry(input_row)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            input_row,
            text="新增",
            command=self.add,
        ).pack(side=tk.LEFT, padx=6)

        tk.Button(
            input_row,
            text="上传获取 URL",
            command=self.upload,
        ).pack(side=tk.LEFT)

        bar = tk.Frame(
            self,
            bg="#202020",
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        tk.Button(
            bar,
            text="预览",
            command=self.preview_selected,
        ).pack(side=tk.LEFT)

        tk.Button(
            bar,
            text="复制",
            command=self.copy_selected,
        ).pack(side=tk.LEFT, padx=6)

        tk.Button(
            bar,
            text="删除",
            command=self.delete_selected,
        ).pack(side=tk.LEFT)

        tk.Button(
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

        self.title("生成视频")
        self.geometry("520x360")
        self.configure(bg="#202020")

        tk.Label(
            self,
            text="视频 prompt",
            fg="white",
            bg="#202020",
            font=("Arial", 15, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))

        self.prompt = tk.Text(
            self,
            height=8,
            wrap=tk.WORD,
            bg="white",
            fg="black",
        )
        self.prompt.pack(
            fill=tk.BOTH,
            expand=True,
            padx=18,
        )

        tk.Label(
            self,
            text="视频时长",
            fg="white",
            bg="#202020",
        ).pack(anchor="w", padx=18, pady=(12, 4))

        self.seconds_var = tk.StringVar(value="5")

        seconds_row = tk.Frame(
            self,
            bg="#202020",
        )
        seconds_row.pack(fill=tk.X, padx=18)

        for value in ["1", "3", "5", "10"]:
            tk.Radiobutton(
                seconds_row,
                text=value + " 秒",
                variable=self.seconds_var,
                value=value,
                bg="#202020",
                fg="white",
                selectcolor="#303030",
            ).pack(side=tk.LEFT)

        bar = tk.Frame(
            self,
            bg="#202020",
        )
        bar.pack(
            fill=tk.X,
            padx=18,
            pady=18,
        )

        tk.Button(
            bar,
            text="取消",
            command=self.destroy,
        ).pack(side=tk.LEFT)

        tk.Button(
            bar,
            text="生成",
            command=self.confirm,
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
    dialog.title(title)
    dialog.geometry("620x420")
    dialog.configure(bg="#202020")

    result = {
        "value": None,
    }

    text = tk.Text(
        dialog,
        wrap=tk.WORD,
        bg="white",
        fg="black",
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
        bg="#202020",
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

    tk.Button(
        bar,
        text="取消",
        command=cancel,
    ).pack(side=tk.LEFT)

    tk.Button(
        bar,
        text="保存",
        command=save,
    ).pack(side=tk.RIGHT)

    dialog.grab_set()
    parent.wait_window(dialog)

    return result["value"]