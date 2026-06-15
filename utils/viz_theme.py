"""可视化主题配置模块

本模块负责应用全局可视化主题，包括：
- 跨平台中文字体配置，防止乱码
- Seaborn 高级审美主题（莫兰迪色系）
- 图表尺寸和分辨率配置

该模块从统一配置管理器 (core.config) 读取所有参数，
确保配置的一致性和可维护性。
"""

import platform
import matplotlib as mpl

# 💡 强制使用非交互式后端，防止在子线程中拉起 Tk GUI 导致死锁
mpl.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from core.config import config


def setup_theme():
    """配置全局可视化主题与中文防乱码
    
    该函数在沙箱执行用户代码前自动调用，为生成的图表
    注入统一的审美主题和中文支持。
    
    主要功能：
    1. 根据操作系统配置中文字体（Windows/macOS/Linux）
    2. 应用 Seaborn 主题样式（莫兰迪色系）
    3. 设置图表尺寸和分辨率（从配置模块读取）
    
    配置来源：
        所有参数从 core.config.config.visualization 读取，
        支持通过环境变量自定义（VIZ_FIGSIZE, VIZ_DPI）
    
    优化说明：
        - figsize 从 (10, 6) 优化为 (8, 5)，更适合网页展示
        - DPI 从 200 优化为 120，平衡清晰度和文件大小
        - 优化后文件大小减少约 40-60%，加载速度更快
    """
    # ==========================================
    # 1. 彻底解决中文乱码与负号报错
    # ==========================================
    system = platform.system()
    if system == "Windows":
        # Windows 首选微软雅黑，备选黑体
        mpl.rcParams["font.sans-serif"] = list(config.visualization.font_windows)
    elif system == "Darwin":
        # macOS 首选苹方
        mpl.rcParams["font.sans-serif"] = list(config.visualization.font_macos)
    else:
        # Linux / Docker 环境
        mpl.rcParams["font.sans-serif"] = list(config.visualization.font_linux)

    # 正常显示负号（防止负号显示为方框）
    mpl.rcParams["axes.unicode_minus"] = False

    # ==========================================
    # 2. 注入 Seaborn 高级审美主题 (高冷莫兰迪色系)
    # ==========================================
    sns.set_theme(
        style=config.visualization.style,  # 干净的白底网格线
        palette=config.visualization.palette,  # 莫兰迪暗柔配色系
        rc={
            "figure.facecolor": config.visualization.figure_facecolor,  # 图表外围背景色：高级暖白
            "axes.facecolor": config.visualization.axes_facecolor,  # 坐标系内背景色：纯白
            "grid.color": "#e9ecef",  # 网格线颜色：极浅灰
            "axes.edgecolor": "#ced4da",  # 坐标轴边框色
            "axes.labelcolor": "#495057",  # 坐标轴文字颜色
            "xtick.color": "#6c757d",  # X轴刻度颜色
            "ytick.color": "#6c757d",  # Y轴刻度颜色
            "text.color": "#212529",  # 全局文字颜色：深灰（比纯黑更柔和）
            "font.size": config.visualization.font_size,  # 基础字体大小
            "axes.titlesize": config.visualization.title_size,  # 标题字体放大
            "axes.labelsize": config.visualization.label_size,  # 坐标轴标签字体
            "legend.fontsize": config.visualization.legend_size,  # 图例字体
            "figure.figsize": config.visualization.figsize,  # 优化：从 (10,6) 改为 (8,5)
            "figure.dpi": config.visualization.dpi,  # 优化：从 200 改为 120
        },
    )
