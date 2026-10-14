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
    plugin._get_or_create_summary = AsyncMock(return_value="**AI 新闻**\n完整新闻")
    plugin._render_text_to_image = AsyncMock()
    event = SimpleNamespace(
        get_platform_name=lambda: "telegram",
        plain_result=lambda text: text,
    )
    results = [result async for result in plugin.cmd_ainews(event)]
    assert results[-1] == "**AI 新闻**\n完整新闻"
    plugin._render_text_to_image.assert_not_awaited()
