import os
import json
import asyncio
from typing import Optional, List, Dict, Any, Callable, Awaitable
from datetime import datetime
from pathlib import Path

# Slack 官方库
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.async_client import AsyncSocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

class SlackBot:
    """
    【Slack 智能适配器】
    负责 Socket Mode 监听、消息预处理、附件上传以及本地 JSONL 同步。
    """

    def __init__(
        self, 
        app_token: str, 
        bot_token: str, 
        working_dir: str = "sessions"
    ):
        # 1. 初始化两个客户端：Web 用于发送/拉取历史，Socket 用于实时监听
        self.web_client = AsyncWebClient(token=bot_token)
        self.socket_client = AsyncSocketModeClient(
            app_token=app_token,
            web_client=self.web_client
        )
        
        self.working_dir = Path(working_dir)
        self.bot_user_id = None
        self.startup_ts = datetime.now().timestamp()
        
        # 记录用户和频道缓存
        self.users: Dict[str, Dict] = {}
        self.channels: Dict[str, Dict] = {}
        
        # 消息处理器回避 (由上层 Loop 注入)
        self.on_message_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

    async def start(self):
        """【启动仪式】初始化连接、获取 Bot 信息并开启监听"""
        # 测试认证
        auth = await self.web_client.auth_test()
        self.bot_user_id = auth["user_id"]
        print(f"[Slack] 认证成功，Bot ID: {self.bot_user_id}")
        
        # 预加载用户和频道信息
        await self._fetch_metadata()
        
        # 注册事件监听逻辑
        self.socket_client.socket_mode_request_listeners.append(self._handle_request)
        
        # 开启长连接
        await self.socket_client.connect()
        print("[Slack] Socket Mode 已连接并处于监听状态...")

    async def _fetch_metadata(self):
        """拉取工作区的所有用户和频道，完善本地映射"""
        try:
            users_res = await self.web_client.users_list()
            for member in users_res.get("members", []):
                self.users[member["id"]] = {
                    "userName": member.get("name"),
                    "displayName": member.get("profile", {}).get("real_name")
                }
            
            # 公开频道
            channels_res = await self.web_client.conversations_list(types="public_channel,private_channel")
            for chan in channels_res.get("channels", []):
                self.channels[chan["id"]] = {"name": chan["name"]}
        except Exception as e:
            print(f"[Slack] 预加载元数据失败: {e}")

    async def _handle_request(self, client: AsyncSocketModeClient, request: SocketModeRequest):
        """【神经反射】处理 Slack 推送的所有事件报文"""
        # 1. 确认收到 (Ack)
        response = SocketModeResponse(envelope_id=request.envelope_id)
        await client.send_socket_mode_response(response)

        # 2. 识别事件类型
        if request.type == "events_api":
            event = request.payload.get("event", {})
            event_type = event.get("type")
            
            # 过滤 Bot 自己的消息，防止无限循环
            if event.get("bot_id") or event.get("user") == self.bot_user_id:
                return

            # 处理 @mention 和 DM 消息
            if event_type in ["app_mention", "message"]:
                await self._process_event(event)

    async def _process_event(self, event: Dict[str, Any]):
        """【清洗与分发】将原始 Slack 数据转化为 Agent 易读的逻辑格式"""
        channel_id = event.get("channel")
        raw_text = event.get("text", "")
        ts = event.get("ts")
        user_id = event.get("user")

        # 剥离 @bot 提到
        # 逻辑：去除形如 <@U12345> 的标签
        clean_text = raw_text.replace(f"<@{self.bot_user_id}>", "").strip()
        
        # 识别指令前缀 (Command Identification)
        is_stop = clean_text.lower() == "stop"
        
        payload = {
            "channel": channel_id,
            "ts": ts,
            "user": user_id,
            "text": clean_text,
            "raw_text": raw_text,
            "is_command": is_stop, # 是否是控制指令
            "command": "stop" if is_stop else None,
            "files": event.get("files", []),
            "type": "dm" if event.get("channel_type") == "im" else "mention"
        }

        # 同步到本地 JSONL (保持日志对齐)
        self.log_to_file(channel_id, payload)

        # 打印调试日志，方便观察消息流入
        print(f"[Slack] 收到来自 {user_id} 的消息: {clean_text} (Command: {is_stop})")

        # 如果绑定了处理器，交给 AI 执行
        if self.on_message_handler:
            await self.on_message_handler(payload)

    def log_to_file(self, channel_id: str, payload: Dict[str, Any]):
        """【影子日志】在本地 sessions 目录下同步一个 JSONL 文件"""
        dir_path = self.working_dir / channel_id
        dir_path.mkdir(parents=True, exist_ok=True)
        
        log_path = dir_path / "log.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "slack_ts": payload["ts"],
            "user": payload["user"],
            "text": payload["text"],
            "is_bot": False
        }
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def post_message(self, channel: str, text: str, thread_ts: str = None):
        """【发声器】回复消息或线程"""
        await self.web_client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts
        )

    async def upload_file(self, channel: str, file_path: str, title: str = None):
        """【附件分发】上传文件并附带标题"""
        # 注意：Slack 推荐使用 files_upload_v2
        if not os.path.exists(file_path):
            print(f"[Slack] 错误：找不到文件 {file_path}")
            return

        with open(file_path, "rb") as f:
            await self.web_client.files_upload_v2(
                channel=channel,
                file=f,
                title=title or os.path.basename(file_path),
                filename=os.path.basename(file_path)
            )

    async def backfill_channel(self, channel_id: str, limit: int = 100):
        """【断线补记】拉取最近的聊天记录，补齐本地 JSONL 缺失的片段"""
        # 读取本地最新的 ts (这部分在 AgentSession 中已有类似逻辑，此处为独立补充)
        print(f"[Slack] 正在同步频道 {channel_id} 的历史记录...")
        result = await self.web_client.conversations_history(
            channel=channel_id,
            limit=limit
        )
        # TODO: 比较 ts 并去重补记
        return result.get("messages", [])
