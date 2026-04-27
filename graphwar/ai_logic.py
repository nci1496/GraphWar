from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .constants import (
    CAPITAL,
    CONVOY_FOOD,
    CONVOY_GOLD,
    ENEMY,
    FOOD_PER_TROOP_LAUNCH,
    FORT,
    FORTIFY_COST,
    INTENT_ATTACK,
    INTENT_OCCUPY,
    LINE_ECONOMY,
    LINE_MILITARY,
    MAX_DEVELOPMENT_LEVEL,
    MAX_ROAD_LEVEL,
    NEUTRAL,
    PLAYER,
    POLICY_LOW,
    POLICY_NORMAL,
    POLICY_STOP,
    REBEL,
    REBEL_RUIN_REPAIR_COST,
    ROAD_COST,
    SITE_STATS,
    TERRAIN_STATS,
    TOWN,
    UPGRADE_COST,
    VILLAGE,
)

if TYPE_CHECKING:
    from random import Random

    from .models import Edge, Node


@dataclass(slots=True)
class AIAction:
    kind: str
    source_id: int
    target_id: int = -1
    ratio: float = 0.0
    amount: float = 0.0
    intent: str = INTENT_ATTACK


class GraphWarAI:
    def __init__(self) -> None:
        self.debug = False

    def take_turn(self, game, owner: str, rng: Random) -> AIAction | None:
        action = self.choose_action(game, owner, rng)
        if action is None:
            return None
        if not self.execute_action(game, owner, action):
            return None
        if self.debug:
            game.message = f"AI[{owner}] -> {action.kind} {action.source_id}->{action.target_id}"
        return action

    def evaluate_state(self, game, owner: str) -> float:
        nodes = game.nodes
        own_nodes = [n for n in nodes if n.owner == owner]
        enemy_nodes = [n for n in nodes if n.owner not in (owner, NEUTRAL)]

        score = 0.0
        score += len(own_nodes) * 130.0
        for node in own_nodes:
            score += node.soldiers * 1.8
            score += node.defense * 23.0
            score += node.food * 0.045
            score += node.gold * 0.040
            score += node.development_level * 18.0
            score += self._node_value(game, node, owner)
            score -= self._rebel_risk_penalty(game, node, owner)
            if node.supply_blocked_time > 0:
                score -= 16.0 * min(node.supply_blocked_time, 12.0)
            if node.food < max(20.0, node.soldiers * 0.35):
                score -= 26.0
            cap = game.garrison_limit(node)
            if node.soldiers > cap:
                score -= (node.soldiers - cap) * 2.6
            score -= 10.0 * self._frontline_threat(game, node, owner)

        for node in enemy_nodes:
            score -= node.soldiers * 0.9
            score -= self._node_value(game, node, owner) * 0.28
        return score

    def generate_candidates(self, game, owner: str) -> list[AIAction]:
        candidates: list[AIAction] = []
        own_nodes = [n for n in game.nodes if n.owner == owner]
        if not own_nodes:
            return candidates

        for source in own_nodes:
            if owner == REBEL:
                if source.soldiers < 8:
                    continue
                for nid in game.neighbor_ids(source.id):
                    target = game.nodes[nid]
                    if target.owner == REBEL:
                        continue
                    candidates.append(AIAction("rebel_attack", source.id, target.id, ratio=0.65, intent=INTENT_ATTACK))
                continue

            rebel_risk = self._rebel_risk_level(game, source, owner)
            if rebel_risk >= 2 and source.recruit_policy != POLICY_STOP:
                candidates.append(AIAction("set_recruit_policy", source.id, intent=POLICY_STOP))
            elif rebel_risk >= 1 and source.recruit_policy == POLICY_NORMAL:
                candidates.append(AIAction("set_recruit_policy", source.id, intent=POLICY_LOW))
            elif (
                rebel_risk == 0
                and source.recruit_policy == POLICY_STOP
                and source.morale >= 55
                and source.soldiers < game.garrison_limit(source) * 0.8
            ):
                candidates.append(AIAction("set_recruit_policy", source.id, intent=POLICY_LOW))

            # Expansion / attack / reinforce.
            if source.soldiers >= 10:
                for nid in game.neighbor_ids(source.id):
                    target = game.nodes[nid]
                    edge = game.edge_between(source.id, target.id)
                    if edge is None:
                        continue
                    if target.owner == owner:
                        threatened = self._frontline_threat(game, target, owner)
                        if source.soldiers >= 18 and (threatened > 0 or target.soldiers < 12):
                            ratio = 0.35 if threatened > 0 else 0.28
                            candidates.append(
                                AIAction("reinforce", source.id, target.id, ratio=ratio, intent=INTENT_ATTACK)
                            )
                        if source.soldiers >= 14 and self._rebel_risk_level(game, target, owner) >= 2:
                            candidates.append(AIAction("reinforce", source.id, target.id, ratio=0.30, intent=INTENT_ATTACK))
                    else:
                        ratio = 0.50 if target.owner == NEUTRAL else 0.60
                        intent = INTENT_OCCUPY if target.soldiers <= 0 else INTENT_ATTACK
                        candidates.append(AIAction("attack", source.id, target.id, ratio=ratio, intent=intent))

            # Logistic actions.
            low_food_need = max(60.0, source.soldiers * 0.40)
            if source.max_food > 0 and source.food < low_food_need:
                food_donor = self._best_supply_source(game, owner, source.id, CONVOY_FOOD)
                if food_donor is not None:
                    amount = min(
                        food_donor.food * 0.40,
                        max(0.0, source.max_food - source.food),
                        max(25.0, low_food_need - source.food + 15.0),
                    )
                    if amount >= 18:
                        candidates.append(AIAction("supply_food", food_donor.id, source.id, amount=amount))

            low_gold_need = 70.0
            if source.max_gold > 0 and source.gold < low_gold_need:
                gold_donor = self._best_supply_source(game, owner, source.id, CONVOY_GOLD)
                if gold_donor is not None:
                    amount = min(
                        gold_donor.gold * 0.40,
                        max(0.0, source.max_gold - source.gold),
                        max(20.0, low_gold_need - source.gold + 10.0),
                    )
                    if amount >= 12:
                        candidates.append(AIAction("supply_gold", gold_donor.id, source.id, amount=amount))

            # Build actions.
            if source.is_ruin:
                if source.gold >= REBEL_RUIN_REPAIR_COST:
                    candidates.append(AIAction("repair_ruin", source.id))
                continue
            if source.gold >= FORTIFY_COST and self._frontline_threat(game, source, owner) > 0:
                candidates.append(AIAction("fortify", source.id))
            if source.development_level < MAX_DEVELOPMENT_LEVEL:
                if source.development_level == 0:
                    frontline = self._frontline_threat(game, source, owner)
                    strategic = self._strategic_defense_score(game, source, owner)
                    if source.site_type == FORT or frontline > 0 or strategic >= 1.0:
                        candidates.append(AIAction("upgrade", source.id, intent=LINE_MILITARY))
                    else:
                        candidates.append(AIAction("upgrade", source.id, intent=LINE_ECONOMY))
                        candidates.append(AIAction("upgrade", source.id, intent=LINE_MILITARY))
                else:
                    candidates.append(AIAction("upgrade", source.id, intent=source.development_line))
            if source.gold >= ROAD_COST:
                for nid in game.neighbor_ids(source.id):
                    target = game.nodes[nid]
                    if target.owner != owner:
                        continue
                    edge = game.edge_between(source.id, target.id)
                    if edge is None or edge.road_level >= MAX_ROAD_LEVEL:
                        continue
                    if self._road_frontline_value(game, edge, owner) > 0:
                        candidates.append(AIAction("repair_road", source.id, target.id))
        return candidates

    def simulate_action_delta(self, game, owner: str, action: AIAction) -> float:
        current = self.evaluate_state(game, owner)
        projected = current + self._estimate_action_gain(game, owner, action)
        return projected - current

    def choose_action(self, game, owner: str, rng: Random) -> AIAction | None:
        candidates = self.generate_candidates(game, owner)
        if not candidates:
            return None
        best: AIAction | None = None
        best_delta = -10**9
        for action in candidates:
            delta = self.simulate_action_delta(game, owner, action)
            # Stable argmax with tiny jitter to avoid deterministic loops on ties.
            delta += rng.uniform(-0.05, 0.05)
            if delta > best_delta:
                best_delta = delta
                best = action
        if best is None or best_delta < -120:
            return None
        return best

    def execute_action(self, game, owner: str, action: AIAction) -> bool:
        if action.kind in ("attack", "reinforce", "rebel_attack"):
            edge = game.edge_between(action.source_id, action.target_id)
            if edge is None:
                return False
            return game.launch_troop(
                action.source_id,
                action.target_id,
                owner,
                ratio=action.ratio,
                edge=edge,
                intent=action.intent,
            )

        if action.kind in ("supply_food", "supply_gold"):
            if owner == REBEL:
                return False
            source = game.nodes[action.source_id]
            target = game.nodes[action.target_id]
            if source.owner != owner or target.owner != owner:
                return False
            if action.kind == "supply_food":
                amount = min(action.amount, source.food, max(0.0, target.max_food - target.food))
                if amount < 12:
                    return False
                if not game.create_convoy(owner, source.id, target.id, CONVOY_FOOD, amount, allow_multihop=True):
                    return False
                source.food -= amount
                return True
            amount = min(action.amount, source.gold, max(0.0, target.max_gold - target.gold))
            if amount < 10:
                return False
            if not game.create_convoy(owner, source.id, target.id, CONVOY_GOLD, amount, allow_multihop=True):
                return False
            source.gold -= amount
            source.local_gold = source.gold
            return True

        if action.kind == "repair_road":
            if owner == REBEL:
                return False
            source = game.nodes[action.source_id]
            target = game.nodes[action.target_id]
            edge = game.edge_between(source.id, target.id)
            if source.owner != owner or target.owner != owner or edge is None:
                return False
            if source.gold < ROAD_COST or edge.road_level >= MAX_ROAD_LEVEL:
                return False
            source.gold -= ROAD_COST
            source.local_gold = source.gold
            edge.road_level += 1
            return True

        if action.kind == "fortify":
            if owner == REBEL:
                return False
            source = game.nodes[action.source_id]
            if source.owner != owner or source.gold < FORTIFY_COST:
                return False
            source.gold -= FORTIFY_COST
            source.local_gold = source.gold
            source.max_defense += 1
            source.defense += 1
            return True

        if action.kind == "upgrade":
            if owner == REBEL:
                return False
            node = game.nodes[action.source_id]
            if node.owner != owner:
                return False
            if node.is_ruin:
                return False
            if node.development_level >= MAX_DEVELOPMENT_LEVEL:
                return False
            line = action.intent
            if node.development_level > 0 and node.development_line != line:
                return False
            cost = UPGRADE_COST * (node.development_level + 1)
            if node.gold < cost:
                return False
            node.gold -= cost
            node.local_gold = node.gold
            node.development_line = line
            node.development_level += 1
            game.apply_development(node)
            return True

        if action.kind == "set_recruit_policy":
            if owner == REBEL:
                return False
            node = game.nodes[action.source_id]
            if node.owner != owner or node.is_ruin or node.max_population <= 0:
                return False
            if action.intent not in (POLICY_STOP, POLICY_LOW, POLICY_NORMAL):
                return False
            node.recruit_policy = action.intent
            return True

        if action.kind == "repair_ruin":
            if owner == REBEL:
                return False
            node = game.nodes[action.source_id]
            if node.owner != owner or not node.is_ruin or node.gold < REBEL_RUIN_REPAIR_COST:
                return False
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
            node.population = float(stats["population"][0] * 0.7)
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
            node.morale = max(35.0, min(55.0, node.morale))
            game.refresh_node_display_name(node)
            return True
        return False

    def _estimate_action_gain(self, game, owner: str, action: AIAction) -> float:
        if action.kind in ("attack", "reinforce", "rebel_attack"):
            source = game.nodes[action.source_id]
            target = game.nodes[action.target_id]
            edge = game.edge_between(source.id, target.id)
            if edge is None:
                return -999.0
            amount = max(1, math.floor(source.soldiers * action.ratio))
            if amount < 4:
                return -999.0
            food_need = amount * FOOD_PER_TROOP_LAUNCH
            if source.food < food_need:
                return -80.0 - (food_need - source.food) * 0.6

            if action.kind == "reinforce":
                threat = self._frontline_threat(game, target, owner)
                return 18.0 + threat * 22.0 + min(50.0, amount * 0.8)

            if action.kind == "rebel_attack":
                if target.site_type in (FORT, CAPITAL):
                    return -180.0
                morale = 100.0 if target.max_population <= 0 or target.site_type == FORT else target.morale
                base = self._node_value(game, target, owner) + target.food * 0.10 + target.gold * 0.08
                if target.owner == NEUTRAL or morale < 30:
                    return base + 95.0
                if morale < 60:
                    return base + 55.0 - target.soldiers * 0.35
                if morale > 90:
                    return base - target.soldiers * 0.90 - 35.0
                return base - target.soldiers * 0.55

            projected_attack = self._projected_attack_power(source, target, edge, amount)
            target_value = self._node_value(game, target, owner) + target.food * 0.05 + target.gold * 0.06
            loss_cost = amount * 0.35 + max(0.0, target.soldiers - projected_attack) * 1.8
            terrain_cost = TERRAIN_STATS[edge.terrain]["loss"] * 90 + (0.12 - TERRAIN_STATS[edge.terrain]["speed"]) * 140
            can_take = projected_attack > target.soldiers * (1.04 if target.owner == NEUTRAL else 1.12)
            score = target_value - loss_cost - terrain_cost
            if can_take:
                score += 42.0
            else:
                score -= 28.0
            if target.site_type in (FORT, CAPITAL) and not can_take:
                score -= 45.0
            return score

        if action.kind == "supply_food":
            source = game.nodes[action.source_id]
            target = game.nodes[action.target_id]
            path_len = self._path_len(game, source.id, target.id, source.owner)
            deficit = max(0.0, target.soldiers * 0.50 - target.food)
            return 24.0 + min(action.amount, deficit + 20.0) * 0.6 - path_len * 5.0

        if action.kind == "supply_gold":
            source = game.nodes[action.source_id]
            target = game.nodes[action.target_id]
            path_len = self._path_len(game, source.id, target.id, source.owner)
            pressure = self._frontline_threat(game, target, source.owner)
            return 15.0 + pressure * 10.0 + min(action.amount, 60.0) * 0.35 - path_len * 4.0

        if action.kind == "repair_road":
            source = game.nodes[action.source_id]
            target = game.nodes[action.target_id]
            edge = game.edge_between(source.id, target.id)
            if edge is None or edge.road_level >= MAX_ROAD_LEVEL or source.gold < ROAD_COST:
                return -999.0
            return 16.0 + self._road_frontline_value(game, edge, source.owner) * 18.0 - ROAD_COST * 0.18

        if action.kind == "fortify":
            source = game.nodes[action.source_id]
            if source.gold < FORTIFY_COST:
                return -999.0
            threat = self._frontline_threat(game, source, source.owner)
            return 12.0 + threat * 18.0 + self._node_value(game, source, source.owner) * 0.08 - FORTIFY_COST * 0.16

        if action.kind == "upgrade":
            node = game.nodes[action.source_id]
            if node.is_ruin:
                return -999.0
            if node.development_level >= MAX_DEVELOPMENT_LEVEL:
                return -999.0
            if node.development_level > 0 and node.development_line != action.intent:
                return -999.0
            cost = UPGRADE_COST * (node.development_level + 1)
            if node.gold < cost:
                return -999.0
            base = self._node_value(game, node, owner) * 0.22
            own_upgraded = [n for n in game.nodes if n.owner == owner and n.development_level > 0 and n.max_population > 0]
            mil_count = sum(1 for n in own_upgraded if n.development_line == LINE_MILITARY)
            econ_count = sum(1 for n in own_upgraded if n.development_line == LINE_ECONOMY)
            food_support = sum(
                1
                for n in own_upgraded
                if n.development_line == LINE_ECONOMY and n.food > max(80.0, n.soldiers * 0.6)
            )
            dist_enemy = self._distance_to_enemy_front(game, node, owner)
            strategic = self._strategic_defense_score(game, node, owner)
            if action.intent == LINE_ECONOMY:
                econ_gain = 32.0 + node.population * 0.01 + node.food * 0.02 + node.gold * 0.03
                frontline_penalty = self._frontline_threat(game, node, owner) * 9.0
                if node.soldiers > game.garrison_limit(node) * 0.75:
                    frontline_penalty += 12.0
                support_bonus = 14.0 if mil_count > econ_count else 0.0
                if food_support <= 1:
                    support_bonus += 10.0
                if dist_enemy >= 4:
                    support_bonus += 8.0
                if strategic >= 1.0:
                    frontline_penalty += 18.0
                return base + econ_gain + support_bonus - frontline_penalty - cost * 0.17
            mil_gain = 20.0 + self._frontline_threat(game, node, owner) * 32.0 + strategic * 52.0 + node.soldiers * 0.38
            if node.soldiers > game.garrison_limit(node):
                mil_gain += 20.0
            upkeep_penalty = max(0.0, node.soldiers * 0.40 - node.food) * -0.06
            if dist_enemy >= 5 and strategic < 0.6:
                mil_gain -= 18.0
            if mil_count > econ_count + 1:
                mil_gain -= 24.0
            if food_support == 0:
                mil_gain -= 18.0
            return base + mil_gain + upkeep_penalty - cost * 0.17

        if action.kind == "set_recruit_policy":
            node = game.nodes[action.source_id]
            if node.owner != owner or node.is_ruin or node.max_population <= 0:
                return -999.0
            risk_penalty = self._rebel_risk_penalty(game, node, owner)
            if action.intent == POLICY_STOP:
                return 12.0 + risk_penalty * 0.45 + max(0.0, 55.0 - node.morale) * 0.35
            if action.intent == POLICY_LOW:
                return 8.0 + risk_penalty * 0.30 + max(0.0, 45.0 - node.morale) * 0.22
            return 3.0 - risk_penalty * 0.20

        if action.kind == "repair_ruin":
            node = game.nodes[action.source_id]
            if node.owner != owner or not node.is_ruin or node.gold < REBEL_RUIN_REPAIR_COST:
                return -999.0
            pressure = self._frontline_threat(game, node, owner)
            return 42.0 + pressure * 10.0 - REBEL_RUIN_REPAIR_COST * 0.18

        return -999.0

    def _projected_attack_power(self, source: Node, target: Node, edge: Edge, amount: float) -> float:
        terrain = TERRAIN_STATS[edge.terrain]
        march_left = max(0.0, 1.0 - terrain["loss"] * 0.65)
        supply_factor = 1.0 if source.food > amount * 0.4 else 0.75
        attack = amount * march_left * supply_factor
        if target.owner == NEUTRAL:
            attack = attack * 1.25 - target.defense * 2.0
        else:
            attack = attack - target.defense * 4.0
        return max(1.0, attack)

    def _node_value(self, game, node: Node, owner: str) -> float:
        base = 0.0
        if node.site_type == CAPITAL:
            base += 220.0
        elif node.site_type == FORT:
            base += 150.0
        elif node.site_type == TOWN:
            base += 92.0
        elif node.site_type == VILLAGE:
            base += 68.0

        degree = len(game.neighbor_ids(node.id))
        base += degree * 16.0
        if degree >= 4:
            base += 28.0
        base += self._strategic_defense_score(game, node, owner) * 24.0
        if self._frontline_threat(game, node, owner) > 0:
            base += 22.0
        base += min(90.0, node.food * 0.03 + node.gold * 0.04)
        base += node.development_level * 20.0
        if owner == REBEL:
            morale = 100.0 if node.max_population <= 0 or node.site_type == FORT else node.morale
            base += max(0.0, 70.0 - morale) * 1.8
            if node.site_type in (FORT, CAPITAL):
                base -= 120.0
        return base

    def _road_frontline_value(self, game, edge: Edge, owner: str) -> float:
        a = game.nodes[edge.a]
        b = game.nodes[edge.b]
        value = 0.0
        if a.owner == owner and self._frontline_threat(game, a, owner) > 0:
            value += 1.0
        if b.owner == owner and self._frontline_threat(game, b, owner) > 0:
            value += 1.0
        if len(game.neighbor_ids(a.id)) >= 4 or len(game.neighbor_ids(b.id)) >= 4:
            value += 0.8
        return value

    def _rebel_risk_level(self, game, node: Node, owner: str) -> int:
        if owner not in (PLAYER, ENEMY):
            return 0
        if node.owner != owner or node.max_population <= 0 or node.site_type in (FORT, CAPITAL):
            return 0
        risk = 0
        if node.morale < 30:
            risk += 2
        elif node.morale < 60:
            risk += 1
        if node.soldiers < 10:
            risk += 2
        elif node.soldiers < 16:
            risk += 1
        if node.food < max(20.0, node.soldiers * 0.35):
            risk += 1
        rebel_pressure = 0.0
        for nid in game.neighbor_ids(node.id):
            other = game.nodes[nid]
            if other.owner == REBEL:
                rebel_pressure += 1.0 + other.soldiers / 35.0
        if rebel_pressure >= 2.5:
            risk += 2
        elif rebel_pressure > 0:
            risk += 1
        if node.rebel_warning:
            risk += 1
        return risk

    def _rebel_risk_penalty(self, game, node: Node, owner: str) -> float:
        level = self._rebel_risk_level(game, node, owner)
        if level <= 0:
            return 0.0
        penalty = float(level * level * 4.0)
        if node.morale < 30:
            penalty += 16.0
        elif node.morale < 60:
            penalty += 7.0
        if node.soldiers < 10:
            penalty += 14.0
        return penalty

    def _frontline_threat(self, game, node: Node, owner: str) -> float:
        threat = 0.0
        for nid in game.neighbor_ids(node.id):
            n = game.nodes[nid]
            if n.owner not in (owner, NEUTRAL):
                threat += 1.0 + n.soldiers / 40.0
        return threat

    def _distance_to_enemy_front(self, game, node: Node, owner: str) -> int:
        from collections import deque

        q = deque([(node.id, 0)])
        seen = {node.id}
        while q:
            nid, dist = q.popleft()
            current = game.nodes[nid]
            if current.owner not in (owner, NEUTRAL):
                return dist
            if dist >= 7:
                continue
            for nxt in game.neighbor_ids(nid):
                if nxt in seen:
                    continue
                seen.add(nxt)
                q.append((nxt, dist + 1))
        return 8

    def _strategic_defense_score(self, game, node: Node, owner: str) -> float:
        degree = len(game.neighbor_ids(node.id))
        is_fort = 1.0 if node.site_type == FORT else 0.0
        near_enemy = max(0.0, 4.0 - self._distance_to_enemy_front(game, node, owner)) / 4.0
        hub = 1.0 if degree >= 4 else (0.4 if degree == 3 else 0.0)
        return is_fort * 1.2 + near_enemy * 1.0 + hub * 0.8

    def _best_supply_source(self, game, owner: str, target_id: int, cargo: str) -> Node | None:
        target = game.nodes[target_id]
        candidates = [n for n in game.nodes if n.owner == owner and n.id != target_id]
        best = None
        best_score = -10**9
        for node in candidates:
            path = game.find_owned_path(node.id, target_id, owner)
            if path is None or len(path) < 2:
                continue
            if cargo == CONVOY_FOOD and node.food < 40:
                continue
            if cargo == CONVOY_GOLD and node.gold < 30:
                continue
            stock = node.food if cargo == CONVOY_FOOD else node.gold
            score = stock - (len(path) - 1) * 12.0
            if score > best_score:
                best_score = score
                best = node
        return best

    def _path_len(self, game, a: int, b: int, owner: str) -> int:
        path = game.find_owned_path(a, b, owner)
        if path is None:
            return 9
        return max(1, len(path) - 1)
