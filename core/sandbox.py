"""AST 级别代码安全沙箱

本模块提供 DataViz Agent 的核心安全机制：AST 静态扫描 + 隔离执行。

主要功能：
1. AST 静态扫描：在代码执行前，通过抽象语法树分析危险操作
2. 隔离执行：在受限的命名空间中执行代码，防止污染全局状态
3. 文件快照：捕获代码执行期间生成的图表文件

安全策略：
- 三道防线：黑名单 -> AST 扫描 -> 隔离执行
- 拦截危险模块（os, sys, subprocess 等）
- 拦截危险函数（eval, exec, open 等）
- 拦截敏感属性访问（__subclasses__, __globals__ 等反射逃逸）

这种静态扫描方法比运行时拦截更安全，因为危险代码根本不会被执行。
"""

import ast
import io
import contextlib
import traceback
import os
from typing import Dict, Any, Set
from core.config import config

# ==========================================
#  第一道防线：危险动作黑名单
# ==========================================
# 从配置模块导入安全黑名单，确保配置的一致性
FORBIDDEN_MODULES: Set[str] = config.security.forbidden_modules
FORBIDDEN_FUNCTIONS: Set[str] = config.security.forbidden_functions


class SecurityError(Exception):
    """安全拦截异常
    
    当代码尝试执行被禁止的操作时抛出，包括：
    - 导入危险模块
    - 调用危险函数
    - 访问敏感属性
    """
    pass


