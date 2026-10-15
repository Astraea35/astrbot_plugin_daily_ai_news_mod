import asyncio
import json
import os
import re
import time
import threading
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict, Set, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import markdown 

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image
from astrbot.api import AstrBotConfig
from astrbot.api.star import Context, Star, register
from astrbot.api.star import StarTools
from astrbot.api import logger

# RSS 订阅源配置
RSS_URL = "https://daily.juya.uk/rss.xml"

# AI 总结 prompt
SUMMARY_PROMPT = """你是一个专业的 AI 资讯编辑。请将以下 AI 早报内容进行精炼总结，要求：
1. 提取最重要的 5-8 条新闻要点
2. 每条用一句话概括，突出关键信息（公司、产品、技术、数据）
3. 使用简洁的中文表述
4. 在开头加上日期
5. 保持新闻的时效性和准确性

原文内容：
{content}

请输出总结："""


class UniversalPlaywrightRenderer:
    """🚀 Playwright 高清长图渲染引擎架构规范说明书 (终极整合版 V3)"""
    def __init__(self, output_dir: str | Path, image_width: int = 1400, services: object = None) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._image_width = image_width
        self._services = services
        
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._playwright = None
        self._browser = None
        self._last_activity_time = 0.0
        self._cleanup_timer = None

    def _schedule_idle_cleanup(self):
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
        def timer_callback():
            self._executor.submit(self._thread_cleanup_job)
        self._cleanup_timer = threading.Timer(60.0, timer_callback)
        self._cleanup_timer.start()

    def _thread_cleanup_job(self):
        if self._browser and (time.monotonic() - self._last_activity_time >= 60.0):
            try:
                self._browser.close()
                self._playwright.stop()
            except Exception:
                pass
            finally:
                self._browser = None
                self._playwright = None

    def render_html_to_png(self, html_body: str, destination: Path, title_text: str = "AI 总结") -> None:
        base_font_size = 32
        theme = "light"
        img_width = self._image_width
        img_fmt = "png"
        img_quality = 100
        scale_factor = 2 

        if self._services and hasattr(self._services, "config"):
            cfg = self._services.config
            if hasattr(cfg, "get"):
                theme = str(cfg.get("theme", "light")).lower().strip()
                img_width = int(cfg.get("image_width", self._image_width))
                img_fmt = str(cfg.get("image_output_format", "png")).lower().strip()
                img_quality = int(cfg.get("image_quality", 100))
                scale_factor = int(cfg.get("image_scale_factor", 2))
                base_font_size = int(cfg.get("image_font_size", 32))
            else:
                theme = str(getattr(cfg, "theme", "light")).lower().strip()
                img_width = int(getattr(cfg, "image_width", self._image_width))
                img_fmt = str(getattr(cfg, "image_output_format", "png")).lower().strip()
                img_quality = int(getattr(cfg, "image_quality", 100))
                scale_factor = int(getattr(cfg, "image_scale_factor", 2))
                base_font_size = int(getattr(cfg, "image_font_size", 32))

        # 内置全维高保真自适应跨平台复合字体族
        font_declaration = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'HarmonyOS Sans SC', 'Microsoft YaHei', 'Source Han Sans CN', sans-serif"

        if theme == "dark":
            theme_style = f"""
                body, html {{ background-color: #111827 !important; color: #E5E7EB !important; }}
                .card, .markdown-body {{ background: #1F2937 !important; border: 1px solid #374151 !important; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5) !important; }}
                h1, .main-title, h2, h3 {{ color: #F3F4F6 !important; }}
                strong {{ color: #F3F4F6 !important; font-weight: bold !important; }}
                hr {{ border: none; border-top: 2px dashed #374151; margin: 30px 0; }}
            """
        else:
            theme_style = f"""
                body, html {{ background-color: #F8FAFC !important; color: #1E293B !important; }}
                .card, .markdown-body {{ background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05) !important; }}
                h1, .main-title {{ color: #16A34A !important; }}
                strong {{ color: #0F172A !important; font-weight: bold !important; }}
                hr {{ border: none; border-top: 2px dashed #E2E8F0; margin: 30px 0; }}
            """

        mobile_style = f"""
        <style>
            html, body {{ padding-bottom: 100px !important; font-family: {font_declaration} !important; }}
            {theme_style}
            body, .markdown-body {{ font-size: {base_font_size}px !important; line-height: 1.7 !important; padding: {int(base_font_size * 1.3)}px !important; border-radius: 24px !important; }}
            .main-title {{ font-size: {int(base_font_size * 1.8)}px !important; font-weight: bold !important; margin-bottom: 30px; text-align: center; }}
            h2, .section-title {{ font-size: {int(base_font_size * 1.4)}px !important; font-weight: bold !important; margin-top: 35px; margin-bottom: 15px; }}
            p, td, th {{ font-size: {base_font_size}px !important; margin-bottom: 12px; }}
            ul, ol {{ padding-left: {int(base_font_size * 1.5)}px !important; margin-top: 10px !important; margin-bottom: 20px !important; }}
            li {{ font-size: {base_font_size}px !important; margin-bottom: {int(base_font_size * 0.4)}px !important; line-height: 1.6 !important; }}
        </style>
        """
        
        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    {mobile_style}
