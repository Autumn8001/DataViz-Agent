import ast
import io
import contextlib
import traceback
import os
from typing import Dict, Any

# ==========================================
#  第一道防线：危险动作黑名单
# ==========================================
FORBIDDEN_MODULES = {
    "os",
    "sys",
    "subprocess",
    "shutil",
    "socket",
    "requests",
    "urllib",
    "pathlib",
    "glob",
    "importlib",
    "builtins",
}
FORBIDDEN_FUNCTIONS = {
    "exec",
    "eval",
    "open",
    "__import__",
    "input",
    "getattr",
    "setattr",
    "delattr",
    "compile",
    "globals",
    "locals",
}


class SecurityError(Exception):
    """自定义安全拦截异常"""

    pass


# ==========================================
# 🕵️‍️ 第二道防线：AST 海关安检员
# ==========================================
class SecurityScanner(ast.NodeVisitor):
    """
    遍历代码的抽象语法树 (AST)，如果发现黑名单操作，直接抛出异常！
    """

    def visit_Import(self, node: ast.Import):
        """拦截 import xxx"""
        for alias in node.names:
            base_module = alias.name.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                raise SecurityError(f" 安全拦截：禁止导入系统级模块 '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """拦截 from xxx import yyy"""
        if node.module:
            base_module = node.module.split(".")[0]
            if base_module in FORBIDDEN_MODULES:
                raise SecurityError(f" 安全拦截：禁止从 '{node.module}' 导入")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """拦截危险的内置函数调用"""
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_FUNCTIONS:
                raise SecurityError(f" 安全拦截：禁止调用高危函数 '{node.func.id}()'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """拦截敏感属性查找，如 __subclasses__, __globals__, __builtins__ 等反射逃逸手段"""
        if node.attr.startswith("__") or node.attr in ["__subclasses__", "__globals__", "__builtins__", "__code__"]:
            raise SecurityError(f" 安全拦截：禁止访问系统敏感属性 '{node.attr}'")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """拦截敏感变量与敏感内置函数名访问，防止利用别名绕过直接调用拦截"""
        if node.id.startswith("__") or node.id in ["__builtins__", "builtins"]:
            raise SecurityError(f" 安全拦截：禁止访问敏感对象 '{node.id}'")
        if node.id in FORBIDDEN_FUNCTIONS:
            raise SecurityError(f" 安全拦截：禁止引用高危函数/关键字 '{node.id}'")
        self.generic_visit(node)


# ==========================================
#  第三道防线：隔离执行舱
# ==========================================
def run_in_sandbox(
    code_string: str, global_context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    在高度受限的环境中执行大模型生成的 Python 代码
    返回统一结构：{"success": bool, "output": str, "error": str}
    """
    if global_context is None:
        global_context = {}

    try:
        # 0.1  挂载全系统级别的高级视觉外挂
        from utils.viz_theme import setup_theme

        setup_theme()

        # 0.2 【快照原理】：记录运行前目录中所有文件的最后修改时间
        output_dir = "./data/outputs"
        os.makedirs(output_dir, exist_ok=True)
        before_mtimes = {
            f: os.path.getmtime(os.path.join(output_dir, f))
            for f in os.listdir(output_dir)
        }

        # 1. 静态解析：把代码字符串变成 AST 树
        tree = ast.parse(code_string)

        # 2. 静态审计：派安检员去查树
        scanner = SecurityScanner()
        scanner.visit(tree)

        # 3. 编译：安全检查通过，编译成字节码
        compiled_code = compile(tree, filename="<ast>", mode="exec")

        # 4. 执行：截获程序的 print 输出
        output_buffer = io.StringIO()
        with contextlib.redirect_stdout(output_buffer):
            # 真正的执行动作！通过显式划分 globals 和 locals 命名空间实现局部作用域彻底隔离
            local_context = {}
            exec(compiled_code, global_context, local_context)

        # 5. 【快照原理】：对比运行后的文件修改时间，找出新增或被覆盖（修改时间更新）的文件！
        after_files = os.listdir(output_dir)
        new_files = []
        for f in after_files:
            mtime = os.path.getmtime(os.path.join(output_dir, f))
            # 如果文件是新出现的，或者它的修改时间比运行前晚，说明是大模型刚刚画出来的图！
            if f not in before_mtimes or mtime > before_mtimes[f]:
                new_files.append(f)

        new_file_paths = [
            os.path.join(output_dir, f).replace("\\", "/") for f in new_files
        ]

        return {
            "success": True,
            "output": output_buffer.getvalue().strip(),
            "error": "",
            "new_files": new_file_paths,  # 返回新生成的图片路径
        }

    except SecurityError as se:
        # 捕获我们自己定义的 AST 拦截报警
        return {"success": False, "output": "", "error": str(se), "new_files": []}

    except Exception as e:
        # 捕获常规的语法错误、除以零、变量不存在等运行时报错
        # 只保留最后两行的报错详情，防止冗长的堆栈撑爆大模型的 Token
        error_msg = traceback.format_exc().strip().split("\n")[-2:]
        return {
            "success": False,
            "output": "",
            "error": "\n".join(error_msg),
            "new_files": [],
        }
