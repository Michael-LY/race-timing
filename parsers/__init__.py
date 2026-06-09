from .base import BaseParser
from .tsl import TSLTimingParser

PARSER_REGISTRY: dict[str, BaseParser] = {
    "tsl_timing": TSLTimingParser(),
}


def get_parser(name: str) -> BaseParser | None:
    return PARSER_REGISTRY.get(name)


def list_parsers() -> list[dict]:
    return [
        {"key": key, "name": p.name, "description": p.description}
        for key, p in PARSER_REGISTRY.items()
    ]
