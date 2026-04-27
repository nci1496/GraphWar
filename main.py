from __future__ import annotations

import math
import random
from collections import deque

import pygame

from graphwar.constants import (
    CAPITAL,
    CAPITAL_GOLD_CAP,
    CONVOY_BATCH_RATIO,
    CONVOY_FOOD,
    CONVOY_GOLD,
    CONVOY_POP,
    DEMOBILIZE_MORALE_BONUS,
    DEMOBILIZE_RATIO,
    ENEMY,
    FOOD_PER_TROOP_LAUNCH,
    FOOD_PER_TROOP_SECOND,
    GARRISON_FOOD_PER_SOLDIER_SECOND,
    FORT,
    FORTIFY_COST,
    FPS,
    HEIGHT,
    INTENT_ATTACK,
    INTENT_LABELS,
    INTENT_MIGRATE,
    INTENT_OCCUPY,
    INTENT_SACK,
    LINE_ECONOMY,
    LINE_MILITARY,
    MAX_DEVELOPMENT_LEVEL,
    MAX_ROAD_LEVEL,
    MAP_SIZE_PRESETS,
    NEUTRAL,
    PLAYER,
    REBEL,
    POLICY_STOP,
    RECRUIT_POLICIES,
    REMIT_INTERVAL,
    REMIT_RATE,
    REPAIR_COST,
    ROAD_COST,
    SITE_STATS,
    TERRAIN_STATS,
    TOP_BAR,
    TOWN,
    TROOP_BATCH_INTERVAL,
    TROOP_BATCH_SIZE,
    UNSUPPLIED_POWER,
    UNSUPPLIED_ROUT_SECONDS,
    UPGRADE_COST,
    VILLAGE,
    WIDTH,
    LOW_FOOD_AUTO_SUPPLY_THRESHOLD,
    LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH,
    REBEL_RUIN_REPAIR_COST,
    REBEL_SPEED_BOOST_DURATION,
    REBEL_SPEED_BOOST_MULTIPLIER,
    REBEL_WARNING_SECONDS,
    POP_PER_SOLDIER,
    MAX_GARRISON_MULTIPLIER,
    MIN_FOOD_CONVOY_AMOUNT,
    MIN_POP_CONVOY_AMOUNT,
    AUTO_MIGRATE_BATCH,
    MIGRATION_BASE_LOSS,
    MIGRATION_LOSS_PER_HOP,
    LOW_FOOD_MORALE_THRESHOLD,
    LOW_FOOD_MORALE_DROP,
    ZERO_FOOD_MORALE_DROP,
    EMPEROR_MOVE_SPEED_MULTIPLIER,
    EMPEROR_NODE_MORALE_CAP,
    EMPEROR_MORALE_RECOVERY_MULT,
    EMPEROR_GOLD_PROD_MULT,
    EMPEROR_LEAVE_CAPITAL_DEF_PENALTY,
    EMPEROR_LEAVE_CAPITAL_MORALE_PENALTY,
    CAPITAL_FALL_OWNER_MORALE_PENALTY,
    CAPITAL_FALL_ATTACKER_MORALE_BONUS,
    MOVE_CAPITAL_COST,
    EMPEROR_DEATH_DEFENSE_PENALTY,
    ANNEX_BASE_COST,
    ANNEX_PER_SOLDIER_COST,
    AI_MOVE_CAPITAL_COOLDOWN,
)
from graphwar.helpers import (
    clamp,
    development_bonus,
    development_data,
    development_name,
    distance,
    is_recruitable,
    is_taxable,
    load_font,
    normalize_edge,
    site_label,
)
from graphwar.ai_logic import GraphWarAI
from graphwar.input_logic import InputLogicMixin
from graphwar.map_logic import MapLogicMixin
from graphwar.models import Convoy, Edge, Emperor, Mode, Node, Troop
from graphwar.rendering import RenderingMixin