</head>
<body>
    <div class="main-title">{title_text}</div>
    <div class="markdown-body">{html_body}</div>
</body>
</html>"""

        current_model = "未知模型"
        if self._services:
            try:
                current_id = ""
                cfg = self._services.config
                if cfg:
                    current_id = cfg.get("summary_provider_id", "").strip() if hasattr(cfg, "get") else getattr(cfg, "summary_provider_id", "").strip()
                
                if current_id:
                    current_model = current_id
                else:
                    prov = self._services.context.get_using_provider()
                    if prov:
                        m_name = str(prov.get_model()) if getattr(prov, "get_model", None) else ""
                        p_id = str(prov.meta().id) if getattr(prov, "meta", None) else ""
                        current_model = m_name or p_id or "AstrBot 默认模型"
            except Exception:
                current_model = "AstrBot 默认模型"

        watermark_size = int(base_font_size * 0.65)
        border_color = "#374151" if theme == "dark" else "#E2E8F0"
        model_tag = f'<div style="text-align: center; color: #94A3B8; font-size: {watermark_size}px; margin-top: 40px; padding-top: 15px; border-top: 1px solid {border_color}; font-family: sans-serif; clear: both; width: 100%;">🤖 总结模型: <span style="font-weight: bold; color: #16A34A;">{current_model}</span></div>'
        full_html = full_html.replace("</body>", f"{model_tag}</body>")

        def thread_screenshot_job():
            from playwright.sync_api import sync_playwright
            nonlocal self
            if not self._browser:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=True)
            
            self._last_activity_time = time.monotonic()
            
            page = self._browser.new_page(device_scale_factor=scale_factor, viewport={"width": img_width, "height": 100})
            page.set_content(full_html, wait_until="networkidle")
            page.wait_for_timeout(500)
            
            save_fmt = "jpeg" if img_fmt in ["jpg", "jpeg", "webp"] else "png"
            screenshot_kwargs = {"type": save_fmt}
            if save_fmt == "jpeg": screenshot_kwargs["quality"] = img_quality

            page.locator("body").screenshot(path=str(destination), **screenshot_kwargs)
            page.close()
            self._last_activity_time = time.monotonic()
            self._schedule_idle_cleanup()

        try:
            future = self._executor.submit(thread_screenshot_job)
            future.result()
        except Exception as exc:
            raise RuntimeError(f"Playwright 长图渲染失败: {exc}")


@register(
    "astrbot_plugin_daily_ai_news_mod",
    "Astraea35",
    "订阅橘鸦AI日报并进行AI总结（魔改全控版）",
    "1.0.6",
    "https://github.com/Astraea35/astrbot_plugin_daily_ai_news_mod",
)
class DailyAINewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._task: Optional[asyncio.Task] = None

        self._data_dir = StarTools.get_data_dir("astrbot_plugin_daily_ai_news_mod")
        self._subscriptions_file = self._data_dir / "subscriptions.json"
        self._sent_file = self._data_dir / "sent_news.json"
        self._cache_file = self._data_dir / "summary_cache.json"

        self._cmd_subscriptions: Set[str] = set()
        self._sent_dates: Set[str] = set()
        self._sent_links: Set[str] = set()

        self._file_lock = asyncio.Lock()
        self.renderer = UniversalPlaywrightRenderer(output_dir=self._data_dir / "render", services=self)

    async def initialize(self):
        os.makedirs(self._data_dir, exist_ok=True)
        await self._load_subscriptions()
        await self._load_sent_news()

        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("每日AI资讯推送插件（魔改版）已初始化（V3全要素视网膜渲染引擎已就绪）")

    # ==================== 指令处理 ====================

    @filter.command("ainews")
    async def cmd_ainews(self, event: AstrMessageEvent):
        """手动获取最新 AI 早报"""
        yield event.plain_result("🔄 正在获取最新 AI 早报并进行排版，请稍候...")
        article = await self._fetch_rss_latest()
        if not article:
            yield event.plain_result("😞 暂时未能获取到 AI 早报，请稍后再试。")
            return

        article_date = self._parse_article_date(article)
        telegram = event.get_platform_name() == "telegram"
        cache = await self._read_summary_cache()
        cached = cache.get(article_date)
        
        if cached:
            text = self._format_summary(cached["title"], cached["url"], cached["summary"], article_date, telegram=telegram)
        else:
            text = await self._get_or_create_summary(article, article_date, telegram=telegram)
            if not text:
                yield event.plain_result("😞 获取或生成 AI 早报失败，请稍后再试。")
                return

        if telegram:
            logo_path = self._get_logo_path()
            if logo_path and Image is not None:
                yield event.chain_result([Image.fromFileSystem(logo_path), Plain(text)])
            else:
                yield event.plain_result(text)
            return

        render_mode = self.config.get("render_mode", "text").strip().lower()
        if render_mode == "image":
            img_path = await self._render_text_to_image(text, article_date)
            if img_path and os.path.exists(img_path):
                chain = [
                    Image.fromFileSystem(str(img_path)),
                    Plain(f"\n🔗 快捷点击阅读原文：\n{article['link']}\n💡 发送 /ainews 随时获取最新资讯")
                ]
                yield event.chain_result(chain)
                return
            else:
                logger.warning("图片渲染失败，自动回退文本输出")
        
        yield event.plain_result(text)

    @filter.command("ainews_sub")
    async def cmd_subscribe(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        if umo in self._cmd_subscriptions:
            yield event.plain_result("📢 当前会话已订阅每日AI资讯推送。")
            return
        self._cmd_subscriptions.add(umo)
        await self._save_subscriptions()
        yield event.plain_result("✅ 订阅成功！每日将自动推送 AI 早报到本群。\n取消订阅请发送 /ainews_unsub")

    @filter.command("ainews_unsub")
    async def cmd_unsubscribe(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        if umo not in self._cmd_subscriptions:
            yield event.plain_result("ℹ️ 当前会话未通过指令订阅过 AI 资讯推送。")
            return
        self._cmd_subscriptions.discard(umo)
        await self._save_subscriptions()
        yield event.plain_result("✅ 已取消每日AI资讯推送订阅。")

    @filter.command("ainews_status")
    async def cmd_status(self, event: AstrMessageEvent):
        hour = self.config.get("push_hour", 8)
        minute = self.config.get("push_minute", 0)
        poll_interval = self.config.get("rss_poll_interval", 600)
        cmd_sub_count = len(self._cmd_subscriptions)
        cfg_groups = self._get_config_groups()
        cfg_users = self._get_config_users()

        ai_enabled = "已启用" if self.config.get("enable_ai_summary", True) else "已关闭"
        render_mode_str = "🎨 浏览器长图" if self.config.get("render_mode", "text") == "image" else "📝 纯文本"
        provider_id = self.config.get("summary_provider_id", "").strip()
        provider_info = f"选中模型: {provider_id}" if provider_id else "使用系统默认模型"

        status_text = (
            "📊 **每日AI资讯推送状态 (魔改版)**\n"
            f"📡 数据源：RSS 订阅（橘鸦 AI 日报）\n"
            f"🚀 输出模式：{render_mode_str}\n"
            f"⏰ 首次检查时间：每天 {hour:02d}:{minute:02d}\n"
            f"🔄 轮询间隔：{poll_interval} 秒\n"
            f"🤖 AI 总结：{ai_enabled}\n"
            f"🔧 总结供应商：{provider_info}\n"
            f"📋 指令订阅数：{cmd_sub_count}\n"
            f"📋 配置群聊数：{len(cfg_groups)}\n"
            f"📋 配置私聊数：{len(cfg_users)}\n"
            f"📚 已推送日期缓存：{len(self._sent_dates)} 天\n"
            f"📚 已推送文章缓存：{len(self._sent_links)} 篇"
        )
        yield event.plain_result(status_text)

    # ==================== 工具核心：转换和解析 Markdown ====================

    async def _render_text_to_image(self, text: str, article_date: str) -> Optional[Path]:
        try:
            md_text = re.sub(r'={3,}', '\n---\n', text)
            
            lines = md_text.split("\n")
            if lines and "📰" in lines[0]:
                lines = lines[1:]
            clean_md = "\n".join(lines)
            
            clean_md = clean_md.replace("📌 原文：", "## 📌 原文：")
            clean_md = clean_md.replace("🤖 AI 总结：", "## 🤖 AI 总结：")
            
            html_body = markdown.markdown(clean_md, extensions=['fenced_code', 'tables', 'nl2br'])
            
            destination = self._data_dir / "render" / f"news_{article_date}.png"
            os.makedirs(destination.parent, exist_ok=True)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, 
                self.renderer.render_html_to_png, 
                html_body, 
                destination, 
                f"AI 早报速递 | {article_date}"
            )
            return destination
        except Exception as e:
            logger.error(f"Playwright 图像超采样生成失败: {e}")
            return None

    # ==================== 定时 + 轮询推送 ====================

    async def _schedule_loop(self):
        await self._startup_compensation_check()
        while True:
            try:
                target_hour = self.config.get("push_hour", 8)
                target_minute = self.config.get("push_minute", 0)
                poll_interval = self.config.get("rss_poll_interval", 600)

                now = datetime.now()
                target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                if target <= now: target += timedelta(days=1)

                wait_seconds = (target - now).total_seconds()
                logger.info(f"下次 RSS 检查时间：{target.strftime('%Y-%m-%d %H:%M')}，等待 {wait_seconds:.0f} 秒")
                await asyncio.sleep(wait_seconds)

                today = datetime.now().strftime("%Y-%m-%d")
                if today in self._sent_dates: continue

                pushed = await self._try_fetch_and_push(today)
                if pushed: continue

                logger.info(f"RSS 尚未更新当日 ({today}) 内容，进入轮询模式")
                while True:
                    await asyncio.sleep(poll_interval)
                    if datetime.now().strftime("%Y-%m-%d") != today: break
                    if await self._try_fetch_and_push(today): break
            except asyncio.CancelledError: break
            except Exception as e:
                logger.error(f"定时推送任务出错: {e}")
                await asyncio.sleep(60)

    async def _startup_compensation_check(self):
        try:
            target_hour = self.config.get("push_hour", 8)
            target_minute = self.config.get("push_minute", 0)
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")

            target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if now < target_time or today in self._sent_dates: return

            logger.info(f"启动补偿检查：今日 ({today}) 尚未推送，尝试拉取")
            await self._try_fetch_and_push(today)
        except Exception as e: logger.error(f"启动补偿检查失败: {e}")

    async def _try_fetch_and_push(self, today: str) -> bool:
        try:
            article = await self._fetch_rss_latest()
            if not article: return False
            article_date = self._parse_article_date(article)
            if article_date != today or article["link"] in self._sent_links: return False
            await self._do_push(article, article_date)
            return True
        except Exception as e: return False

    async def _do_push(self, article: Dict, article_date: str):
        text = await self._get_or_create_summary(article, article_date)
        if not text: return
        targets = self._get_all_targets()
        if not targets: return

        render_mode = self.config.get("render_mode", "text").strip().lower()
        if render_mode == "image":
            img_path = await self._render_text_to_image(text, article_date)
            if img_path and os.path.exists(img_path):
                chain = MessageChain([
                    Image.fromFileSystem(str(img_path)),
                    Plain(f"\n🔗 快捷点击阅读原文：\n{article['link']}\n💡 发送 /ainews 随时获取最新资讯")
                ])
            else: chain = MessageChain([Plain(text)])
        else: chain = MessageChain([Plain(text)])

        success_count = 0
        for umo in targets:
            try:
                platform = self.context.get_platform_inst(umo.split(":", 1)[0])
                if platform and platform.meta().name == "telegram":
                    summary_text = await self._get_or_create_summary(article, article_date, telegram=True) or text
                    logo_path = self._get_logo_path()
                    tg_chain = [Plain(summary_text)]
                    if logo_path and Image is not None:
                        tg_chain.insert(0, Image.fromFileSystem(logo_path))
                    outgoing = MessageChain(tg_chain)
                else:
                    outgoing = chain
                await self.context.send_message(umo, outgoing)
                success_count += 1
            except Exception: pass

        if success_count > 0:
            self._sent_dates.add(article_date)
            self._sent_links.add(article["link"])
            if len(self._sent_dates) > 30: self._sent_dates = set(sorted(self._sent_dates)[-30:])
            if len(self._sent_links) > 100: self._sent_links = set(list(self._sent_links)[-100:])
            await self._save_sent_news()

    # ==================== 后台公共方法 ====================

    async def _get_or_create_summary(self, article: Dict, article_date: str, *, telegram: bool = False) -> Optional[str]:
        if not self.config.get("enable_ai_summary", True): return self._format_fallback(article, article_date, telegram=telegram)
        cache = await self._read_summary_cache()
        cached = cache.get(article_date)
        if cached: return self._format_summary(cached["title"], cached["url"], cached["summary"], article_date, telegram=telegram)

        summary = await self._summarize_with_ai(article["content"])
        if summary:
            cache = await self._read_summary_cache()
            cache[article_date] = {"title": article["title"], "url": article["link"], "summary": summary}
            await self._save_summary_cache(cache)
            return self._format_summary(article["title"], article["link"], summary, article_date, telegram=telegram)
        return self._format_fallback(article, article_date, telegram=telegram)

    async def _fetch_rss_latest(self) -> Optional[Dict]:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; AstrBot/3.0)", "Accept": "application/rss+xml, application/xml, */*"}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(RSS_URL, headers=headers) as resp:
                    if resp.status != 200: return None
                    xml_text = await resp.text()

            root = ET.fromstring(xml_text)
            channel = root.find("channel")
            item = channel.find("item") if channel is not None else None
            if item is None: return None

            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            description = item.findtext("description", "").strip()
            encoded_content = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            return {"title": title, "link": link, "content": self._clean_html(encoded_content or description), "pub_date": pub_date}
        except Exception: pass
        return None

    def _parse_article_date(self, article: Dict) -> str:
        title = article.get("title", "")
        match = re.search(r"(\d{4}-\d{2}-\d{2})", title)
        if match: return match.group(1)
        pub_date = article.get("pub_date", "")
        if pub_date:
            try: return parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")
            except Exception: pass
        return datetime.now().strftime("%Y-%m-%d")

    async def _summarize_with_ai(self, content: str) -> Optional[str]:
        if not content or len(content.strip()) < 50: return None
        try:
            if len(content) > 8000: content = content[:8000] + "\n...(内容过长已截断)"
            prompt = SUMMARY_PROMPT.format(content=content)
            
            provider_id = self.config.get("summary_provider_id", "").strip()
            provider = None
            if provider_id:
                try: provider = self.context.get_provider_by_id(provider_id)
                except Exception: pass
            if not provider: provider = self.context.get_using_provider()
            if provider is None: return None
            
            resp = await provider.text_chat(prompt=prompt, session_id="ainews_summary")
            return resp.completion_text.strip() if resp and resp.completion_text else None
        except Exception: pass
        return None

    def _get_logo_path(self) -> Optional[str]:
        base_dir = Path(__file__).resolve().parent
        for candidate in (
            base_dir / "logo.png",
            base_dir / "astrbot_plugin_daily_ai_news_mod" / "logo.png",
        ):
            if candidate.exists() and candidate.stat().st_size > 0:
                return str(candidate)
        return None

    def _format_summary(self, title: str, url: str, summary: str, article_date: str, *, telegram: bool = False) -> str:
        if telegram:
            clean_title = re.sub(r"\s+", " ", title).strip()
            cleaned_lines = []
            for line in summary.strip().splitlines():
                l = line.strip()
                if not l:
                    continue
                if re.match(r"^#{1,6}\s+", l):
                    cleaned_lines.append(f"> **{re.sub(r'^#{1,6}\s+', '', l)}**")
                elif re.match(r"^[-*•]\s+", l):
                    cleaned_lines.append(f"> • {re.sub(r'^[-*•]\s+', '', l)}")
                elif re.match(r"^\d+[.)]\s+", l):
                    cleaned_lines.append(f"> {l}")
                else:
                    cleaned_lines.append(f"> {l}")
            quote_block = "\n".join(cleaned_lines) if cleaned_lines else f"> {summary.strip()}"
            link_str = f"[阅读原文]({url})" if url else "暂无"
            return (
                f"📰 **AI 科技早报** · `{article_date}`\n\n"
                f"**【{clean_title}】**\n\n"
                f"{quote_block}\n\n"
                f"🔗 来源：{link_str}"
            )
        return f"📰 AI 早报速递 | {article_date}\n============================\n\n📌 原文：{title}\n\n🤖 AI 总结：\n\n{summary}\n\n============================\n🔗 原文链接：{url}\n💡 发送 /ainews 随时获取最新资讯"

    def _format_fallback(self, article: Dict, article_date: str, *, telegram: bool = False) -> str:
        content = article.get("content", "")
        if len(content) > 500: content = content[:500] + "..."
        if telegram:
            return self._format_summary(article["title"], article.get("link", ""), content, article_date, telegram=True)
        return f"📰 AI 早报 | {article_date}\n============================\n\n📌 {article['title']}\n\n{content}\n\n============================\n🔗 原文链接：{article.get('link', '')}\n💡 发送 /ainews 随时获取最新资讯"

    def _clean_html(self, text: str) -> str:
        if not text: return ""
        clean = re.sub(r"<[^>]+>", "", text)
        return clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').strip()

    def _get_config_groups(self) -> List[str]:
        t = self.config.get("subscribed_groups", "")
        return [g.strip() for g in t.strip().split("\n") if g.strip()] if t.strip() else []

    def _get_config_users(self) -> List[str]:
        t = self.config.get("subscribed_users", "")
        return [u.strip() for u in t.strip().split("\n") if u.strip()] if t.strip() else []

    def _get_all_targets(self) -> Set[str]:
        targets = set(self._cmd_subscriptions)
        for g in self._get_config_groups():
            p = g.split(":")
            targets.add(f"{p[0]}:GroupMessage:{p[1]}" if len(p)==2 else (g if len(p)==3 else f"default:GroupMessage:{g}"))
        for u in self._get_config_users():
            p = u.strip().split(":")
            targets.add(f"{p[0]}:FriendMessage:{p[1]}" if len(p)==2 else (u if len(p)==3 else f"default:FriendMessage:{u}"))
        return targets

    def _atomic_write(self, filepath, data: dict):
        dir_path = os.path.dirname(str(filepath))
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(filepath))
        except Exception:
            try: os.unlink(tmp_path)
            except OSError: pass
            raise

    async def _load_subscriptions(self):
        async with self._file_lock:
            try:
                if os.path.exists(str(self._subscriptions_file)):
                    with open(str(self._subscriptions_file), "r", encoding="utf-8") as f: self._cmd_subscriptions = set(json.load(f).get("subscriptions", []))
            except Exception: pass

    async def _save_subscriptions(self):
        async with self._file_lock:
            try: self._atomic_write(self._subscriptions_file, {"subscriptions": list(self._cmd_subscriptions)})
            except Exception: pass

    async def _load_sent_news(self):
        async with self._file_lock:
            try:
                if os.path.exists(str(self._sent_file)):
                    with open(str(self._sent_file), "r", encoding="utf-8") as f: data = json.load(f)
                    if "sent_ids" in data:
                        for item in set(data.get("sent_ids", [])):
                            self._sent_dates.add(item) if re.match(r"\d{4}-\d{2}-\d{2}$", item) else self._sent_links.add(item)
                    else:
                        self._sent_dates = set(data.get("sent_dates", []))
                        self._sent_links = set(data.get("sent_links", []))
            except Exception: pass

    async def _save_sent_news(self):
        async with self._file_lock:
            try: self._atomic_write(self._sent_file, {"sent_dates": sorted(self._sent_dates), "sent_links": list(self._sent_links)})
            except Exception: pass

    async def _read_summary_cache(self) -> Dict[str, Dict]:
        async with self._file_lock:
            try:
                if os.path.exists(str(self._cache_file)):
                    with open(str(self._cache_file), "r", encoding="utf-8") as f: return json.load(f)
            except Exception: pass
            return {}

    async def _save_summary_cache(self, cache: Dict[str, Dict]):
        async with self._file_lock:
            try:
                if len(cache) > 10: cache = {k: cache[k] for k in sorted(cache.keys())[-10:]}
                self._atomic_write(self._cache_file, cache)
            except Exception: pass
