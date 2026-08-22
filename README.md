# Streamlit 版

运行：

```bash
python3 -m streamlit run streamlit_app.py
```

你需要把自己的 API Key 填到“APIkey”页面，或者在 Streamlit Cloud 的 App settings / Secrets 中配置：
- GROK_CHAT_API_KEY
- GROK_IMAGE_API_KEY
- REPLICATE_API_TOKEN
- DEEPSEEK_API_KEY
- DOMOAI_API_KEY
- ZHIPU_API_KEY
- CLOUDINARY_API_KEY
- CLOUDINARY_API_SECRET

API Key 读取优先级：APIkey 页面用户填写并保存的值 > Streamlit Secrets > 空值并提示缺少对应 API Key。
Cloudinary 的 cloud name 默认使用 `dxi0op4os`。

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
| APIkey | `modelSettings` | `web.pages.model_settings.render` |

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
- Story Brain 图谱组件注册：`_story_brain_graph_component`
- 侧边栏上下文渲染：`_render_sidebar_context`
- 聊天列渲染：`_render_chat_column`
- 媒体列渲染：`_render_media_column`
- 初始化状态：`_ensure_state`
- 按导航加载记录：`_load_record_from_nav_if_needed`
- 保存或更新聊天记录：`_upsert_record`
- 获取最近助手回复：`_latest_assistant_message`
- 解码 base64 图片：`_decode_image_base64`
- 聊天记录作用域：`_chat_scope`
- 新建 Story Brain ID：`_new_story_brain_id`
- Story Brain 文本清洗：`_story_brain_text`
- Story Brain 三组动态数组读取：`_story_brain_lists`
- 保存 Story Brain 并刷新：`_save_story_brain_and_refresh`
- Story Brain 图谱编辑目标集合映射：`_story_brain_collection_for_target`
- 应用 Story Brain 图谱双击编辑：`_apply_story_brain_graph_edit`
- 渲染 Story Brain 图谱：`_render_story_brain_graph`
- 清空 Story Brain 更新建议状态：`_clear_story_brain_update_suggestions`
- 渲染 Story Brain 更新建议：`_render_story_brain_update_suggestions`
- 角色标签生成：`_character_label`
- 关系标签生成：`_relationship_label`
- 事件标签生成：`_event_label`
- selectbox 默认值保护：`_ensure_selectbox_value`
- Story Brain 角色编辑器：`_render_story_brain_character_editor`
- Story Brain 关系编辑器：`_render_story_brain_relationship_editor`
- Story Brain 事件编辑器：`_render_story_brain_event_editor`
- Story Brain 编辑器总入口：`_render_story_brain_editors`

Page2 表单、容器和 widget keys：

- 上下文设置表单：`page2_context_form`
- 聊天画布容器：`page2_chat_canvas`
- 聊天历史容器：`page2_chat_history`
- 撤销按钮：`page2_chat_undo_btn`
- 聊天输入框：`page2_chat_input`
- Story Brain 打开按钮：`page2_story_brain_btn`
- Story Brain 图谱组件：`page2_story_brain_graph_component`
- Story Brain 全屏图谱组件：`page2_story_brain_graph_component_fullscreen`
- Story Brain 全屏关闭按钮：`page2_story_brain_fullscreen_close_btn`
- 角色新增按钮：`story_brain_add_character_btn`
- 角色选择器：`story_brain_character_select`
- 角色字段输入前缀：`story_brain_character_name_`、`story_brain_character_speech_style_`、`story_brain_character_behavior_style_`、`story_brain_character_status_`、`story_brain_character_other_`、`story_brain_character_goal_`、`story_brain_character_secret_`
- 角色保存/删除按钮前缀：`story_brain_save_character_`、`story_brain_delete_character_`
- 关系新增按钮：`story_brain_add_relationship_btn`
- 关系选择器：`story_brain_relationship_select`
- 关系字段输入前缀：`story_brain_relationship_from_`、`story_brain_relationship_to_`、`story_brain_relationship_type_`、`story_brain_relationship_detail_`
- 关系保存/删除按钮前缀：`story_brain_save_relationship_`、`story_brain_delete_relationship_`
- 事件新增按钮：`story_brain_add_event_btn`
- 事件选择器：`story_brain_event_select`
- 事件字段输入前缀：`story_brain_event_type_`、`story_brain_event_title_`、`story_brain_event_content_`、`story_brain_event_status_`、`story_brain_event_trigger_`、`story_brain_event_related_characters_`
- 事件保存/删除按钮前缀：`story_brain_save_event_`、`story_brain_delete_event_`

