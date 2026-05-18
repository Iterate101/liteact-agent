import asyncio
import sys
import os

# 确保能找到 src 目录
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 解决 Windows 环境下的编码地雷
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from src.tools.executor.manager import ShellExecutor
from src.tools.executor.sandbox import LocalSandbox

async def smoke_test():
    print("[Sandbox] 开始沙箱集成冒烟测试...\n")
    
    # 实例化执行器（内部默认开启 LocalSandbox）
    executor = ShellExecutor()
    
    # 1. 测试正常执行
    print("[Test 1] 验证正常指令执行...")
    result = await executor.execute(
        tool_call_id="call_1", 
        params={"command": "echo Hello LiteAct Sandbox!", "timeout": 5}
    )
    print(f"输出内容: {result.content[0].text}")
    print(f"详情: {result.details}\n")

    # 2. 测试超时熔断 (Leash Test)
    print("[Test 2] 验证超时熔断 (预期 2秒后强制停止)...")
    # Windows 下使用 ping -n N 127.0.0.1 来模拟睡眠；Unix 下使用 sleep
    cmd = "ping 127.0.0.1 -n 11" if os.name == "nt" else "sleep 10"
    
    result_timeout = await executor.execute(
        tool_call_id="call_2", 
        params={"command": cmd, "timeout": 2}
    )
    print(f"输出内容: {result_timeout.content[0].text}")
    print(f"详情: {result_timeout.details}")

    if result_timeout.details.get("timed_out"):
        print("\n✅ 超时熔断测试通过！沙箱成功拉住了缰绳。")
    else:
        print("\n❌ 超时重试失败，请检查进程杀灭逻辑。")

if __name__ == "__main__":
    asyncio.run(smoke_test())
