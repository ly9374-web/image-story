import tkinter as tk

from app.config import AppStorageKeys, settings
from app.ui.components import (
    PageWithCustomTopBar,
    make_button,
    make_dark_button,
    make_entry,
    make_title,
)


class ModelSettingsPage(PageWithCustomTopBar):
    """
    对应 Swift 里的 ModelSettingsPage。

    这个页面负责保存：
    1. Grok 聊天 API Key
    2. Grok 生图 API Key
    3. Replicate API Token
    4. DeepSeek API Key
    5. DomoAI API Key
    6. 智谱 API Key
    7. 是否打印调试日志
    """

    FIELDS = [
        (
            "输入 Grok 聊天 API Key（会本地持久化保存）",
            AppStorageKeys.XAI_CHAT_API_KEY,
            "XAI_CHAT_API_KEY",
        ),
        (
            "输入 Grok 生图 API Key（会本地持久化保存）",
            AppStorageKeys.XAI_IMAGE_API_KEY,
            "XAI_IMAGE_API_KEY",
        ),
        (
            "输入 Replicate API Token（会本地持久化保存）",
            AppStorageKeys.REPLICATE_API_TOKEN,
            "REPLICATE_API_TOKEN",
        ),
        (
            "输入 DeepSeek API Key（会本地持久化保存）",
            AppStorageKeys.DEEPSEEK_API_KEY,
            "DEEPSEEK_API_KEY",
        ),
        (
            "输入 DomoAI API Key（会本地持久化保存）",
            AppStorageKeys.DOMOAI_API_KEY,
            "DOMOAI_API_KEY",
        ),
        (
            "输入 智谱 API Key（会本地持久化保存）",
            AppStorageKeys.ZHIPU_API_KEY,
            "ZHIPU_API_KEY",
        ),
    ]

    def __init__(self, master, app):
        super().__init__(master, app)

        self.entries = {}
        self.debug_log_var = tk.BooleanVar(
            value=settings.bool(AppStorageKeys.DEBUG_LOG_ENABLED, False)
        )

        self.build_page()
        self.load_from_storage()

    def build_page(self):
        container = tk.Frame(
            self.body,
            bg="#05070d",
        )
        container.pack(
            fill=tk.BOTH,
            expand=True,
            padx=24,
            pady=18,
        )

        title = make_title(container, "模型")
        title.pack(
            anchor="w",
            pady=(18, 12),
        )

        # API Key 输入区
        for label_text, key, placeholder in self.FIELDS:
            label = tk.Label(
                container,
                text=label_text,
                bg="#05070d",
                fg="#b8beca",
                font=("Arial", 13),
            )
            label.pack(
                anchor="w",
                pady=(12, 4),
            )

            entry = make_entry(
                container,
                show="*",
            )
            entry.pack(
                fill=tk.X,
                ipady=8,
            )

            # 记录这个 entry 对应哪个 AppStorageKeys
            self.entries[key] = entry

            # 简单 placeholder 提示
            if not settings.get(key, ""):
                entry.insert(0, "")
                entry.config(fg="black")

        # 调试日志开关
        debug_row = tk.Frame(
            container,
            bg="#05070d",
        )
        debug_row.pack(
            fill=tk.X,
            pady=(16, 4),
        )

        debug_check = tk.Checkbutton(
            debug_row,
            text="打印调试日志",
            variable=self.debug_log_var,
            bg="#05070d",
            fg="white",
            activebackground="#05070d",
            activeforeground="white",
            selectcolor="#202020",
            font=("Arial", 14),
        )
        debug_check.pack(anchor="w")

        debug_note = tk.Label(
            container,
            text="关闭后不会在控制台打印请求体、响应体和调试信息，可减少卡顿。",
            bg="#05070d",
            fg="#888888",
            font=("Arial", 12),
        )
        debug_note.pack(
            anchor="w",
            pady=(0, 8),
        )

        # 底部按钮
        bottom_bar = tk.Frame(
            container,
            bg="#05070d",
        )
        bottom_bar.pack(
            fill=tk.X,
            side=tk.BOTTOM,
            pady=(14, 0),
        )

        cancel_button = make_dark_button(
            bottom_bar,
            text="取消",
            command=self.cancel_and_dismiss,
            width=14,
        )
        cancel_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(0, 6),
        )

        confirm_button = make_button(
            bottom_bar,
            text="确定",
            command=self.save_and_dismiss,
            width=14,
        )
        confirm_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(6, 0),
        )

    def load_from_storage(self):
        """
        对应 Swift 里的 .onAppear。

        Swift 逻辑：
        如果 xaiChatApiKey 和 xaiImageApiKey 都为空，
        但旧的 xaiApiKey 有值，就把旧 key 同步到两个新 key。
        """

        stored_chat_api_key = str(
            settings.get(AppStorageKeys.XAI_CHAT_API_KEY, "") or ""
        ).strip()

        stored_image_api_key = str(
            settings.get(AppStorageKeys.XAI_IMAGE_API_KEY, "") or ""
        ).strip()

        legacy_api_key = str(
            settings.get(AppStorageKeys.XAI_API_KEY, "") or ""
        ).strip()

        if not stored_chat_api_key and not stored_image_api_key and legacy_api_key:
            settings.set(AppStorageKeys.XAI_CHAT_API_KEY, legacy_api_key)
            settings.set(AppStorageKeys.XAI_IMAGE_API_KEY, legacy_api_key)

        for _label_text, key, _placeholder in self.FIELDS:
            value = str(settings.get(key, "") or "")

            entry = self.entries[key]
            entry.delete(0, tk.END)
            entry.insert(0, value)

        self.debug_log_var.set(
            settings.bool(AppStorageKeys.DEBUG_LOG_ENABLED, False)
        )

    def save_and_dismiss(self):
        """
        对应 Swift 里点击“确定”的逻辑。
        """

        for _label_text, key, _placeholder in self.FIELDS:
            entry = self.entries[key]
            value = entry.get().strip()
            settings.set(key, value)

        settings.set(
            AppStorageKeys.DEBUG_LOG_ENABLED,
            bool(self.debug_log_var.get()),
        )

        self.app.go_back()

    def cancel_and_dismiss(self):
        """
        对应 Swift 里点击“取消”的逻辑。
        """

        self.app.go_back()