Page2 主要 UI 区块：

- 会话区：新建会话、记录 ID 显示。
- 上下文设置区：选择 prompt 记录、system prompt、上下文轮数、聊天模型、temperature、图生视频服务商。
- 聊天区：聊天历史、聊天输入、撤销按钮、Story Brain 打开按钮。
- Story Brain 区：交互式知识图谱、角色编辑、关系编辑、事件编辑、原始 JSON 查看。
- Memory Pack 预览：`本轮将代入模型的 Story Brain Memory Pack`。
- Story Brain 自动更新建议：`Story Brain 更新建议`，本轮生成后固定调用 DeepSeek 生成 `suggested_updates`，成功解析后自动增量写入当前 `ChatRecord.story_brain`。
- 伏笔 trigger 规则：`type` 为 `伏笔` 的事件必须有非空 `trigger`，每轮进入 Memory Pack；trigger 未发生时禁止触发，触发后由 DeepSeek 输出 `delete` 自动删除。
- 角色状态规则：`character.status` 记录身体状态、伤势和当前姿势；不记录心理状态、情绪、服装设定或身份背景。
- 媒体记录区：图片/视频记录选择、预览、prompt 查看、URL 复制、删除当前记录。
- 生成图片区：prompt 模式、主体、生成图片prompt、图片prompt编辑、图片 provider、参考图片 URL、生成图片。
- 图生视频区：选择输入图片、视频 prompt、时长、生成视频。
- URL 收藏区：新增 URL 或输入口令解锁隐藏空间、Cloudinary 上传图片获取 URL、收藏列表、删除选中 URL。

Page2 会话状态 keys：

- 当前记录 ID：`page2_record_id`
- 已加载记录 ID：`page2_loaded_record_id`
- 对话轮次：`page2_turns`
- 已生成媒体：`page2_generated_media`
- 当前选中媒体 ID：`page2_selected_media_id`
- 图片prompt：`page2_image_prompt`
- 图片prompt模式：`page2_image_prompt_mode`
- 图片prompt主体：`page2_image_prompt_subject`
- URL 隐藏空间状态：`page2_url_hidden_space`
- Story Brain 更新建议：`page2_story_brain_suggested_updates`
- Story Brain 更新错误：`page2_story_brain_update_error`
- Story Brain 更新对应轮次 ID：`page2_story_brain_update_turn_id`
- Story Brain 更新是否已自动应用：`page2_story_brain_update_applied`
- Story Brain 图谱编辑事件 ID：`page2_story_brain_graph_edit_event_id`
- Story Brain 图谱全屏状态：`page2_story_brain_graph_fullscreen`
- 当前聊天记录 Story Brain：`page2_story_brain`
- Story Brain 功能展开状态：`show_story_brain`
- Story Brain 操作提示：`story_brain_notice`
- 本轮 Story Brain Memory Pack JSON：`page2_story_brain_memory_pack_json`

Page2 样式变量，见 `app/ui/theme.py` 的 `.st-key-page2_chat_canvas`：

- 聊天容器内边距：`--page2-chat-pad`
- 聊天按钮尺寸：`--page2-chat-btn`
- 聊天控件间距：`--page2-chat-gap`
- 撤销按钮横向间距：`--page2-undo-gap-x`
- 撤销按钮底部偏移：`--page2-undo-bottom-pad`
- 撤销按钮纵向微调：`--page2-undo-nudge-y`
- 撤销按钮横向微调：`--page2-undo-nudge-x`
- 聊天输入右侧预留空间：`--page2-controls-pad-right`

