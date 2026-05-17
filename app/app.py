import tkinter as tk

from app.ui.home_page import HomePage
from app.ui.settings_page import SettingsPage
from app.ui.model_settings_page import ModelSettingsPage
from app.ui.records_page import RecordsPage
from app.ui.page2 import Page2SplitView


class PythonApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("图像小说 Python")
        self.geometry("1280x860")
        self.configure(bg="black")

        self.current_page_name = None
        self.current_kwargs = {}
        self.page_history = []

        self.show_page("home", push_history=False)

    def show_page(self, page_name, push_history=True, **kwargs):
        if push_history and self.current_page_name is not None:
            self.page_history.append((self.current_page_name, self.current_kwargs))

        for child in self.winfo_children():
            child.destroy()

        self.current_page_name = page_name
        self.current_kwargs = kwargs

        if page_name == "home":
            page = HomePage(self, self)

        elif page_name == "main":
            page = Page2SplitView(self, self)

        elif page_name == "settings":
            page = SettingsPage(self, self)

        elif page_name == "records":
            page = RecordsPage(self, self)

        elif page_name == "modelSettings":
            page = ModelSettingsPage(self, self)

        elif page_name == "chatRecord":
            page = Page2SplitView(
                self,
                self,
                initial_record=kwargs.get("record"),
            )

        else:
            page = HomePage(self, self)

        page.pack(fill=tk.BOTH, expand=True)

    def go_back(self):
        if not self.page_history:
            self.show_page("home", push_history=False)
            return

        page_name, kwargs = self.page_history.pop()
        self.show_page(page_name, push_history=False, **kwargs)