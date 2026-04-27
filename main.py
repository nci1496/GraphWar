from __future__ import annotations

import math
import random

import pygame

from graphwar.constants import (
    CAPITAL,
    CAPITAL_GOLD_CAP,
    ENEMY,
    FORT,
    FORTIFY_COST,
    FPS,
    HEIGHT,
    INTENT_ATTACK,
    LINE_ECONOMY,
    MAX_ROAD_LEVEL,
    NEUTRAL,
    PLAYER,
    REBEL,
    REMIT_INTERVAL,
    REPAIR_COST,
    ROAD_COST,
    SITE_STATS,
    TERRAIN_STATS,
    TOWN,
    VILLAGE,
    WIDTH,
    LOW_FOOD_AUTO_SUPPLY_THRESHOLD,
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
)
from graphwar.helpers import (
    clamp,
    development_data,
    load_font,
    site_label,
)
from graphwar.ai_logic import GraphWarAI
from graphwar.input_logic import InputLogicMixin
from graphwar.map_logic import MapLogicMixin
from graphwar.models import Convoy, Edge, Emperor, Mode, Node, Troop
from graphwar.rendering import RenderingMixin
from graphwar.combat_logic import CombatLogicMixin
from graphwar.economy_logic import EconomyLogicMixin
from graphwar.rebel_logic import RebelLogicMixin


class GraphWar(CombatLogicMixin, EconomyLogicMixin, RebelLogicMixin, InputLogicMixin, MapLogicMixin, RenderingMixin):
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
            capital.max_gold = self.capital_gold_cap(capital)
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

    def capital_gold_cap(self, node: Node) -> float:
        if node.site_type != CAPITAL:
            return node.max_gold
        level = max(0, min(node.development_level, 4))
        if node.development_line == LINE_ECONOMY:
            caps = (CAPITAL_GOLD_CAP, 900.0, 1300.0, 1800.0, 2200.0)
        else:
            caps = (CAPITAL_GOLD_CAP, 750.0, 900.0, 1200.0, 1500.0)
        return caps[level]

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

    def player_emperor_status_text(self) -> str:
        emperor = self.emperors.get(PLAYER)
        if emperor is None:
            return "无皇帝"
        if not emperor.alive:
            return "已驾崩"
        if emperor.current_node >= 0:
            if emperor.current_node >= len(self.nodes):
                return "状态异常"
            node = self.nodes[emperor.current_node]
            capital = self.owner_capital(PLAYER)
            if capital is not None and node.id == capital.id:
                return f"在都({site_label(node)})"
            return f"驻于{site_label(node)}"
        if len(emperor.route) >= 2 and emperor.route_index < len(emperor.route) - 1:
            src_id = emperor.route[emperor.route_index]
            dst_id = emperor.route[emperor.route_index + 1]
            if 0 <= src_id < len(self.nodes) and 0 <= dst_id < len(self.nodes):
                src = self.nodes[src_id]
                dst = self.nodes[dst_id]
                return f"行军{site_label(src)}->{site_label(dst)}"
        return "行军中"

    def command_player_emperor_tour(self, target_id: int) -> bool:
        if target_id < 0 or target_id >= len(self.nodes):
            self.message = "皇帝出巡失败：目标无效。"
            return False
        target = self.nodes[target_id]
        if target.owner != PLAYER:
            self.message = "皇帝出巡失败：只能前往我方据点。"
            return False
        emperor = self.emperors.get(PLAYER)
        if emperor is None:
            self.message = "皇帝出巡失败：我方未建立皇帝状态。"
            return False
        if not emperor.alive:
            self.message = "皇帝出巡失败：皇帝已驾崩。"
            return False
        if emperor.current_node < 0:
            self.message = "皇帝出巡失败：皇帝正在行军中。"
            return False
        if emperor.current_node == target_id:
            self.message = "皇帝已在该据点。"
            return False
        if not self.move_emperor(PLAYER, target_id):
            self.message = "皇帝出巡失败：无可用路径或条件不满足。"
            return False
        return True

    def command_player_emperor_return(self) -> bool:
        emperor = self.emperors.get(PLAYER)
        if emperor is None:
            self.message = "皇帝回都失败：我方未建立皇帝状态。"
            return False
        if not emperor.alive:
            self.message = "皇帝回都失败：皇帝已驾崩。"
            return False
        capital = self.player_capital()
        if capital is None:
            self.message = "皇帝回都失败：当前无我方都城。"
            return False
        if emperor.current_node < 0:
            self.message = "皇帝回都失败：皇帝正在行军中。"
            return False
        if emperor.current_node == capital.id:
            self.message = "皇帝已在都城。"
            return False
        if not self.move_emperor(PLAYER, capital.id):
            self.message = "皇帝回都失败：无可用路径或条件不满足。"
            return False
        self.message = f"皇帝回都：已启程前往 {site_label(capital)}。"
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
            self.refresh_node_display_name(old_capital)
        node.site_type = CAPITAL
        node.max_defense += 2
        node.defense = min(node.max_defense, node.defense + 2)
        node.max_population = max(node.max_population, SITE_STATS[CAPITAL]["population"][1])
        node.max_gold = self.capital_gold_cap(node)
        node.gold = min(node.gold, node.max_gold)
        self.refresh_node_display_name(node)
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


    def apply_development(self, node: Node) -> None:
        data = development_data(node)
        node.max_population = max(node.max_population, SITE_STATS[node.site_type]["population"][1] * data["pop"])
        node.max_food = max(node.max_food, SITE_STATS[node.site_type]["food"][1] * data["food"])
        node.max_gold = max(node.max_gold, SITE_STATS[node.site_type]["gold"][1] * data["gold"])
        if node.site_type == CAPITAL:
            node.max_gold = self.capital_gold_cap(node)
            node.gold = min(node.gold, node.max_gold)
            node.local_gold = node.gold
            self.treasury = node.gold
        node.max_defense = max(node.max_defense, int(data["defense"]))
        node.max_defense = min(node.max_defense, self.defense_cap(node))
        node.defense = max(node.defense, math.ceil(node.max_defense * 0.75))
        self.refresh_node_display_name(node)

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