Page2 Story Brain 图谱配置，见 `graph_view.py`：

- 图谱默认高度：`GRAPH_HEIGHT_PX`
- 节点距离参数：`GRAPH_NODE_SPACING`
- 特征节点颜色：`GRAPH_TRAIT_NODE_COLOR`
- 角色节点颜色：`GRAPH_CHARACTER_NODE_COLOR`
- 事件节点颜色：`GRAPH_EVENT_NODE_COLOR`
- 节点字体颜色：`GRAPH_NODE_FONT_COLOR`
- 生成 pyvis HTML 图谱：`build_story_brain_graph_html`
- 生成可编辑组件图谱数据：`build_story_brain_graph_data`

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

### APIkey 页组件

见 `web/pages/model_settings.py`：

- APIkey 页渲染：`render`
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

见 `web/components/story_brain_graph/index.html`：

- Story Brain 图谱组件注册名：`story_brain_graph`
- Story Brain 图谱前端入口：`web/components/story_brain_graph/index.html`
- Story Brain 图谱依赖脚本：`web/components/story_brain_graph/vis-network.min.js`
- Story Brain 图谱依赖样式：`web/components/story_brain_graph/vis-network.css`
- 图谱交互能力：拖动画布、双指缩放、普通滚轮平移画布、横向滚动平移画布、禁用普通滚轮缩放、双击节点/关系边编辑并回传 Python 保存、双击图谱背景打开全屏弹窗。

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
- 聊天记录：`ChatRecord`，包含该记录独立的 `story_brain`
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
- Story Brain 小说续写系统规则：`STORY_BRAIN_SYSTEM_RULES`
- Story Brain 更新建议系统规则：`STORY_BRAIN_UPDATE_SYSTEM_PROMPT`
- 获取最近助手回复：`_latest_assistant_message`
- 构造 Memory Pack 识别文本：`_story_brain_memory_source_text`
- 构造 Story Brain Memory Pack JSON：`_build_story_brain_memory_pack_json`
- 注入 Story Brain 到模型 prompt：`_inject_story_brain_into_prompt`
- 解析 Story Brain 更新建议 JSON：`_parse_story_brain_suggested_updates`
- 生成 Story Brain 更新建议：`generate_story_brain_update_suggestions`
- 从设置加载上下文：`load_context_from_settings`
- 保存上下文到设置：`save_context_to_settings`
- 构建上下文消息：`build_context_messages`
- 发送聊天消息：`send_message`
- 生成图片prompt：`generate_image_prompt`
- 生成图片：`generate_image`
- 图生视频：`generate_video_from_image`
- 确保记录 ID：`ensure_record_id`
- 生成记录标题：`make_record_title`
- 新增或更新聊天记录：`upsert_chat_record`

见 `story_brain.py`：

- 创建空 Story Brain：`empty_story_brain`
- 标准化 Story Brain：`normalize_story_brain`
- 加载独立 Story Brain JSON 的兼容工具：`load_story_brain`
- 保存独立 Story Brain JSON 的兼容工具：`save_story_brain`
- 检测当前文本中的活跃角色：`detect_active_characters`
- 构造模型上下文 Memory Pack：`build_memory_pack`
- 压缩 Memory Pack：`compact_memory_pack`
- 输出 Memory Pack JSON：`memory_pack_to_json`
- 构造 Story Brain 更新建议 prompt：`extract_story_brain_update_prompt`
- 应用 Story Brain 更新建议：`apply_story_brain_updates`

见 `graph_view.py`：

- 图谱默认高度：`GRAPH_HEIGHT_PX`
- 图谱节点距离：`GRAPH_NODE_SPACING`
- 图谱颜色常量：`GRAPH_TRAIT_NODE_COLOR`、`GRAPH_CHARACTER_NODE_COLOR`、`GRAPH_EVENT_NODE_COLOR`、`GRAPH_NODE_FONT_COLOR`
- 构造只读 pyvis 图谱 HTML：`build_story_brain_graph_html`
- 构造可编辑 Story Brain 图谱数据：`build_story_brain_graph_data`

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
