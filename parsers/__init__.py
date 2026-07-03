"""赛道计时应用 - CSV 解析器注册表"""

from .base import BaseParser
from .tsl import TSLTimingParser
from .swiss_timing import SwissTimingParser

# 解析器注册表：key 为模块标识，value 为解析器实例
PARSER_REGISTRY: dict[str, BaseParser] = {
    "tsl_timing": TSLTimingParser(),
    "swiss_timing": SwissTimingParser(),
}


def get_parser(name: str) -> BaseParser | None:
    """根据名称获取解析器实例"""
    return PARSER_REGISTRY.get(name)


def list_parsers() -> list[dict]:
    """列出所有可用的解析器"""
    return [
        {"key": key, "name": p.name, "description": p.description}
        for key, p in PARSER_REGISTRY.items()
    ]
