import tkinter as tk
from tkinter import messagebox, simpledialog

from app.storage import ChatRecordStore
from app.ui.components import (
    PageWithCustomTopBar,
    make_title,
    make_button,
    make_dark_button,
    make_danger_button,
)


class RecordsPage(PageWithCustomTopBar):
    """
    对应 Swift 里的 ChatRecordListPage。

    功能：
    1. 显示聊天记录列表
    2. 双击打开聊天记录
    3. 重命名聊天记录
    4. 删除聊天记录
    """

    def __init__(self, master, app):
        super().__init__(master, app)

        self.records = []

        self.build_page()
        self.load_records()

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

        title = make_title(container, "聊天记录")
        title.pack(
            anchor="w",
            pady=(18, 12),
        )

        # 列表区域
        list_frame = tk.Frame(
            container,
            bg="#05070d",
        )
        list_frame.pack(
            fill=tk.BOTH,
            expand=True,
        )

        self.listbox = tk.Listbox(
            list_frame,
            bg="#111722",
            fg="white",
            selectbackground="#293447",
            selectforeground="white",
            relief=tk.FLAT,
            font=("Arial", 15),
            height=16,
        )
        self.listbox.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True,
        )

        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.listbox.yview,
        )
        scrollbar.pack(
            side=tk.RIGHT,
            fill=tk.Y,
        )

        self.listbox.config(yscrollcommand=scrollbar.set)

        # 双击打开
        self.listbox.bind("<Double-Button-1>", self.open_selected_record)

        # 右键菜单
        self.context_menu = tk.Menu(
            self,
            tearoff=0,
        )
        self.context_menu.add_command(
            label="打开",
            command=self.open_selected_record,
        )
        self.context_menu.add_command(
            label="重命名",
            command=self.rename_selected_record,
        )
        self.context_menu.add_command(
            label="删除记录",
            command=self.delete_selected_record,
        )

        self.listbox.bind("<Button-2>", self.show_context_menu)
        self.listbox.bind("<Button-3>", self.show_context_menu)

        # 底部按钮
        bottom_bar = tk.Frame(
            container,
            bg="#05070d",
        )
        bottom_bar.pack(
            fill=tk.X,
            pady=(14, 0),
        )

        open_button = make_button(
            bottom_bar,
            text="打开",
            command=self.open_selected_record,
            width=12,
        )
        open_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(0, 6),
        )

        rename_button = make_dark_button(
            bottom_bar,
            text="重命名",
            command=self.rename_selected_record,
            width=12,
        )
        rename_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=6,
        )

        delete_button = make_danger_button(
            bottom_bar,
            text="删除",
            command=self.delete_selected_record,
            width=12,
        )
        delete_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=6,
        )

        refresh_button = make_dark_button(
            bottom_bar,
            text="刷新",
            command=self.load_records,
            width=12,
        )
        refresh_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(6, 0),
        )

    def load_records(self):
        """
        对应 Swift:
        .onAppear {
            ChatRecordStore.migrateLegacyChatRecordsIfNeeded()
            records = ChatRecordStore.loadIndexSorted()
        }
        """

        try:
            ChatRecordStore.migrate_legacy_chat_records_if_needed()
            self.records = ChatRecordStore.load_index_sorted()
            self.refresh_listbox()

        except Exception as exc:
            messagebox.showerror(
                "加载聊天记录失败",
                str(exc),
            )

    def refresh_listbox(self):
        self.listbox.delete(0, tk.END)

        if not self.records:
            self.listbox.insert(tk.END, "暂无聊天记录")
            return

        for record in self.records:
            title = record.title or "未命名聊天"
            updated_at = record.updated_at or ""
            self.listbox.insert(
                tk.END,
                f"{title}    {updated_at}",
            )

    def selected_index(self):
        selection = self.listbox.curselection()

        if not selection:
            return None

        index = selection[0]

        if not self.records:
            return None

        if index < 0 or index >= len(self.records):
            return None

        return index

    def selected_record_item(self):
        index = self.selected_index()

        if index is None:
            return None

        return self.records[index]

    def open_selected_record(self, _event=None):
        """
        对应 Swift:
        private func openRecord(_ indexItem: ChatRecordIndexItem)
        """

        item = self.selected_record_item()

        if item is None:
            return

        try:
            record = ChatRecordStore.load_record(item)

            # 对应 Swift:
            # onOpenRecord(record)
            #
            # Python 里跳到 chatRecord 页面，
            # 由 app/app.py 传给 Page2SplitView(initial_record=record)
            self.app.show_page(
                "chatRecord",
                record=record,
            )

        except Exception as exc:
            messagebox.showerror(
                "加载聊天记录失败",
                str(exc),
            )

    def rename_selected_record(self):
        """
        对应 Swift:
        ChatRecordRenameSheet + saveRename()
        """

        item = self.selected_record_item()

        if item is None:
            return

        new_title = simpledialog.askstring(
            "重命名聊天记录",
            "聊天记录名称：",
            initialvalue=item.title,
            parent=self,
        )

        if new_title is None:
            return

        new_title = new_title.strip()

        if not new_title:
            return

        try:
            ChatRecordStore.rename_record(
                item.id,
                new_title,
            )

            self.load_records()

        except Exception as exc:
            messagebox.showerror(
                "重命名失败",
                str(exc),
            )

    def delete_selected_record(self):
        """
        对应 Swift:
        deleteRecord(id:)
        """

        item = self.selected_record_item()

        if item is None:
            return

        confirm = messagebox.askyesno(
            "删除记录",
            f"确定删除“{item.title}”吗？",
            parent=self,
        )

        if not confirm:
            return

        try:
            ChatRecordStore.delete_record(item.id)
            self.load_records()

        except Exception as exc:
            messagebox.showerror(
                "删除失败",
                str(exc),
            )

    def show_context_menu(self, event):
        """
        右键菜单：打开 / 重命名 / 删除
        """

        if not self.records:
            return

        index = self.listbox.nearest(event.y)

        if index < 0 or index >= len(self.records):
            return

        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        self.listbox.activate(index)

        self.context_menu.tk_popup(
            event.x_root,
            event.y_root,
        )