class GraphWar(InputLogicMixin, MapLogicMixin, RenderingMixin):
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("GraphWar - 古代城池攻防")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = load_font(18)
        self.small_font = load_font(15)
        self.big_font = load_font(38, bold=True)
        self.mid_font = load_font(24, bold=True)

        self.rng = random.Random()
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.troops: list[Troop] = []
        self.convoys: list[Convoy] = []
        self.selected: int | None = None
        self.inspecting: int | None = None
        self.send_ratio = 0.5
        self.intent = INTENT_ATTACK
        self.repair_mode = False
        self.convoy_mode: str | None = None
        self.convoy_route: list[int] = []
        self.treasury = 120.0
        self.remit_timer = REMIT_INTERVAL
        self.developer_mode = False
        self.auto_fund_neighbors = True
        self.auto_fund_capital = True
        self.auto_supply_neighbors = True
        self.auto_supply_capital = True
        self.auto_supply_low_enabled = True
        self.auto_supply_low_enabled_90 = True
        self.auto_supply_low_enabled_200 = False
        self.auto_supply_low_enabled_military_half = True
        self.auto_pop_redistribute_near = False
        self.auto_pop_redistribute_global = False
        self.auto_supply_low_threshold = LOW_FOOD_AUTO_SUPPLY_THRESHOLD
        self.auto_supply_low_cooldowns: dict[int, float] = {}
        self.rebel_speed_boost_timer = 0.0
        self.pending_action: dict[str, int | float | str] | None = None
        self.map_size_mode = "small"
        self.emperors: dict[str, Emperor] = {}
        self.capital_node_ids: dict[str, int] = {}
        self.ai_capital_move_cooldowns: dict[str, float] = {}
        self.mode = Mode.PLAYING
        self.message = "选择蓝色据点，再点击相邻目标进行操作。"
        self.ai_timer = 0.0
        self.rebel_ai_timer = 0.0
        self.ai_engine = GraphWarAI()
        self.start_new_war()

    def start_new_war(self) -> None:
        self.treasury = 120.0
        self.remit_timer = REMIT_INTERVAL
        self.nodes, self.edges = self.generate_map()
        capital = self.player_capital()
        if capital is not None:
            capital.max_gold = CAPITAL_GOLD_CAP
            capital.gold = min(capital.gold, capital.max_gold)
            capital.local_gold = capital.gold
            self.treasury = capital.gold
        self.troops.clear()
        self.convoys.clear()
        self.pending_action = None
        self.selected = None
        self.inspecting = None
        self.intent = INTENT_ATTACK
        self.repair_mode = False
        self.convoy_mode = None
        self.convoy_route = []
        self.auto_supply_low_cooldowns = {}
        self.rebel_speed_boost_timer = 0.0
        self.emperors = self.build_emperors()
        self.capital_node_ids = self.detect_capitals()
        self.ai_capital_move_cooldowns = {PLAYER: 0.0, ENEMY: 0.0}
        self.mode = Mode.PLAYING
        self.ai_timer = 2.0
        self.rebel_ai_timer = 0.3
        self.message = "治理地方、积蓄财粮，最终统一天下。"

    def player_capital(self) -> Node | None:
        capitals = [node for node in self.nodes if node.owner == PLAYER and node.site_type == CAPITAL]
        return capitals[0] if capitals else None

    def detect_capitals(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for node in self.nodes:
            if node.site_type == CAPITAL and node.owner in (PLAYER, ENEMY):
                result[node.owner] = node.id
        return result

    def owner_capital(self, owner: str) -> Node | None:
        cid = self.capital_node_ids.get(owner, -1)
        if 0 <= cid < len(self.nodes):
            node = self.nodes[cid]
            if node.owner == owner:
                return node
        for node in self.nodes:
            if node.owner == owner and node.site_type == CAPITAL:
                self.capital_node_ids[owner] = node.id
                return node
        return None

    def build_emperors(self) -> dict[str, Emperor]:
        emperors: dict[str, Emperor] = {}
        for owner in (PLAYER, ENEMY):
            cap = self.owner_capital(owner)
            if cap is not None:
                emperors[owner] = Emperor(owner=owner, current_node=cap.id, alive=True, at_capital=True)
        return emperors

    def emperor_node(self, owner: str) -> Node | None:
        emperor = self.emperors.get(owner)
        if emperor is None or not emperor.alive or emperor.current_node < 0:
            return None
        if emperor.current_node >= len(self.nodes):
            return None
        return self.nodes[emperor.current_node]

    def node_morale_cap(self, node: Node) -> float:
        for emperor in self.emperors.values():
            if emperor.alive and emperor.current_node == node.id:
                return EMPEROR_NODE_MORALE_CAP
        return 100.0

    def adjust_node_morale(self, node: Node, delta: float) -> None:
        if node.max_population <= 0:
            node.morale = 0.0
            return
        node.morale = clamp(node.morale + delta, 0.0, self.node_morale_cap(node))

    def apply_emperor_aura(self, owner: str, node: Node, gold_rate: float, morale_recovery: float) -> tuple[float, float]:
        emperor = self.emperors.get(owner)
        if emperor is None or not emperor.alive or emperor.current_node != node.id:
            return gold_rate, morale_recovery
        return gold_rate * EMPEROR_GOLD_PROD_MULT, morale_recovery * EMPEROR_MORALE_RECOVERY_MULT

    def update_emperors(self, dt: float) -> None:
        for owner, emperor in self.emperors.items():
            if not emperor.alive:
                continue
            if len(emperor.route) >= 2 and emperor.route_index < len(emperor.route) - 1:
                a = emperor.route[emperor.route_index]
                b = emperor.route[emperor.route_index + 1]
                if a >= len(self.nodes) or b >= len(self.nodes):
                    self.kill_emperor(owner, "皇帝遇袭身亡")
                    continue
                start_node = self.nodes[a]
                end_node = self.nodes[b]
                if start_node.owner != owner or end_node.owner != owner:
                    self.kill_emperor(owner, "皇帝在途中被伏击")
                    continue
                edge = self.edge_between(a, b)
                if edge is None:
                    self.kill_emperor(owner, "皇帝迷失道路")
                    continue
                terrain = TERRAIN_STATS[edge.terrain]
                speed = terrain["speed"] * (1 + edge.road_level * 0.28) * EMPEROR_MOVE_SPEED_MULTIPLIER
                emperor.progress = min(1.0, emperor.progress + speed * dt)
                emperor.current_node = -1
                if emperor.progress >= 1.0:
                    emperor.route_index += 1
                    emperor.progress = 0.0
                    if emperor.route_index >= len(emperor.route) - 1:
                        emperor.current_node = emperor.route[-1]
                        emperor.route = ()
                        emperor.route_index = 0
            elif emperor.current_node >= 0:
                node = self.nodes[emperor.current_node]
                if node.owner != owner:
                    self.kill_emperor(owner, "皇帝驻地失守")

    def update_population_redistribution(self, dt: float) -> None:
        if dt <= 0:
            return
        if not (self.auto_pop_redistribute_near or self.auto_pop_redistribute_global):
            return
        for node in self.nodes:
            if node.owner != PLAYER or node.max_population <= 0:
                continue
            if node.population + 1.0 < node.max_population:
                continue
            if self.auto_pop_redistribute_near:
                self.auto_migrate_from_node(node, near_only=True, threshold_ratio=0.6)
            if self.auto_pop_redistribute_global:
                self.auto_migrate_from_node(node, near_only=False, threshold_ratio=0.4)

    def move_emperor(self, owner: str, target_id: int) -> bool:
        emperor = self.emperors.get(owner)
        if emperor is None or not emperor.alive:
            return False
        if target_id < 0 or target_id >= len(self.nodes):
            return False
        if emperor.current_node < 0:
            return False
        target = self.nodes[target_id]
        if target.owner != owner:
            return False
        if target_id == emperor.current_node:
            return False
        path = self.find_owned_path(emperor.current_node, target_id, owner)
        if path is None or len(path) < 2:
            return False
        self.apply_emperor_leave_capital_penalty(owner)
        emperor.route = tuple(path)
        emperor.route_index = 0
        emperor.progress = 0.0
        emperor.at_capital = False
        if owner == PLAYER:
            self.message = f"皇帝已启程前往 {site_label(target)}。"
        return True

    def apply_emperor_leave_capital_penalty(self, owner: str) -> None:
        emperor = self.emperors.get(owner)
        if emperor is None or not emperor.alive or emperor.current_node < 0:
            return
        capital = self.owner_capital(owner)
        if capital is None or emperor.current_node != capital.id:
            return
        capital.max_defense = max(0, capital.max_defense - EMPEROR_LEAVE_CAPITAL_DEF_PENALTY)
        capital.defense = min(capital.defense, capital.max_defense)
        self.adjust_node_morale(capital, -EMPEROR_LEAVE_CAPITAL_MORALE_PENALTY)

    def on_capital_lost(self, loser: str, winner: str) -> None:
        for node in self.nodes:
            if node.owner == loser and node.max_population > 0:
                self.adjust_node_morale(node, -CAPITAL_FALL_OWNER_MORALE_PENALTY)
            elif node.owner == winner and node.max_population > 0:
                self.adjust_node_morale(node, CAPITAL_FALL_ATTACKER_MORALE_BONUS)

    def set_new_capital(self, owner: str, node_id: int, by_ai: bool = False) -> bool:
        node = self.nodes[node_id]
        if node.owner != owner or node.site_type != TOWN:
            return False
        if node.gold < MOVE_CAPITAL_COST:
            return False
        node.gold -= MOVE_CAPITAL_COST
        node.local_gold = node.gold
        old_capital = self.owner_capital(owner)
        if old_capital is not None and old_capital.id != node.id:
            old_capital.site_type = TOWN
            old_capital.max_defense = max(0, old_capital.max_defense - 2)
            old_capital.defense = min(old_capital.defense, old_capital.max_defense)
        node.site_type = CAPITAL
        node.max_defense += 2
        node.defense = min(node.max_defense, node.defense + 2)
        node.max_population = max(node.max_population, SITE_STATS[CAPITAL]["population"][1])
        node.max_gold = max(node.max_gold, CAPITAL_GOLD_CAP)
        node.gold = min(node.gold, node.max_gold)
        self.capital_node_ids[owner] = node.id
        emperor = self.emperors.get(owner)
        if emperor is not None and emperor.alive:
            emperor.current_node = node.id
            emperor.route = ()
            emperor.route_index = 0
            emperor.progress = 0.0
            emperor.at_capital = True
        if owner == PLAYER and not by_ai:
            self.message = f"已迁都至 {site_label(node)}。"
        return True

    def kill_emperor(self, owner: str, reason: str) -> None:
        emperor = self.emperors.get(owner)
        if emperor is None or not emperor.alive:
            return
        emperor.alive = False
        emperor.route = ()
        emperor.route_index = 0
        emperor.progress = 0.0
        emperor.current_node = -1
        for node in self.nodes:
            if node.owner != owner:
                continue
            node.max_defense = max(0, node.max_defense - EMPEROR_DEATH_DEFENSE_PENALTY)
            node.defense = min(node.defense, node.max_defense)
        if owner == PLAYER:
            self.message = f"皇帝驾崩：{reason}。全境城防受损，可被招安。"

    def annex_cost(self, node: Node) -> float:
        return ANNEX_BASE_COST + ANNEX_PER_SOLDIER_COST * max(0.0, node.soldiers)

    def try_annex_node(self, actor_owner: str, target_id: int) -> bool:
        target = self.nodes[target_id]
        if target.owner in (actor_owner, NEUTRAL, REBEL):
            return False
        enemy_emperor = self.emperors.get(target.owner)
        if enemy_emperor is None or enemy_emperor.alive:
            if actor_owner == PLAYER:
                self.message = "对方皇帝尚存，无法招安。"
            return False
        owned_nodes = [n for n in self.nodes if n.owner == actor_owner]
        if not owned_nodes:
            return False
        payer = max(owned_nodes, key=lambda n: n.gold)
        cost = self.annex_cost(target)
        if payer.gold < cost:
            if actor_owner == PLAYER:
                self.message = f"招安需 {int(cost)} 金，资金不足。"
            return False
        payer.gold -= cost
        payer.local_gold = payer.gold
        target.owner = actor_owner
        target.rebel_warning = False
        target.rebel_warning_timer = 0.0
        if actor_owner == PLAYER:
            self.message = f"已招安 {site_label(target)}。"
        return True

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
            self.update(dt)
            self.draw()
        pygame.quit()

    def update(self, dt: float) -> None:
        if self.mode != Mode.PLAYING:
            return
        self.update_emperors(dt)
        self.update_economy(dt)
        self.update_population_redistribution(dt)
        self.update_rebel_warnings(dt)
        self.update_troops(dt)
        self.update_convoys(dt)
        self.process_pending_action()
        self.rebel_speed_boost_timer = max(0.0, self.rebel_speed_boost_timer - dt)
        self.ai_capital_move_cooldowns[PLAYER] = max(0.0, self.ai_capital_move_cooldowns.get(PLAYER, 0.0) - dt)
        self.ai_capital_move_cooldowns[ENEMY] = max(0.0, self.ai_capital_move_cooldowns.get(ENEMY, 0.0) - dt)
        self.ai_timer -= dt
        if self.ai_timer <= 0:
            self.enemy_turn()
            self.ai_timer = self.rng.uniform(2.8, 4.8)
        self.rebel_ai_timer -= dt
        if self.rebel_ai_timer <= 0:
            self.rebel_turn()
            self.rebel_ai_timer = self.rng.uniform(0.22, 0.45)
        self.check_end_state()

    def update_economy(self, dt: float) -> None:
        self.remit_timer -= dt
        for node in self.nodes:
            if node.owner == REBEL:
                continue
            if node.owner == ENEMY:
                self.apply_enemy_recruitment(node, dt)
                continue
            if node.owner != PLAYER:
                continue

            if is_taxable(node) and node.population > 0 and not node.sacked:
                morale_factor = clamp(node.morale / 100, 0.15, 1.25)
                line_bonus = development_bonus(node)["gold"]
                base_rate = 0.75 if node.site_type == TOWN else 0.5
                if node.site_type == CAPITAL:
                    base_rate = 0.85
                if node.development_line == LINE_ECONOMY and node.development_level > 0:
                    econ_bonus = (3.0, 5.0, 7.0, 7.0)
                    base_rate += econ_bonus[min(node.development_level - 1, len(econ_bonus) - 1)]
                gold_rate, _ = self.apply_emperor_aura(PLAYER, node, base_rate, 1.0)
                node.gold = min(
                    node.max_gold,
                    node.gold + gold_rate * (node.population / 650) * morale_factor * line_bonus * dt,
                )
                node.local_gold = node.gold

            military_upgraded = node.development_line == LINE_MILITARY and node.development_level > 0
            if node.population > 0 and not node.sacked and node.max_food > 0 and not military_upgraded:
                line_bonus = development_bonus(node)["food"]
                morale_factor = clamp(node.morale / 100, 0.2, 1.15)
                node.food = min(
                    node.max_food,
                    node.food + SITE_STATS[node.site_type]["food_rate"] * (node.population / 500) * morale_factor * line_bonus * dt,
                )

            if node.population > 0 and node.population < node.max_population and not node.sacked:
                growth = node.max_population * 0.00036 * clamp(node.morale / 80, 0.25, 1.25) * dt
                if node.development_line == LINE_ECONOMY:
                    growth *= 1.25
                node.population = min(node.max_population, node.population + growth)

            self.apply_recruitment(node, dt)

        # All nodes consume garrison food over time.
        for node in self.nodes:
            self.apply_garrison_food_and_stability(node, dt)
            self.apply_low_food_morale_decay(node, dt)

        if self.remit_timer <= 0:
            self.collect_taxes()
            self.remit_timer = REMIT_INTERVAL

    def apply_enemy_recruitment(self, node: Node, dt: float) -> None:
        line_bonus = development_bonus(node)
        military_upgraded = node.development_line == LINE_MILITARY and node.development_level > 0
        if node.population > 0 and not node.sacked and node.max_food > 0 and not military_upgraded:
            node.food = min(
                node.max_food,
                node.food + SITE_STATS[node.site_type]["food_rate"] * (node.population / 650) * line_bonus["food"] * dt,
            )
        if not is_recruitable(node) or node.population <= 0 or node.sacked:
            node.recruit_policy = POLICY_STOP
            return
        if node.population <= node.max_population * 0.2:
            node.recruit_policy = POLICY_STOP
            return
        morale_factor = clamp(node.morale / 85, 0.35, 1.0)
        gain = 0.18 * node.production * line_bonus["prod"] * morale_factor * dt
        food_need = gain * 1.1
        if node.food <= 0:
            return
        if node.food < food_need:
            gain *= node.food / max(food_need, 0.001)
            food_need = node.food
        pop_cost = gain * POP_PER_SOLDIER
        if node.population <= pop_cost:
            gain = max(0.0, node.population / POP_PER_SOLDIER)
            pop_cost = node.population
            food_need = min(food_need, gain * 1.1)
        node.soldiers += gain
        node.soldiers = min(node.soldiers, self.garrison_limit(node) * MAX_GARRISON_MULTIPLIER)
        node.population -= pop_cost
        node.food = max(0.0, node.food - food_need)
        node.morale = clamp(node.morale - 0.05 * dt, 0, 100)

    def apply_recruitment(self, node: Node, dt: float) -> None:
        policy = RECRUIT_POLICIES[node.recruit_policy]
        line_bonus = development_bonus(node)
        if not is_recruitable(node) or node.population <= 0 or node.sacked:
            node.recruit_policy = POLICY_STOP
            node.morale = clamp(node.morale + 0.45 * dt, 0, self.node_morale_cap(node))
            return
        if node.population <= node.max_population * 0.2:
            node.recruit_policy = POLICY_STOP
            node.morale = clamp(node.morale + 0.3 * dt, 0, self.node_morale_cap(node))
            return
        if node.recruit_policy == POLICY_STOP:
            morale_gain = policy["morale"] * dt
            _, morale_gain = self.apply_emperor_aura(node.owner, node, 1.0, morale_gain)
            node.morale = clamp(node.morale + morale_gain, 0, self.node_morale_cap(node))
            return
        if node.morale < 18:
            node.morale = clamp(node.morale + 0.12 * dt, 0, self.node_morale_cap(node))
            return
        morale_factor = clamp(node.morale / 80, 0.35, 1.1)
        gain = policy["rate"] * node.production * line_bonus["prod"] * morale_factor * dt
        food_need = gain * 1.2
        if node.food <= 0:
            return
        if node.food < food_need:
            gain *= node.food / max(food_need, 0.001)
            food_need = node.food
        pop_cost = gain * POP_PER_SOLDIER
        if node.population <= pop_cost:
            gain = max(0.0, node.population / POP_PER_SOLDIER)
            pop_cost = node.population
            food_need = min(food_need, gain * 1.2)
        node.soldiers += gain
        node.soldiers = min(node.soldiers, self.garrison_limit(node) * MAX_GARRISON_MULTIPLIER)
        node.population -= pop_cost
        node.food = max(0.0, node.food - food_need)
        node.morale = clamp(node.morale + policy["morale"] * dt, 0, self.node_morale_cap(node))

    def defense_cap(self, node: Node) -> int:
        if node.site_type == CAPITAL:
            return 12
        if node.site_type == FORT:
            return 12
        if node.development_level <= 0:
            if node.site_type == VILLAGE:
                return 1
            if node.site_type == TOWN:
                return 2
            return max(1, node.max_defense)
        if node.development_line == LINE_ECONOMY:
            if node.development_level <= 2:
                return 2
            return 3
        if node.development_level == 1:
            return 3
        if node.development_level == 2:
            return 5
        return 7

    def garrison_limit(self, node: Node) -> float:
        if node.site_type == CAPITAL:
            return 180.0
        if node.site_type == FORT:
            return 120.0
        if node.development_level <= 0:
            if node.site_type == VILLAGE:
                return 15.0
            if node.site_type == TOWN:
                return 25.0
            return 25.0
        if node.development_line == LINE_ECONOMY:
            if node.development_level == 1:
                return 30.0
            if node.development_level == 2:
                return 35.0
            return 40.0
        if node.development_level == 1:
            return 50.0
        if node.development_level == 2:
            return 70.0
        return 120.0

    def apply_low_food_morale_decay(self, node: Node, dt: float) -> None:
        if node.owner not in (PLAYER, ENEMY):
            return
        if node.site_type == FORT or node.max_population <= 0 or node.is_ruin:
            return
        if node.food <= 0:
            node.morale = clamp(node.morale - ZERO_FOOD_MORALE_DROP * dt, 0, self.node_morale_cap(node))
            return
        if node.food < LOW_FOOD_MORALE_THRESHOLD:
            node.morale = clamp(node.morale - LOW_FOOD_MORALE_DROP * dt, 0, self.node_morale_cap(node))

    def node_gold_rate(self, node: Node) -> float:
        if not is_taxable(node) or node.population <= 0:
            return 0.0
        morale_factor = clamp(node.morale / 100, 0.15, 1.25)
        line_bonus = development_bonus(node)["gold"]
        base_rate = 0.75 if node.site_type == TOWN else 0.5
        if node.site_type == CAPITAL:
            base_rate = 0.85
        if node.development_line == LINE_ECONOMY and node.development_level > 0:
            econ_bonus = (3.0, 5.0, 7.0, 7.0)
            base_rate += econ_bonus[min(node.development_level - 1, len(econ_bonus) - 1)]
        base_rate, _ = self.apply_emperor_aura(node.owner, node, base_rate, 1.0)
        return base_rate * (node.population / 650) * morale_factor * line_bonus

    def node_food_production_rate(self, node: Node) -> float:
        if node.population <= 0 or node.sacked or node.max_food <= 0:
            return 0.0
        military_upgraded = node.development_line == LINE_MILITARY and node.development_level > 0
        if military_upgraded or node.owner == REBEL:
            return 0.0
        line_bonus = development_bonus(node)["food"]
        morale_factor = clamp(node.morale / 100, 0.2, 1.15)
        return SITE_STATS[node.site_type]["food_rate"] * (node.population / 500) * morale_factor * line_bonus

    def node_resident_food_consumption_rate(self, node: Node) -> float:
        if node.population <= 0:
            return 0.0
        return node.population / 1300.0

    def node_army_food_consumption_rate(self, node: Node) -> float:
        if node.owner == REBEL:
            return 0.0
        upkeep_factor = development_bonus(node)["upkeep"]
        if node.development_line == LINE_MILITARY and node.development_level > 0:
            upkeep_factor *= 10.0
        defense_weight = 1.0 + max(0.0, node.max_defense) * 0.12
        upkeep_factor *= defense_weight
        cap = self.garrison_limit(node)
        normal_soldiers = min(node.soldiers, cap)
        overflow = max(0.0, node.soldiers - cap)
        weighted_soldiers = normal_soldiers + overflow * 10.0
        return max(0.0, weighted_soldiers * GARRISON_FOOD_PER_SOLDIER_SECOND * upkeep_factor)

    def apply_garrison_food_and_stability(self, node: Node, dt: float) -> None:
        if node.owner == REBEL:
            node.supply_blocked_time = max(0.0, node.supply_blocked_time - dt)
            return

        # Forts never produce food; they must be supplied from surrounding nodes.
        if node.owner == PLAYER and node.site_type == FORT:
            node.food = min(node.food, node.max_food)

        # Optional automatic local replenishment for low food.
        if node.owner == PLAYER and self.auto_supply_low_enabled:
            should_auto = False
            needed = 0.0
            if self.auto_supply_low_enabled_90 and node.food < LOW_FOOD_AUTO_SUPPLY_THRESHOLD:
                should_auto = True
                needed = max(needed, LOW_FOOD_AUTO_SUPPLY_THRESHOLD - node.food)
            if self.auto_supply_low_enabled_200 and node.food < LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH:
                should_auto = True
                needed = max(needed, LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH - node.food)
            if (
                self.auto_supply_low_enabled_military_half
                and node.development_line == LINE_MILITARY
                and node.development_level > 0
                and node.max_food > 0
                and node.food < node.max_food * 0.5
            ):
                should_auto = True
                needed = max(needed, node.max_food * 0.5 - node.food)
            if should_auto and needed > 0:
                cooldown = self.auto_supply_low_cooldowns.get(node.id, 0.0) - dt
                self.auto_supply_low_cooldowns[node.id] = cooldown
                if cooldown <= 0:
                    sent = self.request_auto_food(node.id, needed)
                    if sent > 0:
                        self.auto_supply_low_cooldowns[node.id] = 4.0

        upkeep_factor = development_bonus(node)["upkeep"]
        if node.development_line == LINE_MILITARY and node.development_level > 0:
            upkeep_factor *= 10.0
        defense_weight = 1.0 + max(0.0, node.max_defense) * 0.12
        upkeep_factor *= defense_weight
        cap = self.garrison_limit(node)
        normal_soldiers = min(node.soldiers, cap)
        overflow = max(0.0, node.soldiers - cap)
        weighted_soldiers = normal_soldiers + overflow * 10.0
        need = max(0.0, weighted_soldiers * GARRISON_FOOD_PER_SOLDIER_SECOND * upkeep_factor * dt)
        if need <= 0:
            node.supply_blocked_time = max(0.0, node.supply_blocked_time - dt * 0.5)
            return

        if node.food >= need:
            node.food -= need
            node.supply_blocked_time = max(0.0, node.supply_blocked_time - dt * 0.6)
            return

        # Starving nodes lose their defensive structure value temporarily.
        node.food = 0.0
        node.supply_blocked_time += dt
        node.defense = 0

        # Capitals and forts cannot be subverted.
        if node.site_type in (CAPITAL, FORT):
            return
        if node.max_population <= 0:
            return
        if node.owner not in (PLAYER, ENEMY):
            return
        has_pressure = any(self.nodes[nid].owner != node.owner for nid in self.neighbor_ids(node.id))
        if not has_pressure:
            return

        # Rebellion chance rises with starvation duration and low morale.
        morale_factor = max(0.0, (60 - node.morale) / 60.0)
        chance_per_second = clamp(0.004 + node.supply_blocked_time * 0.002 + morale_factor * 0.06, 0.0, 0.25)
        if self.rng.random() < chance_per_second * dt:
            self.mark_rebel_warning(node, "断粮失序")
            if False:
                self.message = f"{site_label(node)} 因断粮与低民心被策反。"

    def collect_taxes(self) -> None:
        gained = 0.0
        capital = self.player_capital()
        if capital is None:
            return
        capital.max_gold = CAPITAL_GOLD_CAP
        for node in self.nodes:
            if (
                node.owner == PLAYER
                and is_taxable(node)
                and node.id != capital.id
                and node.gold >= node.max_gold - 0.01
            ):
                remitted = node.gold * REMIT_RATE
                node.gold -= remitted
                node.local_gold = node.gold
                gained += remitted
        capital.gold = min(capital.max_gold, capital.gold + gained)
        capital.local_gold = capital.gold
        self.treasury = capital.gold
        if gained > 0:
            self.message = f"地方向都城上缴 {int(gained)} 金。"

    def update_troops(self, dt: float) -> None:
        arrived: list[Troop] = []
        routed: list[Troop] = []
        for troop in self.troops:
            if troop.depart_delay > 0:
                troop.depart_delay -= dt
                continue
            edge = self.edge_between(troop.source, troop.target)
            if edge is None:
                continue
            if troop.intent != INTENT_MIGRATE:
                if self.consume_troop_supply(troop, dt):
                    troop.unsupplied_time = max(0.0, troop.unsupplied_time - dt * 0.5)
                    troop.combat_power_modifier = 1.0
                else:
                    troop.unsupplied_time += dt
                    troop.combat_power_modifier = UNSUPPLIED_POWER
                    if troop.unsupplied_time >= UNSUPPLIED_ROUT_SECONDS:
                        routed.append(troop)
                        continue
            terrain = TERRAIN_STATS[troop.terrain]
            speed = terrain["speed"] * (1 + edge.road_level * 0.28)
            troop.progress = min(1.0, troop.progress + speed * dt)
            troop.amount = max(1.0, troop.start_amount * (1 - terrain["loss"] * troop.progress))
            if troop.progress >= 1.0:
                arrived.append(troop)

        for troop in routed:
            if troop in self.troops:
                self.troops.remove(troop)
                if troop.owner == PLAYER:
                    self.message = "有一支断粮兵团溃散。"

        self.resolve_encounters()
        for troop in arrived:
            if troop not in self.troops:
                continue
            self.resolve_arrival(troop)
            if troop in self.troops:
                self.troops.remove(troop)

    def consume_troop_supply(self, troop: Troop, dt: float) -> bool:
        if troop.supply_source is None:
            troop.supply_source = troop.source
        if troop.supply_source >= len(self.nodes):
            return False
        source = self.nodes[troop.supply_source]
        road_base = self.nodes[troop.source]
        if source.owner != troop.owner or road_base.owner != troop.owner:
            return False
        if not self.connected_by_owner(source.id, road_base.id, troop.owner):
            return False
        need = max(0.04, troop.amount * FOOD_PER_TROOP_SECOND * dt)
        if source.food < need:
            return False
        source.food -= need
        return True

    def connected_by_owner(self, start: int, goal: int, owner: str) -> bool:
        if start == goal:
            return True
        seen = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for neighbor_id in self.neighbor_ids(current):
                if neighbor_id in seen:
                    continue
                neighbor = self.nodes[neighbor_id]
                if neighbor.owner != owner:
                    continue
                if neighbor_id == goal:
                    return True
                seen.add(neighbor_id)
                frontier.append(neighbor_id)
        return False

    def resolve_encounters(self) -> None:
        handled: set[int] = set()
        current = list(self.troops)
        for i, first in enumerate(current):
            if i in handled or first.depart_delay > 0:
                continue
            for j, second in enumerate(current):
                if j <= i or j in handled or second.depart_delay > 0:
                    continue
                if first.owner == second.owner:
                    continue
                if first.source == second.target and first.target == second.source and first.progress + second.progress >= 0.96:
                    self.resolve_encounter(first, second)
                    handled.add(i)
                    handled.add(j)
                    break

    def resolve_encounter(self, first: Troop, second: Troop) -> None:
        first_power = first.amount * first.combat_power_modifier
        second_power = second.amount * second.combat_power_modifier
        first_loss = min(first.amount, second_power * 0.85)
        second_loss = min(second.amount, first_power * 0.85)
        first.amount -= first_loss
        second.amount -= second_loss
        first.start_amount = min(first.start_amount, max(0.0, first.amount))
        second.start_amount = min(second.start_amount, max(0.0, second.amount))
        if first.amount <= 1 and first in self.troops:
            self.troops.remove(first)
        if second.amount <= 1 and second in self.troops:
            self.troops.remove(second)
        if first.owner == PLAYER or second.owner == PLAYER:
            self.message = "道路上爆发遭遇战。"

    def resolve_arrival(self, troop: Troop) -> None:
        target = self.nodes[troop.target]
        source = self.nodes[troop.source]
        if troop.intent == INTENT_MIGRATE:
            self.resolve_migration(troop, target)
            return
        if target.owner == troop.owner:
            target.soldiers += troop.amount
            target.soldiers = min(target.soldiers, self.garrison_limit(target) * MAX_GARRISON_MULTIPLIER)
            if target.max_population > 0:
                target.morale = clamp(target.morale - 1.5, 0, 100)
            if troop.owner == PLAYER:
                self.message = f"援军抵达 {site_label(target)}。"
            return
        if troop.intent == INTENT_OCCUPY and target.soldiers > 0:
            if troop.owner == PLAYER:
                source.soldiers += troop.amount
                self.message = f"{site_label(target)} 仍有守军，无法直接占领。"
            return

        if target.owner == NEUTRAL:
            defense_power = target.defense * 2
            attack = max(1.0, troop.amount * 1.25 * troop.combat_power_modifier - defense_power)
        else:
            defense_power = target.defense * 4
            attack = max(1.0, troop.amount * troop.combat_power_modifier - defense_power)

        if attack > target.soldiers:
            self.capture_node(target, troop, attack - target.soldiers)
        else:
            target.soldiers -= attack
            self.damage_defense(target, attack)
            if target.max_population > 0:
                target.morale = clamp(target.morale - 4, 0, 100)
            if troop.owner == PLAYER:
                if source.max_population > 0:
                    source.morale = clamp(source.morale - 1.5, 0, 100)
                self.message = f"进攻 {site_label(target)} 失败。"

    def capture_node(self, target: Node, troop: Troop, remaining_attack: float) -> None:
        old_owner = target.owner
        source = self.nodes[troop.source]
        was_capital = target.id == self.capital_node_ids.get(old_owner, -1)
        emperor_old = self.emperors.get(old_owner)
        if emperor_old is not None and emperor_old.alive and emperor_old.current_node == target.id:
            self.kill_emperor(old_owner, "皇帝随城破阵亡")
        loot = 0.0
        if troop.owner == PLAYER and old_owner != PLAYER and troop.intent in (INTENT_ATTACK, INTENT_SACK):
            loot = target.gold

        target.owner = troop.owner
        target.soldiers = max(1.0, remaining_attack)
        target.soldiers = min(target.soldiers, self.garrison_limit(target) * MAX_GARRISON_MULTIPLIER)

        if was_capital and old_owner in (PLAYER, ENEMY):
            self.on_capital_lost(old_owner, troop.owner)

        if troop.intent == INTENT_SACK:
            self.apply_sack(target)
            suffix = f"，焚毁并掠夺 {int(loot)} 金" if loot else ""
            self.message = f"屠城 {site_label(target)}{suffix}。"
        else:
            if target.max_population > 0:
                target.morale = clamp(target.morale - (4 if troop.intent == INTENT_OCCUPY else 8), 0, 100)
            else:
                target.morale = 0
            if troop.owner == PLAYER:
                if source.max_population > 0:
                    source.morale = clamp(source.morale - 1.5, 0, 100)
                suffix = f"，接管本地 {int(loot)} 金" if loot else ""
                self.message = f"占领 {site_label(target)}{suffix}。"

    def damage_defense(self, target: Node, attack: float) -> None:
        if target.max_defense <= 0 or target.defense <= 0:
            return
        floor = math.ceil(target.max_defense * 0.5)
        if target.defense <= floor:
            return
        if attack >= max(4, target.defense * 2):
            target.defense = max(floor, target.defense - 1)

    def apply_sack(self, target: Node) -> None:
        target.population = 0
        target.local_gold = 0
        target.gold = 0
        target.food = 0
        target.recruit_policy = POLICY_STOP
        target.sacked = True
        target.morale = 0
        for node in self.nodes:
            if node.owner == PLAYER:
                node.morale = clamp(node.morale - 3, 0, 100)
        for neighbor_id in self.neighbor_ids(target.id):
            self.nodes[neighbor_id].morale = clamp(self.nodes[neighbor_id].morale - 22, 0, 100)

    def resolve_migration(self, troop: Troop, target: Node) -> None:
        if target.owner != troop.owner:
            return
        arrived = troop.migrants * 0.8
        target.population = min(target.max_population, target.population + arrived)
        if target.population > 0:
            target.sacked = False
        target.morale = clamp(target.morale - 4, 0, 100)
        if troop.owner == PLAYER:
            self.message = f"{int(arrived)} 名居民迁入 {site_label(target)}。"

    def update_convoys(self, dt: float) -> None:
        arrived: list[Convoy] = []
        intercepted: list[Convoy] = []
        for convoy in self.convoys:
            edge = self.edge_between(convoy.source, convoy.target)
            if edge is None:
                arrived.append(convoy)
                continue
            terrain = TERRAIN_STATS[convoy.terrain]
            speed = terrain["speed"] * 0.9 * (1 + edge.road_level * 0.28)
            convoy.progress = min(1.0, convoy.progress + speed * dt)
            if self.try_intercept_convoy(convoy):
                intercepted.append(convoy)
                continue
            if convoy.progress >= 1.0:
                arrived.append(convoy)
        for convoy in arrived:
            finished = self.resolve_convoy_arrival(convoy)
            if finished and convoy in self.convoys:
                self.convoys.remove(convoy)
        for convoy in intercepted:
            if convoy in self.convoys:
                self.convoys.remove(convoy)

    def try_intercept_convoy(self, convoy: Convoy) -> bool:
        for troop in self.troops:
            if troop.owner == convoy.owner or troop.depart_delay > 0:
                continue
            same_road = normalize_edge(troop.source, troop.target) == normalize_edge(convoy.source, convoy.target)
            if not same_road:
                continue
            troop_pos = troop.progress if troop.source == convoy.source else 1 - troop.progress
            if abs(troop_pos - convoy.progress) <= 0.08:
                captor_base = self.nodes[troop.source]
                if convoy.cargo == CONVOY_FOOD:
                    captor_base.food = min(captor_base.max_food, captor_base.food + convoy.amount)
                elif convoy.cargo == CONVOY_POP:
                    if convoy.owner == PLAYER:
                        self.message = "迁民队在途中被截获，百姓伤亡惨重。"
                else:
                    captor_base.gold = min(captor_base.max_gold, captor_base.gold + convoy.amount)
                    captor_base.local_gold = captor_base.gold
                if convoy.owner == PLAYER:
                    self.message = "一支运输队在路上被敌军截获。"
                return True
        return False

    def resolve_convoy_arrival(self, convoy: Convoy) -> bool:
        target = self.nodes[convoy.target]
        if target.owner != convoy.owner:
            if convoy.owner == PLAYER:
                self.message = f"运输队抵达时 {site_label(target)} 已失守，物资被截获。"
            if convoy.cargo == CONVOY_FOOD:
                target.food = min(target.max_food, target.food + convoy.amount)
            elif convoy.cargo == CONVOY_POP:
                return True
            else:
                target.gold = min(target.max_gold, target.gold + convoy.amount)
                target.local_gold = target.gold
            return True

        if convoy.route and convoy.route_index + 2 < len(convoy.route):
            next_source = convoy.route[convoy.route_index + 1]
            next_target = convoy.route[convoy.route_index + 2]
            edge = self.edge_between(next_source, next_target)
            if edge is None:
                return True
            convoy.source = next_source
            convoy.target = next_target
            convoy.terrain = edge.terrain
            convoy.route_index += 1
            convoy.progress = 0.0
            return False

        if convoy.cargo == CONVOY_FOOD:
            target.food = min(target.max_food, target.food + convoy.amount)
            cargo_name = "粮草"
        else:
            target.gold = min(target.max_gold, target.gold + convoy.amount)
            target.local_gold = target.gold
            cargo_name = "金钱"
        if convoy.owner == PLAYER:
            self.message = f"{int(convoy.amount)} {cargo_name} 运抵 {site_label(target)}。"
        self.process_pending_action()
        return True

    def find_owned_path(self, start: int, goal: int, owner: str) -> list[int] | None:
        if start == goal:
            return [start]
        queue: deque[int] = deque([start])
        parent: dict[int, int | None] = {start: None}
        while queue:
            current = queue.popleft()
            for nxt in self.neighbor_ids(current):
                if nxt in parent:
                    continue
                if self.nodes[nxt].owner != owner:
                    continue
                parent[nxt] = current
                if nxt == goal:
                    path = [goal]
                    while parent[path[-1]] is not None:
                        path.append(parent[path[-1]])  # type: ignore[arg-type]
                    path.reverse()
                    return path
                queue.append(nxt)
        return None

    def expand_route_markers(self, markers: list[int], owner: str) -> list[int] | None:
        if len(markers) < 2:
            return None
        expanded = [markers[0]]
        for i in range(len(markers) - 1):
            path = self.find_owned_path(markers[i], markers[i + 1], owner)
            if path is None or len(path) < 2:
                return None
            expanded.extend(path[1:])
        return expanded

    def create_convoy(
        self,
        owner: str,
        source_id: int,
        target_id: int,
        cargo: str,
        amount: float,
        allow_multihop: bool,
        explicit_route: list[int] | None = None,
    ) -> bool:
        if amount <= 0 or source_id == target_id:
            return False
        route: tuple[int, ...] = ()
        edge = None
        if explicit_route is not None:
            if len(explicit_route) < 2 or explicit_route[0] != source_id or explicit_route[-1] != target_id:
                return False
            route = tuple(explicit_route)
            source_id = explicit_route[0]
            target_id = explicit_route[1]
            edge = self.edge_between(source_id, target_id)
            if edge is None:
                return False
        if edge is None:
            edge = self.edge_between(source_id, target_id)
        if edge is None:
            if not allow_multihop:
                return False
            path = self.find_owned_path(source_id, target_id, owner)
            if path is None or len(path) < 2:
                return False
            route = tuple(path)
            source_id, target_id = path[0], path[1]
            edge = self.edge_between(source_id, target_id)
            if edge is None:
                return False
        self.convoys.append(
            Convoy(
                owner=owner,
                source=source_id,
                target=target_id,
                cargo=cargo,
                amount=amount,
                terrain=edge.terrain,
                route=route,
                route_index=0,
            )
        )
        return True

    def launch_convoy(self, target: Node) -> bool:
        if self.selected is None or self.convoy_mode is None:
            return False
        source = self.nodes[self.selected]
        if source.owner != PLAYER or target.owner != PLAYER:
            self.message = "运输只能在己方据点之间进行。"
            return False

        if not self.convoy_route or self.convoy_route[0] != source.id:
            self.convoy_route = [source.id]

        if target.id != self.convoy_route[-1]:
            if target.id in self.convoy_route:
                self.message = "运输路线不能重复绕行。"
                return False
            if self.find_owned_path(self.convoy_route[-1], target.id, PLAYER) is None:
                self.message = "当前路线无法连通该节点。"
                return False
            self.convoy_route.append(target.id)
            route_text = " -> ".join(str(node_id) for node_id in self.convoy_route)
            self.message = f"运输路线：{route_text}（再点一次终点发车）"
            return False

        if len(self.convoy_route) < 2:
            self.message = "请先选择运输终点。"
            return False

        full_route = self.expand_route_markers(self.convoy_route, PLAYER)
        if full_route is None or len(full_route) < 2:
            self.message = "运输路线无效，请重选。"
            self.convoy_route = [source.id]
            return False
        destination = self.nodes[full_route[-1]]

        if self.convoy_mode == CONVOY_FOOD:
            amount = min(source.food * CONVOY_BATCH_RATIO, max(0.0, destination.max_food - destination.food))
            if amount < MIN_FOOD_CONVOY_AMOUNT:
                self.message = "粮草不足或目标粮仓已满。"
                return False
            source.food -= amount
            cargo_name = "粮草"
        else:
            amount = min(source.gold * CONVOY_BATCH_RATIO, max(0.0, destination.max_gold - destination.gold))
            if amount < 10:
                self.message = "金钱不足或目标库房已满。"
                return False
            source.gold -= amount
            source.local_gold = source.gold
            cargo_name = "金钱"

        if not self.create_convoy(
            PLAYER,
            source.id,
            destination.id,
            self.convoy_mode,
            amount,
            allow_multihop=True,
            explicit_route=full_route,
        ):
            self.message = "运输发车失败，请重选路线。"
            self.convoy_route = [source.id]
            return False
        self.message = f"向 {site_label(destination)} 运输 {int(amount)} {cargo_name}。"
        self.convoy_route = [source.id]
        return True

    def incoming_gold(self, node_id: int) -> float:
        return sum(c.amount for c in self.convoys if c.owner == PLAYER and c.cargo == CONVOY_GOLD and c.target == node_id)

    def incoming_food(self, node_id: int) -> float:
        return sum(c.amount for c in self.convoys if c.owner == PLAYER and c.cargo == CONVOY_FOOD and c.target == node_id)

    def request_auto_gold(self, node_id: int, required: float) -> float:
        if required <= 0:
            return 0.0
        target = self.nodes[node_id]
        if target.owner != PLAYER:
            return 0.0
        capacity = max(0.0, target.max_gold - target.gold - self.incoming_gold(node_id))
        need = min(required, capacity)
        if need <= 0:
            return 0.0
        sent = 0.0
        used_sources: set[int] = set()
        if self.auto_fund_neighbors:
            neighbors = [self.nodes[nid] for nid in self.neighbor_ids(node_id) if self.nodes[nid].owner == PLAYER and nid != node_id]
            neighbors.sort(key=lambda n: n.gold, reverse=True)
            for source in neighbors:
                if need <= 0:
                    break
                amount = min(source.gold * CONVOY_BATCH_RATIO, need)
                if amount < 10:
                    continue
                if self.create_convoy(PLAYER, source.id, node_id, CONVOY_GOLD, amount, allow_multihop=False):
                    source.gold -= amount
                    source.local_gold = source.gold
                    need -= amount
                    sent += amount
                    used_sources.add(source.id)
        if self.auto_fund_capital and need > 0:
            capital = self.player_capital()
            if capital is not None and capital.id not in used_sources and capital.id != node_id:
                amount = min(capital.gold * CONVOY_BATCH_RATIO, need)
                if amount >= 10 and self.create_convoy(PLAYER, capital.id, node_id, CONVOY_GOLD, amount, allow_multihop=True):
                    capital.gold -= amount
                    capital.local_gold = capital.gold
                    self.treasury = capital.gold
                    need -= amount
                    sent += amount
        return sent

    def request_auto_food(self, node_id: int, required: float) -> float:
        if required <= 0:
            return 0.0
        target = self.nodes[node_id]
        if target.owner != PLAYER:
            return 0.0
        capacity = max(0.0, target.max_food - target.food - self.incoming_food(node_id))
        need = min(required, capacity)
        if need <= 0:
            return 0.0
        sent = 0.0
        used_sources: set[int] = set()
        if self.auto_supply_neighbors:
            neighbors = [self.nodes[nid] for nid in self.neighbor_ids(node_id) if self.nodes[nid].owner == PLAYER and nid != node_id]
            neighbors.sort(key=lambda n: n.food, reverse=True)
            for source in neighbors:
                if need <= 0:
                    break
                amount = min(source.food * CONVOY_BATCH_RATIO, need)
                if amount < 1:
                    continue
                if self.create_convoy(PLAYER, source.id, node_id, CONVOY_FOOD, amount, allow_multihop=False):
                    source.food -= amount
                    need -= amount
                    sent += amount
                    used_sources.add(source.id)
        if self.auto_supply_capital and need > 0:
            capital = self.player_capital()
            if capital is not None and capital.id not in used_sources and capital.id != node_id:
                amount = min(capital.food * CONVOY_BATCH_RATIO, need)
                if amount >= 1 and self.create_convoy(PLAYER, capital.id, node_id, CONVOY_FOOD, amount, allow_multihop=True):
                    capital.food -= amount
                    need -= amount
                    sent += amount
        return sent

    def migration_loss_ratio(self, hop_count: int) -> float:
        return clamp(MIGRATION_BASE_LOSS + max(0, hop_count - 1) * MIGRATION_LOSS_PER_HOP, 0.05, 0.75)

    def launch_population_convoy(self, source_id: int, target_id: int, amount: float) -> bool:
        source = self.nodes[source_id]
        target = self.nodes[target_id]
        if source.owner != PLAYER or target.owner != PLAYER:
            return False
        if source.max_population <= 0 or target.max_population <= 0:
            return False
        path = self.find_owned_path(source_id, target_id, PLAYER)
        if path is None or len(path) < 2:
            return False
        reserve = source.max_population * 0.2
        movable = max(0.0, source.population - reserve)
        if movable <= 0:
            return False
        room = max(0.0, target.max_population - target.population - self.incoming_population(target_id))
        if room <= 0:
            return False
        hop_count = len(path) - 1
        loss_ratio = self.migration_loss_ratio(hop_count)
        dispatch = min(amount, movable, room / max(0.01, 1.0 - loss_ratio))
        if dispatch < MIN_POP_CONVOY_AMOUNT:
            return False
        source.population -= dispatch
        source.morale = clamp(source.morale - 2.0, 0, self.node_morale_cap(source))
        morale_payload = source.morale
        if not self.create_convoy(
            PLAYER,
            source_id,
            target_id,
            CONVOY_POP,
            dispatch,
            allow_multihop=True,
            explicit_route=path,
        ):
            source.population += dispatch
            return False
        if self.convoys:
            self.convoys[-1].morale_payload = morale_payload
        return True

    def incoming_population(self, node_id: int) -> float:
        incoming = 0.0
        for convoy in self.convoys:
            if convoy.owner != PLAYER or convoy.cargo != CONVOY_POP or convoy.target != node_id:
                continue
            if len(convoy.route) >= 2:
                hop_count = len(convoy.route) - 1
            else:
                hop_count = 1
            incoming += convoy.amount * (1.0 - self.migration_loss_ratio(hop_count))
        return incoming

    def auto_migrate_from_node(self, source: Node, near_only: bool, threshold_ratio: float) -> float:
        if source.owner != PLAYER or source.max_population <= 0:
            return 0.0
        reserve = source.max_population * 0.2
        available = max(0.0, source.population - reserve)
        if available <= MIN_POP_CONVOY_AMOUNT:
            return 0.0
        destinations: list[tuple[int, int, Node]] = []
        for node in self.nodes:
            if node.owner != PLAYER or node.id == source.id or node.max_population <= 0:
                continue
            if node.population >= node.max_population * threshold_ratio:
                continue
            path = self.find_owned_path(source.id, node.id, PLAYER)
            if path is None or len(path) < 2:
                continue
            hops = len(path) - 1
            if near_only and hops > 3:
                continue
            destinations.append((hops, -int(node.max_population - node.population), node))
        if not destinations:
            return 0.0
        destinations.sort(key=lambda item: (item[0], item[1]))
        moved = 0.0
        budget = min(AUTO_MIGRATE_BATCH, available)
        for _, __, dst in destinations:
            if budget <= MIN_POP_CONVOY_AMOUNT:
                break
            if self.launch_population_convoy(source.id, dst.id, budget):
                moved += budget
                break
        return moved

    def migrate_into_selected(self) -> None:
        if self.selected is None:
            return
        target = self.nodes[self.selected]
        if target.owner != PLAYER:
            return
        if target.max_population <= 0:
            self.message = "此据点不能接纳居民。"
            return
        donors: list[tuple[int, float, Node]] = []
        for node in self.nodes:
            if node.owner != PLAYER or node.id == target.id or node.max_population <= 0:
                continue
            path = self.find_owned_path(node.id, target.id, PLAYER)
            if path is None or len(path) < 2:
                continue
            reserve = node.max_population * 0.2
            available = max(0.0, node.population - reserve)
            if available <= MIN_POP_CONVOY_AMOUNT:
                continue
            donors.append((len(path) - 1, -int(node.population), node))
        if not donors:
            self.message = "附近暂无可迁入居民来源。"
            return
        donors.sort(key=lambda item: (item[0], item[1]))
        amount_left = AUTO_MIGRATE_BATCH
        launched = 0
        for _, __, donor in donors:
            if amount_left <= MIN_POP_CONVOY_AMOUNT:
                break
            before = amount_left
            if self.launch_population_convoy(donor.id, target.id, amount_left):
                launched += 1
                amount_left = 0.0
                break
            if amount_left == before:
                continue
        if launched > 0:
            self.message = f"{site_label(target)} 已发起迁入运输。"
        else:
            self.message = "迁入失败：可能目标容量不足或路径不通。"

    def queue_pending_action(
        self,
        action: str,
        node_id: int,
        cost: float,
        line: str | None = None,
        road_target_id: int | None = None,
        source_id: int | None = None,
        target_id: int | None = None,
        owner: str | None = None,
        ratio: float | None = None,
        intent: str | None = None,
        needed_food: float = 0.0,
    ) -> bool:
        node = self.nodes[node_id]
        if action == "launch_troop":
            sent = self.request_auto_food(node_id, max(0.0, needed_food - node.food))
            if sent <= 0:
                return False
            self.message = f"{site_label(node)} 粮草不足，已自动调粮 {int(sent)}，到粮后自动出兵。"
        else:
            sent = self.request_auto_gold(node_id, max(0.0, cost - node.gold))
            if sent <= 0:
                return False
            self.message = f"{site_label(node)} 金钱不足，已自动调款 {int(sent)}，到款后自动执行。"

        self.pending_action = {
            "action": action,
            "node_id": node_id,
            "cost": cost,
            "line": line or "",
            "road_target_id": road_target_id if road_target_id is not None else -1,
            "source_id": source_id if source_id is not None else -1,
            "target_id": target_id if target_id is not None else -1,
            "owner": owner or "",
            "ratio": ratio if ratio is not None else -1.0,
            "intent": intent or "",
            "needed_food": needed_food,
        }
        return True

    def process_pending_action(self) -> None:
        if self.pending_action is None:
            return
        action = str(self.pending_action.get("action", ""))
        node_id = int(self.pending_action.get("node_id", -1))
        if node_id < 0 or node_id >= len(self.nodes):
            self.pending_action = None
            return
        node = self.nodes[node_id]
        if node.owner != PLAYER:
            self.pending_action = None
            return

        if action == "launch_troop":
            source_id = int(self.pending_action.get("source_id", -1))
            target_id = int(self.pending_action.get("target_id", -1))
            owner = str(self.pending_action.get("owner", PLAYER))
            ratio = float(self.pending_action.get("ratio", self.send_ratio))
            intent = str(self.pending_action.get("intent", INTENT_ATTACK))
            needed_food = float(self.pending_action.get("needed_food", 0.0))
            if source_id < 0 or target_id < 0 or source_id >= len(self.nodes) or target_id >= len(self.nodes):
                self.pending_action = None
                return
            if self.nodes[source_id].food < needed_food:
                return
            edge = self.edge_between(source_id, target_id)
            if edge is None:
                self.pending_action = None
                return
            self.pending_action = None
            self.launch_troop(source_id, target_id, owner, ratio=ratio, edge=edge, intent=intent, from_pending=True)
            return

        cost = float(self.pending_action.get("cost", 0.0))
        if node.gold < cost:
            return
        line = str(self.pending_action.get("line", ""))
        road_target_id = int(self.pending_action.get("road_target_id", -1))
        self.pending_action = None

        old_selected = self.selected
        self.selected = node_id
        if action == "fortify":
            self.fortify_selected(from_pending=True)
        elif action == "repair_wall":
            self.repair_wall_selected(from_pending=True)
        elif action == "repair_ruin":
            self.repair_ruin_selected()
        elif action == "upgrade":
            self.upgrade_selected(line, from_pending=True)
        elif action == "repair_road" and 0 <= road_target_id < len(self.nodes):
            self.try_repair_road(self.nodes[road_target_id], from_pending=True)
        self.selected = old_selected

    def destroy_selected_stock(self) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            self.message = "只能销毁己方据点库存。"
            return
        node.food = 0
        node.gold = 0
        node.local_gold = 0
        self.message = f"{site_label(node)} 已销毁粮草和金钱库存。"

    def demobilize_selected(self) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            self.message = "只能在我方据点执行转民。"
            return
        if node.max_population <= 0:
            self.message = "该据点无居民体系，无法转民。"
            return
        if node.soldiers < 8:
            self.message = "兵力过低，无法转民。"
            return
        room = max(0.0, node.max_population - node.population)
        if room < 1:
            self.message = "居民容量已满，无法继续转民。"
            return
        demobilized = min(node.soldiers * DEMOBILIZE_RATIO, room / POP_PER_SOLDIER)
        if demobilized < 1:
            self.message = "可转民数量不足。"
            return
        node.soldiers -= demobilized
        node.population += demobilized * POP_PER_SOLDIER
        node.sacked = False
        node.morale = clamp(node.morale + DEMOBILIZE_MORALE_BONUS, 0, 100)
        self.message = f"{site_label(node)} 转民 {int(demobilized)}，民心回升。"

    def low_food_node(self, node: Node) -> bool:
        return node.food < max(18.0, node.soldiers * 0.35)

    def trigger_rebellion(self, node: Node, reason: str) -> None:
        if node.owner != PLAYER or node.site_type in (CAPITAL, FORT) or node.max_population <= 0:
            return
        node.owner = REBEL
        node.recruit_policy = POLICY_STOP
        militia = max(8.0, min(node.population / POP_PER_SOLDIER * 0.04, 60.0))
        node.soldiers = max(militia, node.soldiers * 0.6)
        node.soldiers = min(node.soldiers, self.garrison_limit(node) * MAX_GARRISON_MULTIPLIER)
        node.morale = 42.0
        self.message = f"{site_label(node)} 爆发起义（{reason}）。"

    def try_empty_garrison_uprising(self, node: Node) -> None:
        if node.owner != PLAYER or node.site_type in (CAPITAL, FORT) or node.max_population <= 0:
            return
        if node.soldiers >= 10 or node.morale >= 30:
            return
        chance = clamp(0.68 + (30 - node.morale) * 0.015 + (10 - node.soldiers) * 0.02, 0.68, 0.96)
        if self.rng.random() >= chance:
            return
        self.trigger_rebellion(node, "空城失控")
        for nid in self.neighbor_ids(node.id):
            neighbor = self.nodes[nid]
            if neighbor.owner != PLAYER or neighbor.site_type in (CAPITAL, FORT) or neighbor.max_population <= 0:
                continue
            if not (self.low_food_node(neighbor) or neighbor.morale < 60):
                continue
            chain_chance = 0.55
            if self.low_food_node(neighbor):
                chain_chance += 0.20
            if neighbor.morale < 60:
                chain_chance += (60 - neighbor.morale) * 0.005
            if self.rng.random() < min(0.9, chain_chance):
                self.trigger_rebellion(neighbor, "周边连锁")

    def enemy_turn(self) -> None:
        self.ai_take_turn(ENEMY)
        return

        for source in enemy_nodes:
            # 后勤动作：缺粮时优先运输
            if source.food < max(30.0, source.soldiers * 0.18):
                for nid in self.neighbor_ids(source.id):
                    n = self.nodes[nid]
                    if n.owner == ENEMY and n.food > 60:
                        score = 20 + n.food * 0.08 - source.food * 0.05
                        candidates.append((score, "supply", n.id, source.id, 0.0, INTENT_ATTACK))

            # 回防动作
            for nid in self.neighbor_ids(source.id):
                target = self.nodes[nid]
                if target.owner == ENEMY and source.soldiers >= 20 and target.soldiers < 12:
                    threatened = any(self.nodes[k].owner == PLAYER for k in self.neighbor_ids(target.id))
                    if threatened:
                        score = 14 + (12 - target.soldiers) * 1.5 + source.soldiers * 0.1
                        candidates.append((score, "reinforce", source.id, target.id, 0.35, INTENT_ATTACK))

            # 进攻动作
            if source.soldiers < 16:
                continue
            for nid in self.neighbor_ids(source.id):
                target = self.nodes[nid]
                if target.owner == ENEMY:
                    continue
                edge = self.edge_between(source.id, target.id)
                if edge is None:
                    continue
                intent = INTENT_OCCUPY if target.soldiers <= 0 else INTENT_ATTACK
                score = self.enemy_target_score(source, target, edge)
                ratio = 0.52 if target.owner == NEUTRAL else 0.58
                candidates.append((score, "attack", source.id, target.id, ratio, intent))

        if not candidates:
            return
        candidates.sort(key=lambda x: x[0], reverse=True)
        score, action, source_id, target_id, ratio, intent = candidates[0]
        if score < 0:
            return

        if action == "supply":
            src = self.nodes[source_id]
            dst = self.nodes[target_id]
            amount = min(src.food * 0.45, max(0.0, dst.max_food - dst.food))
            if amount >= 20 and self.create_convoy(ENEMY, src.id, dst.id, CONVOY_FOOD, amount, allow_multihop=True):
                src.food -= amount
            return
        if action == "reinforce":
            edge = self.edge_between(source_id, target_id)
            if edge is not None:
                self.launch_troop(source_id, target_id, ENEMY, ratio=ratio, edge=edge, intent=INTENT_ATTACK)
            return
        if action == "attack":
            edge = self.edge_between(source_id, target_id)
            if edge is not None:
                self.launch_troop(source_id, target_id, ENEMY, ratio=ratio, edge=edge, intent=intent)

    def enemy_target_score(self, source: Node, target: Node, edge: Edge) -> float:
        terrain = TERRAIN_STATS[edge.terrain]
        travel_cost = terrain["loss"] * 100 + (0.12 - terrain["speed"]) * 180
        defense_cost = target.soldiers + target.defense * (6 if target.owner == NEUTRAL else 8)
        source_food_penalty = 0.0 if source.food > 40 else (40 - source.food) * 1.4
        neutral_bonus = 28 if target.owner == NEUTRAL else 0
        player_bonus = 12 if target.owner == PLAYER else 0
        village_bonus = 14 if target.site_type == VILLAGE else 0
        town_bonus = 7 if target.site_type == TOWN else 0
        fort_penalty = 16 if target.site_type in (FORT, CAPITAL) else 0
        frontline_bonus = 8 if any(self.nodes[n].owner == PLAYER for n in self.neighbor_ids(target.id)) else 0
        return (
            neutral_bonus
            + player_bonus
            + village_bonus
            + town_bonus
            + frontline_bonus
            - defense_cost
            - travel_cost
            - fort_penalty
            - source_food_penalty
            + source.soldiers * 0.35
        )

    def ai_take_turn(self, owner: str) -> None:
        self.ai_engine.take_turn(self, owner, self.rng)

    def rebel_turn(self) -> None:
        self.ai_take_turn(REBEL)
        self.ai_take_turn(REBEL)

    def check_rebel_enemy_alliance(self) -> None:
        has_rebel = any(n.owner == REBEL for n in self.nodes) or any(t.owner == REBEL for t in self.troops)
        if not has_rebel:
            return
        linked = False
        for edge in self.edges:
            a = self.nodes[edge.a]
            b = self.nodes[edge.b]
            if {a.owner, b.owner} == {ENEMY, REBEL}:
                linked = True
                break
        if not linked:
            for troop in self.troops:
                if troop.owner == ENEMY and self.nodes[troop.target].owner == REBEL:
                    linked = True
                    break
                if troop.owner == REBEL and self.nodes[troop.target].owner == ENEMY:
                    linked = True
                    break
        if not linked:
            return
        for node in self.nodes:
            if node.owner == REBEL:
                node.owner = ENEMY
        for troop in self.troops:
            if troop.owner == REBEL:
                troop.owner = ENEMY
        for convoy in self.convoys:
            if convoy.owner == REBEL:
                convoy.owner = ENEMY
        self.message = "起义军与敌军汇合结盟，已并入敌方。"

    def launch_troop(
        self,
        source_id: int,
        target_id: int,
        owner: str,
        ratio: float | None = None,
        edge: Edge | None = None,
        intent: str = INTENT_ATTACK,
        from_pending: bool = False,
    ) -> bool:
        source = self.nodes[source_id]
        source_cap = self.garrison_limit(source) * MAX_GARRISON_MULTIPLIER
        if source.soldiers > source_cap:
            source.soldiers = source_cap
        if source.owner != owner or source.soldiers < 8:
            if owner == PLAYER:
                self.message = "至少需要 8 名士兵才能出征。"
            return False
        road = edge or self.edge_between(source_id, target_id)
        if road is None:
            return False
        target = self.nodes[target_id]
        if intent == INTENT_OCCUPY and target.soldiers > 0:
            if owner == PLAYER:
                self.message = "占领只适用于无守军据点。"
            return False
        if intent == INTENT_MIGRATE:
            return self.launch_migration(source_id, target_id)

        send_ratio = ratio if ratio is not None else self.send_ratio
        amount = max(1, math.floor(source.soldiers * send_ratio))
        if amount < 4:
            return False
        food_need = amount * FOOD_PER_TROOP_LAUNCH
        if source.food < food_need:
            if owner == PLAYER and not from_pending:
                # 防重复排队：同一source的待执行发兵只保留一条
                if self.pending_action and str(self.pending_action.get("action", "")) == "launch_troop":
                    pending_source = int(self.pending_action.get("source_id", -1))
                    if pending_source == source_id:
                        self.request_auto_food(source_id, max(0.0, food_need - source.food))
                        self.message = f"{site_label(source)} 仍在等待粮草，已继续尝试调粮。"
                        return False
                if self.queue_pending_action(
                    "launch_troop",
                    source_id,
                    0.0,
                    source_id=source_id,
                    target_id=target_id,
                    owner=owner,
                    ratio=send_ratio,
                    intent=intent,
                    needed_food=food_need,
                ):
                    return False
                self.message = f"粮草不足，需要 {int(food_need)} 粮。"
            return False

        source.soldiers -= amount
        if source.soldiers < 0:
            source.soldiers = 0.0
        source.food -= food_need
        if owner == PLAYER:
            if source.max_population > 0:
                source.morale = clamp(source.morale - (3 if target.owner != PLAYER else 1), 0, 100)
            if from_pending:
                self.pending_action = None
            if send_ratio >= 0.999:
                self.try_empty_garrison_uprising(source)

        batch_count = max(1, min(8, math.ceil(amount / TROOP_BATCH_SIZE)))
        remaining = float(amount)
        for batch_id in range(batch_count):
            left = batch_count - batch_id
            batch_amount = max(1.0, remaining / left)
            remaining -= batch_amount
            self.troops.append(
                Troop(
                    owner=owner,
                    source=source_id,
                    target=target_id,
                    start_amount=float(batch_amount),
                    amount=float(batch_amount),
                    terrain=road.terrain,
                    intent=intent,
                    batch_id=batch_id,
                    supply_source=source_id,
                    depart_delay=batch_id * max(0.12, TROOP_BATCH_INTERVAL - amount / 300),
                )
            )
        if owner == PLAYER:
            if target.owner == PLAYER:
                self.message = f"分 {batch_count} 队调动 {amount} 人前往 {site_label(target)}。"
            else:
                self.message = f"{INTENT_LABELS[intent]}：分 {batch_count} 队派出 {amount} 人。"
        return True

    def launch_migration(self, source_id: int, target_id: int) -> bool:
        source = self.nodes[source_id]
        target = self.nodes[target_id]
        edge = self.edge_between(source_id, target_id)
        if edge is None:
            self.message = "迁徙目标必须相邻。"
            return False
        if source.owner != PLAYER or target.owner != PLAYER:
            self.message = "迁徙只能在己方据点之间进行。"
            return False
        if source.population < 30:
            self.message = "居民太少，无法迁徙。"
            return False
        if target.max_population <= 0:
            self.message = "关隘不能接纳居民。"
            return False
        migrants = min(source.population * self.send_ratio, max(0.0, target.max_population - target.population) / 0.8)
        if migrants < 20:
            self.message = "目标容量不足或迁徙人数太少。"
            return False
        source.population -= migrants
        source.morale = clamp(source.morale - 3, 0, 100)
        self.troops.append(
            Troop(
                owner=PLAYER,
                source=source_id,
                target=target_id,
                start_amount=1,
                amount=1,
                terrain=edge.terrain,
                intent=INTENT_MIGRATE,
                migrants=migrants,
            )
        )
        self.message = f"迁徙 {int(migrants)} 名居民，预计损失 20%。"
        return True

    def fortify_selected(self, from_pending: bool = False) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            return
        if node.gold < FORTIFY_COST:
            if not from_pending and self.queue_pending_action("fortify", node.id, FORTIFY_COST):
                return
            self.message = "本地金钱不足，无法加固。"
            return
        cap = self.defense_cap(node)
        if node.max_defense >= cap:
            if node.defense < node.max_defense:
                if node.gold >= REPAIR_COST:
                    node.gold -= REPAIR_COST
                    node.local_gold = node.gold
                    node.defense = min(node.max_defense, node.defense + 1)
                    self.message = f"{site_label(node)} 已达城防上限，已执行维修。"
                else:
                    self.message = "城防已达上限，且本地金钱不足以维修。"
                return
            self.message = f"{site_label(node)} 城防已达上限 {cap}。"
            return
        node.gold -= FORTIFY_COST
        node.local_gold = node.gold
        node.max_defense = min(cap, node.max_defense + 1)
        node.defense = min(node.max_defense, node.defense + 1)
        if node.max_population > 0:
            node.morale = clamp(node.morale + 2, 0, 100)
        self.message = f"{site_label(node)} 最大城防提升至 {node.max_defense}。"

    def repair_wall_selected(self, from_pending: bool = False) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            return
        if node.defense >= node.max_defense:
            self.message = "城防无需维修。"
            return
        if node.gold < REPAIR_COST:
            if not from_pending and self.queue_pending_action("repair_wall", node.id, REPAIR_COST):
                return
            self.message = "本地金钱不足，无法维修。"
            return
        node.gold -= REPAIR_COST
        node.local_gold = node.gold
        node.defense = min(node.max_defense, node.defense + 1)
        self.message = f"{site_label(node)} 城防恢复至 {node.defense}/{node.max_defense}。"

    def upgrade_selected(self, line: str, from_pending: bool = False) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            return
        if node.development_line != line and node.development_level > 0:
            self.message = "已选择发展线，不能中途转向。"
            return
        if node.development_level >= MAX_DEVELOPMENT_LEVEL:
            self.message = "此据点已经发展到顶级。"
            return
        cost = UPGRADE_COST * (node.development_level + 1)
        if node.gold < cost:
            if not from_pending and self.queue_pending_action("upgrade", node.id, cost, line=line):
                return
            self.message = f"本地金钱不足，升级需要 {cost} 金。"
            return
        node.gold -= cost
        node.local_gold = node.gold
        node.development_line = line
        node.development_level += 1
        self.apply_development(node)
        self.message = f"{site_label(node)} 升级为 {development_name(node)}。"

    def apply_development(self, node: Node) -> None:
        data = development_data(node)
        node.max_population = max(node.max_population, SITE_STATS[node.site_type]["population"][1] * data["pop"])
        node.max_food = max(node.max_food, SITE_STATS[node.site_type]["food"][1] * data["food"])
        node.max_gold = max(node.max_gold, SITE_STATS[node.site_type]["gold"][1] * data["gold"])
        if node.site_type == CAPITAL:
            node.max_gold = CAPITAL_GOLD_CAP
            node.gold = min(node.gold, node.max_gold)
            node.local_gold = node.gold
            self.treasury = node.gold
        node.max_defense = max(node.max_defense, int(data["defense"]))
        node.max_defense = min(node.max_defense, self.defense_cap(node))
        node.defense = max(node.defense, math.ceil(node.max_defense * 0.75))

    def try_repair_road(self, target: Node, from_pending: bool = False) -> None:
        if self.selected is None:
            return
        source = self.nodes[self.selected]
        edge = self.edge_between(source.id, target.id)
        if edge is None:
            self.message = "只能修相邻道路。"
            return
        if source.gold < ROAD_COST:
            if not from_pending and self.queue_pending_action("repair_road", source.id, ROAD_COST, road_target_id=target.id):
                self.repair_mode = False
                return
            self.message = "本地金钱不足，无法修路。"
            return
        if edge.road_level >= MAX_ROAD_LEVEL:
            self.message = "这条道路已经修到最高等级。"
            return
        source.gold -= ROAD_COST
        source.local_gold = source.gold
        edge.road_level += 1
        self.repair_mode = False
        self.message = f"{site_label(source)} 至 {site_label(target)} 道路升至 {edge.road_level} 级。"

    # --- Yellow Turban / warning / logistics overrides ---
    def apply_garrison_food_and_stability(self, node: Node, dt: float) -> None:
        if node.owner == REBEL:
            node.supply_blocked_time = max(0.0, node.supply_blocked_time - dt)
            return

        if node.owner == PLAYER and node.site_type == FORT:
            node.food = min(node.food, node.max_food)

        resident_need = self.node_resident_food_consumption_rate(node) * dt
        if resident_need > 0:
            if node.food >= resident_need:
                node.food -= resident_need
            else:
                node.food = 0.0

        if node.owner == PLAYER and self.auto_supply_low_enabled:
            should_auto = False
            need_amount = 0.0
            if self.auto_supply_low_enabled_90 and node.food < LOW_FOOD_AUTO_SUPPLY_THRESHOLD:
                should_auto = True
                need_amount = max(need_amount, LOW_FOOD_AUTO_SUPPLY_THRESHOLD - node.food)
            if self.auto_supply_low_enabled_200 and node.food < LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH:
                should_auto = True
                need_amount = max(need_amount, LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH - node.food)
            if (
                self.auto_supply_low_enabled_military_half
                and node.development_line == LINE_MILITARY
                and node.development_level > 0
                and node.max_food > 0
                and node.food < node.max_food * 0.5
            ):
                should_auto = True
                need_amount = max(need_amount, node.max_food * 0.5 - node.food)
            if should_auto and need_amount > 0:
                cooldown = self.auto_supply_low_cooldowns.get(node.id, 0.0) - dt
                self.auto_supply_low_cooldowns[node.id] = cooldown
                if cooldown <= 0:
                    sent = self.request_auto_food(node.id, need_amount)
                    if sent > 0:
                        self.auto_supply_low_cooldowns[node.id] = 4.0

        upkeep_factor = development_bonus(node)["upkeep"]
        if node.development_line == LINE_MILITARY and node.development_level > 0:
            upkeep_factor *= 10.0
        defense_weight = 1.0 + max(0.0, node.max_defense) * 0.12
        upkeep_factor *= defense_weight
        cap = self.garrison_limit(node)
        normal_soldiers = min(node.soldiers, cap)
        overflow = max(0.0, node.soldiers - cap)
        weighted_soldiers = normal_soldiers + overflow * 10.0
        need = max(0.0, weighted_soldiers * GARRISON_FOOD_PER_SOLDIER_SECOND * upkeep_factor * dt)
        if need <= 0:
            node.supply_blocked_time = max(0.0, node.supply_blocked_time - dt * 0.5)
            return
        if node.food >= need:
            node.food -= need
            node.supply_blocked_time = max(0.0, node.supply_blocked_time - dt * 0.6)
            return

        node.food = 0.0
        node.supply_blocked_time += dt
        node.defense = 0
        if node.owner in (PLAYER, ENEMY):
            self.mark_rebel_warning(node, "断粮失序")

    def consume_troop_supply(self, troop: Troop, dt: float) -> bool:
        if troop.owner == REBEL:
            return True
        if troop.supply_source is None:
            troop.supply_source = troop.source
        if troop.supply_source >= len(self.nodes):
            return False
        source = self.nodes[troop.supply_source]
        road_base = self.nodes[troop.source]
        if source.owner != troop.owner or road_base.owner != troop.owner:
            return False
        if not self.connected_by_owner(source.id, road_base.id, troop.owner):
            return False
        need = max(0.04, troop.amount * FOOD_PER_TROOP_SECOND * dt)
        if source.food < need:
            return False
        source.food -= need
        return True

    def request_auto_gold(self, node_id: int, required: float) -> float:
        if required <= 0:
            return 0.0
        target = self.nodes[node_id]
        if target.owner != PLAYER:
            return 0.0
        capacity = max(0.0, target.max_gold - target.gold - self.incoming_gold(node_id))
        need = min(required, capacity)
        if need <= 0:
            return 0.0
        sent = 0.0
        used_sources: set[int] = set()

        if self.auto_fund_neighbors:
            candidates = [n for n in self.nodes if n.owner == PLAYER and n.id != node_id]
            candidates.sort(key=lambda n: n.gold, reverse=True)
            for source in candidates:
                if need <= 0:
                    break
                if source.id in used_sources:
                    continue
                if self.find_owned_path(source.id, node_id, PLAYER) is None:
                    continue
                amount = min(source.gold * CONVOY_BATCH_RATIO, need)
                if amount < 10:
                    continue
                if self.create_convoy(PLAYER, source.id, node_id, CONVOY_GOLD, amount, allow_multihop=True):
                    source.gold -= amount
                    source.local_gold = source.gold
                    need -= amount
                    sent += amount
                    used_sources.add(source.id)

        if self.auto_fund_capital and need > 0:
            capital = self.player_capital()
            if capital is not None and capital.id != node_id and capital.id not in used_sources:
                amount = min(capital.gold * CONVOY_BATCH_RATIO, need)
                if amount >= 10 and self.create_convoy(PLAYER, capital.id, node_id, CONVOY_GOLD, amount, allow_multihop=True):
                    capital.gold -= amount
                    capital.local_gold = capital.gold
                    self.treasury = capital.gold
                    need -= amount
                    sent += amount
        return sent

    def request_auto_food(self, node_id: int, required: float) -> float:
        if required <= 0:
            return 0.0
        target = self.nodes[node_id]
        if target.owner != PLAYER:
            return 0.0
        capacity = max(0.0, target.max_food - target.food - self.incoming_food(node_id))
        need = min(required, capacity)
        if need <= 0:
            return 0.0
        sent = 0.0
        used_sources: set[int] = set()

        if self.auto_supply_neighbors:
            candidates = [n for n in self.nodes if n.owner == PLAYER and n.id != node_id]
            candidates.sort(key=lambda n: n.food, reverse=True)
            for source in candidates:
                if need <= 0:
                    break
                if source.id in used_sources:
                    continue
                if self.find_owned_path(source.id, node_id, PLAYER) is None:
                    continue
                amount = min(source.food * CONVOY_BATCH_RATIO, need)
                if amount < MIN_FOOD_CONVOY_AMOUNT:
                    continue
                if self.create_convoy(PLAYER, source.id, node_id, CONVOY_FOOD, amount, allow_multihop=True):
                    source.food -= amount
                    need -= amount
                    sent += amount
                    used_sources.add(source.id)

        if self.auto_supply_capital and need > 0:
            capital = self.player_capital()
            if capital is not None and capital.id != node_id and capital.id not in used_sources:
                amount = min(capital.food * CONVOY_BATCH_RATIO, need)
                if amount >= MIN_FOOD_CONVOY_AMOUNT and self.create_convoy(
                    PLAYER,
                    capital.id,
                    node_id,
                    CONVOY_FOOD,
                    amount,
                    allow_multihop=True,
                ):
                    capital.food -= amount
                    need -= amount
                    sent += amount
        return sent

    def low_food_node(self, node: Node) -> bool:
        return node.food < max(18.0, node.soldiers * 0.35)

    def unrest_condition(self, node: Node) -> bool:
        if node.owner not in (PLAYER, ENEMY):
            return False
        if node.site_type in (CAPITAL, FORT):
            return False
        if node.max_population <= 0 or node.is_ruin:
            return False
        return node.soldiers < 10 and node.morale < 30

    def mark_rebel_warning(self, node: Node, reason: str = "") -> None:
        if node.site_type in (CAPITAL, FORT) or node.max_population <= 0:
            return
        if node.owner not in (PLAYER, ENEMY):
            return
        if not node.rebel_warning:
            node.rebel_warning = True
            node.rebel_warning_timer = REBEL_WARNING_SECONDS
            if node.owner == PLAYER:
                self.message = f"{site_label(node)} 进入暗黄预警（30秒）。"

    def clear_rebel_warning(self, node: Node) -> None:
        node.rebel_warning = False
        node.rebel_warning_timer = 0.0

    def trigger_rebellion(self, node: Node, reason: str) -> None:
        if node.owner not in (PLAYER, ENEMY):
            return
        if node.site_type in (CAPITAL, FORT) or node.max_population <= 0:
            return
        node.owner = REBEL
        node.recruit_policy = POLICY_STOP
        node.rebel_warning = False
        node.rebel_warning_timer = 0.0
        militia = max(8.0, min(node.population * 0.04, 60.0))
        node.soldiers = max(militia, node.soldiers * 0.6)
        node.morale = 42.0
        self.message = f"{site_label(node)} 爆发黄巾起义（{reason}）。"

    def update_rebel_warnings(self, dt: float) -> None:
        for node in self.nodes:
            if node.owner in (REBEL, NEUTRAL):
                node.rebel_warning = False
                node.rebel_warning_timer = 0.0
                continue
            if node.site_type in (CAPITAL, FORT) or node.max_population <= 0:
                node.rebel_warning = False
                node.rebel_warning_timer = 0.0
                continue
            if self.unrest_condition(node):
                if not node.rebel_warning:
                    self.mark_rebel_warning(node, "低兵低民心")
                else:
                    node.rebel_warning_timer = max(0.0, node.rebel_warning_timer - dt)
                    if node.rebel_warning_timer <= 0:
                        self.trigger_rebellion(node, "预警失控")
            elif node.rebel_warning:
                self.clear_rebel_warning(node)

    def try_empty_garrison_uprising(self, node: Node) -> None:
        if self.unrest_condition(node):
            self.mark_rebel_warning(node, "空城失控")
            for nid in self.neighbor_ids(node.id):
                neighbor = self.nodes[nid]
                if self.unrest_condition(neighbor) and (self.low_food_node(neighbor) or neighbor.morale < 60):
                    self.mark_rebel_warning(neighbor, "周边连锁")

    def rebel_target_morale(self, target: Node) -> float:
        if target.site_type == FORT or target.max_population <= 0:
            return 100.0
        return target.morale

    def apply_rebel_ruin(self, target: Node) -> None:
        if target.site_type not in (VILLAGE, TOWN):
            return
        target.is_ruin = True
        target.ruin_origin_type = target.site_type
        target.food = 0.0
        target.gold = 0.0
        target.local_gold = 0.0
        target.sacked = True
        target.recruit_policy = POLICY_STOP
        target.development_level = 0
        target.development_line = LINE_ECONOMY
        converted = max(0.0, target.population / POP_PER_SOLDIER)
        target.soldiers += converted
        target.soldiers = min(target.soldiers, self.garrison_limit(target) * MAX_GARRISON_MULTIPLIER)
        target.population = 0.0
        target.max_population = 0.0
        target.morale = 0.0

    def repair_ruin_selected(self) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            return
        if not node.is_ruin:
            self.message = "该据点不是废墟。"
            return
        if node.gold < REBEL_RUIN_REPAIR_COST:
            self.message = f"修复废墟需要 {REBEL_RUIN_REPAIR_COST} 金。"
            return
        origin = node.ruin_origin_type if node.ruin_origin_type in (VILLAGE, TOWN) else VILLAGE
        stats = SITE_STATS[origin]
        node.gold -= REBEL_RUIN_REPAIR_COST
        node.site_type = origin
        node.is_ruin = False
        node.sacked = False
        node.ruin_origin_type = ""
        node.development_level = 0
        node.development_line = LINE_ECONOMY
        node.max_population = float(stats["population"][1])
        node.population = float(stats["population"][0])
        node.max_food = float(max(stats["food"][1], 1))
        node.food = float(stats["food"][0])
        node.max_gold = float(max(stats["gold"][1], 1))
        node.local_gold = node.gold
        if origin == VILLAGE:
            node.defense = 0
            node.max_defense = 1
        else:
            node.defense = 1
            node.max_defense = 2
        node.morale = 55.0
        self.message = f"{site_label(node)} 废墟已修复。"

    def resolve_arrival(self, troop: Troop) -> None:
        target = self.nodes[troop.target]
        source = self.nodes[troop.source]
        if troop.intent == INTENT_MIGRATE:
            self.resolve_migration(troop, target)
            return
        if target.owner == troop.owner:
            target.soldiers += troop.amount
            target.soldiers = min(target.soldiers, self.garrison_limit(target) * MAX_GARRISON_MULTIPLIER)
            if target.max_population > 0:
                target.morale = clamp(target.morale - 1.5, 0, 100)
            if troop.owner == PLAYER:
                self.message = f"援军抵达 {site_label(target)}。"
            return
        if troop.intent == INTENT_OCCUPY and target.soldiers > 0:
            if troop.owner == PLAYER:
                source.soldiers += troop.amount
                self.message = f"{site_label(target)} 仍有守军，无法直接占领。"
            return

        if troop.owner == REBEL:
            morale = self.rebel_target_morale(target)
            if target.owner == NEUTRAL or morale < 30:
                self.capture_node(target, troop, max(1.0, troop.amount + target.soldiers))
                return
            if morale < 60:
                attack = max(1.0, troop.amount * troop.combat_power_modifier * 2.0)
            elif morale > 90:
                attack = max(1.0, troop.amount * troop.combat_power_modifier * 0.5)
            else:
                defense_power = target.defense * 4
                attack = max(1.0, troop.amount * troop.combat_power_modifier - defense_power)
        elif target.owner == NEUTRAL:
            defense_power = target.defense * 2
            attack = max(1.0, troop.amount * 1.25 * troop.combat_power_modifier - defense_power)
        else:
            defense_power = target.defense * 4
            attack = max(1.0, troop.amount * troop.combat_power_modifier - defense_power)

        if attack > target.soldiers:
            self.capture_node(target, troop, attack - target.soldiers)
        else:
            target.soldiers -= attack
            if troop.owner != REBEL:
                self.damage_defense(target, attack)
            if target.max_population > 0:
                target.morale = clamp(target.morale - 4, 0, 100)
            if troop.owner == PLAYER:
                if source.max_population > 0:
                    source.morale = clamp(source.morale - 1.5, 0, 100)
                self.message = f"进攻 {site_label(target)} 失败。"

    def capture_node(self, target: Node, troop: Troop, remaining_attack: float) -> None:
        old_owner = target.owner
        source = self.nodes[troop.source]
        loot = 0.0
        if troop.owner == PLAYER and old_owner != PLAYER and troop.intent in (INTENT_ATTACK, INTENT_SACK):
            loot = target.gold

        target.owner = troop.owner
        target.rebel_warning = False
        target.rebel_warning_timer = 0.0
        target.soldiers = max(1.0, remaining_attack)

        if troop.owner == REBEL:
            if target.site_type in (VILLAGE, TOWN):
                self.apply_rebel_ruin(target)
            self.rebel_speed_boost_timer = REBEL_SPEED_BOOST_DURATION
            self.message = f"黄巾攻下 {site_label(target)}。"
            return

        if troop.intent == INTENT_SACK:
            self.apply_sack(target)
            suffix = f"，焚毁并掠夺 {int(loot)} 金" if loot else ""
            self.message = f"屠城 {site_label(target)}{suffix}。"
        else:
            if target.max_population > 0:
                target.morale = clamp(target.morale - (4 if troop.intent == INTENT_OCCUPY else 8), 0, 100)
            else:
                target.morale = 0
            if troop.owner == PLAYER:
                if source.max_population > 0:
                    source.morale = clamp(source.morale - 1.5, 0, 100)
                suffix = f"，接管本地 {int(loot)} 金" if loot else ""
                self.message = f"占领 {site_label(target)}{suffix}。"

    def launch_troop(
        self,
        source_id: int,
        target_id: int,
        owner: str,
        ratio: float | None = None,
        edge: Edge | None = None,
        intent: str = INTENT_ATTACK,
        from_pending: bool = False,
    ) -> bool:
        source = self.nodes[source_id]
        source_cap = self.garrison_limit(source) * MAX_GARRISON_MULTIPLIER
        if source.soldiers > source_cap:
            source.soldiers = source_cap
        if source.owner != owner or source.soldiers < 8:
            if owner == PLAYER:
                self.message = "至少需要 8 名士兵才能出征。"
            return False
        road = edge or self.edge_between(source_id, target_id)
        if road is None:
            return False
        target = self.nodes[target_id]
        if intent == INTENT_OCCUPY and target.soldiers > 0:
            if owner == PLAYER:
                self.message = "占领只适用于无守军据点。"
            return False
        if intent == INTENT_MIGRATE:
            return self.launch_migration(source_id, target_id)

        send_ratio = ratio if ratio is not None else self.send_ratio
        amount = max(1, math.floor(source.soldiers * send_ratio))
        if amount < 4:
            return False
        food_need = amount * FOOD_PER_TROOP_LAUNCH
        if owner != REBEL and source.food + 1e-6 < food_need:
            if owner == PLAYER and not from_pending:
                if self.pending_action and str(self.pending_action.get("action", "")) == "launch_troop":
                    pending_source = int(self.pending_action.get("source_id", -1))
                    if pending_source == source_id:
                        self.request_auto_food(source_id, max(0.0, food_need - source.food))
                        self.message = f"{site_label(source)} 仍在等待粮草，已继续尝试调粮。"
                        return False
                if self.queue_pending_action(
                    "launch_troop",
                    source_id,
                    0.0,
                    source_id=source_id,
                    target_id=target_id,
                    owner=owner,
                    ratio=send_ratio,
                    intent=intent,
                    needed_food=food_need,
                ):
                    return False
                self.message = f"粮草不足，需要 {int(food_need)} 粮。"
            return False

        source.soldiers -= amount
        if source.soldiers < 0:
            source.soldiers = 0.0
        if owner != REBEL:
            source.food = max(0.0, source.food - food_need)
        if owner == PLAYER:
            if source.max_population > 0:
                source.morale = clamp(source.morale - (3 if target.owner != PLAYER else 1), 0, 100)
            if from_pending:
                self.pending_action = None
            if send_ratio >= 0.999:
                self.try_empty_garrison_uprising(source)

        batch_count = max(1, min(8, math.ceil(amount / TROOP_BATCH_SIZE)))
        remaining = float(amount)
        for batch_id in range(batch_count):
            left = batch_count - batch_id
            batch_amount = max(1.0, remaining / left)
            remaining -= batch_amount
            self.troops.append(
                Troop(
                    owner=owner,
                    source=source_id,
                    target=target_id,
                    start_amount=float(batch_amount),
                    amount=float(batch_amount),
                    terrain=road.terrain,
                    intent=intent,
                    batch_id=batch_id,
                    supply_source=source_id,
                    depart_delay=batch_id * max(0.12, TROOP_BATCH_INTERVAL - amount / 300),
                )
            )
        if owner == PLAYER:
            if target.owner == PLAYER:
                self.message = f"分 {batch_count} 队调动 {amount} 人前往 {site_label(target)}。"
            else:
                self.message = f"{INTENT_LABELS[intent]}：分 {batch_count} 队派出 {amount} 人。"
        return True

    def upgrade_selected(self, line: str, from_pending: bool = False) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            return
        if node.is_ruin:
            self.message = "废墟无法升级，请先修复。"
            return
        if node.development_line != line and node.development_level > 0:
            self.message = "已选择发展线，不能中途转向。"
            return
        if node.development_level >= MAX_DEVELOPMENT_LEVEL:
            self.message = "此据点已经发展到顶级。"
            return
        cost = UPGRADE_COST * (node.development_level + 1)
        if node.gold < cost:
            if not from_pending and self.queue_pending_action("upgrade", node.id, cost, line=line):
                return
            self.message = f"本地金钱不足，升级需要 {cost} 金。"
            return
        node.gold -= cost
        node.local_gold = node.gold
        node.development_line = line
        node.development_level += 1
        self.apply_development(node)
        self.message = f"{site_label(node)} 升级为 {development_name(node)}。"

    def update_troops(self, dt: float) -> None:
        arrived: list[Troop] = []
        routed: list[Troop] = []
        for troop in self.troops:
            if troop.depart_delay > 0:
                troop.depart_delay -= dt
                continue
            edge = self.edge_between(troop.source, troop.target)
            if edge is None:
                continue
            if troop.intent != INTENT_MIGRATE:
                if self.consume_troop_supply(troop, dt):
                    troop.unsupplied_time = max(0.0, troop.unsupplied_time - dt * 0.5)
                    troop.combat_power_modifier = 1.0
                else:
                    troop.unsupplied_time += dt
                    troop.combat_power_modifier = UNSUPPLIED_POWER
                    if troop.unsupplied_time >= UNSUPPLIED_ROUT_SECONDS:
                        routed.append(troop)
                        continue
            terrain = TERRAIN_STATS[troop.terrain]
            speed = terrain["speed"] * (1 + edge.road_level * 0.28)
            if troop.owner == REBEL and self.rebel_speed_boost_timer > 0:
                speed *= REBEL_SPEED_BOOST_MULTIPLIER
            troop.progress = min(1.0, troop.progress + speed * dt)
            troop.amount = max(1.0, troop.start_amount * (1 - terrain["loss"] * troop.progress))
            if troop.progress >= 1.0:
                arrived.append(troop)

        for troop in routed:
            if troop in self.troops:
                self.troops.remove(troop)
                if troop.owner == PLAYER:
                    self.message = "有一支断粮兵团溃散。"

        self.resolve_encounters()
        for troop in arrived:
            if troop not in self.troops:
                continue
            self.resolve_arrival(troop)
            if troop in self.troops:
                self.troops.remove(troop)

    def enemy_turn(self) -> None:
        self.ai_take_turn(ENEMY)

    def ai_take_turn(self, owner: str) -> None:
        self.ai_engine.take_turn(self, owner, self.rng)

    def rebel_turn(self) -> None:
        self.ai_take_turn(REBEL)

    def check_rebel_enemy_alliance(self) -> None:
        return

    def request_auto_population(self, node_id: int, desired_population: float) -> tuple[float, float]:
        if desired_population <= 0:
            return 0.0, 50.0
        target = self.nodes[node_id]
        if target.owner != PLAYER:
            return 0.0, 50.0
        need = desired_population
        moved = 0.0
        morale_weighted = 0.0
        candidates: list[tuple[int, float, Node]] = []
        for node in self.nodes:
            if node.owner != PLAYER or node.id == node_id or node.max_population <= 0:
                continue
            path = self.find_owned_path(node.id, node_id, PLAYER)
            if path is None or len(path) < 2:
                continue
            candidates.append((len(path) - 1, -node.population, node))
        candidates.sort(key=lambda item: (item[0], item[1]))
        for hops, _, donor in candidates:
            if need <= 0:
                break
            reserve = donor.max_population * 0.2
            available = max(0.0, donor.population - reserve)
            if available <= 1:
                continue
            loss_ratio = self.migration_loss_ratio(hops)
            dispatch = min(available, need / max(0.05, 1.0 - loss_ratio))
            if dispatch <= 1:
                continue
            arrived = dispatch * (1.0 - loss_ratio)
            donor.population -= dispatch
            moved += arrived
            need -= arrived
            morale_weighted += donor.morale * arrived
        if moved <= 0:
            return 0.0, 50.0
        return moved, morale_weighted / moved

    def repair_ruin_selected(self) -> None:
        if self.selected is None:
            return
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            return
        if not node.is_ruin:
            self.message = "该据点不是废墟。"
            return
        if node.gold < REBEL_RUIN_REPAIR_COST:
            if self.queue_pending_action("repair_ruin", node.id, REBEL_RUIN_REPAIR_COST):
                return
            self.message = f"修复废墟需要 {REBEL_RUIN_REPAIR_COST} 金。"
            return

        origin = node.ruin_origin_type if node.ruin_origin_type in (VILLAGE, TOWN) else VILLAGE
        stats = SITE_STATS[origin]
        node.gold -= REBEL_RUIN_REPAIR_COST
        node.site_type = origin
        node.is_ruin = False
        node.sacked = False
        node.ruin_origin_type = ""
        node.development_level = 0
        node.development_line = LINE_ECONOMY
        node.max_population = float(stats["population"][1])
        node.population = 0.0
        node.max_food = float(max(stats["food"][1], 1))
        node.food = float(stats["food"][0])
        node.max_gold = float(max(stats["gold"][1], 1))
        node.local_gold = node.gold
        if origin == VILLAGE:
            node.defense = 0
            node.max_defense = 1
        else:
            node.defense = 1
            node.max_defense = 2

        desired_population = float(stats["population"][0])
        moved, avg_morale = self.request_auto_population(node.id, desired_population)
        node.population = min(node.max_population, moved)
        if node.population > 0:
            node.morale = clamp(avg_morale * 0.9, 0, 100)
        else:
            node.morale = 45.0
        self.message = f"{site_label(node)} 废墟已修复，迁入居民 {int(node.population)}。"

    def check_end_state(self) -> None:
        player_nodes = [node for node in self.nodes if node.owner == PLAYER]
        enemy_or_neutral = [node for node in self.nodes if node.owner != PLAYER]
        player_troops = [troop for troop in self.troops if troop.owner == PLAYER]
        if not enemy_or_neutral:
            self.mode = Mode.VICTORY
            self.message = "天下一统。点击或按 R 开启新战局。"
        elif not player_nodes and not player_troops:
            self.mode = Mode.DEFEAT
            self.message = "兵败如山倒。点击或按 R 重新开始。"


if __name__ == "__main__":
    GraphWar().run()
