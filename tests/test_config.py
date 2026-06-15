"""配置模块单元测试

测试 core/config.py 的配置加载、验证和环境变量覆盖功能。
"""

import os
import sys
import pytest
from unittest.mock import patch
import importlib.util


def _import_config_module():
    """直接导入 config.py 模块，避免触发 core/__init__.py 的导入链"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "core", 
        "config.py"
    )
    spec = importlib.util.spec_from_file_location("core_config", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    return config_module


def test_default_figsize():
    """验证默认 figsize 优化为 (8, 5)
    
    需求：1.1, 1.2 - 优化图表尺寸
    """
    config_module = _import_config_module()
    
    viz_config = config_module.VisualizationConfig()
    assert viz_config.figsize == (8, 5), \
        f"Expected default figsize (8, 5), got {viz_config.figsize}"


def test_default_dpi():
    """验证默认 DPI 优化为 120
    
    需求：1.1, 1.2 - 优化图表 DPI
    """
    config_module = _import_config_module()
    
    viz_config = config_module.VisualizationConfig()
    assert viz_config.dpi == 120, \
        f"Expected default DPI 120, got {viz_config.dpi}"


def test_visualization_config_frozen():
    """验证可视化配置为不可变（frozen=True）
    
    需求：2.7 - 配置验证和安全性
    """
    config_module = _import_config_module()
    
    viz_config = config_module.VisualizationConfig()
    
    # 尝试修改配置应该抛出异常
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        viz_config.figsize = (10, 6)


def test_path_config_defaults():
    """验证路径配置默认值
    
    需求：2.3 - 路径配置管理
    """
    config_module = _import_config_module()
    
    path_config = config_module.PathConfig()
    assert path_config.uploads_dir == "./data/uploads"
    assert path_config.outputs_dir == "./data/outputs"
    assert path_config.data_dict_path == "./data/data_dict.json"


def test_security_config_forbidden_modules():
    """验证安全配置包含关键禁用模块
    
    需求：2.4 - 沙箱安全配置
    """
    config_module = _import_config_module()
    
    security_config = config_module.SecurityConfig()
    
    # 验证关键危险模块在黑名单中
    dangerous_modules = {"os", "sys", "subprocess", "socket"}
    assert dangerous_modules.issubset(security_config.forbidden_modules), \
        f"Missing dangerous modules in forbidden_modules"


def test_security_config_forbidden_functions():
    """验证安全配置包含关键禁用函数
    
    需求：2.4 - 沙箱安全配置
    """
    config_module = _import_config_module()
    
    security_config = config_module.SecurityConfig()
    
    # 验证关键危险函数在黑名单中
    dangerous_functions = {"eval", "exec", "open", "__import__"}
    assert dangerous_functions.issubset(security_config.forbidden_functions), \
        f"Missing dangerous functions in forbidden_functions"


def test_security_config_max_retry_count():
    """验证安全配置的最大重试次数
    
    需求：2.4 - 沙箱安全配置
    """
    config_module = _import_config_module()
    
    security_config = config_module.SecurityConfig()
    assert security_config.max_retry_count == 3


def test_parse_figsize_valid():
    """测试 figsize 字符串解析 - 有效输入
    
    需求：2.5 - 从环境变量加载配置
    """
    config_module = _import_config_module()
    
    app_config = config_module.AppConfig()
    
    # 测试有效的 figsize 字符串
    assert app_config._parse_figsize("8,5") == (8, 5)
    assert app_config._parse_figsize("10,6") == (10, 6)
    assert app_config._parse_figsize("12,8") == (12, 8)


def test_parse_figsize_invalid_fallback():
    """测试 figsize 字符串解析 - 无效输入回退到默认值
    
    需求：2.5 - 配置解析错误处理
    """
    config_module = _import_config_module()
    
    app_config = config_module.AppConfig()
    
    # 测试无效输入应该回退到默认值 (8, 5)
    assert app_config._parse_figsize("invalid") == (8, 5)
    assert app_config._parse_figsize("abc,def") == (8, 5)
    assert app_config._parse_figsize("8") == (8, 5)  # 缺少逗号
    assert app_config._parse_figsize("8,5,10") == (8, 5)  # 太多参数
    assert app_config._parse_figsize("") == (8, 5)  # 空字符串


def test_config_validation_valid():
    """测试配置验证 - 有效配置通过
    
    需求：2.7, 7.4 - 配置验证
    """
    # 使用默认配置应该通过验证（不抛出异常）
    config_module = _import_config_module()
    
    try:
        app_config = config_module.AppConfig()
        assert app_config.visualization.dpi == 120
        assert app_config.visualization.figsize == (8, 5)
    except ValueError:
        pytest.fail("Valid configuration should not raise ValueError")


def test_config_validation_invalid_dpi_too_low():
    """测试配置验证 - DPI 过低抛出异常
    
    需求：2.7, 7.4 - 配置验证
    """
    config_module = _import_config_module()
    
    # 直接测试 AppConfig 的验证逻辑（不使用环境变量）
    # 创建一个具有无效 DPI 的配置对象
    try:
        with patch.dict(os.environ, {"VIZ_DPI": "30"}, clear=False):
            # 创建新的 AppConfig 实例触发验证
            invalid_config = config_module.AppConfig()
        pytest.fail("Expected ValueError for invalid DPI")
    except ValueError as e:
        assert "DPI must be between 50-300" in str(e)


def test_config_validation_invalid_dpi_too_high():
    """测试配置验证 - DPI 过高抛出异常
    
    需求：2.7, 7.4 - 配置验证
    """
    config_module = _import_config_module()
    
    try:
        with patch.dict(os.environ, {"VIZ_DPI": "500"}, clear=False):
            invalid_config = config_module.AppConfig()
        pytest.fail("Expected ValueError for invalid DPI")
    except ValueError as e:
        assert "DPI must be between 50-300" in str(e)


def test_config_validation_invalid_figsize_negative():
    """测试配置验证 - 负数 figsize 抛出异常
    
    需求：2.7, 7.4 - 配置验证
    """
    config_module = _import_config_module()
    
    try:
        with patch.dict(os.environ, {"VIZ_FIGSIZE": "-5,8"}, clear=False):
            invalid_config = config_module.AppConfig()
        pytest.fail("Expected ValueError for negative figsize")
    except ValueError as e:
        assert "figsize dimensions must be positive" in str(e)


def test_config_validation_invalid_figsize_too_large():
    """测试配置验证 - figsize 过大抛出异常
    
    需求：2.7, 7.4 - 配置验证
    """
    config_module = _import_config_module()
    
    try:
        with patch.dict(os.environ, {"VIZ_FIGSIZE": "25,30"}, clear=False):
            invalid_config = config_module.AppConfig()
        pytest.fail("Expected ValueError for oversized figsize")
    except ValueError as e:
        assert "figsize dimensions must be <= 20" in str(e)


def test_config_env_var_override_figsize():
    """测试从环境变量覆盖 figsize
    
    需求：2.5 - 支持环境变量覆盖
    """
    # 设置环境变量
    with patch.dict(os.environ, {"VIZ_FIGSIZE": "10,6", "VIZ_DPI": "120"}):
        config_module = _import_config_module()
        app_config = config_module.AppConfig()
        assert app_config.visualization.figsize == (10, 6), \
            f"Expected figsize (10, 6) from env var, got {app_config.visualization.figsize}"


def test_config_env_var_override_dpi():
    """测试从环境变量覆盖 DPI
    
    需求：2.5 - 支持环境变量覆盖
    """
    # 设置环境变量
    with patch.dict(os.environ, {"VIZ_DPI": "150", "VIZ_FIGSIZE": "8,5"}):
        config_module = _import_config_module()
        app_config = config_module.AppConfig()
        assert app_config.visualization.dpi == 150, \
            f"Expected DPI 150 from env var, got {app_config.visualization.dpi}"


def test_config_singleton_exists():
    """验证全局配置单例存在
    
    需求：2.6 - 其他模块可以导入配置
    """
    config_module = _import_config_module()
    
    # 验证 config 对象存在并可访问
    assert hasattr(config_module, 'config')
    config = config_module.config
    assert config is not None
    assert hasattr(config, 'visualization')
    assert hasattr(config, 'paths')
    assert hasattr(config, 'security')


def test_visualization_config_font_attributes():
    """验证可视化配置包含所有字体属性
    
    需求：2.2 - 图表可视化配置完整性
    """
    config_module = _import_config_module()
    
    viz_config = config_module.VisualizationConfig()
    
    # 验证字体大小配置
    assert hasattr(viz_config, 'font_size')
    assert hasattr(viz_config, 'title_size')
    assert hasattr(viz_config, 'label_size')
    assert hasattr(viz_config, 'legend_size')
    
    # 验证字体配置
    assert hasattr(viz_config, 'font_windows')
    assert hasattr(viz_config, 'font_macos')
    assert hasattr(viz_config, 'font_linux')


def test_visualization_config_color_attributes():
    """验证可视化配置包含颜色主题属性
    
    需求：2.2 - 图表可视化配置完整性
    """
    config_module = _import_config_module()
    
    viz_config = config_module.VisualizationConfig()
    
    # 验证颜色和主题配置
    assert hasattr(viz_config, 'style')
    assert hasattr(viz_config, 'palette')
    assert hasattr(viz_config, 'figure_facecolor')
    assert hasattr(viz_config, 'axes_facecolor')
    
    # 验证默认值
    assert viz_config.style == "whitegrid"
    assert viz_config.palette == "muted"


def test_config_comprehensive_attributes():
    """验证配置管理器包含所有必需属性
    
    需求：2.1, 2.2, 2.3, 2.4 - 配置管理完整性
    """
    config_module = _import_config_module()
    config = config_module.config
    
    # 验证三个主要配置类别
    assert hasattr(config, 'visualization')
    assert hasattr(config, 'paths')
    assert hasattr(config, 'security')
    
    # 验证可视化配置
    assert hasattr(config.visualization, 'figsize')
    assert hasattr(config.visualization, 'dpi')
    
    # 验证路径配置
    assert hasattr(config.paths, 'uploads_dir')
    assert hasattr(config.paths, 'outputs_dir')
    assert hasattr(config.paths, 'data_dict_path')
    
    # 验证安全配置
    assert hasattr(config.security, 'forbidden_modules')
    assert hasattr(config.security, 'forbidden_functions')
    assert hasattr(config.security, 'max_retry_count')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
