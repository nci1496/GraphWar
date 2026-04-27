from dataclasses import dataclass
from enum import Enum

from .constants import (
    INTENT_ATTACK,
    LINE_ECONOMY,
    NEUTRAL,
    PLAINS,
    POLICY_NORMAL,
)


class Mode(Enum):
    PLAYING = "playing"
    VICTORY = "victory"
    DEFEAT = "defeat"


@dataclass
class Node:
    id: int
    x: float
    y: float
    site_type: str
    owner: str = NEUTRAL
    soldiers: float = 15.0
    production: float = 1.0
    defense: int = 0
    population: float = 0.0
    max_population: float = 0.0
    morale: float = 70.0
    local_gold: float = 0.0
    food: float = 0.0
    max_food: float = 0.0
    gold: float = 0.0
    max_gold: float = 0.0
    max_defense: int = 0
    development_line: str = LINE_ECONOMY
    development_level: int = 0
    supply_blocked_time: float = 0.0
    recruit_policy: str = POLICY_NORMAL
    sacked: bool = False
    rebel_warning: bool = False
    rebel_warning_timer: float = 0.0
    is_ruin: bool = False
    ruin_origin_type: str = ""
    ruin_origin_defense: int = 0
    ruin_origin_max_defense: int = 0


@dataclass
class Edge:
    a: int
    b: int
    terrain: str = PLAINS
    road_level: int = 0


@dataclass
class Troop:
    owner: str
    source: int
    target: int
    start_amount: float
    amount: float
    terrain: str
    intent: str = INTENT_ATTACK
    migrants: float = 0.0
    progress: float = 0.0
    batch_id: int = 0
    supply_source: int | None = None
    unsupplied_time: float = 0.0
    combat_power_modifier: float = 1.0
    depart_delay: float = 0.0


@dataclass
class Convoy:
    owner: str
    source: int
    target: int
    cargo: str
    amount: float
    terrain: str
    progress: float = 0.0
    route: tuple[int, ...] = ()
    route_index: int = 0
    morale_payload: float = 50.0


@dataclass
class Emperor:
    owner: str
    current_node: int = -1
    route: tuple[int, ...] = ()
    route_index: int = 0
    progress: float = 0.0
    alive: bool = True
    at_capital: bool = True
