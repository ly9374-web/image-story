import unittest
from unittest.mock import patch

from app.models import Page2ConversationTurn
from app.services import page2_service
from web.pages.page2 import _roll_user_dice_message


class Page2PromptAssemblyTests(unittest.TestCase):
    def test_short_story_brain_is_only_in_current_user_prompt(self):
        ctx = page2_service.default_context()
        ctx.system_prompt = "原始 system"
        ctx.story_brain_mode = page2_service.STORY_BRAIN_SHORT
        turns = [Page2ConversationTurn(user_message="旧用户消息", assistant_message="旧回复")]

        with patch.object(
            page2_service.GrokAPIClient,
            "send_message",
            return_value="新回复",
        ) as send_message:
            result = page2_service.send_message(
                ctx=ctx,
                turns=turns,
                user_message="打开门",
                story_brain={},
                story_brain_short="雨夜的旅店",
                story_brain_enabled=True,
            )

        self.assertEqual(result, "新回复")
        kwargs = send_message.call_args.kwargs
        self.assertEqual(kwargs["system_prompt"], "原始 system")
        self.assertEqual(
            kwargs["user_message"],
            "<当前故事背景>雨夜的旅店</当前故事背景>\n\n打开门",
        )
        self.assertEqual(
            kwargs["context_messages"],
            [
                {"role": "user", "content": "旧用户消息"},
                {"role": "assistant", "content": "旧回复"},
            ],
        )

    def test_unexpected_event_roll_is_separate_and_hidden_from_context(self):
        ctx = page2_service.default_context()
        ctx.unexpected_event_enabled = True
        ctx.unexpected_event_threshold = 20
        turns = [Page2ConversationTurn(user_message="历史用户消息", assistant_message="历史回复")]

        with (
            patch.object(page2_service, "roll_point", return_value=20) as roll_point,
            patch.object(
                page2_service.GrokAPIClient,
                "send_message",
                return_value="意外后的回复",
            ) as send_message,
        ):
            page2_service.send_message(
                ctx=ctx,
                turns=turns,
                user_message="继续前进",
                story_brain={},
                story_brain_enabled=False,
            )

        roll_point.assert_called_once_with()
        kwargs = send_message.call_args.kwargs
        self.assertTrue(kwargs["user_message"].startswith("继续前进\n\n"))
        self.assertIn(page2_service.UNEXPECTED_EVENT_PROMPT, kwargs["user_message"])
        self.assertNotIn(
            page2_service.UNEXPECTED_EVENT_PROMPT,
            str(kwargs["context_messages"]),
        )

    def test_unexpected_event_is_not_added_below_threshold(self):
        ctx = page2_service.default_context()
        ctx.unexpected_event_enabled = True
        ctx.unexpected_event_threshold = 20

        with (
            patch.object(page2_service, "roll_point", return_value=19),
            patch.object(
                page2_service.GrokAPIClient,
                "send_message",
                return_value="普通回复",
            ) as send_message,
        ):
            page2_service.send_message(
                ctx=ctx,
                turns=[],
                user_message="继续前进",
                story_brain={},
                story_brain_enabled=False,
            )

        self.assertEqual(send_message.call_args.kwargs["user_message"], "继续前进")

    def test_roll_point_uses_uniform_0_to_24_source(self):
        with patch.object(page2_service.secrets, "randbelow", return_value=12) as randbelow:
            self.assertEqual(page2_service.roll_point(), 12)
        randbelow.assert_called_once_with(25)


class UserDiceFormattingTests(unittest.TestCase):
    def test_user_dice_is_a_single_sendable_message_without_numbering(self):
        with patch.object(page2_service, "roll_point", return_value=7):
            self.assertEqual(_roll_user_dice_message(), "掷骰结果：“7”")

    def test_short_story_brain_is_injected_even_when_update_is_not_due(self):
        ctx = page2_service.default_context()
        ctx.story_brain_mode = page2_service.STORY_BRAIN_SHORT
        ctx.story_brain_turns = 10

        with patch.object(
            page2_service.GrokAPIClient,
            "send_message",
            return_value="回复",
        ) as send_message:
            page2_service.send_message(
                ctx=ctx,
                turns=[],
                user_message="继续",
                story_brain={},
                story_brain_short="当前剧情",
                story_brain_enabled=True,
            )

        self.assertEqual(
            send_message.call_args.kwargs["user_message"],
            "<当前故事背景>当前剧情</当前故事背景>\n\n继续",
        )


if __name__ == "__main__":
    unittest.main()
