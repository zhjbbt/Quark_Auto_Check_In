"""PushPlus notification helper (WeChat push through pushplus.plus).

The module only relies on the standard library so that it can be used as a
standalone fallback inside a workflow step, even when ``pip install`` failed.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import urllib.error
import urllib.request

PUSHPLUS_URL = "https://www.pushplus.plus/send"
DEFAULT_CHANNEL = "wechat"
DEFAULT_TEMPLATE = "html"


class PushPlusError(RuntimeError):
    """Raised when PushPlus rejects a message or cannot be reached."""


def render_html(text: str) -> str:
    """Escape plain text and turn line breaks into ``<br>`` tags.

    The ``html`` template renders the content as HTML, so the raw summary has
    to be escaped first; otherwise characters such as ``&`` would break the
    markup.
    """

    return html.escape(text, quote=False).replace("\n", "<br>")


class PushPlusNotifier:
    """Send a message to WeChat through the PushPlus HTTP API."""

    def __init__(
        self,
        token: str,
        topic: str = "",
        channel: str = DEFAULT_CHANNEL,
        template: str = DEFAULT_TEMPLATE,
        timeout: int = 15,
    ) -> None:
        if not token:
            raise PushPlusError("未配置 PushPlus token")
        self.token = token
        self.topic = topic
        self.channel = channel
        self.template = template
        self.timeout = timeout

    def build_payload(self, title: str, content: str) -> dict:
        """Build the JSON body accepted by ``POST /send``."""

        payload = {
            "token": self.token,
            "title": title,
            "content": (
                render_html(content) if self.template == "html" else content
            ),
            "template": self.template,
            "channel": self.channel,
        }
        if self.topic:
            payload["topic"] = self.topic
        return payload

    def send(self, title: str, content: str) -> dict:
        """Push a message and return the decoded API response."""

        payload = self.build_payload(title, content)
        request = urllib.request.Request(
            PUSHPLUS_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise PushPlusError(f"PushPlus 请求失败（HTTP {exc.code}）") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PushPlusError(
                f"PushPlus 网络错误（{type(exc).__name__}）"
            ) from exc

        try:
            result = json.loads(raw)
        except ValueError as exc:
            raise PushPlusError("PushPlus 返回了无法解析的数据") from exc

        if not isinstance(result, dict):
            raise PushPlusError("PushPlus 返回格式异常")

        code = result.get("code")
        if code != 200:
            detail = result.get("msg") or result.get("message") or "未知错误"
            raise PushPlusError(f"PushPlus 推送失败（code={code}）：{detail}")
        return result


def notifier_from_env(env: dict | None = None) -> PushPlusNotifier | None:
    """Build a notifier from environment variables.

    Returns ``None`` when no token is configured, which keeps the workflow
    usable without PushPlus.
    """

    env = os.environ if env is None else env
    token = (env.get("PUSHPLUS_TOKEN") or "").strip()
    if not token:
        return None
    topic = (env.get("PUSHPLUS_TOPIC") or "").strip()
    return PushPlusNotifier(token=token, topic=topic)


def push(title: str, content: str, notifier: PushPlusNotifier | None = None) -> bool:
    """Best-effort notification helper.

    Never raises: a failed push must not turn a successful sign-in into a
    failed workflow run.
    """

    if notifier is None:
        notifier = notifier_from_env()
    if notifier is None:
        print("ℹ️ 未配置 PUSHPLUS_TOKEN，跳过微信推送。")
        return False
    try:
        notifier.send(title, content)
    except PushPlusError as exc:
        print(f"⚠️ 微信推送失败：{exc}")
        return False
    print("✅ 微信推送成功。")
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by the workflow fallback step."""

    parser = argparse.ArgumentParser(description="Send a PushPlus notification.")
    parser.add_argument("--title", default="GitHub Actions")
    parser.add_argument("--content", default="Notification from GitHub Actions.")
    args = parser.parse_args(argv)

    notifier = notifier_from_env()
    if notifier is None:
        print("未配置 PUSHPLUS_TOKEN，跳过推送。")
        return 0
    try:
        notifier.send(args.title, args.content)
    except PushPlusError as exc:
        print(f"PushPlus 推送失败：{exc}")
        return 1
    print("PushPlus 推送成功。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
