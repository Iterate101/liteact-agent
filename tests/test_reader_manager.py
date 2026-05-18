import asyncio
import sys
import os
import base64

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.reader.manager import FileReadManager

# 解决 Windows 终端编码问题
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

async def test_local_text_pagination():
    """测试 1: 本地文本分页与截断页脚"""
    print("\n--- [测试 1] 本地文本分页与截断测试 ---")
    manager = FileReadManager(mode="local")
    
    # 建立一个超长测试文件 (1000 行)
    test_file = "reader_test_large.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        for i in range(1, 1001):
            f.write(f"This is line {i:04d} for pagination testing.\n")
            
    # 只读前 10 行
    res = await manager.read_file(test_file, offset=1, limit=10)
    print(f"类型: {res['type']}, 总行数: {res.get('total_lines')}")
    print("内容预览:")
    print(res['content'])
    
    # 清理
    if os.path.exists(test_file):
        os.remove(test_file)

async def test_local_image_modal():
    """测试 2: 本地图片多模态识别 (Base64)"""
    print("\n--- [测试 2] 本地图片多模态识别 (Base64) ---")
    manager = FileReadManager(mode="local")
    
    # 检查我们之前的测试图片
    img_path = "test_image.png"
    if os.path.exists(img_path):
        res = await manager.read_file(img_path)
        print(f"检测到类型: {res['type']}, MIME: {res.get('mime')}")
        print(f"Base64 预览 (前50位): {res['content'][:50]}...")
    else:
        print("跳过：未找到测试图片 test_image.png")

async def test_remote_mode():
    """测试 3: 远程模式 (Bash 指令生成)"""
    print("\n--- [测试 3] 远程指令生成测试 ---")
    manager = FileReadManager(mode="remote")
    
    # 模拟读一个远程路径
    remote_path = "/var/log/syslog"
    cmd = await manager.read_file(remote_path)
    print(f"生成的远程读取指令为:\n{cmd}")

async def main():
    await test_local_text_pagination()
    await test_local_image_modal()
    await test_remote_mode()

if __name__ == "__main__":
    asyncio.run(main())
