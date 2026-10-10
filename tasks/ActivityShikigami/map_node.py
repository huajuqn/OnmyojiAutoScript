# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
"""磐长故地可攻略点的颜色、边缘和形状特征，不依赖怪物头像或战斗文字。"""
from functools import lru_cache

import cv2
import numpy as np

from module.atom.image import RuleImage


@lru_cache(maxsize=1)
def _diamond_kernels():
    result = []
    for radius in range(30, 45, 2):
        corners = np.array([(radius, 0), (2 * radius, radius),
                            (radius, 2 * radius), (0, radius)])
        sides = []
        for index in range(4):
            kernel = np.zeros((2 * radius + 1, 2 * radius + 1), np.float32)
            start, end = corners[index], corners[(index + 1) % 4]
            # 去掉顶角的光效，单独比较四条斜边，允许其中一条被人物遮挡。
            p1 = tuple(np.rint(start + (end - start) * 0.15).astype(int))
            p2 = tuple(np.rint(start + (end - start) * 0.85).astype(int))
            cv2.line(kernel, p1, p2, 1, 1)
            sides.append(kernel / kernel.sum())
        result.append((radius, sides))
    return result


def find_battle_nodes(image: np.ndarray) -> list[tuple[int, int, float]]:
    """返回中心坐标及边缘匹配分数，按分数排序；输入为设备 RGB 截图。"""
    if image.shape[:2] != (720, 1280):
        return []
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gold = cv2.inRange(hsv, (15, 45, 205), (45, 255, 255))
    highlight = cv2.inRange(hsv, (0, 0, 245), (179, 65, 255))
    color = cv2.dilate(gold | highlight, np.ones((3, 3), np.uint8))
    edges = cv2.Canny(gray, 60, 130)
    edges = cv2.dilate(edges & color, np.ones((3, 3), np.uint8)).astype(np.float32) / 255
    glow = cv2.inRange(hsv, (0, 0, 240), (179, 140, 255))
    glow = cv2.dilate(glow, np.ones((3, 3), np.uint8)).astype(np.float32) / 255

    best = np.zeros(image.shape[:2], np.float32)
    radii = np.zeros(image.shape[:2], np.int32)
    for radius, kernels in _diamond_kernels():
        sides = np.sort(np.array([cv2.filter2D(edges, -1, k) for k in kernels]), axis=0)
        score = sides[1:].mean(axis=0)
        score[sides[1] < 0.6] = 0
        # 在候选生成时就校验光带，防止无效中心抑制附近的真正点位。
        glow_sides = np.sort(np.array([cv2.filter2D(glow, -1, k) for k in kernels]), axis=0)
        score[glow_sides[2] < 0.3] = 0
        radii[score > best] = radius
        best = np.maximum(best, score)

    # 避开标题、左侧日常入口、右侧工具栏和底部战利品；边缘点通过平移露出。
    best[:180] = 0
    best[565:] = 0
    best[:, :290] = 0
    best[:, 1150:] = 0

    nodes = []
    for _ in range(40):
        _, score, _, (x, y) = cv2.minMaxLoc(best)
        if score < 0.8:
            break
        radius = int(radii[y, x])
        cv2.rectangle(best, (x - 40, y - 40), (x + 40, y + 40), 0, -1)
        # 地图底色也是红色：真正的进度条是窄而暗的横条，上下背景更亮。
        rows = gray[y + 28:y + 72, x - 25:x + 25].mean(axis=1)
        contrast = np.minimum(rows[:-16], rows[16:]) - rows[8:-8]
        valid = (contrast >= 10) & (rows[8:-8] < 100)
        valid[:4] = False
        if not np.any(valid):
            continue
        nodes.append((x, y, float(score)))
    return nodes


class BattleNode(RuleImage):
    """接入 GameUi 的 RuleImage 接口，点击识别到的框中心。"""
    def __init__(self):
        super().__init__(roi_front=(0, 0, 16, 16), roi_back=(290, 180, 860, 385),
                         threshold=0.8, method='Template matching',
                         file='./tasks/ActivityShikigami/as/as_battle_node.png')
        self.name = 'ACTIVITY_MAP_BATTLE_NODE'

    def match(self, image, threshold=None):
        nodes = find_battle_nodes(image)
        if not nodes:
            return False
        x, y, _ = nodes[0]
        self.roi_front = [x - 8, y - 8, 16, 16]
        return True


BATTLE_NODE = BattleNode()

# 相邻坐标代表平移一个屏幕步长。先左右，再逐行覆盖上下区域，最后回到起点附近。
SEARCH_ROUTE = ((0, 0), (-1, 0), (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0),
                (2, -1), (1, -1), (0, -1), (-1, -1), (-2, -1), (-2, 0),
                (-2, 1), (-1, 1), (0, 1), (1, 1), (2, 1), (2, 0), (1, 0), (0, 0))
