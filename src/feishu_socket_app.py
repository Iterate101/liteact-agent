import os
import asyncio
import sys
import threading
import lark_oapi as lark

# 寻路逻辑：确保 src 包能被找到
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ai.feishu_client import FeishuClient
from src.agent.runner import AgentRunner
from src.agent.loop import ReActLoop

def start_async_loop(loop):
    """【副驾驶】在独立线程中启动事件循环"""
    asyncio.set_event_loop(loop)
    loop.run_forever()

def main():
    # 1. 飞书认证配置
    APP_ID = os.getenv("FEISHU_APP_ID")
    APP_SECRET = os.getenv("FEISHU_APP_SECRET")

    if not APP_ID or not APP_SECRET:
        print("❌ 错误: 请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量")
        exit(1)

    # 2. 准备异步环境与 AI 配置
    # 读取环境变量，决定“大脑”的驱动方式
    model_id = os.getenv("MODEL_ID", "qwen-max")
    ds_key = os.getenv("DASHSCOPE_API_KEY")
    oa_key = os.getenv("OPENAI_API_KEY")
    
    # 智能判别驱动模式
    if ds_key and ("qwen" in model_id.lower() or not oa_key):
        api_type = "dashscope"
    else:
        api_type = "openai-responses"

    print(f"DEBUG: [启动自检] 模型: {model_id} | 驱动类型: {api_type}")

    # 我们先创建一个循环，并把它交给一个专门的后台线程去运行
    new_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_async_loop, args=(new_loop,), daemon=True)
    t.start()

    # 3. 初始化核心逻辑
    client = FeishuClient(app_id=APP_ID, app_secret=APP_SECRET)
    client.loop = new_loop 
    
    # 【核心修正】：将感知到的模型配置注入大脑
    runner = AgentRunner(
        messaging_client=client, 
        loop_engine=ReActLoop(model_id=model_id, api_type=api_type)
    )

    # 4. 注册推理回调
    async def on_new_message(payload):
        print(f"[FeishuSocket] ➜ 正在唤醒大脑进行思考: {payload['text']}")
        await runner.run(payload)

    client.on_message_handler = on_new_message

    # 5. 获取分发器并启动飞书长连接
    event_handler = client.get_event_handler()

    print("🚀 LiteAct Feishu (Socket Mode) 正在建立加密长连接...")
    print("模式：双线程协作 | 背景异步心跳已开启")

    ws_client = lark.ws.Client(
        APP_ID, 
        APP_SECRET, 
        event_handler=event_handler, 
        log_level=lark.LogLevel.INFO
    )

    # 此处会阻塞主线程，监听飞书信号
    ws_client.start()

if __name__ == "__main__":
    main()
