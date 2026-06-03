import platform
import matplotlib as mpl

mpl.use("Agg")  # 💡 强制使用非交互式后端，防止在子线程中拉起 Tk GUI 导致死锁
import matplotlib.pyplot as plt
import seaborn as sns


def setup_theme():
    """
    配置全局工业级可视化主题与中文防乱码。
    （这个函数会在沙箱执行大模型代码前，被系统悄悄调用，给大模型套上审美外挂）
    """
    # ==========================================
    # 1. 彻底解决中文乱码与负号报错
    # ==========================================
    system = platform.system()
    if system == "Windows":
        # Windows 首选微软雅黑，备选黑体
        mpl.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    elif system == "Darwin":
        # macOS 首选苹方
        mpl.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC"]
    else:
        # Linux / Docker 环境
        mpl.rcParams["font.sans-serif"] = ["WenQuanYi Micro Hei"]

    mpl.rcParams["axes.unicode_minus"] = False  # 正常显示负号

    # ==========================================
    # 2. 注入 Seaborn 高级审美主题 (高冷莫兰迪色系)
    # ==========================================
    sns.set_theme(
        style="whitegrid",  # 干净的白底网格线
        palette="muted",  # 莫兰迪暗柔配色系
        rc={
            "figure.facecolor": "#f8f9fa",  # 图表外围背景色：高级暖白
            "axes.facecolor": "#ffffff",  # 坐标系内背景色：纯白
            "grid.color": "#e9ecef",  # 网格线颜色：极浅灰
            "axes.edgecolor": "#ced4da",  # 坐标轴边框色
            "axes.labelcolor": "#495057",  # 坐标轴文字颜色
            "xtick.color": "#6c757d",  # X轴刻度颜色
            "ytick.color": "#6c757d",  # Y轴刻度颜色
            "text.color": "#212529",  # 全局文字颜色：深灰（比纯黑更柔和）
            "font.size": 12,
            "axes.titlesize": 16,  # 标题字体放大
            "axes.labelsize": 13,  # 坐标轴标签字体
            "legend.fontsize": 11,
            "figure.figsize": (10, 6),  # 默认长宽比，类似黄金比例
            "figure.dpi": 200,  # 提高输出分辨率，保证高清
        },
    )
