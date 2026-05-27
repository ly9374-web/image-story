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

## 组件名称总览

本项目不是 React/Vue 组件结构，组件主要以 Streamlit 页面渲染函数、自定义 Streamlit component、导航/主题工具和后端业务类的形式存在。

### 页面组件

入口页由 `streamlit_app.py` 的 `PAGES` 统一注册：

| 中文名 | 页面 key | 渲染组件 |
| --- | --- | --- |
| 登陆 | `signin` | `web.pages.signin_page.render` |
| 首页 | `home` | `web.pages.home.render` |
| 开始 | `main` | `web.pages.page2.render` |
| 设置 | `settings` | `web.pages.settings.render` |
| 记录 | `records` | `web.pages.records.render` |
| 模型 | `modelSettings` | `web.pages.model_settings.render` |

`streamlit_app.py` 顶层组件：

- 应用入口：`main`
- 侧边栏渲染：`_render_sidebar`
- 游客倒计时渲染：`_render_guest_countdown`

### 登录页组件

见 `web/pages/signin_page.py`：

- 登陆页渲染：`render`
- 错误提示：`_toast_error`
- 登陆卡片：`ly-signin-card`
- 登陆标题：`ly-signin-title`
- 口令输入框样式：`ly-input`
- 按钮行：`ly-btn-row`
- 按钮样式：`ly-btn`
- 口令输入框：`signin_passcode`

### 首页组件

见 `web/pages/home.py`：

- 首页渲染：`render`

### Page2 / 开始页组件

见 `web/pages/page2.py`：

- 开始页渲染：`render`
- 侧边栏上下文渲染：`_render_sidebar_context`
- 聊天列渲染：`_render_chat_column`
- 媒体列渲染：`_render_media_column`
- 初始化状态：`_ensure_state`
- 按导航加载记录：`_load_record_from_nav_if_needed`
- 保存或更新聊天记录：`_upsert_record`
- 获取最近助手回复：`_latest_assistant_message`
- 解码 base64 图片：`_decode_image_base64`
- 聊天记录作用域：`_chat_scope`

Page2 表单、容器和 widget keys：

- 上下文设置表单：`page2_context_form`
- 聊天画布容器：`page2_chat_canvas`
- 聊天历史容器：`page2_chat_history`
- 撤销按钮：`page2_chat_undo_btn`
- 聊天输入框：`page2_chat_input`

Page2 会话状态 keys：

- 当前记录 ID：`page2_record_id`
- 已加载记录 ID：`page2_loaded_record_id`
- 对话轮次：`page2_turns`
- 已生成媒体：`page2_generated_media`
- 当前选中媒体 ID：`page2_selected_media_id`
- 图片 prompt：`page2_image_prompt`
- 图片 prompt 模式：`page2_image_prompt_mode`
- 图片 prompt 主体：`page2_image_prompt_subject`
- URL 隐藏空间状态：`page2_url_hidden_space`

Page2 样式变量，见 `app/ui/theme.py` 的 `.st-key-page2_chat_canvas`：

- 聊天容器内边距：`--page2-chat-pad`
- 聊天按钮尺寸：`--page2-chat-btn`
- 聊天控件间距：`--page2-chat-gap`
- 撤销按钮横向间距：`--page2-undo-gap-x`
- 撤销按钮底部偏移：`--page2-undo-bottom-pad`
- 撤销按钮纵向微调：`--page2-undo-nudge-y`
- 撤销按钮横向微调：`--page2-undo-nudge-x`
- 聊天输入右侧预留空间：`--page2-controls-pad-right`

### 设置页组件

见 `web/pages/settings.py`：

- 设置页渲染：`render`
- 记录标签生成：`_label_for_record`
- 设置页隐藏空间状态：`settings_hidden_space`

### 记录页组件

见 `web/pages/records.py`：

- 记录页渲染：`render`
- 记录标签生成：`_label`
- 重命名输入框：`records_rename_title`
- 记录页隐藏空间状态：`records_hidden_space`

### 模型页组件

见 `web/pages/model_settings.py`：

- 模型页渲染：`render`
- 待保存 key 生成：`_pending_key`
- 提示 key 生成：`_flash_key`
- 保存单个配置：`_save_single`
- 删除单个配置：`_delete_single`
- API Key 字段配置：`FIELDS`
- 待保存输入框前缀：`model_settings_pending_`
- 保存/删除提示前缀：`model_settings_flash_`
- 删除按钮前缀：`model_settings_delete_btn_`

