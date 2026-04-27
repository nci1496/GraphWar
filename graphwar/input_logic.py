from __future__ import annotations

import pygame

from graphwar.constants import (
    CONVOY_FOOD,
    CONVOY_GOLD,
    INTENT_ATTACK,
    INTENT_LABELS,
    INTENT_MIGRATE,
    MAP_SIZE_PRESETS,
    PLAYER,
    RECRUIT_POLICIES,
)
from graphwar.helpers import is_recruitable, site_label
from graphwar.models import Mode


class InputLogicMixin:
    def handle_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.selected = None
            self.inspecting = None
            self.repair_mode = False
            self.convoy_mode = None
            self.convoy_route = []
        elif key == pygame.K_r:
            self.start_new_war()
        elif key == pygame.K_F2:
            self.developer_mode = not self.developer_mode
            state = "开启" if self.developer_mode else "关闭"
            self.message = f"开发者模式已{state}。点击据点可增加 50 兵力与 100 居民。"
        elif key == pygame.K_1:
            self.send_ratio = 0.35
        elif key == pygame.K_2:
            self.send_ratio = 0.5
        elif key == pygame.K_3:
            self.send_ratio = 0.75
        elif key == pygame.K_4:
            self.send_ratio = 1.0
        elif key == pygame.K_m:
            order = ["small", "medium", "large"]
            idx = order.index(self.map_size_mode) if self.map_size_mode in order else 0
            self.map_size_mode = order[(idx + 1) % len(order)]
            self.start_new_war()
            self.message = f"地图切换为：{MAP_SIZE_PRESETS[self.map_size_mode]['label']}"

    def handle_click(self, pos: tuple[int, int]) -> None:
        if self.mode in (Mode.VICTORY, Mode.DEFEAT):
            self.start_new_war()
            return
        if self.handle_button_click(pos):
            return

        clicked_node = self.node_at(pos)
        if clicked_node is None:
            self.selected = None
            self.inspecting = None
            self.repair_mode = False
            return

        if self.developer_mode:
            clicked_node.soldiers += 50
            clicked_node.population += 100
            clicked_node.max_population = max(clicked_node.max_population, clicked_node.population)
            self.message = f"开发者模式：{site_label(clicked_node)} 增加 50 兵力与 100 居民。"
            return

        if self.repair_mode:
            self.try_repair_road(clicked_node)
            return

        if self.convoy_mode is not None:
            if self.launch_convoy(clicked_node):
                self.selected = None
                self.inspecting = None
                self.convoy_mode = None
                self.convoy_route = []
            return

        if clicked_node.owner == PLAYER:
            if self.selected is not None and self.selected != clicked_node.id:
                if self.intent == INTENT_MIGRATE:
                    if self.launch_migration(self.selected, clicked_node.id):
                        self.selected = None
                        self.inspecting = None
                    return
                edge = self.edge_between(self.selected, clicked_node.id)
                if edge is not None and self.launch_troop(
                    self.selected,
                    clicked_node.id,
                    PLAYER,
                    edge=edge,
                    intent=INTENT_ATTACK,
                ):
                    self.selected = None
                    self.inspecting = None
                    return
            self.selected = clicked_node.id
            self.inspecting = None
            self.message = f"已选择 {site_label(clicked_node)}。"
            return

        if self.selected is None:
            self.inspecting = clicked_node.id
            self.message = f"正在查看：{site_label(clicked_node)}"
            return

        edge = self.edge_between(self.selected, clicked_node.id)
        if edge is None:
            self.inspecting = clicked_node.id
            self.message = f"{site_label(clicked_node)} 与当前选中据点不相邻，已切换为查看。"
            return
        if self.launch_troop(self.selected, clicked_node.id, PLAYER, edge=edge, intent=self.intent):
            self.selected = None
            self.inspecting = None

    def handle_button_click(self, pos: tuple[int, int]) -> bool:
        for ratio, rect in self.ratio_buttons():
            if rect.collidepoint(pos):
                self.send_ratio = ratio
                return True

        for mode, rect in self.map_size_buttons():
            if rect.collidepoint(pos):
                if self.map_size_mode != mode:
                    self.map_size_mode = mode
                    self.start_new_war()
                    self.message = f"地图切换为：{MAP_SIZE_PRESETS[self.map_size_mode]['label']}"
                return True

        for intent, rect in self.intent_buttons():
            if rect.collidepoint(pos):
                self.intent = intent
                self.repair_mode = False
                self.convoy_mode = None
                self.convoy_route = []
                self.message = f"行军目的切换为：{INTENT_LABELS[intent]}"
                return True

        for key, rect in self.auto_fund_buttons():
            if rect.collidepoint(pos):
                if key == "neighbors":
                    self.auto_fund_neighbors = not self.auto_fund_neighbors
                    state = "开启" if self.auto_fund_neighbors else "关闭"
                    self.message = f"自动调款（全局）已{state}。"
                else:
                    self.auto_fund_capital = not self.auto_fund_capital
                    state = "开启" if self.auto_fund_capital else "关闭"
                    self.message = f"自动调款（都城）已{state}。"
                return True

        for key, rect in self.auto_supply_buttons():
            if rect.collidepoint(pos):
                if key == "neighbors":
                    self.auto_supply_neighbors = not self.auto_supply_neighbors
                    state = "开启" if self.auto_supply_neighbors else "关闭"
                    self.message = f"自动调粮（全局）已{state}。"
                else:
                    self.auto_supply_capital = not self.auto_supply_capital
                    state = "开启" if self.auto_supply_capital else "关闭"
                    self.message = f"自动调粮（都城）已{state}。"
                return True

        for key, rect in self.auto_supply_low_buttons():
            if not rect.collidepoint(pos):
                continue
            if key == "lt90":
                self.auto_supply_low_enabled_90 = not self.auto_supply_low_enabled_90
                state = "开启" if self.auto_supply_low_enabled_90 else "关闭"
                self.message = f"低粮<90 自动调粮已{state}。"
            elif key == "lt200":
                self.auto_supply_low_enabled_200 = not self.auto_supply_low_enabled_200
                state = "开启" if self.auto_supply_low_enabled_200 else "关闭"
                self.message = f"低粮<200 自动调粮已{state}。"
            else:
                self.auto_supply_low_enabled_military_half = not self.auto_supply_low_enabled_military_half
                state = "开启" if self.auto_supply_low_enabled_military_half else "关闭"
                self.message = f"军事线<1/2 自动调粮已{state}。"
            return True

        for action, rect in self.emperor_buttons():
            if not rect.collidepoint(pos):
                continue
            if action == "emperor_tour":
                if self.selected is None:
                    self.message = "皇帝出巡失败：请先选中我方据点。"
                    return True
                node = self.nodes[self.selected]
                if node.owner != PLAYER:
                    self.message = "皇帝出巡失败：请先选中我方据点。"
                    return True
                self.command_player_emperor_tour(node.id)
                return True
            if action == "emperor_return":
                self.command_player_emperor_return()
                return True

        if self.selected is None:
            return False
        node = self.nodes[self.selected]
        if node.owner != PLAYER:
            return False

        for policy, rect in self.policy_buttons():
            if rect.collidepoint(pos):
                if not is_recruitable(node):
                    self.message = "此据点不能征兵。"
                    return True
                node.recruit_policy = policy
                self.message = f"{site_label(node)} 征兵调整为：{RECRUIT_POLICIES[policy]['label']}"
                return True

        for action, rect in self.action_buttons():
            if not rect.collidepoint(pos):
                continue
            if action == "fortify":
                self.fortify_selected()
            elif action == "repair_wall":
                self.repair_wall_selected()
            elif action == "repair":
                self.repair_mode = True
                self.convoy_mode = None
                self.convoy_route = []
                self.message = "修路模式：点击相邻据点升级道路。"
            elif action == "upgrade_econ":
                self.upgrade_selected("economy")
            elif action == "upgrade_mil":
                self.upgrade_selected("military")
            elif action == "repair_ruin":
                self.repair_ruin_selected()
            elif action == "send_food":
                self.convoy_mode = CONVOY_FOOD
                self.repair_mode = False
                self.convoy_route = [node.id]
                self.message = "运粮模式：依次点选节点规划路径，再点终点发车。"
            elif action == "send_gold":
                self.convoy_mode = CONVOY_GOLD
                self.repair_mode = False
                self.convoy_route = [node.id]
                self.message = "运钱模式：依次点选节点规划路径，再点终点发车。"
            elif action == "destroy":
                self.destroy_selected_stock()
            elif action == "demobilize":
                self.demobilize_selected()
            elif action == "emperor_tour":
                self.command_player_emperor_tour(node.id)
            elif action == "emperor_return":
                self.command_player_emperor_return()
            return True
        return False
