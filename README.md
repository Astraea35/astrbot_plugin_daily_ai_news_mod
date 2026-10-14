# astrbot_plugin_daily_ai_news_mod

Telegram 的手动查询和订阅推送默认使用 Markdown 文字，以标题、日期、分段正文和原文链接排版。QQ 保留配置的长图
模式。通过 NAS 联动平台使用时，处理中提示和结果会编辑同一条 TG 消息。

每日 AI 资讯自动推送插件 (魔改版) - 为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 开发

通过 RSS 订阅 [橘鸦 AI 日报](https://daily.juya.uk/rss.xml) 获取最新 AI 早报，经 **AI 总结** 后自动推送到各平台群聊 / 私聊。支持通过 Playwright 进行长图高清无缝渲染推送。

## ✨ 功能特点

- 📰 **每日自动推送**：每天定时（默认早 8:00）自动推送最新 AI 资讯
- 🤖 **AI 智能总结**：调用 AstrBot 配置的 LLM，将长篇早报精炼为 5-8 条关键要点
- 🎨 **Playwright 渲染长图**：支持直接将排版后的 AI 总结转化为超高清长图并进行视网膜超采样导出
- 🔄 **手动获取**：发送 `/ainews` 随时获取最新 AI 资讯
- 📋 **灵活订阅**：支持配置文件填写群号/QQ号 + 聊天内指令订阅两种方式
- ⏳ **智能轮询**：若 RSS 尚未更新当日内容，插件会自动间隔轮询直到获取到当日文章
- 💾 **缓存去重**：AI 总结结果自动缓存，规避重复调用 LLM

## 📝 指令列表

| 指令             | 说明                              |
| ---------------- | --------------------------------- |
| `/ainews`        | 立即获取最新 AI 资讯（AI 总结版） |
| `/ainews_sub`    | 订阅每日推送（群聊/私聊均可使用） |
| `/ainews_unsub`  | 取消每日推送订阅                  |
| `/ainews_status` | 查看推送状态与订阅信息            |

## 📦 安装与升级

直接在 AstrBot 的插件目录 `addons/plugins/` 下执行克隆：

```bash
git clone [https://github.com/Astraea35/astrbot_plugin_daily_ai_news_mod.git](https://github.com/Astraea35/astrbot_plugin_daily_ai_news_mod.git)
后续更新只需在插件目录下执行 git pull 即可无缝拉取升级。

📄 License
AGPL-3.0
