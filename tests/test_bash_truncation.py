import asyncio
import sys
import os

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.executor.manager import ShellExecutor

# 强制设置环境编码
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

async def test_tail_truncation():
    print("\n--- [长日志截断压力测试] ShellExecutor ---")
    executor = ShellExecutor()
    
    # 缩小截断阈值，方便测试 (临时修改为 1KB)
    executor.MAX_OUTPUT_SIZE = 1024 
    
    # 模拟一个产生大量文本的命令 (约 5KB)
    # 每行约 50 字符 * 100 行 = 5000 字节
    command = (
        "python -c \"for i in range(100): "
        "print('Line ' + str(i).zfill(3) + ' - This is a very long log entry to fill up the buffer quickly.')\""
    )
    
    print(f"正在启动高压指令...")
    
    # 定义实时监听回调
    partial_count = 0
    async def monitor(data):
        nonlocal partial_count
        partial_count += 1
        # 只打印前几行和最后几行，避免刷屏
        if partial_count <= 2 or partial_count >= 99:
            print(f"  [实时上报] {data.strip()}")

    # 启动执行
    result = await executor.execute(
        tool_call_id="call_trunc",
        params={"command": command},
        on_partial_result=monitor
    )
    
    print("\n--- [最终汇总验证] ---")
    final_text = result.content[0].text
    original_size = result.details.get("original_size", 0)
    
    print(f"原始输出总大小: {original_size} 字节")
    print(f"最终结果大小: {len(final_text)} 字节")
    print(f"最终内容预览 (前100字): {final_text[:100]}")
    
    # 验证逻辑
    # 我们搜索一部分稳定的字符，避免全匹配失败
    if "OUTPUT TRUNCATED" in final_text:
        print("[SUCCESS] 成功探测到截断标识。")
        # 确认保留的是末尾部分 (应该包含 Line 099)
        if "Line 099" in final_text:
            print("[SUCCESS] 验证通过：保留了日志的末尾 (Tail) 部分。")
        else:
            print("[FAIL] 截断位置错误：未保留末尾日志。")
    else:
        print("[FAIL] 未触发截断！")

if __name__ == "__main__":
    asyncio.run(test_tail_truncation())
