from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from gotify import AsyncGotify
from gotify.response_types import Message
import asyncio

from astrbot.core.message.message_event_result import MessageChain


@register(
    "astrbot_plugin_gotify",
    "BetaCat",
    "此插件可以监听Gotify的消息，并推送给你的机器人",
    "1.0.0",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.context = context
        self.server = config.get("server")
        self.token = config.get("token")
        self.monitor_app_name = set(config.get("application") or [])
        self.chat_id = list(config.get("chat_id") or [])
        self.gotify: AsyncGotify = AsyncGotify(
            base_url=self.server, client_token=self.token
        )

        self.cache_app = {}  # dict{id: application}

        print(self.__dict__)

    async def update_applications(self):
        """更新应用列表"""
        applications = await self.gotify.get_applications()
        self.cache_app = {app.get("id"): app for app in applications if "id" in app}

    async def initialize(self):
        """获取要监听的App。"""
        self.listen_task = asyncio.create_task(self.start_listen())
        logger.info("插件初始化完成")

    async def handle_message(self, msg: Message):
        """处理收到的消息"""
        # 确保appid已记录
        if not self.cache_app.get(msg.get("appid")):
            await self.update_applications()
            # 重新获取应用列表
            if not self.cache_app.get(msg.get("appid")):
                logger.info(f"appid {msg.get('appid')} 不在应用列表中")

        # 获取应用名称
        appname = self.cache_app.get(msg.get("appid")).get("name")

        # 设置了监听的app
        if self.monitor_app_name:
            if appname not in self.monitor_app_name:
                logger.info(f"未监听的App: {msg.get('appname')}")
                return

        for chat_id in self.chat_id:
            sendMsg = MessageChain().message(
                f"📨新消息 \n来源: {appname} \n 标题：{msg.get('title')} \n 内容：{msg.get('message')}"
            )
            await self.context.send_message(chat_id, sendMsg)

    async def start_listen(self):
        """开始监听 Gotify 消息的异步方法，掉线时尝试重连"""
        while True:
            received: int = 0
            try:
                async for msg in self.gotify.stream():
                    logger.info(msg)
                    received = received + 1
                    await self.handle_message(msg)

            except Exception as e:
                logger.error(f"Gotify 连接断开，已收到的消息 {received}，尝试重连: {e}")
            if received == 0:
                await asyncio.sleep(60)  # 等待 1 分钟后重连
        pass

    @filter.command("gotify_register")
    async def helloworld(self, event: AstrMessageEvent):
        logger.info(f"当前的chat_id:{event.unified_msg_origin}")
        self.chat_id.append(event.unified_msg_origin)
        self.chat_id = list(set(self.chat_id))  # 去重
        logger.info(f"当前的chat_id:{self.chat_id}")
        self.config["chat_id"] = self.chat_id
        self.config.save_config()
        logger.info(f"当前config:{self.config}，已保存到配置文件中")
        yield event.stop_event()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        if hasattr(self, "listen_task") and not self.listen_task.done():
            logger.info("Gotify 连接关闭")
            self.listen_task.cancel()
