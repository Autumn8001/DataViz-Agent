import sys
sys.path.append(".")

from core.sandbox import run_in_sandbox

# 1. 尝试直接导入 pathlib
res_pathlib = run_in_sandbox("""
import pathlib
p = pathlib.Path(".")
print(p.absolute())
""")
print("1. Pathlib 测试结果:", res_pathlib)

# 2. 尝试魔法反射逃逸 "".__class__.__mro__[1].__subclasses__()
res_escape = run_in_sandbox("""
s = ""
subclasses = s.__class__.__mro__[1].__subclasses__()
print(subclasses)
""")
print("2. 魔法属性反射测试结果:", res_escape)

# 3. 尝试引用 eval 别名绕过
res_alias = run_in_sandbox("""
my_eval = eval
my_eval("1 + 1")
""")
print("3. 别名绕过测试结果:", res_alias)

# 4. 正常绘图代码测试
res_normal = run_in_sandbox("""
import pandas as pd
print("正常代码顺利通过！")
""")
print("4. 正常绘图代码测试结果:", res_normal)
