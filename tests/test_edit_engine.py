import sys
import os
# 确保能找到 src 目录
sys.path.append(os.getcwd())

from src.utils.edit_engine import FuzzyEditEngine

def test_engine():
    engine = FuzzyEditEngine()
    
    # 模拟一份源码，包含一些特殊的 Unicode 字符
    content = """def hello():
    print("Hello World")  # 注意这行末尾有隐藏空格  
    print('Single Quote')
    # 这是一段中文注释：使用了智能引号 “”
    x = 100
"""

    print("--- 场景 1: 精确匹配测试 ---")
    res1 = engine.fuzzy_find(content, "x = 100")
    print(f"找到位置: {res1.index}, 长度: {res1.match_length}, 模糊匹配: {res1.used_fuzzy_match}")

    print("\n--- 场景 2: 模糊匹配（容错）测试 ---")
    # 模拟 Agent 发送了带有“智能双引号”和“错误空格”的搜索词
    search_faulty = 'print(“Hello World”) # 这里的引号和空格都不对'
    # 注意：我们的内容中实际是 print("Hello World")，且行末有空格
    
    try:
        # 这里演示 replace 流程
        new_content = engine.apply_edit(content, 'print("Hello World")', 'print("Welcome Alchemist!")')
        print(f"✅ 成功替换! 生成 Diff:\n")
        diff = engine.generate_unified_diff(content, new_content)
        print(diff)
    except Exception as e:
        print(f"❌ 场景 2 失败: {e}")

    print("\n--- 场景 3: 唯一性拦截测试 ---")
    duplicate_content = "x = 1\nx = 1\nx = 1"
    try:
        engine.fuzzy_find(duplicate_content, "x = 1")
    except ValueError as e:
        print(f"✅ 成功拦截不唯一匹配: {e}")

if __name__ == "__main__":
    test_engine()
