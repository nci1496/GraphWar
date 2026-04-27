from __future__ import annotations

import math

from graphwar.constants import (
    ENEMY,
    FOOD_PER_TROOP_LAUNCH,
    FOOD_PER_TROOP_SECOND,
    INTENT_ATTACK,
    INTENT_LABELS,
    INTENT_MIGRATE,
    INTENT_OCCUPY,
    INTENT_SACK,
    MAX_GARRISON_MULTIPLIER,
    NEUTRAL,
    PLAYER,
    POLICY_STOP,
    POP_PER_SOLDIER,
    REBEL,
    REBEL_SPEED_BOOST_DURATION,
    REBEL_SPEED_BOOST_MULTIPLIER,
    TERRAIN_STATS,
    TROOP_BATCH_INTERVAL,
    TROOP_BATCH_SIZE,
    UNSUPPLIED_POWER,
    UNSUPPLIED_ROUT_SECONDS,
    TOWN,
    VILLAGE,
)
from graphwar.helpers import clamp, site_label
from graphwar.models import Edge, Node, Troop


class CombatLogicMixin:
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
