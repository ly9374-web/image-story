import random
import tkinter as tk

from app.config import Layout


# =========================
# 全局颜色
# =========================

COLOR_BLACK = "#000000"
COLOR_PAGE_BG = "#05070d"
COLOR_TOP_BAR_BG = "#020406"
COLOR_PANEL_BG = "#0b1017"
COLOR_WHITE = "#ffffff"
COLOR_MUTED_TEXT = "#b8beca"
COLOR_PURPLE = "#9b5cff"


# =========================
# 对应 Swift: StarryBackground
# =========================

class StarryBackground(tk.Canvas):
    """
    对应 Swift 里的 StarryBackground。

    Swift 版本是 Canvas + TimelineView 动画星空。
    Python tkinter 版本这里先做静态星空背景。
    """

    def __init__(self, master, star_count=190, seed=0xC0FFEE, **kwargs):
        super().__init__(
            master,
            bg=COLOR_BLACK,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )

        self.star_count = star_count
        self.seed = seed
        self.stars = []

        self.bind("<Configure>", self.redraw)

    def generate_stars(self, width, height):
        random.seed(self.seed)

        stars = []

        for _ in range(self.star_count):
            x = random.randint(0, max(1, width))
            y = random.randint(0, max(1, height))
            radius = random.choice([1, 1, 1, 2])
            opacity_level = random.choice(["#666666", "#888888", "#aaaaaa", "#ffffff"])

            stars.append(
                {
                    "x": x,
                    "y": y,
                    "radius": radius,
                    "color": opacity_level,
                    "has_glare": random.random() < 0.08,
                }
            )

        return stars

    def redraw(self, _event=None):
        self.delete("all")

        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        self.stars = self.generate_stars(width, height)

        for star in self.stars:
            x = star["x"]
            y = star["y"]
            r = star["radius"]
            color = star["color"]

            self.create_oval(
                x - r,
                y - r,
                x + r,
                y + r,
                fill=color,
                outline="",
            )

            if star["has_glare"]:
                glare = 6
                self.create_line(
                    x - glare,
                    y,
                    x + glare,
                    y,
                    fill="#777777",
                    width=1,
                )
                self.create_line(
                    x,
                    y - glare,
                    x,
                    y + glare,
                    fill="#777777",
                    width=1,
                )


# =========================
# 基础 Page
# =========================

class Page(tk.Frame):
    """
    所有页面的基础类。

    每个页面都继承 Page，例如：
        HomePage(Page)
        SettingsPage(Page)
        ModelSettingsPage(Page)
        RecordsPage(Page)
        Page2SplitView(Page)
    """

    def __init__(self, master, app):
        super().__init__(master, bg=COLOR_BLACK)

        self.app = app

        self.background = StarryBackground(self)
        self.background.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.content = tk.Frame(self, bg=COLOR_PAGE_BG)
        self.content.place(relx=0, rely=0, relwidth=1, relheight=1)


# =========================
# 对应 Swift: CustomTopBar
# =========================

class CustomTopBar(tk.Frame):
    """
    对应 Swift 里的 CustomTopBar。

    Swift 版是顶部一条黑色栏，左边有返回箭头。
    Python 版用 Frame + Button 实现。
    """

    HEIGHT = 52

    def __init__(self, master, on_back):
        super().__init__(
            master,
            height=self.HEIGHT,
            bg=COLOR_TOP_BAR_BG,
            highlightbackground="#888888",
            highlightthickness=1,
        )

        self.pack_propagate(False)

        self.back_button = tk.Button(
            self,
            text="‹",
            command=on_back,
            bg=COLOR_TOP_BAR_BG,
            fg=COLOR_PURPLE,
            activebackground=COLOR_TOP_BAR_BG,
            activeforeground=COLOR_PURPLE,
            bd=0,
            relief=tk.FLAT,
            font=("Arial", 28, "bold"),
            width=3,
        )
        self.back_button.pack(side=tk.LEFT, padx=12)


# 为了和之前代码兼容，保留 TopBar 这个名字
TopBar = CustomTopBar


# =========================
# 对应 Swift: PageWithCustomTopBar
# =========================

class PageWithCustomTopBar(Page):
    """
    对应 Swift 里的 PageWithCustomTopBar。

    它会自动创建：
    1. 星空背景
    2. 顶部返回栏
    3. body 内容区域

    其他页面如果需要顶部返回栏，可以继承这个。
    """

    def __init__(self, master, app, on_back=None):
        super().__init__(master, app)

        if on_back is None:
            on_back = app.go_back

        self.top_bar = CustomTopBar(self.content, on_back)
        self.top_bar.pack(
            fill=tk.X,
            padx=28,
            pady=(8, 0),
        )

        self.body = tk.Frame(self.content, bg=COLOR_PAGE_BG)
        self.body.pack(
            fill=tk.BOTH,
            expand=True,
        )


# =========================
# 通用控件
# =========================

def make_title(parent, text):
    label = tk.Label(
        parent,
        text=text,
        bg=COLOR_PAGE_BG,
        fg=COLOR_WHITE,
        font=("Arial", 22, "bold"),
    )
    return label


def make_button(
    parent,
    text,
    command,
    width=22,
    height=2,
    bg=COLOR_WHITE,
    fg=COLOR_BLACK,
):
    button = tk.Button(
        parent,
        text=text,
        command=command,
        width=width,
        height=height,
        bg=bg,
        fg=fg,
        activebackground=bg,
        activeforeground=fg,
        relief=tk.FLAT,
        bd=0,
        font=("Arial", 14, "bold"),
    )
    return button


def make_dark_button(parent, text, command, width=14):
    return make_button(
        parent=parent,
        text=text,
        command=command,
        width=width,
        bg="#2a2e38",
        fg=COLOR_WHITE,
    )


def make_danger_button(parent, text, command, width=14):
    return make_button(
        parent=parent,
        text=text,
        command=command,
        width=width,
        bg="#733330",
        fg=COLOR_WHITE,
    )


def make_text_input(parent, height=10):
    text = tk.Text(
        parent,
        height=height,
        wrap=tk.WORD,
        bg="#151922",
        fg=COLOR_WHITE,
        insertbackground=COLOR_WHITE,
        relief=tk.FLAT,
        padx=12,
        pady=12,
        font=("Arial", 14),
    )
    return text


def make_entry(parent, textvariable=None, show=None):
    entry = tk.Entry(
        parent,
        textvariable=textvariable,
        show=show,
        bg=COLOR_WHITE,
        fg=COLOR_BLACK,
        insertbackground=COLOR_BLACK,
        relief=tk.FLAT,
        font=("Arial", 14),
    )
    return entry


def clear_frame(frame):
    for child in frame.winfo_children():
        child.destroy()


# =========================
# 兼容旧命名
# =========================

def title(parent, text):
    return make_title(parent, text)


def button(parent, text, command, width=22):
    return make_button(parent, text, command, width=width)