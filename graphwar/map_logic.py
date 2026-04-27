from __future__ import annotations

from graphwar.constants import (
    CAPITAL,
    CAPITAL_GOLD_CAP,
    ENEMY,
    FORT,
    HEIGHT,
    LINE_ECONOMY,
    LINE_MILITARY,
    MAP_LEFT,
    MAP_RIGHT,
    MAP_SIZE_PRESETS,
    NEUTRAL,
    PLAYER,
    POLICY_LOW,
    POLICY_STOP,
    SITE_STATS,
    TOP_BAR,
    TOWN,
    VILLAGE,
    FORD,
    MOUNTAIN,
    PLAINS,
)
from graphwar.helpers import distance, distance_xy, is_recruitable, normalize_edge
from graphwar.models import Edge, Node


class MapLogicMixin:
    def generate_map(self) -> tuple[list[Node], list[Edge]]:
        preset = MAP_SIZE_PRESETS.get(getattr(self, "map_size_mode", "small"), MAP_SIZE_PRESETS["small"])
        node_count = int(preset["nodes"])
        min_spacing = float(preset["spacing"])
        points: list[tuple[float, float]] = []
        attempts = 0
        while len(points) < node_count and attempts < 5000:
            attempts += 1
            x = self.rng.uniform(MAP_LEFT + 92, MAP_RIGHT - 92)
            y = self.rng.uniform(TOP_BAR + 72, HEIGHT - 78)
            if all(distance_xy(x, y, px, py) > min_spacing for px, py in points):
                points.append((x, y))

        while len(points) < node_count:
            points.append(
                (
                    self.rng.uniform(MAP_LEFT + 92, MAP_RIGHT - 92),
                    self.rng.uniform(TOP_BAR + 72, HEIGHT - 78),
                )
            )

        site_types = self.assign_site_types(points)
        nodes = [self.create_node(i, x, y, site_types[i]) for i, (x, y) in enumerate(points)]

        player_start = min(nodes, key=lambda n: n.x)
        enemy_start = max(nodes, key=lambda n: n.x)
        player_start.site_type = CAPITAL
        enemy_start.site_type = CAPITAL
        self.apply_site_stats(player_start, PLAYER, fixed_soldiers=54)
        self.apply_site_stats(enemy_start, ENEMY, fixed_soldiers=52)

        for node in nodes:
            if node.id not in (player_start.id, enemy_start.id):
                self.apply_site_stats(node, NEUTRAL)

        edges = self.build_edges(nodes)
        self.correct_forts(nodes, edges)
        return nodes, edges

    def assign_site_types(self, points: list[tuple[float, float]]) -> list[str]:
        types = [VILLAGE for _ in points]
        sorted_by_x = sorted(range(len(points)), key=lambda i: points[i][0])
        for index in sorted_by_x[1:-1]:
            roll = self.rng.random()
            if roll < 0.22:
                types[index] = FORT
            elif roll < 0.62:
                types[index] = TOWN
            else:
                types[index] = VILLAGE
        return types

    def create_node(self, node_id: int, x: float, y: float, site_type: str) -> Node:
        node = Node(id=node_id, x=x, y=y, site_type=site_type)
        self.apply_site_stats(node, NEUTRAL)
        return node

    def apply_site_stats(self, node: Node, owner: str, fixed_soldiers: int | None = None) -> None:
        stats = SITE_STATS[node.site_type]
        low, high = stats["soldiers"]
        pop_low, pop_high = stats["population"]
        food_low, food_high = stats["food"]
        gold_low, gold_high = stats["gold"]
        node.owner = owner
        if fixed_soldiers is not None:
            node.soldiers = fixed_soldiers
        elif owner == NEUTRAL and node.site_type == FORT:
            node.soldiers = 0
        else:
            node.soldiers = self.rng.randint(low, high)
        node.production = float(stats["production"])
        node.defense = int(stats["defense"])
        node.max_defense = int(stats["defense"])
        if node.site_type == VILLAGE:
            node.defense = 0
            node.max_defense = 1
        elif node.site_type == TOWN:
            node.defense = 1
            node.max_defense = 2
        node.max_population = float(pop_high)
        node.population = float(self.rng.randint(pop_low, pop_high)) if pop_high > 0 else 0.0
        node.morale = 72.0 if owner == PLAYER else 62.0
        node.max_food = float(max(food_high, 1))
        node.food = float(self.rng.randint(food_low, food_high)) if food_high > 0 else 0.0
        node.max_gold = float(max(gold_high, 1))
        node.gold = float(self.rng.randint(gold_low, gold_high)) if gold_high > 0 else 0.0
        if node.site_type == CAPITAL:
            node.max_gold = CAPITAL_GOLD_CAP
            node.gold = min(node.gold, node.max_gold)
        node.local_gold = node.gold
        node.development_line = LINE_MILITARY if node.site_type == FORT else LINE_ECONOMY
        node.development_level = 0
        node.recruit_policy = POLICY_LOW if is_recruitable(node) else POLICY_STOP
        node.sacked = False
        node.rebel_warning = False
        node.rebel_warning_timer = 0.0
        node.is_ruin = False
        node.ruin_origin_type = ""
        node.ruin_origin_defense = 0
        node.ruin_origin_max_defense = 0
        if node.site_type == FORT:
            node.population = 0.0
            node.max_population = 0.0
            node.morale = 0.0
            node.recruit_policy = POLICY_STOP

    def build_edges(self, nodes: list[Node]) -> list[Edge]:
        edge_pairs: set[tuple[int, int]] = set()
        connected = {0}
        remaining = set(range(1, len(nodes)))

        while remaining:
            best_pair = None
            best_dist = float("inf")
            for a in connected:
                for b in remaining:
                    dist = distance(nodes[a], nodes[b])
                    if dist < best_dist:
                        best_dist = dist
                        best_pair = (a, b)
            assert best_pair is not None
            a, b = best_pair
            edge_pairs.add(normalize_edge(a, b))
            connected.add(b)
            remaining.remove(b)

        for node in nodes:
            nearest = sorted(
                (other for other in nodes if other.id != node.id),
                key=lambda other: distance(node, other),
            )[:3]
            for other in nearest:
                if distance(node, other) < 355:
                    edge_pairs.add(normalize_edge(node.id, other.id))

        return [Edge(a, b, self.choose_terrain(nodes[a], nodes[b])) for a, b in sorted(edge_pairs)]

    def correct_forts(self, nodes: list[Node], edges: list[Edge]) -> None:
        degrees = {node.id: 0 for node in nodes}
        for edge in edges:
            degrees[edge.a] += 1
            degrees[edge.b] += 1
        for node in nodes:
            if node.site_type == FORT and degrees[node.id] < 2:
                node.site_type = TOWN
                self.apply_site_stats(node, node.owner)

    def choose_terrain(self, a: Node, b: Node) -> str:
        dy = abs(a.y - b.y)
        dist = distance(a, b)
        roll = self.rng.random()
        if dy > 210 or dist > 310:
            return MOUNTAIN if roll < 0.62 else FORD
        if roll < 0.16:
            return FORD
        if roll < 0.32:
            return MOUNTAIN
        return PLAINS
