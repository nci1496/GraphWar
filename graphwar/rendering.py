from __future__ import annotations

import math

import pygame

from graphwar.constants import (
    COLORS,
    CONVOY_FOOD,
    CONVOY_GOLD,
    ENEMY,
    FORD,
    FORTIFY_COST,
    HEIGHT,
    INTENT_LABELS,
    INTENT_MIGRATE,
    INTENT_OCCUPY,
    INTENT_ATTACK,
    INTENT_SACK,
    LEFT_PANEL,
    LOW_FOOD_AUTO_SUPPLY_THRESHOLD,
    LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH,
    MAP_LEFT,
    MAP_RIGHT,
    MAP_SIZE_PRESETS,
    MAX_ROAD_LEVEL,
    MOUNTAIN,
    NEUTRAL,
    PLAYER,
    POLICY_HIGH,
    POLICY_LOW,
    POLICY_NORMAL,
    POLICY_STOP,
    REBEL,
    REBEL_RUIN_REPAIR_COST,
    RECRUIT_POLICIES,
    REPAIR_COST,
    ROAD_COST,
    SIDE_PANEL,
    SITE_STATS,
    TERRAIN_STATS,
    TOP_BAR,
    WIDTH,
)
from graphwar.helpers import development_name, distance_xy, lerp, normalize_edge, owner_label, site_label


