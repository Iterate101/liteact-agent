import os
import json
import asyncio
import traceback
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 飞书官方 SDK 高级组件
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi.api.application.v6 import *
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

class FeishuClient:
    """
    【飞书旗舰版适配器 - 防御增强版】
    具备全链路异常捕获与状态自检功能。
    """

    def __init__(
        self, 
        app_id: str, 
        app_secret: str, 
        sessions_dir: str = "sessions"
    ):
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
            
        self.sessions_dir = Path(sessions_dir).resolve()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # 显式初始化回调
        self.on_message_handler = None
        self.loop = asyncio.get_event_loop()

    def get_event_handler(self) -> lark.EventDispatcherHandler:
        """【神经中枢】构建事件分发器对象"""
        return lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._do_p2_im_message_receive_v1) \
            .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(self._do_p2p_chat_entered) \
            .register_p2_card_action_trigger(self._do_card_action_trigger) \
            .build()

    def _do_p2_im_message_receive_v1(self, data: P2ImMessageReceiveV1) -> None:
        """【同步入口】转发至异步处理"""
        print(f"DEBUG: [收到飞书消息事件] ID: {data.event.message.message_id}")
        # 确保跨线程调度
        asyncio.run_coroutine_threadsafe(self._async_handle_message(data), self.loop)

    async def _async_handle_message(self, data: P2ImMessageReceiveV1) -> None:
        """【核心异步处理器】带异常护盾版"""
        try:
            msg = data.event.message
            sender = data.event.sender
            chat_id = msg.chat_id
            
            content_json = json.loads(msg.content)
            user_text = ""
            
            # 【消息类型自适应解析】
            if msg.message_type == "text":
                user_text = content_json.get("text", "")
            elif msg.message_type == "post":
                # 解析富文本中的文字和链接
                post_content = content_json.get("content", [])
                text_parts = []
                for paragraph in post_content:
                    for element in paragraph:
                        tag = element.get("tag")
                        if tag == "text":
                            text_parts.append(element.get("text", ""))
                        elif tag == "a":
                            # 提取超链接中的文字，并可选附带 URL
                            link_text = element.get("text", "")
                            link_url = element.get("href", "")
                            text_parts.append(f"{link_text} ({link_url})")
                user_text = "".join(text_parts)
            
            print(f"DEBUG: [核心提取成功] Text: '{user_text}' | ChatID: {chat_id}")

            attachment_dir = self.sessions_dir / chat_id / "attachments"
            attachment_dir.mkdir(parents=True, exist_ok=True)
            attachments = []

            # 资源下载逻辑（带防御）
            if msg.message_type == "image":
                path = await self.download_resource(msg.message_id, content_json.get("image_key"), "image", attachment_dir)
                if path: attachments.append(path)
            elif msg.message_type == "file":
                path = await self.download_resource(msg.message_id, content_json.get("file_key"), "file", attachment_dir, content_json.get("file_name"))
                if path: attachments.append(path)

            payload = {
                "channel": chat_id,
                "user": sender.sender_id.open_id,
                "text": user_text,
                "attachments": attachments,
                "ts": msg.create_time,
                "platform": "feishu"
            }

            # 检查回调可用性
            if self.on_message_handler:
                print(f"DEBUG: [状态检查] 回调函数已挂载，准备执行推理逻辑...")
                await self.on_message_handler(payload)
                print(f"DEBUG: [推理执行完毕] ➜ 信号已移交给 AgentRunner")
            else:
                print(f"WARNING: [严重警告] 收到消息但 on_message_handler 尚未挂载！")

        except Exception as e:
            print(f"❌ [严重逻辑错误]: {str(e)}")
            traceback.print_exc()

    async def handle_http_event(self, data: Dict[str, Any]) -> None:
        """
        【HTTP Webhook 入口】
        将飞书原始 JSON 事件转换为 AgentRunner 能理解的统一 payload。
        """
        try:
            event = data.get("event", {})
            msg = event.get("message", {})
            sender = event.get("sender", {})
            sender_id = sender.get("sender_id", {})

            chat_id = msg.get("chat_id") or sender_id.get("open_id", "")
            message_type = msg.get("message_type", "")
            content_json = json.loads(msg.get("content") or "{}")
            user_text = ""

            if message_type == "text":
                user_text = content_json.get("text", "")
            elif message_type == "post":
                post_content = content_json.get("content", [])
                text_parts = []
                for paragraph in post_content:
                    for element in paragraph:
                        tag = element.get("tag")
                        if tag == "text":
                            text_parts.append(element.get("text", ""))
                        elif tag == "a":
                            link_text = element.get("text", "")
                            link_url = element.get("href", "")
                            text_parts.append(f"{link_text} ({link_url})")
                user_text = "".join(text_parts)

            attachment_dir = self.sessions_dir / chat_id / "attachments"
            attachment_dir.mkdir(parents=True, exist_ok=True)
            attachments = []
            message_id = msg.get("message_id", "")

            if message_type == "image":
                image_key = content_json.get("image_key")
                if image_key and message_id:
                    path = await self.download_resource(message_id, image_key, "image", attachment_dir)
                    if path:
                        attachments.append(path)
            elif message_type == "file":
                file_key = content_json.get("file_key")
                if file_key and message_id:
                    path = await self.download_resource(
                        message_id,
                        file_key,
                        "file",
                        attachment_dir,
                        content_json.get("file_name")
                    )
                    if path:
                        attachments.append(path)

            payload = {
                "channel": chat_id,
                "user": sender_id.get("open_id") or sender_id.get("user_id", ""),
                "text": user_text,
                "attachments": attachments,
                "ts": msg.get("create_time"),
                "platform": "feishu"
            }

            if self.on_message_handler:
                await self.on_message_handler(payload)
            else:
                print("WARNING: [严重警告] 收到 HTTP 消息但 on_message_handler 尚未挂载！")

        except Exception as e:
            print(f"❌ [HTTP Webhook 处理失败]: {str(e)}")
            traceback.print_exc()

    def _do_p2p_chat_entered(self, data: P2ImChatAccessEventBotP2pChatEnteredV1) -> None:
        print(f"DEBUG: [进入聊天事件] ID: {data.event.operator_id.open_id}")
        asyncio.run_coroutine_threadsafe(self._async_p2p_chat_entered(data), self.loop)

    async def _async_p2p_chat_entered(self, data: P2ImChatAccessEventBotP2pChatEnteredV1) -> None:
        try:
            open_id = data.event.operator_id.open_id
            await self.send_markdown(open_id, f"你好 <at user_id=\"{open_id}\"></at>！我是 LiteAct。\n\n我们可以正式对话了！", "LiteAct 已就绪 🚀")
        except Exception as e:
            print(f"❌ [欢迎逻辑失败]: {str(e)}")

    def _do_card_action_trigger(self, data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        print(f"DEBUG: [卡片交互点击] Value: {data.event.action.value}")
        return P2CardActionTriggerResponse(json.dumps({"toast": {"type": "info", "content": "收到指令"}}))

    async def send_markdown(self, chat_id: str, markdown_content: str, title: str = "LiteAct 响应"):
        """【API 调用防御层】"""
        now = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M")
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": markdown_content}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"LiteAct System | {now}"}]}
            ]
        }

        # 飞书 ID 类型感知
        id_type = "chat_id" if (chat_id.startswith("oc_") or chat_id.startswith("oc-")) else "open_id"

        request = CreateMessageRequest.builder() \
            .receive_id_type(id_type) \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id).msg_type("interactive").content(json.dumps(card)).build()) \
            .build()

        print(f"DEBUG: [API 投递中] Target: {chat_id} | Type: {id_type}")
        
        # 异步调用阻塞式 SDK
        response = await self.loop.run_in_executor(None, lambda: self.client.im.v1.message.create(request))

        if not response.success():
            print(f"❌ [飞书 API 报错]: {response.code} | {response.msg} | Trace: {response.get_header('otapi-trace-id')}")
        else:
            print(f"✅ [卡片发送成功] MsgID: {response.data.message_id}")
        return response

    async def download_resource(self, message_id: str, file_key: str, r_type: str, save_dir: Path, name: str = None) -> str:
        try:
            request = GetMessageResourceRequest.builder() \
                .message_id(message_id).file_key(file_key).type(r_type).build()
            response = await self.loop.run_in_executor(None, lambda: self.client.im.v1.message_resource.get(request))
            if response.success():
                ext = ".png" if r_type == "image" else f".{name.split('.')[-1]}" if name else ""
                p = save_dir / f"{file_key}{ext}"
                with open(p, "wb") as f: f.write(response.file.read())
                return str(p)
        except: pass
        return ""
