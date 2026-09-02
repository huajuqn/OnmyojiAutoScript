# This Python file uses the following encoding: utf-8
"""将资源 JSON 中的识别/点击区域绘制到游戏截图上。

红框表示 ``roiFront``，绿框表示 ``roiBack``。该工具只读取截图和资源 JSON，
不会修改资源文件。

示例：
    python dev_tools/roi_overlay.py screenshot.png \
        --rule tasks/Restart/login/image.json \
        --rule tasks/Restart/login/ocr.json \
        --item user_center --item login_8 --item login_enter_game \
        --output login_roi.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


FRONT_COLOR = (0, 0, 255)  # red, BGR
BACK_COLOR = (0, 210, 0)  # green, BGR
TEXT_COLOR = (0, 255, 255)  # yellow, BGR


def parse_roi(value: str | list[int] | tuple[int, ...]) -> tuple[int, int, int, int]:
    """解析 JSON 中的 ``x,y,w,h`` 区域。"""
    if isinstance(value, str):
        values = [int(part.strip()) for part in value.split(',')]
    else:
        values = [int(part) for part in value]
    if len(values) != 4:
        raise ValueError(f'ROI must contain four integers, got: {value!r}')
    x, y, width, height = values
    if width <= 0 or height <= 0:
        raise ValueError(f'ROI width and height must be positive, got: {value!r}')
    return x, y, width, height


def load_image(path: Path) -> np.ndarray:
    """兼容 Windows 非 ASCII 路径读取图片。"""
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Cannot decode image: {path}')
    return image


def save_image(path: Path, image: np.ndarray) -> None:
    """兼容 Windows 非 ASCII 路径保存图片。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix or '.png'
    success, encoded = cv2.imencode(suffix, image)
    if not success:
        raise ValueError(f'Cannot encode image as {suffix}: {path}')
    encoded.tofile(path)


def load_rules(paths: list[Path]) -> list[dict]:
    rules = []
    for path in paths:
        with path.open('r', encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError(f'Rule JSON root must be a list: {path}')
        for item in data:
            rule = dict(item)
            rule['_source'] = str(path)
            rules.append(rule)
    return rules


def draw_roi(image: np.ndarray, roi: tuple[int, int, int, int], color: tuple[int, int, int],
             thickness: int) -> None:
    x, y, width, height = roi
    cv2.rectangle(image, (x, y), (x + width - 1, y + height - 1), color, thickness)


def draw_rules(image: np.ndarray, rules: list[dict]) -> np.ndarray:
    output = image.copy()
    for index, rule in enumerate(rules, start=1):
        front = parse_roi(rule['roiFront'])
        back = parse_roi(rule['roiBack'])
        draw_roi(output, back, BACK_COLOR, 3)
        draw_roi(output, front, FRONT_COLOR, 1)

        x = max(0, min(front[0], back[0]))
        y = max(18, min(front[1], back[1]) - 5)
        label = f"{index}:{rule.get('itemName', 'unnamed')}"
        cv2.putText(output, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(output, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                    TEXT_COLOR, 1, cv2.LINE_AA)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description='在截图上绘制资源 JSON 的 roiFront/roiBack。')
    parser.add_argument('image', type=Path, help='1280x720 游戏截图路径')
    parser.add_argument('--rule', action='append', required=True, type=Path,
                        help='资源 JSON 路径；可重复传入多个文件')
    parser.add_argument('--item', action='append', default=[],
                        help='只绘制指定 itemName；可重复传入，默认绘制全部')
    parser.add_argument('--output', type=Path, help='输出图片路径')
    args = parser.parse_args()

    image = load_image(args.image)
    rules = load_rules(args.rule)
    if args.item:
        requested = set(args.item)
        rules = [rule for rule in rules if rule.get('itemName') in requested]
        found = {rule.get('itemName') for rule in rules}
        missing = sorted(requested - found)
        if missing:
            raise ValueError(f"Unknown itemName: {', '.join(missing)}")
    if not rules:
        raise ValueError('No rules selected')

    output_path = args.output or args.image.with_name(f'{args.image.stem}_roi.png')
    save_image(output_path, draw_rules(image, rules))
    print(f'Wrote {output_path} ({len(rules)} rules, image={image.shape[1]}x{image.shape[0]})')


if __name__ == '__main__':
    main()
