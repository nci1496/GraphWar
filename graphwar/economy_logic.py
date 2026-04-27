from __future__ import annotations

from collections import deque

from graphwar.constants import (
    AUTO_MIGRATE_BATCH,
    CAPITAL,
    CONVOY_BATCH_RATIO,
    CONVOY_FOOD,
    CONVOY_GOLD,
    CONVOY_POP,
    DEMOBILIZE_MORALE_BONUS,
    DEMOBILIZE_RATIO,
    ENEMY,
    FOOD_PER_TROOP_SECOND,
    FORT,
    GARRISON_FOOD_PER_SOLDIER_SECOND,
    INTENT_ATTACK,
    INTENT_LABELS,
    INTENT_MIGRATE,
    INTENT_OCCUPY,
    LINE_ECONOMY,
    LINE_MILITARY,
    LOW_FOOD_AUTO_SUPPLY_THRESHOLD,
    LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH,
    LOW_FOOD_MORALE_DROP,
    LOW_FOOD_MORALE_THRESHOLD,
    MAX_DEVELOPMENT_LEVEL,
    MAX_GARRISON_MULTIPLIER,
    MAX_ROAD_LEVEL,
    MIGRATION_BASE_LOSS,
    MIGRATION_LOSS_PER_HOP,
    MIN_FOOD_CONVOY_AMOUNT,
    MIN_POP_CONVOY_AMOUNT,
    NEUTRAL,
    PLAYER,
    POLICY_STOP,
    POP_PER_SOLDIER,
    REBEL,
    RECRUIT_POLICIES,
    REMIT_INTERVAL,
    REMIT_RATE,
    ROAD_COST,
    SITE_STATS,
    TERRAIN_STATS,
    TOWN,
    UPGRADE_COST,
    VILLAGE,
    ZERO_FOOD_MORALE_DROP,
)
from graphwar.helpers import clamp, development_bonus, development_name, is_recruitable, is_taxable, normalize_edge, site_label
from graphwar.models import Convoy, Edge, Node


class EconomyLogicMixin:
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
    def collect_taxes(self) -> None:
        gained = 0.0
        capital = self.player_capital()
        if capital is None:
            return
        capital.max_gold = self.capital_gold_cap(capital)
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
