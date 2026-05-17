import json
from dataclasses import dataclass
from typing import Optional, List

import requests

from app.config import (
    XAIConfig,
    DeepSeekConfig,
    debug_log,
    mask_authorization_header,
)


# =========================
# 对应 Swift: GrokResponseResult
# =========================

@dataclass
class GrokResponseResult:
    id: Optional[str]
    text: str


# =========================
# 对应 Swift: GrokInputMessage
# =========================

@dataclass
class GrokInputMessage:
    role: str
    content: str

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
        }


# =========================
# 对应 Swift: GrokAPIClient
# =========================

class GrokAPIClient:
    """
    对应 Swift 里的 final class GrokAPIClient。

    功能：
    1. 普通聊天 send_message()
    2. 生成图片 prompt generate_image_prompt()
    3. 第一人称图片 prompt generate_first_person_image_prompt()
    4. 人物特写图片 prompt generate_character_closeup_image_prompt()
    5. 解析 Grok Responses API 返回
    """

    RESPONSES_URL = "https://api.x.ai/v1/responses"

    @classmethod
    def send_message(
        cls,
        system_prompt,
        context_messages,
        user_message,
        model="grok-4-1-fast-reasoning",
        temperature=0.8,
    ):
        """
        对应 Swift:
        sendMessage(systemPrompt:contextMessages:userMessage:model:temperature:)
        """

        input_messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        for message in context_messages:
            if isinstance(message, GrokInputMessage):
                input_messages.append(message.to_dict())
            elif isinstance(message, dict):
                input_messages.append(message)

        input_messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        body = {
            "model": model,
            "input": input_messages,
            "temperature": temperature,
        }

        data = cls._post_responses(body, label="Grok Request")
        return cls.parse_response(data).text

    @classmethod
    def generate_image_prompt(cls, user_message):
        """
        对应 Swift:
        generateImagePrompt(from userMessage:)
        """

        system_prompt = """
# 根据 userMessage 生成一个图片描述，以以下模板提取画面主要角色并描述画面，提到人物时描写人物：

场景：[此处描述角色所处环境]
人物：[此处描述画面中有几个人物，角色长相和穿着、特征、人物的动作和互动]
摄像头角度：[此处描述摄像头以什么角度看到画面]
画风：
#限制：总字数少于130字，仅客观具体的描述画面，不用抽象词语，不描述氛围和心情
# 案例：
场景：学校教室
人物：漂亮的亚洲老师穿着教师服，站在讲台上面对学生，表情悲伤。可爱且白皙皮肤的亚洲学生穿着校服，学生站在桌子旁，脸上有伤。
摄像头角度：面对老师的斜前方
画风：写实
""".strip()

        body = {
            "model": "grok-4-1-fast-reasoning",
            "input": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
        }

        data = cls._post_responses(body, label="Grok Prompt Request")
        return cls.parse_response(data).text

    @classmethod
    def generate_first_person_image_prompt(cls, user_message, subject):
        """
        对应 Swift:
        generateFirstPersonImagePrompt(from userMessage:subject:)
        """

        subject = str(subject or "").strip()
        if not subject:
            raise ValueError("Subject is empty")

        system_prompt = (
            f"分析我给你的故事，以“{subject}”为第一人称，并用“我”代指自己的名字，"
            f"使用客观具体的描述，最终输出不超过100字“{subject}”所看到的画面，"
            f"用第一人称“我”来描述所看到的画面。禁止使用抽象的词汇，"
            f"禁止生成“{subject}”看不到的内容，比如“{subject}”的形象，"
            f"“{subject}”背后的环境，禁止使用成语抽象描述场景。"
            f"并且在prompt中描述“{subject}”的一个肢体在画面何处出现输出少于150字。"
            "输出结尾加上“摄像头视角：我的第一人称视角”和“画风：写实”\n"
            "案例：我看到前方有一位黄头发蓝眼睛的可爱亚洲成年女性蹲在教室的地面上，"
            "她的表情悲伤，穿着校服。背景是教室，周围有其他学生，后面的光线昏暗发黄。"
            "画面左侧伸出我拿着铅笔的手指着那位女生 摄像头视角：我的第一人称视角 画风：写实"
        )

        body = {
            "model": "grok-4-1-fast-reasoning",
            "input": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
        }

        data = cls._post_responses(body, label="Grok First Person Prompt Request")
        return cls.parse_response(data).text

    @classmethod
    def generate_character_closeup_image_prompt(cls, user_message, subject):
        """
        对应 Swift:
        generateCharacterCloseupImagePrompt(from userMessage:subject:)
        """

        subject = str(subject or "").strip()
        if not subject:
            raise ValueError("Character closeup subject is empty")

        system_prompt = f"""
根据 userMessage 生成一个图片描述，以以下模板提取画面主要角并生成{subject}的人物特写，不要出现{subject}的人物的名字，给我详细描述{subject}的外貌,穿着，姿势，状态，表情，特征,还有场景背景。描述中不要出现别的角色。最终输出字数不超过80字
范例：一个漂亮皮肤白皙的蓝头发女生。女生带着红色帽子，穿着蓝色格子校服，脸上有泪痕，头上有杂草。女生左手举起右手放松的放在大腿上，两腿分开。女生眉毛皱起，眼睛眯成一条缝露出一个勉强的微笑。背景是学校的老师办公室
""".strip()

        body = {
            "model": "grok-4-1-fast-reasoning",
            "input": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
        }

        data = cls._post_responses(body, label="Grok Character Closeup Prompt Request")
        return cls.parse_response(data).text

    @classmethod
    def _post_responses(cls, body, label="Grok Request"):
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + XAIConfig.chat_api_key(),
        }

        debug_log("====== " + label + " ======")
        debug_log("URL:", cls.RESPONSES_URL)
        debug_log("Authorization:", mask_authorization_header(headers["Authorization"]))
        debug_log("Body:", json.dumps(body, ensure_ascii=False))

        response = requests.post(
            cls.RESPONSES_URL,
            headers=headers,
            json=body,
            timeout=3600,
        )

        debug_log("====== " + label + " HTTP Status ======")
        debug_log(response.status_code)

        debug_log("====== " + label + " Raw Response ======")
        debug_log(response.text)

        try:
            data = response.json()
        except Exception:
            return {
                "error": {
                    "message": "Grok 返回内容不是 JSON：" + response.text
                }
            }

        return data

    @staticmethod
    def parse_response(data):
        """
        对应 Swift:
        private static func parseResponse(from data: Data, rawResponse: String? = nil)
        """

        if not isinstance(data, dict):
            return GrokResponseResult(
                id=None,
                text="未解析到 Grok 回复内容。",
            )

        response_id = data.get("id")

        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or "unknown"
            return GrokResponseResult(
                id=response_id,
                text="Grok API 错误：" + str(message),
            )

        if isinstance(error, str) and error.strip():
            return GrokResponseResult(
                id=response_id,
                text="Grok API 错误：" + error,
            )

        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return GrokResponseResult(
                id=response_id,
                text=output_text,
            )

        pieces = []

        output = data.get("output")
        if isinstance(output, list):
            extracted_from_message_items = False

            # 优先只取 type == message 的 output_text
            for item in output:
                if not isinstance(item, dict):
                    continue

                if item.get("type") != "message":
                    continue

                extracted_from_message_items = True

                content_array = item.get("content")
                if not isinstance(content_array, list):
                    continue

                for block in content_array:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "output_text":
                        text = block.get("text")
                        if isinstance(text, str) and text.strip():
                            pieces.append(text)

            # 兼容其他返回结构
            if not extracted_from_message_items:
                for item in output:
                    if not isinstance(item, dict):
                        continue

                    content_array = item.get("content")
                    if isinstance(content_array, list):
                        for block in content_array:
                            if not isinstance(block, dict):
                                continue

                            text = block.get("text") or block.get("content")
                            if isinstance(text, str) and text.strip():
                                pieces.append(text)

                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        pieces.append(text)

                    message = item.get("message")
                    if isinstance(message, dict):
                        message_content = message.get("content")

                        if isinstance(message_content, str) and message_content.strip():
                            pieces.append(message_content)

                        if isinstance(message_content, list):
                            for block in message_content:
                                if not isinstance(block, dict):
                                    continue

                                text = block.get("text") or block.get("content")
                                if isinstance(text, str) and text.strip():
                                    pieces.append(text)

        # 去重，避免上下文污染
        seen = set()
        unique_pieces = []

        for piece in pieces:
            text = str(piece).strip()
            if not text:
                continue

            if text not in seen:
                seen.add(text)
                unique_pieces.append(text)

        combined = "\n".join(unique_pieces).strip()

        if not combined:
            return GrokResponseResult(
                id=response_id,
                text="未解析到 Grok 回复内容。",
            )

        return GrokResponseResult(
            id=response_id,
            text=combined,
        )


