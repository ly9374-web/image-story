# Swift 项目的 Python 拆分版骨架

这是把原 SwiftUI 大文件按 Python 项目结构拆开的第一版。

运行方式：

```bash
cd python_app_split
pip install -r requirements.txt
python main.py
```

你需要把自己的 API Key 填到“模型”页面，或者设置环境变量：
- XAI_CHAT_API_KEY
- XAI_IMAGE_API_KEY
- REPLICATE_API_TOKEN
- DEEPSEEK_API_KEY
- DOMOAI_API_KEY
- ZHIPU_API_KEY

说明：
- 这个版本是 Python 桌面版，不是 iOS App。
- SwiftUI 的页面结构被转换成 tkinter 页面。
- API 调用、聊天记录、模型设置、Page2 主聊天页已经拆成单独文件。
# Streamlit 版本（进行中）

运行：

```bash
streamlit run streamlit_app.py
```
