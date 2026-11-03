import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

import pushplus
from pushplus import (
    PushPlusError,
    PushPlusNotifier,
    notifier_from_env,
    render_html,
)


class RenderHtmlTests(unittest.TestCase):
    def test_line_breaks_become_br_tags(self):
        self.assertEqual(render_html("a\nb"), "a<br>b")

    def test_html_special_characters_are_escaped(self):
        self.assertEqual(render_html("A&B <c>"), "A&amp;B &lt;c&gt;")

    def test_emoji_and_chinese_are_preserved(self):
        self.assertEqual(render_html("✅ 签到成功"), "✅ 签到成功")


class PayloadTests(unittest.TestCase):
    def test_payload_contains_required_fields(self):
        notifier = PushPlusNotifier(token="tk")
        payload = notifier.build_payload("标题", "正文")
        self.assertEqual(payload["token"], "tk")
        self.assertEqual(payload["title"], "标题")
        self.assertEqual(payload["content"], "正文")
        self.assertEqual(payload["template"], "html")
        self.assertEqual(payload["channel"], "wechat")

    def test_topic_is_only_included_when_set(self):
        without = PushPlusNotifier(token="tk").build_payload("t", "c")
        with_topic = PushPlusNotifier(token="tk", topic="grp").build_payload("t", "c")
        self.assertNotIn("topic", without)
        self.assertEqual(with_topic["topic"], "grp")

    def test_empty_token_is_rejected(self):
        with self.assertRaises(PushPlusError):
            PushPlusNotifier(token="")


class SendTests(unittest.TestCase):
    def _response(self, payload):
        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__ = lambda self_: self_
        response.__exit__ = lambda *args: False
        return response

    def test_successful_send_returns_payload(self):
        notifier = PushPlusNotifier(token="tk")
        with mock.patch.object(
            pushplus.urllib.request, "urlopen", return_value=self._response({"code": 200})
        ):
            result = notifier.send("标题", "正文")
        self.assertEqual(result["code"], 200)

    def test_non_200_code_raises(self):
        notifier = PushPlusNotifier(token="tk")
        with mock.patch.object(
            pushplus.urllib.request,
            "urlopen",
            return_value=self._response({"code": 401, "msg": "token无效"}),
        ):
            with self.assertRaisesRegex(PushPlusError, "token无效"):
                notifier.send("标题", "正文")

    def test_invalid_json_raises(self):
        response = mock.MagicMock()
        response.read.return_value = b"not-json"
        response.__enter__ = lambda self_: self_
        response.__exit__ = lambda *args: False
        notifier = PushPlusNotifier(token="tk")
        with mock.patch.object(pushplus.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(PushPlusError, "无法解析"):
                notifier.send("标题", "正文")

    def test_network_error_raises_pushplus_error(self):
        notifier = PushPlusNotifier(token="tk")
        with mock.patch.object(
            pushplus.urllib.request,
            "urlopen",
            side_effect=pushplus.urllib.error.URLError("boom"),
        ):
            with self.assertRaisesRegex(PushPlusError, "网络错误"):
                notifier.send("标题", "正文")


class EnvTests(unittest.TestCase):
    def test_notifier_is_none_without_token(self):
        self.assertIsNone(notifier_from_env({}))

    def test_notifier_is_built_from_token(self):
        notifier = notifier_from_env({"PUSHPLUS_TOKEN": " tk "})
        self.assertIsNotNone(notifier)
        self.assertEqual(notifier.token, "tk")

    def test_topic_is_read_from_env(self):
        notifier = notifier_from_env(
            {"PUSHPLUS_TOKEN": "tk", "PUSHPLUS_TOPIC": "grp"}
        )
        self.assertEqual(notifier.topic, "grp")

    def test_push_without_token_returns_false(self):
        with redirect_stdout(io.StringIO()):
            self.assertFalse(pushplus.push("标题", "正文", notifier_from_env({})))

    def test_push_failure_is_swallowed(self):
        notifier = mock.MagicMock()
        notifier.send.side_effect = PushPlusError("网络错误")
        with redirect_stdout(io.StringIO()):
            self.assertFalse(pushplus.push("标题", "正文", notifier))


class CliTests(unittest.TestCase):
    def test_cli_without_token_exits_zero(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(pushplus.main(["--title", "t", "--content", "c"]), 0)

    def test_cli_sends_message(self):
        with mock.patch.dict("os.environ", {"PUSHPLUS_TOKEN": "tk"}, clear=True):
            with mock.patch.object(PushPlusNotifier, "send") as send:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(pushplus.main(["--title", "t", "--content", "c"]), 0)
        send.assert_called_once_with("t", "c")

    def test_cli_reports_failure(self):
        with mock.patch.dict("os.environ", {"PUSHPLUS_TOKEN": "tk"}, clear=True):
            with mock.patch.object(
                PushPlusNotifier, "send", side_effect=PushPlusError("boom")
            ):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(pushplus.main(["--title", "t", "--content", "c"]), 1)


if __name__ == "__main__":
    unittest.main()
