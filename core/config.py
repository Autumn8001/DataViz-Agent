"""统一配置管理模块

本模块提供 DataViz Agent 系统的统一配置管理，包括：
- 可视化配置：图表尺寸、DPI、字体、颜色主题
- 路径配置：上传目录、输出目录、数据字典路径
- 安全配置：沙箱执行的安全限制（禁用模块和函数列表）

配置优先级：环境变量 > 默认值

使用示例：
    from core.config import config
    
    # 访问可视化配置
    figsize = config.visualization.figsize
    dpi = config.visualization.dpi
    
    # 访问路径配置
    output_dir = config.paths.outputs_dir
    
    # 访问安全配置
    forbidden = config.security.forbidden_modules
"""

from dataclasses import dataclass
from typing import List, Set, Tuple
import os


@dataclass(frozen=True)
class VisualizationConfig:
    """可视化配置
    
    管理图表尺寸、分辨率、字体、颜色等可视化相关参数。
    
    Attributes:
        figsize: 图表尺寸（英寸），格式 (width, height)，默认 (8, 5)
                 优化说明：从 (10, 6) 改为 (8, 5)，减少文件大小，更适合网页展示
        dpi: 图表分辨率（Dots Per Inch），默认 120，范围 50-300
             优化说明：从 200 改为 120，平衡清晰度和文件大小
        font_size: 基础字体大小，默认 12
        title_size: 标题字体大小，默认 14
        label_size: 坐标轴标签字体大小，默认 11
        legend_size: 图例字体大小，默认 10
        font_windows: Windows 平台中文字体列表，按优先级排序
        font_macos: macOS 平台中文字体列表，按优先级排序
        font_linux: Linux 平台中文字体列表，按优先级排序
        style: Seaborn 主题风格，默认 "whitegrid"
        palette: 配色方案，默认 "muted"
        figure_facecolor: 图表外围背景色，默认 "#f8f9fa"
        axes_facecolor: 坐标系内背景色，默认 "#ffffff"
    """
    figsize: Tuple[int, int] = (8, 5)
    dpi: int = 120
    font_size: int = 12
    title_size: int = 14
    label_size: int = 11
    legend_size: int = 10
    
    # 字体配置（按平台）
    font_windows: Tuple[str, ...] = ("Microsoft YaHei", "SimHei")
    font_macos: Tuple[str, ...] = ("Arial Unicode MS", "PingFang SC")
    font_linux: Tuple[str, ...] = ("WenQuanYi Micro Hei",)
    
    # 颜色主题
    style: str = "whitegrid"
    palette: str = "muted"
    figure_facecolor: str = "#f8f9fa"
    axes_facecolor: str = "#ffffff"


@dataclass(frozen=True)
class PathConfig:
    """路径配置
    
    管理数据上传、输出、字典等文件路径。
    
    Attributes:
        uploads_dir: 用户上传文件目录，默认 "./data/uploads"
        outputs_dir: AI 生成图表输出目录，默认 "./data/outputs"
        data_dict_path: 企业数据字典文件路径，默认 "./data/data_dict.json"
    """
    uploads_dir: str = "./data/uploads"
    outputs_dir: str = "./data/outputs"
    data_dict_path: str = "./data/data_dict.json"


@dataclass(frozen=True)
class SecurityConfig:
    """安全配置
    
    管理沙箱执行的安全限制，包括禁用模块和函数列表。
    
    **安全警告**：这些配置直接影响系统安全边界，修改时需谨慎评估。
    禁用模块和函数列表用于 AST 静态扫描，防止恶意代码执行。
    
    Attributes:
        forbidden_modules: 禁止导入的模块集合
                          包含可能危险的系统模块（os, sys, subprocess 等）
        forbidden_functions: 禁止调用的函数集合
                            包含可能执行任意代码的危险函数（eval, exec 等）
        max_retry_count: 代码执行失败最大重试次数，默认 3
                        用于 Reflexion 自我修复机制
    """
    forbidden_modules: Set[str] = frozenset({
        "os", "sys", "subprocess", "shutil", "socket",
        "requests", "urllib", "pathlib", "glob",
        "importlib", "builtins"
    })
    
    forbidden_functions: Set[str] = frozenset({
        "exec", "eval", "open", "__import__",
        "input", "getattr", "setattr", "delattr",
        "compile", "globals", "locals"
    })
    
    max_retry_count: int = 3


class AppConfig:
    """应用配置管理器
    
    提供统一的配置访问接口，支持从环境变量覆盖默认值。
    
    配置优先级：
        1. 环境变量（最高优先级）
        2. 默认值
    
    环境变量支持：
        - VIZ_FIGSIZE: 图表尺寸，格式 "width,height"，例如 "8,5"
        - VIZ_DPI: 图表 DPI，整数值，例如 "120"
    
    使用示例：
        # 通过环境变量自定义配置
        export VIZ_FIGSIZE=10,6
        export VIZ_DPI=150
        
        # 在代码中使用
        from core.config import config
        figsize = config.visualization.figsize  # (10, 6)
        dpi = config.visualization.dpi  # 150
    
    Attributes:
        visualization: 可视化配置实例
        paths: 路径配置实例
        security: 安全配置实例
    """
    
    def __init__(self):
        """初始化配置管理器
        
        从环境变量加载配置，如果环境变量不存在或无效，使用默认值。
        初始化后自动验证配置有效性。
        
        Raises:
            ValueError: 如果配置验证失败（例如 DPI 超出范围）
        """
        # 从环境变量加载可视化配置
        figsize = self._parse_figsize(os.getenv("VIZ_FIGSIZE", "8,5"))
        dpi = int(os.getenv("VIZ_DPI", "120"))
        
        self.visualization = VisualizationConfig(
            figsize=figsize,
            dpi=dpi
        )
        self.paths = PathConfig()
        self.security = SecurityConfig()
        
        # 验证配置有效性
        self._validate()
    
    def _parse_figsize(self, value: str) -> Tuple[int, int]:
        """解析 figsize 字符串
        
        Args:
            value: figsize 字符串，格式 "width,height"，例如 "8,5"
        
        Returns:
            元组 (width, height)
        
        Examples:
            >>> _parse_figsize("8,5")
            (8, 5)
            >>> _parse_figsize("10,6")
            (10, 6)
            >>> _parse_figsize("invalid")
            (8, 5)  # 回退到默认值
        """
        try:
            parts = value.split(',')
            if len(parts) != 2:
                return (8, 5)
            width, height = map(int, parts)
            return (width, height)
        except (ValueError, AttributeError):
            # 解析失败，返回默认值
            return (8, 5)
    
    def _validate(self):
        """验证配置有效性
        
        检查配置参数是否在合理范围内，如果验证失败则抛出异常。
        
        验证规则：
            - DPI 必须在 50-300 之间
            - figsize 的宽度和高度必须在 1-20 之间
        
        Raises:
            ValueError: 如果配置参数超出有效范围
        """
        # 验证 DPI 范围
        if not (50 <= self.visualization.dpi <= 300):
            raise ValueError(
                f"DPI must be between 50-300, got {self.visualization.dpi}"
            )
        
        # 验证 figsize 范围
        width, height = self.visualization.figsize
        if width <= 0 or height <= 0:
            raise ValueError(
                f"figsize dimensions must be positive, got {self.visualization.figsize}"
            )
        if width > 20 or height > 20:
            raise ValueError(
                f"figsize dimensions must be <= 20, got {self.visualization.figsize}"
            )


# 全局配置实例（单例模式）
# 在模块导入时创建，应用启动时自动加载和验证配置
config = AppConfig()
