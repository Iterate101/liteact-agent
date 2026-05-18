import asyncio
import os
from src.tools.search.manager import SearchTextTool, SearchFilesTool

async def test_search_suite():
    # 模拟沙箱环境：指向当前项目根目录
    base_path = os.getcwd()
    
    text_searcher = SearchTextTool(base_path=base_path)
    file_finder = SearchFilesTool(base_path=base_path)
    
    print("--- 测试 1: 内容搜索 (Grep - 'import') ---")
    # 这是一个高频词，必然触发 50 条熔断
    res1 = await text_searcher.execute("test_t1", {"pattern": "import", "path": "/workspace/src"})
    print(res1.content[0].text)
    
    print("\n--- 测试 2: 文件查找 (Find - '*.py') ---")
    res2 = await file_finder.execute("test_f1", {"pattern": "**/*.py", "path": "/workspace/src"})
    print(res2.content[0].text)
    
    # 验证逻辑
    if "[已熔断]" in res1.content[0].text:
        print("\n✅ 成功：内容搜索已触发 50 条安全熔断保护。")
    
    if ".py" in res2.content[0].text:
        print("✅ 成功：文件名通配符查找已递归探测到文件。")

if __name__ == "__main__":
    asyncio.run(test_search_suite())
