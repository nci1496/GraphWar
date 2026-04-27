WIDTH = 1280
HEIGHT = 780
FPS = 60
TOP_BAR = 82
LEFT_PANEL = 250
SIDE_PANEL = 300
MAP_LEFT = LEFT_PANEL
MAP_RIGHT = WIDTH - SIDE_PANEL

PLAYER = "player"
ENEMY = "enemy"
NEUTRAL = "neutral"
REBEL = "rebel"

CAPITAL = "capital"
TOWN = "town"
FORT = "fort"
VILLAGE = "village"

PLAINS = "plains"
MOUNTAIN = "mountain"
FORD = "ford"

INTENT_OCCUPY = "occupy"
INTENT_ATTACK = "attack"
INTENT_SACK = "sack"
INTENT_MIGRATE = "migrate"

LINE_ECONOMY = "economy"
LINE_MILITARY = "military"

CONVOY_FOOD = "food"
CONVOY_GOLD = "gold"
CONVOY_POP = "population"

POLICY_STOP = "stop"
POLICY_LOW = "low"
POLICY_NORMAL = "normal"
POLICY_HIGH = "high"

REMIT_INTERVAL = 12.0
REMIT_RATE = 0.5
FORTIFY_COST = 80
REPAIR_COST = 35
ROAD_COST = 70
UPGRADE_COST = 120
MAX_ROAD_LEVEL = 3
MAX_DEVELOPMENT_LEVEL = 4
TROOP_BATCH_SIZE = 12
TROOP_BATCH_INTERVAL = 0.35
UNSUPPLIED_POWER = 0.4
UNSUPPLIED_ROUT_SECONDS = 16.0
FOOD_PER_TROOP_LAUNCH = 0.12
FOOD_PER_TROOP_SECOND = 0.010
CONVOY_BATCH_RATIO = 0.45
CAPITAL_GOLD_CAP = 600.0
GARRISON_FOOD_PER_SOLDIER_SECOND = 0.012
LOW_FOOD_AUTO_SUPPLY_THRESHOLD = 90.0
LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH = 200.0
DEMOBILIZE_RATIO = 0.25
DEMOBILIZE_MORALE_BONUS = 8.0

REBEL_WARNING_SECONDS = 30.0
REBEL_SPEED_BOOST_MULTIPLIER = 3.0
REBEL_SPEED_BOOST_DURATION = 30.0
REBEL_RUIN_REPAIR_COST = 100
POP_PER_SOLDIER = 10.0
MAX_GARRISON_MULTIPLIER = 1.5
MIN_FOOD_CONVOY_AMOUNT = 100.0
MIN_POP_CONVOY_AMOUNT = 50.0
AUTO_MIGRATE_BATCH = 300.0
MIGRATION_BASE_LOSS = 0.12
MIGRATION_LOSS_PER_HOP = 0.06
LOW_FOOD_MORALE_THRESHOLD = 200.0
LOW_FOOD_MORALE_DROP = 0.55
ZERO_FOOD_MORALE_DROP = 1.15

EMPEROR_MOVE_SPEED_MULTIPLIER = 1.5
EMPEROR_NODE_MORALE_CAP = 120.0
EMPEROR_MORALE_RECOVERY_MULT = 1.25
EMPEROR_GOLD_PROD_MULT = 1.5
EMPEROR_LEAVE_CAPITAL_DEF_PENALTY = 2
EMPEROR_LEAVE_CAPITAL_MORALE_PENALTY = 20.0
CAPITAL_FALL_OWNER_MORALE_PENALTY = 10.0
CAPITAL_FALL_ATTACKER_MORALE_BONUS = 5.0
MOVE_CAPITAL_COST = 500.0
EMPEROR_DEATH_DEFENSE_PENALTY = 2
ANNEX_BASE_COST = 200.0
ANNEX_PER_SOLDIER_COST = 2.0
AI_MOVE_CAPITAL_COOLDOWN = 24.0

MAP_SIZE_PRESETS = {
    "small": {"label": "小图", "nodes": 13, "spacing": 118},
    "medium": {"label": "中图", "nodes": 18, "spacing": 96},
    "large": {"label": "大图", "nodes": 24, "spacing": 82},
}

