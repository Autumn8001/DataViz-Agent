import os

# 定义大厂规范目录结构
project_structure = [
    "core/__init__.py",
    "core/agent.py",
    "core/state.py",
    "core/sandbox.py",
    "core/tools.py",
    "core/llm_factory.py",
    "api/__init__.py",
    "api/chat_routes.py",
    "api/upload_routes.py",
    "data/uploads/.gitkeep",  # 占位符，保持空文件夹存在
    "data/outputs/.gitkeep",
    "utils/__init__.py",
    "utils/viz_theme.py",
    ".env"  # 存储 API KEY 的环境变量文件
]


def create_structure():
    print(" 开始构筑 DataViz Agent 项目目录底座...")
    for path in project_structure:
        # 获取文件夹路径
        dir_name = os.path.dirname(path)
        # 如果文件夹不存在，则创建
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name)
            print(f"  [创建文件夹] -> {dir_name}")

        # 创建空文件
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                if path.endswith(".env"):
                    f.write("OPENAI_API_KEY=your_key_here\nBASE_URL=https://api.openai.com/v1\n")
                else:
                    f.write("# Created initialized file\n")
            print(f"  [创建文件]   -> {path}")

    print(" 项目底座构筑完毕！极其完美！")


if __name__ == "__main__":
    create_structure()