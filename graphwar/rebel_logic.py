from __future__ import annotations

from graphwar.constants import (
    CAPITAL,
    ENEMY,
    FORT,
    LINE_ECONOMY,
    MAX_GARRISON_MULTIPLIER,
    NEUTRAL,
    PLAYER,
    POLICY_STOP,
    POP_PER_SOLDIER,
    REBEL,
    REBEL_RUIN_REPAIR_COST,
    REBEL_WARNING_SECONDS,
    SITE_STATS,
    TOWN,
    VILLAGE,
)
from graphwar.helpers import clamp, site_label
from graphwar.models import Node


class RebelLogicMixin:
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
        previous_name = target.display_name
        target.ruin_origin_defense = int(max(0, target.defense))
        target.ruin_origin_max_defense = int(max(target.ruin_origin_defense, target.max_defense))
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
        self.apply_ruin_display_name(target, previous_name)
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
        if node.ruin_origin_max_defense > 0:
            node.max_defense = int(node.ruin_origin_max_defense)
            node.defense = int(min(node.max_defense, max(0, node.ruin_origin_defense)))
        elif origin == VILLAGE:
            node.defense = 0
            node.max_defense = 1
        else:
            node.defense = 1
            node.max_defense = 2
        node.ruin_origin_defense = 0
        node.ruin_origin_max_defense = 0
        self.refresh_node_display_name(node)

        desired_population = float(stats["population"][0])
        moved, avg_morale = self.request_auto_population(node.id, desired_population)
        node.population = min(node.max_population, moved)
        if node.population > 0:
            node.morale = clamp(avg_morale * 0.9, 0, 100)
        else:
            node.morale = 45.0
        self.message = f"{site_label(node)} 废墟已修复，迁入居民 {int(node.population)}。"
    def enemy_turn(self) -> None:
        self.ai_take_turn(ENEMY)
    def ai_take_turn(self, owner: str) -> None:
        self.ai_engine.take_turn(self, owner, self.rng)
    def rebel_turn(self) -> None:
        self.ai_take_turn(REBEL)
    def check_rebel_enemy_alliance(self) -> None:
        return
