import asyncio
import sys
import os

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.executor.manager import ShellExecutor

# 解决 Windows 终端编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

async def test_streaming_execution():
    print("\n--- [流式上报测试] ShellExecutor ---")
    executor = ShellExecutor()
    
    # 定义一个实时回调函数 (心跳监听器)
    async def my_ui_callback(data: str):
        # 模拟 UI 的实时更新输出
        print(f"  [实时更新] 收到一行数据: {data.strip()}")

    # 使用 Python 脚本作为测试指令：跨平台且语法统一
    command = 'python -c "import time; print(\'Count 1\', flush=True); time.sleep(1); print(\'Count 2\', flush=True); time.sleep(1); print(\'Count 3\', flush=True)"'

    print(f"正在启动指令: {command}")
    
    # 启动执行
    result = await executor.execute(
        tool_call_id="call_999",
        params={"command": command, "timeout": 10},
        on_partial_result=my_ui_callback
    )
    
    print("\n--- [最终汇总] ---")
    print(f"退出代码: {result.details.get('exit_code')}")
    print(f"完整内容大小: {len(result.content[0].text)} 字符")

if __name__ == "__main__":
    asyncio.run(test_streaming_execution())
