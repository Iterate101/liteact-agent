import asyncio
import sys
import os
import shutil
from pathlib import Path

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.reader.manager import FileReadManager
from src.tools.writer.manager import FileWriteManager

async def test_writer_recursive_mkdir():
    print("\n--- [测试 A] 验证：递归目录创建 (mkdir -p) ---")
    writer = FileWriteManager(mode="local")
    
    # 一个深度嵌套的路径
    deep_path = "temp_tests/deep/folder/structure/hello.txt"
    if os.path.exists("temp_tests"):
        shutil.rmtree("temp_tests")
        
    # 执行写入
    try:
        res = await writer.write_file(path=deep_path, content="这是一条深度消息。")
        print(f"写入反馈: {res}")
        assert os.path.exists(deep_path), "[FAIL] 文件夹未被正确创建！"
        print("[SUCCESS] 深度目录创建测试通过。")
    except Exception as e:
        print(f"[ERROR] 写入失败: {str(e)}")

async def test_reader_truncation_safety():
    print("\n--- [测试 B] 验证：大文件安全截断 (50KB Limit) ---")
    reader = FileReadManager(mode="local")
    
    # 1. 制造一个巨型垃圾文件 (200KB)
    large_file = "temp_tests/giant.txt"
    with open(large_file, "w", encoding="utf-8") as f:
        f.write("X" * (200 * 1024))
        
    # 2. 尝试读取
    try:
        res = await reader.read_file(path=large_file)
        
        # 验证反馈
        content = res["content"]
        actual_bytes = len(content.encode('utf-8'))
        print(f"读取到的大小: {actual_bytes} 字节")
        
        # 我们的安全红线是 50KB = 51200 字节
        # 考虑到 UTF-8 编码和 Paged 提示词结尾，应当在此量级
        assert actual_bytes <= 52000, "[FAIL] 安全截断失效！读取过大。"
        
        if "[TRUNCATED]" in content:
            print("[SUCCESS] 已成功探测到截断标识。")
        print("[SUCCESS] 巨量文件安全测试通过。")
        
    except Exception as e:
        print(f"[ERROR] 读取异常: {str(e)}")

async def main():
    await test_writer_recursive_mkdir()
    await test_reader_truncation_safety()
    
    # 清理
    if os.path.exists("temp_tests"):
        shutil.rmtree("temp_tests")

if __name__ == "__main__":
    asyncio.run(main())
