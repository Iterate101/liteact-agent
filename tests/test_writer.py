import asyncio
import sys
import os

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.writer.manager import FileWriteManager

# 解决 Windows 终端编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

async def test_concurrency():
    """测试并发：3 个任务同时写同一个文件"""
    print("\n--- [测试 1] 并发写入测试 (Concurrency) ---")
    manager = FileWriteManager(mode="local")
    target = "race_condition.txt"
    
    # 模拟 3 个不同的内容
    tasks = [
        manager.write_file(target, f"Content FROM Task {i}\n") 
        for i in range(3)
    ]
    
    # 并发启动，观察日志中的顺序
    results = await asyncio.gather(*tasks)
    for r in results:
        print(r)

async def test_abort_signal():
    """测试中止：在写入前触发中止信号"""
    print("\n--- [测试 2] 中止信号测试 (Abort Signal) ---")
    manager = FileWriteManager(mode="local")
    target = "aborted_file.txt"
    
    # 创建并立即触发中止信号
    abort_event = asyncio.Event()
    abort_event.set() 
    
    try:
        await manager.write_file(target, "这些内容不应该出现在磁盘上", abort_event)
    except asyncio.CancelledError:
        print("成功检测到中止信号并停止了写入。")
        
    if not os.path.exists(target):
        print("验证成功：磁盘上没有产生任何碎片文件。")

async def test_remote_mode():
    """测试远程模式：生成转义指令"""
    print("\n--- [测试 3] 远程指令生成 (Shell Escape) ---")
    manager = FileWriteManager(mode="remote")
    # 内容包含单引号、美元符，考验转义能力
    complex_content = "Hello 'LiteAct' $VAR `date`"
    
    result = await manager.write_file("remote/path/config.py", complex_content)
    print("生成的 Bash 指令如下：")
    print(result)

async def main():
    await test_concurrency()
    await test_abort_signal()
    await test_remote_mode()
    
    # 清理残留
    if os.path.exists("race_condition.txt"):
        os.remove("race_condition.txt")

if __name__ == "__main__":
    asyncio.run(main())
