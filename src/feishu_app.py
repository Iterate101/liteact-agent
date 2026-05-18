import os
import sys
import json
import asyncio

# 自动寻路：将项目根目录加入 Python 搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Request
from src.ai.feishu_client import FeishuClient
from src.agent.runner import AgentRunner
from src.agent.loop import ReActLoop

# 初始化 Web 服务
app = FastAPI()

# 1. 飞书认证配置（建议从环境变量读取）
APP_ID = os.getenv("FEISHU_APP_ID", "your_app_id")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "your_app_secret")

# 2. 构造 LiteAct 的跨平台指挥系统
# 给 FeishuClient 分配“眼耳”，给 Runner 分配“大脑”
client = FeishuClient(app_id=APP_ID, app_secret=APP_SECRET)
runner = AgentRunner(messaging_client=client, loop_engine=ReActLoop())

# 3. 定义消息触发回调
async def on_new_message(payload):
    """【大脑被唤醒】当 FeishuClient 解析完事件后，触发推理"""
    print(f"[FeishuApp] 收到新消息 payload，启动推理流程...")
    await runner.run(payload)

# 注入回调
client.on_message_handler = on_new_message

@app.post("/webhook")
async def feishu_endpoint(request: Request):
    """【总机接到电话】飞书服务器推送的所有事件都会进入这里"""
    
    # 读取原始字节流，以便飞书签名验证（可选）或后续解析
    body = await request.body()
    try:
        data = json.loads(body)
    except:
        return {"error": "Invalid JSON"}

    # --- 飞书认证握手 (URL Challenge) ---
    # 第一次在飞书后台填 URL 时，飞书会发来 challenge 字段
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # --- 异步推理处理 ---
    # 我们不能在这里等待 Agent 思考完，因为飞书要求回调必须在 3 秒内返回结果。
    # 我们先给飞书回个“收到”，然后丢进后台任务（Background Task）执行。
    asyncio.create_task(client.handle_http_event(data))

    return {"status": "accepted"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 LiteAct Feishu Gateway 正在启动...")
    print("请确保公网 Webhook 地址指向: http://<你的域名>/webhook")
    uvicorn.run(app, host="0.0.0.0", port=8000)