### 自定义 Streamlit 组件

见 `web/components/page2_inline_editor/__init__.py`：

- Page2 行内编辑器注册名：`page2_inline_editor`
- Page2 行内编辑器调用函数：`page2_inline_editor`
- Page2 行内编辑器前端入口：`web/components/page2_inline_editor/frontend/index.html`

### 导航和主题组件

导航组件，见 `web/nav.py`：

- 导航状态模型：`_NavState`
- 导航初始化：`nav_init`
- 读取导航状态：`nav_state`
- 跳转页面：`goto`
- 返回上一页：`back`
- 获取页面参数：`get_arg`
- 当前页面：`nav_page`
- 当前页面参数：`nav_page_kwargs`
- 导航历史：`nav_history`

主题组件，见 `app/ui/theme.py`：

- 应用深色主题：`apply_dark_mode`

### 数据模型组件

见 `app/models.py`：

- Page2 聊天模型枚举：`Page2ChatModel`
- Page2 视频生成服务商枚举：`Page2VideoGenerationProvider`
- 生成媒体类型枚举：`GeneratedMediaKind`
- 系统 Prompt 记录：`SystemPromptRecord`
- Page2 对话轮次：`Page2ConversationTurn`
- 生成媒体记录：`GeneratedImageRecord`
- 已存图片 URL 记录：`StoredImageURLRecord`
- 聊天记录：`ChatRecord`
- 聊天记录索引项：`ChatRecordIndexItem`

### 配置和存储组件

见 `app/config.py`：

- 应用存储 key：`AppStorageKeys`
- 布局配置：`Layout`
- 设置存储：`SettingsStore`
- XAI 配置：`XAIConfig`
- Replicate 配置：`ReplicateConfig`
- DeepSeek 配置：`DeepSeekConfig`
- DomoAI 配置：`DomoAIConfig`
- 智谱配置：`ZhipuConfig`

见 `app/storage.py`：

- 聊天记录存储：`ChatRecordStore`

### API 客户端组件

见 `app/api/chat_clients.py`：

- Grok 响应结果：`GrokResponseResult`
- Grok 输入消息：`GrokInputMessage`
- Grok 聊天客户端：`GrokAPIClient`
- DeepSeek 聊天客户端：`DeepSeekAPIClient`

见 `app/api/media_clients.py`：

- 生成图片结果：`GeneratedImageResult`
- Grok 图片客户端：`GrokImageAPIClient`
- Replicate 图片客户端：`ReplicateImageAPIClient`
- DomoAI 客户端：`DomoAIClient`
- 智谱视频客户端：`ZhipuVideoClient`
- Cloudinary 上传器：`CloudinaryUploader`

### 服务组件

见 `app/services/page2_service.py`：

- Page2 上下文：`Page2Context`
- 从设置加载上下文：`load_context_from_settings`
- 保存上下文到设置：`save_context_to_settings`
- 构建上下文消息：`build_context_messages`
- 发送聊天消息：`send_message`
- 生成图片 prompt：`generate_image_prompt`
- 生成图片：`generate_image`
- 图生视频：`generate_video_from_image`
- 确保记录 ID：`ensure_record_id`
- 生成记录标题：`make_record_title`
- 新增或更新聊天记录：`upsert_chat_record`

见 `app/services/chat_records.py`：

- 加载排序后的记录索引：`load_index_sorted`
- 查找记录索引项：`find_index_item`
- 按 ID 加载记录：`load_record_by_id`
- 重命名记录：`rename_record`
- 删除记录：`delete_record`

见 `app/services/system_prompts.py`：

- Prompt 状态：`PromptState`
- 加载 Prompt 状态：`load_state`
- 可见 Prompt 记录：`visible_records`
- 记录所在空间：`record_space`
- 获取 Prompt 记录：`get_record`
- 解锁隐藏空间：`unlock_hidden_space`
- 保存 Prompt：`save_prompt`
- 删除 Prompt 记录：`delete_record`

见 `app/services/stored_urls.py`：

- URL 收藏状态：`StoredURLState`
- 加载 URL 收藏状态：`load_state`
- 持久化 URL 收藏状态：`persist_state`
- 可见 URL 收藏记录：`visible_records`
- 校验 URL：`validate_url`
- 新增 URL：`add_url`
- 删除 URL：`delete_url`

见 `app/services/hidden_space.py`：

- 校验隐藏空间口令：`is_valid_passcode`
- 解锁隐藏空间：`unlock`
