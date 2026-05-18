import asyncio
import sys
import os
import shutil

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.editor.manager import FileEditManager

async def test_precision_edit():
    print("\n--- [测试 A] 验证：精准局部替换 ---")
    editor = FileEditManager()
    
    # 1. 准备一个模拟的 Python 源代码文件
    test_file = "temp_src.py"
    original_code = """
def main():
    x = 10
    print(f"X is {x}")
    return x
""".strip()

    with open(test_file, "w", encoding="utf-8") as f:
        f.write(original_code)
        
    print("1. [准备] 已创建模拟代码文件。")

    # 2. 尝试精准替换 x = 10 -> x = 20
    res = await editor.execute(
        tool_call_id="call_001",
        params={
            "path": test_file,
            "target": "    x = 10", # 携带缩进
            "replacement": "    x = 20"
        }
    )
    
    print(f"2. [执行结果]: {res.content[0].text}")
    
    with open(test_file, "r", encoding="utf-8") as f:
        new_content = f.read()
        assert "x = 20" in new_content, "[FAIL] 替换内容未生效！"
        print("[SUCCESS] 精准替换测试通过。")

async def test_error_not_found():
    print("\n--- [测试 B] 验证：内容不存在报错 ---")
    editor = FileEditManager()
    test_file = "temp_src.py"
    
    # 故意少一个空格的错误匹配
    res = await editor.execute(
        tool_call_id="call_002",
        params={
            "path": test_file,
            "target": "x=20", # 原文有空格
            "replacement": "x=30"
        }
    )
    
    print(f"1. [报错信息]: {res.content[0].text}")
    assert "Error:" in res.content[0].text, "[FAIL] 错误未被正确捕获！"
    print("[SUCCESS] 不存在匹配报错正常。")

async def test_error_ambiguous():
    print("\n--- [测试 C] 验证：歧义冲突报错 ---")
    editor = FileEditManager()
    test_file = "temp_src.py"
    
    # 制造一个包含重复内容的文件
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("print('hello')\nprint('hello')")
        
    # 尝试替换没有区分度的内容
    res = await editor.execute(
        tool_call_id="call_003",
        params={
            "path": test_file,
            "target": "print('hello')",
            "replacement": "print('world')"
        }
    )
    
    print(f"1. [报错信息]: {res.content[0].text}")
    assert "找到了 2 处" in res.content[0].text, "[FAIL] 歧义检测失效！"
    print("[SUCCESS] 歧义检测报警正常。")

async def main():
    await test_precision_edit()
    await test_error_not_found()
    await test_error_ambiguous()
    
    # 清理
    if os.path.exists("temp_src.py"):
        os.remove("temp_src.py")

if __name__ == "__main__":
    asyncio.run(main())
