import asyncio
import os
from src.tools.explorer.manager import SafeLsTool

async def test_safe_ls():
    # 模拟一个会话沙箱目录（指向当前项目根目录进行测试）
    base_path = os.getcwd()
    explorer = SafeLsTool(base_path=base_path)
    
    print(f"--- 测试 1: 根目录概览 (depth=1) ---")
    res1 = await explorer.execute("test_1", {"path": "/workspace/", "depth": 1, "recursive": True})
    print(res1.content[0].text)
    
    print(f"\n--- 测试 2: 深入 src 目录 (depth=2) ---")
    res2 = await explorer.execute("test_2", {"path": "/workspace/src", "depth": 2, "recursive": True})
    print(res2.content[0].text)
    
    # 验证是否忽略了 .git
    if ".git" in res1.content[0].text:
        print("\n❌ 错误：.git 文件夹未被忽略！")
    else:
        print("\n✅ 成功：.git 文件夹已被黑名单屏蔽。")

if __name__ == "__main__":
    asyncio.run(test_safe_ls())
