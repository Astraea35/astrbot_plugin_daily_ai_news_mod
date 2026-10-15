import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

spec = importlib.util.spec_from_file_location(
    "daily_news_telegram_test", Path(__file__).resolve().parents[1] / "main.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.asyncio
async def test_telegram_news_does_not_render_the_qq_image():
    plugin = module.DailyAINewsPlugin.__new__(module.DailyAINewsPlugin)
    plugin.config = {"render_mode": "image"}
    plugin._fetch_rss_latest = AsyncMock(return_value={"link": "https://example.test/news"})
    plugin._parse_article_date = lambda article: "2026-10-14"
    plugin._read_summary_cache = AsyncMock(return_value={})
    plugin._get_or_create_summary = AsyncMock(return_value="📰 **AI 科技早报**\n完整新闻")
    plugin._render_text_to_image = AsyncMock()
    plugin._get_logo_path = lambda: None
    event = SimpleNamespace(
        get_platform_name=lambda: "telegram",
        plain_result=lambda text: text,
        chain_result=lambda chain: chain,
    )
    results = [result async for result in plugin.cmd_ainews(event)]
    assert results[-1] == "📰 **AI 科技早报**\n完整新闻"
    plugin._render_text_to_image.assert_not_awaited()
    plugin._get_or_create_summary.assert_awaited_once_with(
        {"link": "https://example.test/news"}, "2026-10-14", telegram=True,
    )


def test_telegram_news_has_clear_sections_and_preserves_qq_layout():
    plugin = module.DailyAINewsPlugin.__new__(module.DailyAINewsPlugin)
    args = ("新闻标题", "https://example.test/news", "## 要点\n\n1. 第一条\n\n2. 第二条", "2026-10-15")
    telegram = plugin._format_summary(*args, telegram=True)
    qq = plugin._format_summary(*args)
    assert telegram.startswith("📰 **AI 科技早报** · `2026-10-15`\n\n• **主题**：新闻标题\n\n")
    assert "[点击查看完整资讯](https://example.test/news)" in telegram
    assert "> 1. 第一条\n> 2. 第二条" in telegram
    assert "====" not in telegram
    assert "============================" in qq

    # 验证当标题为纯日期时，不生成重复的日期标题行
    date_only_args = ("2026-10-15", "https://example.test/news", "2026年10月15日 AI早报要点\n\n1. 第一条\n\n2. 第二条", "2026-10-15")
    date_telegram = plugin._format_summary(*date_only_args, telegram=True)
    assert "• **主题**" not in date_telegram
    assert date_telegram.count("2026-10-15") == 1
    assert "> 1. 第一条\n> 2. 第二条" in date_telegram

