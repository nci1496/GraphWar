import math

import pygame

from .constants import (
    CAPITAL,
    ECONOMY_LINE,
    ENEMY,
    FORT,
    LINE_ECONOMY,
    LINE_MILITARY,
    MAX_DEVELOPMENT_LEVEL,
    MILITARY_LINE,
    NEUTRAL,
    PLAYER,
    REBEL,
    SITE_STATS,
    TOWN,
    VILLAGE,
)
from .models import Node


def is_taxable(node: Node) -> bool:
    return node.max_population > 0 and node.development_line != LINE_MILITARY and not node.sacked and not node.is_ruin


def is_recruitable(node: Node) -> bool:
    return node.site_type in (CAPITAL, TOWN, VILLAGE) and not node.sacked and not node.is_ruin


def development_data(node: Node) -> dict[str, float | int | str]:
    line = ECONOMY_LINE if node.development_line == LINE_ECONOMY else MILITARY_LINE
    return line[max(0, min(node.development_level, MAX_DEVELOPMENT_LEVEL))]


def development_bonus(node: Node) -> dict[str, float]:
    data = development_data(node)
    return {
        "food": float(data["food"]),
        "gold": float(data["gold"]),
        "pop": float(data["pop"]),
        "prod": float(data.get("prod", 1.0)),
        "upkeep": float(data.get("upkeep", 1.0)),
    }


def development_name(node: Node) -> str:
    if node.is_ruin:
        return "废墟"
    if node.site_type == CAPITAL and node.development_level == 0:
        return SITE_STATS[CAPITAL]["label"]
    if node.site_type == FORT and node.development_level == 0:
        return SITE_STATS[FORT]["label"]
    if node.site_type in (TOWN, VILLAGE) or node.development_level > 0:
        return str(development_data(node)["name"])
    return SITE_STATS[node.site_type]["label"]


def owner_label(owner: str) -> str:
    mapping = {
        PLAYER: "汉军",
        ENEMY: "敌军",
        NEUTRAL: "中立",
        REBEL: "黄巾",
    }
    return mapping.get(owner, owner)


def site_label(node: Node) -> str:
    display = getattr(node, "display_name", "")
    if display:
        return f"{display}#{node.id}"
    return f"{development_name(node)} {node.id}"


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    for name in ("Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "Arial Unicode MS"):
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.SysFont("consolas", size, bold=bold)


def distance(a: Node, b: Node) -> float:
    return distance_xy(a.x, a.y, b.x, b.y)


def distance_xy(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def normalize_edge(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