# =========================
# 对应 Swift: DeepSeekAPIClient
# =========================

class DeepSeekAPIClient:
    """
    对应 Swift 里的 final class DeepSeekAPIClient。
    """

    CHAT_URL = "https://api.deepseek.com/v1/chat/completions"

    @classmethod
    def send_message(
        cls,
        system_prompt,
        context_messages,
        user_message,
        temperature=0.8,
    ):
        """
        对应 Swift:
        sendMessage(systemPrompt:contextMessages:userMessage:temperature:)
        """

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        for message in context_messages:
            if isinstance(message, GrokInputMessage):
                messages.append(message.to_dict())
            elif isinstance(message, dict):
                messages.append(message)

        messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + DeepSeekConfig.api_key(),
        }

        body = {
            "messages": messages,
            "model": "deepseek-v4-pro",
            "thinking": {
                "type": "enabled",
            },
            "reasoning_effort": "high",
            "max_tokens": 4096,
            "response_format": {
                "type": "text",
            },
            "stream": False,
            "temperature": temperature,
            "top_p": 1,
            "tool_choice": "none",
            "logprobs": False,
        }

        debug_log("====== DeepSeek Chat Request ======")
        debug_log("URL:", cls.CHAT_URL)
        debug_log("Authorization:", mask_authorization_header(headers["Authorization"]))
        debug_log("Body:", json.dumps(body, ensure_ascii=False))

        response = requests.post(
            cls.CHAT_URL,
            headers=headers,
            json=body,
            timeout=3600,
        )

        debug_log("====== DeepSeek Chat HTTP Status ======")
        debug_log(response.status_code)

        debug_log("====== DeepSeek Chat Raw Response ======")
        debug_log(response.text)

        try:
            data = response.json()
        except Exception:
            return "未解析到 DeepSeek 回复内容。"

        if data.get("error"):
            debug_log("====== DeepSeek Chat Error ======")
            debug_log(data.get("error"))
            raise RuntimeError("DeepSeek API error: " + str(data.get("error")))

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return "未解析到 DeepSeek 回复内容。"

        first = choices[0]
        if not isinstance(first, dict):
            return "未解析到 DeepSeek 回复内容。"

        message = first.get("message")
        if not isinstance(message, dict):
            return "未解析到 DeepSeek 回复内容。"

        content = message.get("content")
        if not isinstance(content, str):
            return "未解析到 DeepSeek 回复内容。"

        content = content.strip()
        return content if content else "未解析到 DeepSeek 回复内容。"