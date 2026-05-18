import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class FuzzyMatchResult:
    """
    【模糊匹配结果模型】
    记录匹配的状态、位置以及规格化后的内容。
    """
    found: bool
    index: int = -1
    match_length: int = 0
    used_fuzzy_match: bool = False
    content_for_replacement: str = ""

class FuzzyEditEngine:
    """
    【精密文本编辑引擎】
    复刻 edit-diff.ts。支持智能容错匹配、唯一性断言以及 Git 风格的 Diff 渲染。
    """

    @staticmethod
    def normalize_for_fuzzy_match(text: str) -> str:
        """
        【规格化工厂】
        1. NFKC 归一化（处理 Unicode 兼容性字符）
        2. 移除每行末尾空格
        3. 统一智能引号、破折号和特殊空格为 ASCII 标准
        """
        if not text:
            return ""
            
        # NFKC 归一化 (兼容性分解并重新合成)
        text = unicodedata.normalize("NFKC", text)
        
        # 逐行处理行尾空格
        lines = text.splitlines()
        text = "\n".join([line.rstrip() for line in lines])
        
        # 智能单引号替换: \u2018 (‘), \u2019 (’), \u201A (‚), \u201B (‛)
        text = re.sub(r'[\u2018\u2019\u201A\u201B]', "'", text)
        
        # 智能双引号替换: \u201C (“), \u201D (”), \u201E („), \u201F (‟)
        text = re.sub(r'[\u201C\u201D\u201E\u201F]', '"', text)
        
        # 各种破折号替换为 ASCII -: \u2010 (\u2010), \u2011 (‑), \u2012 (–), \u2013 (–), \u2014 (—), \u2015 (―), \u2212 (−)
        text = re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]', "-", text)
        
        # 特殊空格替换为普通空格: \u00A0 (NBSP), \u2002-\u200A, \u202F, \u205F, \u3000 (全角空格)
        text = re.sub(r'[\u00A0\u2002-\u200A\u202F\u205F\u3000]', " ", text)
        
        return text

    def fuzzy_find(self, content: str, search_text: str) -> FuzzyMatchResult:
        """
        【多阶段定位雷达】
        第一步：尝试精确匹配。
        第二步：如果失败，进入规格化后的模糊空间进行搜索。
        """
        # 1. 精确匹配尝试
        index = content.find(search_text)
        if index != -1:
            # 唯一性检查（物理空间）
            if content.find(search_text, index + 1) != -1:
                raise ValueError("在文档中找到多处精确匹配。请提供更多上下文以示区分。")
            
            return FuzzyMatchResult(
                found=True,
                index=index,
                match_length=len(search_text),
                used_fuzzy_match=False,
                content_for_replacement=content
            )

        # 2. 模糊匹配尝试
        norm_content = self.normalize_for_fuzzy_match(content)
        norm_search = self.normalize_for_fuzzy_match(search_text)
        
        index = norm_content.find(norm_search)
        if index != -1:
            # 唯一性检查（规格化空间）
            count = norm_content.count(norm_search)
            if count > 1:
                raise ValueError(f"在格式规格化后找到 {count} 处匹配。内容不唯一，无法确定修改位置。")
            
            return FuzzyMatchResult(
                found=True,
                index=index,
                match_length=len(norm_search),
                used_fuzzy_match=True,
                content_for_replacement=norm_content
            )

        return FuzzyMatchResult(found=False)

    @staticmethod
    def generate_unified_diff(old_content: str, new_content: str, context_lines: int = 3) -> str:
        """
        【Git 风格 Diff 引擎】
        生成带有行号的增量对比图。仅展示修改点前后的上下文。
        """
        import difflib
        
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        diff = list(difflib.unified_diff(old_lines, new_lines, n=context_lines, lineterm=''))
        
        output = []
        for line in diff:
            if line.startswith('---') or line.startswith('+++'):
                continue # 忽略标准头部
            
            if line.startswith('@@'):
                # 解析元数据: @@ -start,len +start,len @@
                output.append(f"  \033[36m{line}\033[0m") # 使用青色标注位置信息
                continue
            
            if line.startswith('+'):
                output.append(f"\033[32m{line}\033[0m") # 绿色代表新增
            elif line.startswith('-'):
                output.append(f"\033[31m{line}\033[0m") # 红色代表移除
            else:
                output.append(f" {line}") # 上下文保持原样
                
        return "\n".join(output)

    def apply_edit(self, content: str, search_text: str, replacement_text: str) -> str:
        """
        【执行修改】
        定位匹配项并执行替换。
        """
        match = self.fuzzy_find(content, search_text)
        if not match.found:
            raise ValueError("无法定位到指定的代码块。请检查代码是否已在其他位置被修改，或提供更准确的上下文。")
        
        base_content = match.content_for_replacement
        new_content = (
            base_content[:match.index] + 
            replacement_text + 
            base_content[match.index + match.match_length:]
        )
        return new_content