# ==========================================
# 🕵️‍️ 第二道防线：AST 海关安检员
# ==========================================
class SecurityScanner(ast.NodeVisitor):
    """AST 安全扫描器
    
    遍历代码的抽象语法树（Abstract Syntax Tree），在编译前
    静态分析代码结构，拦截危险操作。
    
    工作原理：
    1. Python 代码被解析为 AST（语法树结构）
    2. 扫描器访问树中的每个节点（import、函数调用、属性访问等）
    3. 如果发现黑名单中的危险操作，立即抛出 SecurityError
    4. 只有通过扫描的代码才会被编译和执行
    
    这种方法比运行时拦截更安全，因为危险代码根本不会被执行。
    
    拦截规则：
    - Import 节点：检查模块是否在 FORBIDDEN_MODULES 中
    - Call 节点：检查函数是否在 FORBIDDEN_FUNCTIONS 中
    - Attribute 节点：检查是否访问敏感属性（__subclasses__ 等）
    - Name 节点：检查是否引用敏感对象（__builtins__ 等）
    """

    def visit_Import(self, node: ast.Import):
        """拦截 import 语句
        
        检查：import os, import sys 等
        
        Args:
            node: AST Import 节点
        
        Raises:
            SecurityError: 如果导入的模块在黑名单中
        
        Examples:
            import os  # 被拦截
            import pandas  # 允许
        """
        for alias in node.names:
            base_module = alias.name.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                raise SecurityError(f"⛔ 安全拦截：禁止导入系统级模块 '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """拦截 from...import 语句
        
        检查：from os import path, from sys import argv 等
        
        Args:
            node: AST ImportFrom 节点
        
        Raises:
            SecurityError: 如果导入的模块在黑名单中
        
        Examples:
            from os import path  # 被拦截
            from pandas import DataFrame  # 允许
        """
        if node.module:
            base_module = node.module.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                raise SecurityError(f"⛔ 安全拦截：禁止从 '{node.module}' 导入")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """拦截函数调用
        
        检查：eval(), exec(), open() 等危险函数
        这些函数可能执行任意代码或访问文件系统。
        
        Args:
            node: AST Call 节点
        
        Raises:
            SecurityError: 如果调用的函数在黑名单中
        
        Examples:
            eval("malicious_code")  # 被拦截
            print("hello")  # 允许
        """
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_FUNCTIONS:
                raise SecurityError(f"⛔ 安全拦截：禁止调用高危函数 '{node.func.id}()'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """拦截敏感属性访问
        
        防止通过反射机制逃逸沙箱，例如：
        - __subclasses__: 获取所有子类，可能访问敏感类
        - __globals__: 访问全局命名空间
        - __builtins__: 访问内置函数
        - __code__: 访问函数字节码
        
        Args:
            node: AST Attribute 节点
        
        Raises:
            SecurityError: 如果访问的属性是敏感属性
        
        Examples:
            obj.__subclasses__()  # 被拦截（反射逃逸）
            obj.name  # 允许
        """
        if node.attr.startswith("__") or node.attr in [
            "__subclasses__",
            "__globals__",
            "__builtins__",
            "__code__",
        ]:
            raise SecurityError(f"⛔ 安全拦截：禁止访问系统敏感属性 '{node.attr}'")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """拦截敏感变量与敏感内置函数名访问
        
        防止利用别名绕过直接调用拦截，例如：
        - e = eval; e("code")  # 通过别名绕过
        - __builtins__  # 直接访问内置对象
        
        Args:
            node: AST Name 节点
        
        Raises:
            SecurityError: 如果引用的名称是敏感对象或危险函数
        
        Examples:
            __builtins__  # 被拦截
            e = eval  # 被拦截（防止别名绕过）
            x = 10  # 允许
        """
        if node.id.startswith("__") or node.id in ["__builtins__", "builtins"]:
            raise SecurityError(f"⛔ 安全拦截：禁止访问敏感对象 '{node.id}'")
        if node.id in FORBIDDEN_FUNCTIONS:
            raise SecurityError(f"⛔ 安全拦截：禁止引用高危函数/关键字 '{node.id}'")
        self.generic_visit(node)


# ==========================================
#  第三道防线：隔离执行舱
# ==========================================
def run_in_sandbox(
    code_string: str, global_context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """在隔离环境中执行代码
    
    在高度受限的命名空间中执行 AI 生成的 Python 代码，
    捕获输出并识别新生成的图表文件。
    
    执行流程：
    1. 应用可视化主题（setup_theme）
    2. 记录输出目录文件快照（执行前）
    3. AST 静态扫描（安全检查）
    4. 编译代码为字节码
    5. 在隔离的命名空间中执行
    6. 对比文件快照，捕获新生成的图表
    7. 返回执行结果和图表路径
    
    快照原理：
    通过记录文件的修改时间（mtime），对比执行前后的差异，
    精确识别代码运行期间新创建或修改的文件（如图表图片）。
    
    这种方法避免了在代码中插入监控逻辑，保持了代码的纯净性。
    
    Args:
        code_string: 要执行的 Python 代码字符串
        global_context: 全局命名空间（可选），用于传入预定义的变量和函数
                       例如：{"df": dataframe, "np": numpy}
    
    Returns:
        字典包含以下字段：
        {
            "success": bool,        # 执行是否成功
            "output": str,          # 控制台输出（print 的内容）
            "error": str,           # 错误信息（如果失败）
            "new_files": List[str]  # 新生成的图表文件路径列表
        }
    
    Raises:
        不会抛出异常，所有异常都被捕获并返回在 error 字段中
    
    Examples:
        >>> code = '''
        ... import pandas as pd
        ... import matplotlib.pyplot as plt
        ... df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        ... df.plot(kind="bar")
        ... plt.savefig("chart.png")
        ... print("Chart saved!")
        ... '''
        >>> result = run_in_sandbox(code)
        >>> result["success"]
        True
        >>> result["output"]
        'Chart saved!'
        >>> len(result["new_files"]) > 0
        True
    """
    if global_context is None:
        global_context = {}

    try:
        # 0.1 挂载全系统级别的高级视觉外挂
        # 在代码执行前应用可视化主题，确保生成的图表符合审美标准
        from utils.viz_theme import setup_theme

        setup_theme()

        # 0.2 【快照原理】：记录运行前目录中所有文件的最后修改时间
        # 通过对比执行前后的文件时间戳，精确识别新生成的图表
        output_dir = config.paths.outputs_dir
        os.makedirs(output_dir, exist_ok=True)
        before_mtimes = {
            f: os.path.getmtime(os.path.join(output_dir, f))
            for f in os.listdir(output_dir)
        }

        # 1. 静态解析：把代码字符串解析为抽象语法树（AST）
        # AST 是代码的树状结构表示，便于静态分析
        tree = ast.parse(code_string)

        # 2. 静态审计：派安检员去遍历语法树，查找危险操作
        # 如果发现黑名单中的操作，立即抛出 SecurityError
        scanner = SecurityScanner()
        scanner.visit(tree)

        # 3. 编译：安全检查通过后，编译为字节码
        # 字节码是 Python 虚拟机可执行的二进制指令
        compiled_code = compile(tree, filename="<ast>", mode="exec")

        # 4. 执行：在隔离的命名空间中运行代码
        # 使用 contextlib.redirect_stdout 截获 print 输出
        # 通过显式划分 globals 和 locals 实现局部作用域隔离
        output_buffer = io.StringIO()
        with contextlib.redirect_stdout(output_buffer):
            local_context = {}
            exec(compiled_code, global_context, local_context)

        # 5. 【快照原理】：对比运行后的文件修改时间，找出新增或被覆盖的文件
        # 如果文件是新出现的，或者修改时间比执行前更新，说明是代码刚生成的
        after_files = os.listdir(output_dir)
        new_files = []
        for f in after_files:
            mtime = os.path.getmtime(os.path.join(output_dir, f))
            # 文件不存在于快照中（新创建）或修改时间更新（被覆盖）
            if f not in before_mtimes or mtime > before_mtimes[f]:
                new_files.append(f)

        # 将相对路径转为统一的正斜杠格式（跨平台兼容）
        new_file_paths = [
            os.path.join(output_dir, f).replace("\\", "/") for f in new_files
        ]

        return {
            "success": True,
            "output": output_buffer.getvalue().strip(),
            "error": "",
            "new_files": new_file_paths,  # 返回新生成的图表文件路径
        }

    except SecurityError as se:
        # 捕获 AST 扫描器抛出的安全拦截异常
        return {"success": False, "output": "", "error": str(se), "new_files": []}

    except Exception as e:
        # 捕获常规的运行时错误：
        # - 语法错误（SyntaxError）
        # - 运行时错误（NameError, ZeroDivisionError, TypeError 等）
        # - 库调用错误（pandas, matplotlib 等）
        #
        # 只保留最后两行的报错详情，防止冗长的堆栈撑爆 LLM 的 Token
        # 这样可以保留最关键的错误信息，同时减少上下文占用
        error_msg = traceback.format_exc().strip().split("\n")[-2:]
        return {
            "success": False,
            "output": "",
            "error": "\n".join(error_msg),
            "new_files": [],
        }

