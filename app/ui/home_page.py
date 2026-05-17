import tkinter as tk

from app.config import Layout
from app.ui.components import Page, make_button


class HomePage(Page):
    """
    对应 Swift 里的 HomePage。

    Swift 首页有四个按钮：
    1. 开始 -> Page2SplitView
    2. 设置 -> SettingsPage
    3. 记录 -> ChatRecordListPage
    4. 模型 -> ModelSettingsPage
    """

    def __init__(self, master, app):
        super().__init__(master, app)

        # 中间按钮容器
        center = tk.Frame(
            self.content,
            bg="#05070d",
        )
        center.place(
            relx=0.5,
            rely=0.5,
            anchor="center",
        )

        # 开始
        start_button = make_button(
            center,
            text="开始",
            command=lambda: app.show_page("main"),
            width=18,
        )
        start_button.pack(
            pady=Layout.HOME_BUTTON_SPACING // 2,
        )

        # 设置
        settings_button = make_button(
            center,
            text="设置",
            command=lambda: app.show_page("settings"),
            width=18,
        )
        settings_button.pack(
            pady=Layout.HOME_BUTTON_SPACING // 2,
        )

        # 记录
        records_button = make_button(
            center,
            text="记录",
            command=lambda: app.show_page("records"),
            width=18,
        )
        records_button.pack(
            pady=Layout.HOME_BUTTON_SPACING // 2,
        )

        # 模型
        model_button = make_button(
            center,
            text="模型",
            command=lambda: app.show_page("modelSettings"),
            width=18,
        )
        model_button.pack(
            pady=Layout.HOME_BUTTON_SPACING // 2,
        )