class RenderingMixin:
    def draw(self) -> None:
        self.screen.fill(COLORS["bg"])
        self.draw_map_background()
        self.draw_top_bar()
        self.draw_edges()
        self.draw_convoys()
        self.draw_emperors()
        self.draw_troops()
        self.draw_nodes()
        self.draw_left_panel()
        self.draw_right_panel()
        if self.mode.value == "victory":
            self.draw_victory_overlay()
        elif self.mode.value == "defeat":
            self.draw_defeat_overlay()
        pygame.display.flip()

    def draw_map_background(self) -> None:
        pygame.draw.rect(self.screen, COLORS["map"], (MAP_LEFT, TOP_BAR, MAP_RIGHT - MAP_LEFT, HEIGHT - TOP_BAR))
        for y in range(TOP_BAR + 35, HEIGHT, 58):
            pygame.draw.line(self.screen, (151, 107, 60), (MAP_LEFT, y), (MAP_RIGHT, y), 1)
        for x in range(MAP_LEFT + 38, MAP_RIGHT, 76):
            pygame.draw.line(self.screen, (151, 107, 60), (x, TOP_BAR), (x, HEIGHT), 1)
        pygame.draw.rect(self.screen, (75, 45, 24), (MAP_LEFT + 10, TOP_BAR + 10, MAP_RIGHT - MAP_LEFT - 20, HEIGHT - TOP_BAR - 20), 3)

    def draw_top_bar(self) -> None:
        pygame.draw.rect(self.screen, COLORS["panel"], (0, 0, WIDTH, TOP_BAR))
        player_count = sum(1 for n in self.nodes if n.owner == PLAYER)
        enemy_count = sum(1 for n in self.nodes if n.owner == ENEMY)
        neutral_count = sum(1 for n in self.nodes if n.owner == NEUTRAL)
        rebel_count = sum(1 for n in self.nodes if n.owner == REBEL)
        warning_count = sum(1 for n in self.nodes if n.rebel_warning)
        capital = self.player_capital()
        emperor_text = self.player_emperor_status_text()
        capital_text = "都城失守"
        if capital is not None:
            capital_text = f"都城 粮{int(capital.food)} 金{int(capital.gold)}/{int(capital.max_gold)}"
        text = (
            f"诸侯征战 | {capital_text} | 汉{player_count} 敌{enemy_count} 中立{neutral_count} 黄巾{rebel_count} 预警{warning_count} | "
            f"兵团{len(self.troops)} 运输{len(self.convoys)} | 地图{MAP_SIZE_PRESETS[self.map_size_mode]['label']} | "
            f"行军{INTENT_LABELS[self.intent]} 比例{int(self.send_ratio * 100)}% | 皇帝{emperor_text}"
        )
        self.draw_text(text, 18, 11, COLORS["text"])
        self.draw_text(self.message, 18, 42, COLORS["muted"])

    def draw_edges(self) -> None:
        selected_neighbors = set(self.neighbor_ids(self.selected)) if self.selected is not None else set()
        for edge in self.edges:
            a = self.nodes[edge.a]
            b = self.nodes[edge.b]
            terrain = TERRAIN_STATS[edge.terrain]
            active = self.selected in (edge.a, edge.b) or a.id in selected_neighbors or b.id in selected_neighbors
            road_colors = [(105, 76, 42), (139, 99, 50), (178, 127, 59), (220, 166, 82)]
            color = COLORS["line_active"] if active else road_colors[min(edge.road_level, MAX_ROAD_LEVEL)]
            width = int(terrain["width"]) + edge.road_level * 2 + (2 if active else 0)
            pygame.draw.line(self.screen, color, (a.x, a.y), (b.x, b.y), width)
            self.draw_terrain_icon(a, b, edge.terrain, color)

    def draw_terrain_icon(self, a, b, terrain: str, color: tuple[int, int, int]) -> None:
        mx = round((a.x + b.x) / 2)
        my = round((a.y + b.y) / 2)
        if terrain == MOUNTAIN:
            points = [(mx - 12, my + 8), (mx - 3, my - 8), (mx + 5, my + 8)]
            points2 = [(mx - 2, my + 8), (mx + 8, my - 5), (mx + 16, my + 8)]
            pygame.draw.lines(self.screen, COLORS["black"], False, points, 3)
            pygame.draw.lines(self.screen, COLORS["black"], False, points2, 3)
        elif terrain == FORD:
            for offset in (-6, 2):
                pygame.draw.arc(self.screen, (60, 91, 100), pygame.Rect(mx - 16, my + offset, 16, 10), 0, math.pi, 2)
                pygame.draw.arc(self.screen, (60, 91, 100), pygame.Rect(mx, my + offset, 16, 10), 0, math.pi, 2)
        else:
            pygame.draw.circle(self.screen, color, (mx - 5, my), 3)
            pygame.draw.circle(self.screen, color, (mx + 5, my + 4), 2)

    def draw_nodes(self) -> None:
        focus_id = self.selected if self.selected is not None else self.inspecting
        emperor_marks: dict[int, str] = {}
        for owner, emperor in self.emperors.items():
            if emperor.alive and emperor.current_node >= 0 and emperor.current_node < len(self.nodes):
                emperor_marks[emperor.current_node] = owner
        for node in self.nodes:
            color = COLORS["rebel_warning"] if node.rebel_warning else COLORS[node.owner]
            pos = (round(node.x), round(node.y))
            radius = int(SITE_STATS[node.site_type]["radius"]) + (4 if node.id == focus_id else 0)
            pygame.draw.circle(self.screen, COLORS["black"], pos, radius + 5)
            pygame.draw.circle(self.screen, color, pos, radius)
            pygame.draw.circle(self.screen, COLORS["gold"], pos, radius + 5, max(1, node.defense // 2))
            if node.is_ruin:
                pygame.draw.line(self.screen, COLORS["bad"], (pos[0] - radius, pos[1] - radius), (pos[0] + radius, pos[1] + radius), 3)
                pygame.draw.line(self.screen, COLORS["bad"], (pos[0] + radius, pos[1] - radius), (pos[0] - radius, pos[1] + radius), 3)
            self.draw_centered_text(str(int(node.soldiers)), pygame.Rect(node.x - 30, node.y - 15, 60, 22), COLORS["white"], self.font)
            node_text = node.display_name if node.display_name else development_name(node)
            self.draw_centered_text(node_text, pygame.Rect(node.x - 42, node.y + radius + 2, 84, 18), COLORS["muted"], self.small_font)
            if node.max_population > 0:
                self.draw_centered_text(f"民{int(node.morale)}", pygame.Rect(node.x - 25, node.y - radius - 22, 50, 18), COLORS["gold"], self.small_font)
            if node.rebel_warning:
                self.draw_centered_text(f"{int(node.rebel_warning_timer)}", pygame.Rect(node.x - 20, node.y + 10, 40, 18), COLORS["black"], self.small_font)
            emperor_owner = emperor_marks.get(node.id)
            if emperor_owner is not None:
                marker_center = (pos[0] + radius - 4, pos[1] - radius + 4)
                pygame.draw.circle(self.screen, COLORS["white"], marker_center, 10)
                pygame.draw.circle(self.screen, COLORS[emperor_owner], marker_center, 8)
                self.draw_centered_text("帝", pygame.Rect(marker_center[0] - 8, marker_center[1] - 8, 16, 16), COLORS["black"], self.small_font)

    def draw_emperors(self) -> None:
        for owner, emperor in self.emperors.items():
            if not emperor.alive:
                continue
            if emperor.current_node >= 0:
                continue
            if len(emperor.route) < 2 or emperor.route_index >= len(emperor.route) - 1:
                continue
            a = emperor.route[emperor.route_index]
            b = emperor.route[emperor.route_index + 1]
            if a < 0 or b < 0 or a >= len(self.nodes) or b >= len(self.nodes):
                continue
            src = self.nodes[a]
            dst = self.nodes[b]
            x = lerp(src.x, dst.x, emperor.progress)
            y = lerp(src.y, dst.y, emperor.progress)
            pos = (round(x), round(y))
            pygame.draw.circle(self.screen, COLORS["white"], pos, 11)
            pygame.draw.circle(self.screen, COLORS[owner], pos, 9)
            pygame.draw.circle(self.screen, COLORS["black"], pos, 9, 1)
            self.draw_centered_text("帝", pygame.Rect(x - 8, y - 8, 16, 16), COLORS["black"], self.small_font)

    def draw_troops(self) -> None:
        for troop in self.troops:
            if troop.depart_delay > 0:
                continue
            source = self.nodes[troop.source]
            target = self.nodes[troop.target]
            x = lerp(source.x, target.x, troop.progress)
            y = lerp(source.y, target.y, troop.progress)
            color = COLORS["green"] if troop.intent == INTENT_MIGRATE else COLORS[troop.owner]
            pygame.draw.circle(self.screen, color, (round(x), round(y)), 9)
            pygame.draw.circle(self.screen, COLORS["black"], (round(x), round(y)), 9, 2)
            label = str(int(troop.migrants)) if troop.intent == INTENT_MIGRATE else str(int(troop.amount))
            self.draw_centered_text(label, pygame.Rect(x - 28, y - 29, 56, 18), COLORS["text"], self.small_font)

    def draw_convoys(self) -> None:
        for convoy in self.convoys:
            source = self.nodes[convoy.source]
            target = self.nodes[convoy.target]
            x = lerp(source.x, target.x, convoy.progress)
            y = lerp(source.y, target.y, convoy.progress)
            color = COLORS["gold"] if convoy.cargo == CONVOY_GOLD else COLORS["green"]
            rect = pygame.Rect(round(x) - 8, round(y) - 8, 16, 16)
            pygame.draw.rect(self.screen, color, rect, border_radius=3)
            pygame.draw.rect(self.screen, COLORS["black"], rect, 2, border_radius=3)

    def draw_left_panel(self) -> None:
        rect = pygame.Rect(0, TOP_BAR, LEFT_PANEL, HEIGHT - TOP_BAR)
        pygame.draw.rect(self.screen, COLORS["panel"], rect)
        pygame.draw.line(self.screen, COLORS["black"], (LEFT_PANEL, TOP_BAR), (LEFT_PANEL, HEIGHT), 3)
        x = 16
        y = TOP_BAR + 16
        self.draw_text("全局控制", x, y, COLORS["text"], self.mid_font)

        y += 34
        self.draw_text("出兵比例", x, y, COLORS["muted"])
        for ratio, rect in self.ratio_buttons():
            color = COLORS["line_active"] if self.send_ratio == ratio else COLORS["panel_hover"]
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, COLORS["muted"], rect, 1, border_radius=6)
            self.draw_centered_text(f"{int(ratio * 100)}%", rect, COLORS["text"], self.small_font)

        y += 72
        self.draw_text("地图规模", x, y, COLORS["muted"])
        for mode, rect in self.map_size_buttons():
            active = self.map_size_mode == mode
            color = COLORS["line_active"] if active else COLORS["panel_hover"]
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, COLORS["muted"], rect, 1, border_radius=6)
            self.draw_centered_text(MAP_SIZE_PRESETS[mode]["label"], rect, COLORS["text"], self.small_font)

        y += 74
        self.draw_text("自动调款", x, y, COLORS["muted"])
        for key, button in self.auto_fund_buttons():
            enabled = self.auto_fund_neighbors if key == "neighbors" else self.auto_fund_capital
            self.draw_toggle_button(button, "全局" if key == "neighbors" else "都城", enabled)

        y += 40
        self.draw_text("自动调粮", x, y, COLORS["muted"])
        for key, button in self.auto_supply_buttons():
            enabled = self.auto_supply_neighbors if key == "neighbors" else self.auto_supply_capital
            self.draw_toggle_button(button, "全局" if key == "neighbors" else "都城", enabled)

        y += 40
        self.draw_text("低粮补给", x, y, COLORS["muted"])
        for key, button in self.auto_supply_low_buttons():
            if key == "lt90":
                label = f"<{int(LOW_FOOD_AUTO_SUPPLY_THRESHOLD)}"
                enabled = self.auto_supply_low_enabled_90
            elif key == "lt200":
                label = f"<{int(LOW_FOOD_AUTO_SUPPLY_THRESHOLD_HIGH)}"
                enabled = self.auto_supply_low_enabled_200
            else:
                label = "军事<1/2"
                enabled = self.auto_supply_low_enabled_military_half
            self.draw_toggle_button(button, label, enabled)

    def _wrapped_line_count(self, text: str, max_width: int, font: pygame.font.Font | None = None) -> int:
        draw_font = font or self.font
        line = ""
        lines = 0
        for char in text:
            candidate = line + char
            if draw_font.size(candidate)[0] <= max_width:
                line = candidate
            else:
                lines += 1
                line = char
        if line:
            lines += 1
        return max(1, lines)

    def draw_right_panel(self) -> None:
        rect = pygame.Rect(MAP_RIGHT, TOP_BAR, SIDE_PANEL, HEIGHT - TOP_BAR)
        pygame.draw.rect(self.screen, COLORS["panel"], rect)
        pygame.draw.line(self.screen, COLORS["black"], (MAP_RIGHT, TOP_BAR), (MAP_RIGHT, HEIGHT), 3)
        x = MAP_RIGHT + 18
        y = TOP_BAR + 18
        self.draw_text("治理与军务", x, y, COLORS["text"], self.mid_font)
        y += 38
        self.draw_text("行军目的", x, y, COLORS["muted"])
        for intent, button in self.intent_buttons():
            color = COLORS["line_active"] if self.intent == intent else COLORS["panel_hover"]
            pygame.draw.rect(self.screen, color, button, border_radius=6)
            pygame.draw.rect(self.screen, COLORS["muted"], button, 1, border_radius=6)
            self.draw_centered_text(INTENT_LABELS[intent], button, COLORS["text"], self.small_font)

        for action, button in self.emperor_buttons():
            pygame.draw.rect(self.screen, COLORS["panel_hover"], button, border_radius=6)
            pygame.draw.rect(self.screen, COLORS["muted"], button, 1, border_radius=6)
            label = "皇帝出巡" if action == "emperor_tour" else "皇帝回都"
            self.draw_centered_text(label, button, COLORS["text"], self.small_font)
        self.draw_text(f"皇帝状态：{self.player_emperor_status_text()}", x, TOP_BAR + 204, COLORS["muted"], self.small_font)
        info_y = TOP_BAR + 230
        if self.convoy_mode is not None and self.convoy_route:
            route_text = "->".join(str(node_id) for node_id in self.convoy_route)
            route_y = TOP_BAR + 148
            self.draw_text("运输路线", x, route_y, COLORS["muted"])
            self.draw_wrapped(route_text, x, route_y + 22, SIDE_PANEL - 36, COLORS["text"])
            lines = self._wrapped_line_count(route_text, SIDE_PANEL - 36, self.font)
            info_y = max(info_y, route_y + 22 + lines * 25 + 14)

        selected_player = self.selected is not None and self.nodes[self.selected].owner == PLAYER
        info_node_id = self.selected if selected_player else self.inspecting
        if info_node_id is None:
            self.draw_wrapped("点击我方据点可操作；点击敌方/中立/黄巾据点可查看详情。", x, info_y, SIDE_PANEL - 36, COLORS["muted"])
            self._right_policy_y = TOP_BAR + 470
            self._right_action_y = TOP_BAR + 520
            return

        node = self.nodes[info_node_id]
        self.draw_text(site_label(node), x, info_y, COLORS["gold"], self.mid_font)
        y = info_y + 32
        lines = [
            f"归属：{owner_label(node.owner)}",
            f"兵力：{int(node.soldiers)}    城防：{node.defense}/{node.max_defense}",
            f"屯兵上限：{int(self.garrison_limit(node))}",
            f"居民：{int(node.population)} / {int(node.max_population)}",
            f"民心：{int(node.morale)}    金：{int(node.gold)}/{int(node.max_gold)}",
            f"粮：{int(node.food)}/{int(node.max_food)}",
            f"发展：{development_name(node)}",
        ]
        if node.max_population <= 0:
            lines[3] = "居民：无"
            lines[4] = f"民心：无    金：{int(node.gold)}/{int(node.max_gold)}"
        if node.rebel_warning:
            lines.append(f"黄巾预警：{int(node.rebel_warning_timer)} 秒")
        if selected_player:
            lines.append(f"征兵：{RECRUIT_POLICIES[node.recruit_policy]['label']}")
            if node.is_ruin:
                lines.append(f"废墟修复：{REBEL_RUIN_REPAIR_COST} 金")
        for line in lines:
            self.draw_text(line, x, y, COLORS["text"])
            y += 24

        if self.pending_action is not None and int(self.pending_action.get("node_id", -1)) == node.id:
            action = str(self.pending_action.get("action", ""))
            pending_text = "待执行：到款后自动执行" if action != "launch_troop" else "待执行：到粮后自动发兵"
            self.draw_text(pending_text, x, y + 2, COLORS["gold"], self.small_font)
            y += 22

        if not selected_player:
            self.draw_text("当前为查看模式（不可操作）", x, y + 8, COLORS["muted"], self.small_font)
            self._right_policy_y = TOP_BAR + 470
            self._right_action_y = TOP_BAR + 520
            return

        policy_y = max(TOP_BAR + 468, y + 16)
        policy_y = min(policy_y, HEIGHT - 198)
        action_y = policy_y + 50
        self._right_policy_y = policy_y
        self._right_action_y = action_y

        self.draw_text("征兵档位", x, policy_y - 22, COLORS["muted"])
        for policy, button in self.policy_buttons():
            color = COLORS["line_active"] if node.recruit_policy == policy else COLORS["panel_hover"]
            pygame.draw.rect(self.screen, color, button, border_radius=6)
            pygame.draw.rect(self.screen, COLORS["muted"], button, 1, border_radius=6)
            self.draw_centered_text(RECRUIT_POLICIES[policy]["label"], button, COLORS["text"], self.small_font)

        for action, button in self.action_buttons():
            active = (
                (action == "repair" and self.repair_mode)
                or (action == "send_food" and self.convoy_mode == CONVOY_FOOD)
                or (action == "send_gold" and self.convoy_mode == CONVOY_GOLD)
            )
            color = COLORS["line_active"] if active else COLORS["panel_hover"]
            pygame.draw.rect(self.screen, color, button, border_radius=6)
            pygame.draw.rect(self.screen, COLORS["muted"], button, 1, border_radius=6)
            labels = {
                "fortify": f"加固{FORTIFY_COST}",
                "repair_wall": f"维修{REPAIR_COST}",
                "repair": f"修路{ROAD_COST}",
                "upgrade_econ": "经济升级",
                "upgrade_mil": "军事升级",
                "repair_ruin": "修复废墟",
                "send_food": "运粮",
                "send_gold": "运钱",
                "destroy": "销毁库存",
                "demobilize": "转民",
            }
            self.draw_centered_text(labels[action], button, COLORS["text"], self.small_font)

    def draw_toggle_button(self, button: pygame.Rect, label: str, enabled: bool) -> None:
        pygame.draw.rect(self.screen, COLORS["panel_hover"], button, border_radius=6)
        pygame.draw.rect(self.screen, COLORS["muted"], button, 1, border_radius=6)
        box = pygame.Rect(button.x + 6, button.y + 6, 16, 16)
        pygame.draw.rect(self.screen, COLORS["black"], box, border_radius=3)
        if enabled:
            pygame.draw.rect(self.screen, COLORS["line_active"], box.inflate(-4, -4), border_radius=2)
        self.draw_text(label, button.x + 28, button.y + 5, COLORS["text"], self.small_font)

    def draw_victory_overlay(self) -> None:
        self.draw_overlay_base("统一天下", "点击任意位置或按 R 开启新战局。")

    def draw_defeat_overlay(self) -> None:
        self.draw_overlay_base("兵败", "点击任意位置或按 R 重新开始。")

    def draw_overlay_base(self, title: str, subtitle: str) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 155))
        self.screen.blit(shade, (0, 0))
        self.draw_centered_text(title, pygame.Rect(MAP_LEFT, 170, MAP_RIGHT - MAP_LEFT, 64), COLORS["text"], self.big_font)
        self.draw_centered_text(subtitle, pygame.Rect(MAP_LEFT, 230, MAP_RIGHT - MAP_LEFT, 38), COLORS["muted"], self.mid_font)

    def ratio_buttons(self) -> list[tuple[float, pygame.Rect]]:
        return [
            (0.35, pygame.Rect(16, TOP_BAR + 48, 52, 28)),
            (0.50, pygame.Rect(74, TOP_BAR + 48, 52, 28)),
            (0.75, pygame.Rect(132, TOP_BAR + 48, 52, 28)),
            (1.00, pygame.Rect(190, TOP_BAR + 48, 52, 28)),
        ]

    def map_size_buttons(self) -> list[tuple[str, pygame.Rect]]:
        return [
            ("small", pygame.Rect(16, TOP_BAR + 120, 72, 28)),
            ("medium", pygame.Rect(92, TOP_BAR + 120, 72, 28)),
            ("large", pygame.Rect(168, TOP_BAR + 120, 72, 28)),
        ]

    def intent_buttons(self) -> list[tuple[str, pygame.Rect]]:
        x = MAP_RIGHT + 18
        y = TOP_BAR + 112
        w = 60
        h = 30
        gap = 8
        return [
            (INTENT_OCCUPY, pygame.Rect(x, y, w, h)),
            (INTENT_ATTACK, pygame.Rect(x + (w + gap), y, w, h)),
            (INTENT_SACK, pygame.Rect(x + (w + gap) * 2, y, w, h)),
            (INTENT_MIGRATE, pygame.Rect(x + (w + gap) * 3, y, w, h)),
        ]

    def emperor_buttons(self) -> list[tuple[str, pygame.Rect]]:
        x = MAP_RIGHT + 18
        y = TOP_BAR + 152
        return [
            ("emperor_tour", pygame.Rect(x, y, 126, 30)),
            ("emperor_return", pygame.Rect(x + 136, y, 126, 30)),
        ]

    def auto_fund_buttons(self) -> list[tuple[str, pygame.Rect]]:
        x = 16
        y = TOP_BAR + 206
        return [("neighbors", pygame.Rect(x, y, 112, 28)), ("capital", pygame.Rect(x + 120, y, 112, 28))]

    def auto_supply_buttons(self) -> list[tuple[str, pygame.Rect]]:
        x = 16
        y = TOP_BAR + 244
        return [("neighbors", pygame.Rect(x, y, 112, 28)), ("capital", pygame.Rect(x + 120, y, 112, 28))]

    def auto_supply_low_buttons(self) -> list[tuple[str, pygame.Rect]]:
        x = 16
        y = TOP_BAR + 284
        return [
            ("lt90", pygame.Rect(x, y, 72, 28)),
            ("lt200", pygame.Rect(x + 78, y, 72, 28)),
            ("mil_half", pygame.Rect(x + 156, y, 86, 28)),
        ]

    def policy_buttons(self) -> list[tuple[str, pygame.Rect]]:
        x = MAP_RIGHT + 18
        y = int(getattr(self, "_right_policy_y", TOP_BAR + 470))
        w = 60
        h = 30
        gap = 8
        return [
            (POLICY_STOP, pygame.Rect(x, y, w, h)),
            (POLICY_LOW, pygame.Rect(x + (w + gap), y, w, h)),
            (POLICY_NORMAL, pygame.Rect(x + (w + gap) * 2, y, w, h)),
            (POLICY_HIGH, pygame.Rect(x + (w + gap) * 3, y, w, h)),
        ]

    def action_buttons(self) -> list[tuple[str, pygame.Rect]]:
        x = MAP_RIGHT + 18
        y = int(getattr(self, "_right_action_y", TOP_BAR + 520))
        return [
            ("fortify", pygame.Rect(x, y, 82, 30)),
            ("repair_wall", pygame.Rect(x + 90, y, 82, 30)),
            ("repair", pygame.Rect(x + 180, y, 82, 30)),
            ("upgrade_econ", pygame.Rect(x, y + 38, 126, 30)),
            ("upgrade_mil", pygame.Rect(x + 136, y + 38, 126, 30)),
            ("repair_ruin", pygame.Rect(x, y + 76, 126, 30)),
            ("send_food", pygame.Rect(x + 136, y + 76, 62, 30)),
            ("send_gold", pygame.Rect(x + 202, y + 76, 60, 30)),
            ("destroy", pygame.Rect(x, y + 114, 82, 30)),
            ("demobilize", pygame.Rect(x + 90, y + 114, 172, 30)),
        ]

    def node_at(self, pos: tuple[int, int]):
        px, py = pos
        if px >= MAP_RIGHT or px <= MAP_LEFT:
            return None
        for node in sorted(self.nodes, key=lambda n: distance_xy(px, py, n.x, n.y)):
            radius = int(SITE_STATS[node.site_type]["radius"])
            if distance_xy(px, py, node.x, node.y) <= radius + 9:
                return node
        return None

    def edge_between(self, a: int, b: int):
        normalized = normalize_edge(a, b)
        for edge in self.edges:
            if normalize_edge(edge.a, edge.b) == normalized:
                return edge
        return None

    def neighbor_ids(self, node_id: int | None) -> list[int]:
        if node_id is None:
            return []
        neighbors = []
        for edge in self.edges:
            if edge.a == node_id:
                neighbors.append(edge.b)
            elif edge.b == node_id:
                neighbors.append(edge.a)
        return neighbors

    def draw_text(self, text: str, x: float, y: float, color: tuple[int, int, int], font: pygame.font.Font | None = None) -> None:
        surface = (font or self.font).render(text, True, color)
        self.screen.blit(surface, (x, y))

    def draw_centered_text(self, text: str, rect: pygame.Rect, color: tuple[int, int, int], font: pygame.font.Font | None = None) -> None:
        surface = (font or self.font).render(text, True, color)
        self.screen.blit(surface, surface.get_rect(center=rect.center))

    def draw_wrapped(self, text: str, x: int, y: int, max_width: int, color: tuple[int, int, int]) -> None:
        line = ""
        for char in text:
            candidate = line + char
            if self.font.size(candidate)[0] <= max_width:
                line = candidate
            else:
                self.draw_text(line, x, y, color)
                y += 25
                line = char
        if line:
            self.draw_text(line, x, y, color)
