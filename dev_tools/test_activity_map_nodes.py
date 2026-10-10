"""不连接设备的活动地图回归测试：遮挡、无点位及四向搜索。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from module.exception import GameStuckError
from tasks.ActivityShikigami.map_node import find_battle_nodes
from tasks.ActivityShikigami.script_task import ScriptTask


def node_image(center=(600, 350), occluded=False, progress=True):
    image = np.full((720, 1280, 3), (130, 75, 50), np.uint8)
    x, y = center
    points = np.array([(x, y - 38), (x + 38, y), (x, y + 38), (x - 38, y)])
    cv2.polylines(image, [points], True, (255, 220, 100), 5)
    cv2.polylines(image, [points], True, (255, 255, 220), 2)
    if occluded:
        # 一整条上右斜边被人物遮住，剩余三边及进度条仍可识别。
        cv2.rectangle(image, (x + 4, y - 45), (x + 46, y - 2), (50, 50, 90), -1)
    if progress:
        cv2.rectangle(image, (x - 34, y + 43), (x + 34, y + 49), (130, 25, 25), -1)
        cv2.rectangle(image, (x - 30, y + 44), (x + 32, y + 48), (50, 30, 30), -1)
    return image


class SearchTask(ScriptTask):
    def __init__(self):
        self.moves = []
        self.entered = False
        self.device = SimpleNamespace(image=None, swipe=self.move, click=self.enter)

    def screenshot(self):
        pass

    def appear(self, target, **kwargs):
        return self.entered if target is self.I_FIRE_BUTTON else not self.entered

    def move(self, start, end, **kwargs):
        self.moves.append((end[0] - start[0], end[1] - start[1]))

    def enter(self, **kwargs):
        self.entered = True

    def wait_until_appear(self, *args, **kwargs):
        return self.entered


class MapNodesTest(unittest.TestCase):
    def test_single_node_and_refreshed_position(self):
        for center in [(480, 310), (900, 480)]:
            nodes = find_battle_nodes(node_image(center))
            self.assertTrue(any(abs(x - center[0]) < 12 and abs(y - center[1]) < 12
                                for x, y, _ in nodes), nodes)

    def test_occluded_edge_without_battle_text(self):
        self.assertTrue(find_battle_nodes(node_image(occluded=True)))

    def test_decoration_without_progress_is_rejected(self):
        self.assertFalse(find_battle_nodes(node_image(progress=False)))

    def test_empty_map_is_rejected(self):
        self.assertFalse(find_battle_nodes(np.zeros((720, 1280, 3), np.uint8)))

    def test_search_covers_four_directions_and_enters(self):
        task = SearchTask()
        with patch('tasks.ActivityShikigami.script_task.sleep'), \
                patch('tasks.ActivityShikigami.script_task.find_battle_nodes',
                      side_effect=lambda _: [(600, 350, 0.95)] if len(task.moves) >= 16 else []):
            self.assertTrue(task.search_climb_node())
        self.assertTrue(any(x > 0 for x, y in task.moves))
        self.assertTrue(any(x < 0 for x, y in task.moves))
        self.assertTrue(any(y > 0 for x, y in task.moves))
        self.assertTrue(any(y < 0 for x, y in task.moves))

    def test_no_nodes_stops_after_finite_route(self):
        task = SearchTask()
        with patch('tasks.ActivityShikigami.script_task.sleep'), \
                patch('tasks.ActivityShikigami.script_task.find_battle_nodes', return_value=[]):
            with self.assertRaises(GameStuckError):
                task.search_climb_node()
        self.assertEqual(len(task.moves), 20)
        self.assertFalse(task.entered)

    def test_failed_click_tries_another_candidate(self):
        task = SearchTask()
        task.device.click = lambda x, **kwargs: setattr(task, 'entered', x == 900)
        with patch('tasks.ActivityShikigami.script_task.sleep'), \
                patch('tasks.ActivityShikigami.script_task.find_battle_nodes',
                      return_value=[(600, 350, 0.95), (900, 400, 0.9)]):
            self.assertTrue(task.search_climb_node())
        self.assertFalse(task.moves)

    def test_unknown_page_never_swipes(self):
        task = SearchTask()
        task.appear = lambda *args, **kwargs: False
        with self.assertRaises(GameStuckError):
            task.search_climb_node()
        self.assertFalse(task.moves)


if __name__ == '__main__':
    unittest.main()
