import json
import tkinter as tk
from tkinter import messagebox

from app.config import settings, AppStorageKeys
from app.models import SystemPromptRecord, now_iso
from app.ui.components import Page, TopBar


class SettingsPage(Page):
    HIDDEN_PASSCODE = "ly123"

    def __init__(self, master, app):
        super().__init__(master, app)

        self.records = []
        self.hidden_records = []
        self.selected_record_id = None
        self.renaming_record_id = None
        self.is_hidden_settings_space = False

        self.next_record_index = 1
        self.hidden_next_record_index = 1

        TopBar(self, app.go_back).pack(fill=tk.X)

        self.body = tk.Frame(self, bg=self["bg"])
        self.body.pack(fill=tk.BOTH, expand=True, padx=24, pady=18)

        self.title_label = tk.Label(
            self.body,
            text="system prompt",
            bg=self["bg"],
            fg="white",
            font=("Arial", 22, "bold"),
        )
        self.title_label.pack(anchor="w", pady=(0, 12))

        self.prompt_box = tk.Text(
            self.body,
            height=18,
            wrap=tk.WORD,
            bg="#151922",
            fg="white",
            insertbackground="white",
            relief=tk.FLAT,
            padx=12,
            pady=12,
        )
        self.prompt_box.pack(fill=tk.X)
        self.prompt_box.bind("<KeyRelease>", self.detect_hidden_space)

        self.records_frame = tk.Frame(self.body, bg=self["bg"])
        self.records_frame.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        self.listbox = tk.Listbox(
            self.records_frame,
            bg="#111722",
            fg="white",
            selectbackground="#293447",
            relief=tk.FLAT,
            font=("Arial", 15),
            height=8,
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.select_record)

        rename_row = tk.Frame(self.body, bg=self["bg"])
        rename_row.pack(fill=tk.X, pady=(12, 0))

        tk.Label(
            rename_row,
            text="记录名称",
            bg=self["bg"],
            fg="#b8beca",
            font=("Arial", 13),
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.rename_var = tk.StringVar(value="")
        self.rename_entry = tk.Entry(
            rename_row,
            textvariable=self.rename_var,
            bg="#151922",
            fg="white",
            insertbackground="white",
            relief=tk.FLAT,
            font=("Arial", 14),
        )
        self.rename_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7)
        self.rename_entry.bind("<Return>", self.save_rename)

        bottom_bar = tk.Frame(self.body, bg=self["bg"])
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(14, 0))

        tk.Button(
            bottom_bar,
            text="取消",
            command=self.cancel_and_dismiss,
            bg="#2a2e38",
            fg="white",
            relief=tk.FLAT,
            height=2,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.delete_button = tk.Button(
            bottom_bar,
            text="delete",
            command=self.delete_selected_record,
            bg="#733330",
            fg="white",
            relief=tk.FLAT,
            height=2,
        )
        self.delete_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        tk.Button(
            bottom_bar,
            text="确定",
            command=self.confirm_and_dismiss,
            bg="white",
            fg="black",
            relief=tk.FLAT,
            height=2,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        self.load_from_storage()
        self.refresh_records()
        self.update_delete_button()

    # ---------- 数据读取 / 保存 ----------

    def load_from_storage(self):
        self.next_record_index = max(
            1,
            int(settings.get(AppStorageKeys.SYSTEM_PROMPT_RECORD_NEXT_INDEX, 1) or 1),
        )
        self.hidden_next_record_index = max(
            1,
            int(settings.get(AppStorageKeys.HIDDEN_SYSTEM_PROMPT_RECORD_NEXT_INDEX, 1) or 1),
        )

        self.records = self.decode_records(
            settings.get(AppStorageKeys.SYSTEM_PROMPT_RECORDS, "")
        )
        self.hidden_records = self.decode_records(
            settings.get(AppStorageKeys.HIDDEN_SYSTEM_PROMPT_RECORDS, "")
        )

        # 兼容旧数据：如果以前只保存过 systemPrompt，就自动生成一条“记录1”
        if not self.records:
            legacy_prompt = str(settings.get(AppStorageKeys.SYSTEM_PROMPT, "") or "").strip()
            if legacy_prompt:
                record = SystemPromptRecord(
                    title="记录1",
                    prompt=legacy_prompt,
                    created_at=now_iso(),
                    updated_at=now_iso(),
                )
                self.records = [record]
                self.selected_record_id = record.id
                self.next_record_index = max(self.next_record_index, 2)

                settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, record.id)
                settings.set(AppStorageKeys.SYSTEM_PROMPT, record.prompt)
                self.persist_all_records()

                self.prompt_box.delete("1.0", tk.END)
                self.prompt_box.insert("1.0", record.prompt)
                return

        self.selected_record_id = None
        self.renaming_record_id = None
        self.rename_var.set("")
        self.prompt_box.delete("1.0", tk.END)

    def persist_all_records(self):
        settings.set(AppStorageKeys.SYSTEM_PROMPT_RECORDS, self.encode_records(self.records))
        settings.set(AppStorageKeys.SYSTEM_PROMPT_RECORD_NEXT_INDEX, self.next_record_index)
        settings.set(AppStorageKeys.HIDDEN_SYSTEM_PROMPT_RECORDS, self.encode_records(self.hidden_records))
        settings.set(AppStorageKeys.HIDDEN_SYSTEM_PROMPT_RECORD_NEXT_INDEX, self.hidden_next_record_index)

    def encode_records(self, records):
        result = []
        for record in records:
            result.append(
                {
                    "id": record.id,
                    "title": record.title,
                    "prompt": record.prompt,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
            )
        return json.dumps(result, ensure_ascii=False)

    def decode_records(self, raw):
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

            # 同时兼容 Swift 的 createdAt / updatedAt 和 Python 的 created_at / updated_at
            records.append(
                SystemPromptRecord(
                    id=item.get("id"),
                    title=item.get("title", "未命名记录"),
                    prompt=item.get("prompt", ""),
                    created_at=item.get("created_at") or item.get("createdAt") or now_iso(),
                    updated_at=item.get("updated_at") or item.get("updatedAt") or now_iso(),
                )
            )

        return records

    # ---------- 列表逻辑 ----------

    def visible_records(self):
        if self.is_hidden_settings_space:
            return self.records + self.hidden_records
        return self.records

    def record_space(self, record_id):
        for record in self.hidden_records:
            if record.id == record_id:
                return "hidden"

        for record in self.records:
            if record.id == record_id:
                return "normal"

        return None

    def get_record_by_id(self, record_id):
        for record in self.records + self.hidden_records:
            if record.id == record_id:
                return record
        return None

    def refresh_records(self):
        self.listbox.delete(0, tk.END)

        visible = self.visible_records()
        for record in visible:
            prefix = "隐藏：" if self.record_space(record.id) == "hidden" else ""
            self.listbox.insert(tk.END, prefix + record.title)

        self.update_delete_button()

    def select_record(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        visible = self.visible_records()
        if index >= len(visible):
            return

        record = visible[index]

        self.selected_record_id = record.id
        self.renaming_record_id = record.id
        self.rename_var.set(record.title)

        self.prompt_box.delete("1.0", tk.END)
        self.prompt_box.insert("1.0", record.prompt)

        self.rename_entry.focus_set()
        self.update_delete_button()

    # ---------- 隐藏空间 ----------

    def detect_hidden_space(self, _event=None):
        text = self.prompt_box.get("1.0", tk.END).strip()

        if text == self.HIDDEN_PASSCODE:
            self.is_hidden_settings_space = True
            self.prompt_box.delete("1.0", tk.END)
            self.title_label.config(text="隐藏 system prompt")
            self.refresh_records()

    # ---------- 按钮逻辑 ----------

    def cancel_and_dismiss(self):
        self.app.go_back()

    def confirm_and_dismiss(self):
        self.save_rename()

        prompt = self.prompt_box.get("1.0", tk.END).strip()

        # 如果选中了旧记录，就更新旧记录
        if self.selected_record_id:
            record = self.get_record_by_id(self.selected_record_id)

            if record is not None:
                if record.prompt != prompt:
                    record.prompt = prompt
                    record.updated_at = now_iso()

                settings.set(AppStorageKeys.SYSTEM_PROMPT, record.prompt)
                settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, record.id)

                self.persist_all_records()
                self.app.go_back()
                return

        # 如果没有选中旧记录，而且输入为空，就直接返回
        if not prompt:
            self.app.go_back()
            return

        # 如果没有选中旧记录，而且输入不为空，就创建新记录
        if self.is_hidden_settings_space:
            title = f"隐藏记录{self.hidden_next_record_index}"
            self.hidden_next_record_index += 1
        else:
            title = f"记录{self.next_record_index}"
            self.next_record_index += 1

        record = SystemPromptRecord(
            title=title,
            prompt=prompt,
            created_at=now_iso(),
            updated_at=now_iso(),
        )

        if self.is_hidden_settings_space:
            self.hidden_records.append(record)
        else:
            self.records.append(record)

        self.selected_record_id = record.id

        settings.set(AppStorageKeys.SYSTEM_PROMPT, record.prompt)
        settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, record.id)

        self.persist_all_records()
        self.app.go_back()

    def delete_selected_record(self):
        if not self.selected_record_id:
            return

        target_id = self.selected_record_id

        self.records = [record for record in self.records if record.id != target_id]
        self.hidden_records = [record for record in self.hidden_records if record.id != target_id]

        if settings.get(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, "") == target_id:
            settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, "")
            settings.set(AppStorageKeys.SYSTEM_PROMPT, "")

        self.selected_record_id = None
        self.renaming_record_id = None
        self.rename_var.set("")

        self.prompt_box.delete("1.0", tk.END)

        self.persist_all_records()
        self.refresh_records()

    def save_rename(self, _event=None):
        if not self.renaming_record_id:
            return

        record = self.get_record_by_id(self.renaming_record_id)
        if record is None:
            return

        title = self.rename_var.get().strip()
        if title and title != record.title:
            record.title = title
            record.updated_at = now_iso()
            self.persist_all_records()
            self.refresh_records()

        self.renaming_record_id = None

    def update_delete_button(self):
        if self.selected_record_id:
            self.delete_button.config(state=tk.NORMAL)
        else:
            self.delete_button.config(state=tk.DISABLED)