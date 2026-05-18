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
