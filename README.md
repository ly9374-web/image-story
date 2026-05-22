# Streamlit 版

运行：

```bash
streamlit run streamlit_app.py
```

你需要把自己的 API Key 填到“模型”页面，或者设置环境变量：
- XAI_CHAT_API_KEY
- XAI_IMAGE_API_KEY
- REPLICATE_API_TOKEN
- DEEPSEEK_API_KEY
- DOMOAI_API_KEY
- ZHIPU_API_KEY

说明：
- 这是把原 SwiftUI 逻辑迁移到 Web 版的实现。
- API 调用、聊天记录、模型设置、主聊天页等业务逻辑保留在 `app/` 下，界面层在 `web/` 下。

Page2（开始页）组件/标识（见 `web/pages/page2.py`）：
- 主要渲染函数：`render()` / `_render_sidebar_context()` / `_render_chat_column()` / `_render_media_column()`
- Sidebar 表单：`page2_context_form`（`st.form("page2_context_form", ...)`）
- 左侧聊天列（widget/container keys）：
  - `page2_chat_canvas`：聊天画布容器（整体样式/滚动承载）
  - `page2_chat_history`：聊天历史容器（消息列表）
  - `page2_chat_undo_btn`：撤销按钮（`st.button(key=...)`）
  - `page2_chat_input`：输入框（`st.chat_input(key=...)`）
- 撤销按钮位置参数（见 `app/ui/theme.py` 的 `.st-key-page2_chat_canvas` CSS 变量）：
  - `--page2-undo-gap-x`：撤销与发送按钮间距
  - `--page2-undo-bottom-pad`：底部额外偏移
  - `--page2-undo-nudge-y`：上下微调（负数上移）
- Page2 会话状态（`st.session_state` keys，见 `_ensure_state()`）：
  - `page2_record_id` / `page2_loaded_record_id`
  - `page2_turns`
  - `page2_generated_media` / `page2_selected_media_id`
  - `page2_image_prompt` / `page2_image_prompt_mode` / `page2_image_prompt_subject`
  - `page2_url_hidden_space`