SITE_STATS = {
    CAPITAL: {
        "label": "都城",
        "soldiers": (42, 56),
        "production": 2.5,
        "defense": 4,
        "radius": 30,
        "population": (2600, 3600),
        "tax": 0.0,
        "food": (1700, 3200),
        "gold": (140, 520),
        "food_rate": 0.30,
        "gold_rate": 0.08,
    },
    TOWN: {
        "label": "城镇",
        "soldiers": (0, 7),
        "production": 1.7,
        "defense": 2,
        "radius": 26,
        "population": (1300, 2200),
        "tax": 0.22,
        "food": (1300, 2800),
        "gold": (120, 560),
        "food_rate": 0.32,
        "gold_rate": 0.30,
    },
    FORT: {
        "label": "关隘",
        "soldiers": (0, 0),
        "production": 0.0,
        "defense": 5,
        "radius": 28,
        "population": (0, 0),
        "tax": 0.0,
        "food": (220, 700),
        "gold": (40, 320),
        "food_rate": 0.0,
        "gold_rate": 0.0,
    },
    VILLAGE: {
        "label": "村庄",
        "soldiers": (0, 4),
        "production": 0.9,
        "defense": 0,
        "radius": 23,
        "population": (480, 900),
        "tax": 0.10,
        "food": (1500, 3200),
        "gold": (30, 320),
        "food_rate": 0.42,
        "gold_rate": 0.08,
    },
}

ECONOMY_LINE = [
    {"name": "村庄", "pop": 1.00, "food": 1.00, "gold": 1.00, "defense": 0, "prod": 1.00, "upkeep": 1.00},
    {"name": "农贸集镇", "pop": 1.30, "food": 1.55, "gold": 1.80, "defense": 1, "prod": 0.98, "upkeep": 0.96},
    {"name": "富庶大镇", "pop": 1.65, "food": 2.05, "gold": 2.70, "defense": 2, "prod": 0.95, "upkeep": 0.93},
    {"name": "财赋郡城", "pop": 2.05, "food": 2.70, "gold": 3.90, "defense": 3, "prod": 0.92, "upkeep": 0.90},
    {"name": "天府名都", "pop": 2.55, "food": 3.50, "gold": 5.40, "defense": 3, "prod": 0.90, "upkeep": 0.88},
]

MILITARY_LINE = [
    {"name": "村落", "pop": 0.90, "food": 0.90, "gold": 0.75, "defense": 1, "prod": 1.05, "upkeep": 1.05},
    {"name": "边防坞堡", "pop": 0.95, "food": 0.95, "gold": 0.80, "defense": 3, "prod": 1.14, "upkeep": 1.10},
    {"name": "守备重镇", "pop": 1.05, "food": 1.00, "gold": 0.95, "defense": 5, "prod": 1.24, "upkeep": 1.16},
    {"name": "天下雄关", "pop": 1.10, "food": 1.05, "gold": 1.05, "defense": 7, "prod": 1.34, "upkeep": 1.22},
    {"name": "镇国雄都", "pop": 1.20, "food": 1.10, "gold": 1.20, "defense": 9, "prod": 1.45, "upkeep": 1.30},
]

TERRAIN_STATS = {
    PLAINS: {"label": "平原道", "speed": 0.15, "loss": 0.03, "color": (123, 92, 54), "width": 2},
    MOUNTAIN: {"label": "山路", "speed": 0.09, "loss": 0.12, "color": (95, 74, 48), "width": 3},
    FORD: {"label": "渡口", "speed": 0.12, "loss": 0.08, "color": (75, 103, 107), "width": 3},
}

RECRUIT_POLICIES = {
    POLICY_STOP: {"label": "停止", "rate": 0.0, "morale": 1.2},
    POLICY_LOW: {"label": "低征兵", "rate": 0.16, "morale": 0.15},
    POLICY_NORMAL: {"label": "常规", "rate": 0.42, "morale": -0.25},
    POLICY_HIGH: {"label": "强征", "rate": 0.82, "morale": -0.75},
}

INTENT_LABELS = {
    INTENT_OCCUPY: "占领",
    INTENT_ATTACK: "攻打",
    INTENT_SACK: "屠城",
    INTENT_MIGRATE: "迁徙",
}

COLORS = {
    "bg": (132, 91, 48),
    "map": (172, 129, 74),
    "panel": (88, 57, 32),
    "panel_hover": (119, 80, 43),
    "panel_dark": (63, 40, 24),
    "line_active": (246, 204, 116),
    "rebel_warning": (167, 138, 62),
    PLAYER: (170, 48, 42),
    ENEMY: (53, 101, 151),
    NEUTRAL: (126, 101, 70),
    REBEL: (228, 192, 72),
    "text": (250, 232, 190),
    "muted": (224, 193, 139),
    "gold": (241, 190, 83),
    "green": (99, 139, 80),
    "bad": (216, 103, 83),
    "black": (45, 28, 16),
    "white": (255, 242, 209),
}
