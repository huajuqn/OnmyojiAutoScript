"""庭院入口导航回归：可见但冷却、列表刷新、同帧坐标与页面识别。"""
import unittest
from types import SimpleNamespace

import numpy as np

from module.base.timer import Timer
from tasks.ActivityShikigami.script_task import ScriptTask
from tasks.ActivityShikigami.page import page_main
from tasks.Component.RightActivity.assets import RightActivityAssets


class EntryTask(ScriptTask):
    def __init__(self, visible=True, position=(1186, 225)):
        self.interval_timer = {}
        self.clicks = []
        self.screenshots = 0
        self.frame = np.zeros((720, 1280, 3), np.uint8)
        self.device = SimpleNamespace(image=self.frame, click=self.record_click)
        self.buttons = [self.I_SHI, RightActivityAssets.I_TOGGLE_BUTTON]
        toggle = self.buttons[1]
        self.frame[527:527 + toggle.image.shape[0], 1193:1193 + toggle.image.shape[1]] = toggle.image
        if visible:
            x, y = position
            h, w = self.I_SHI.image.shape[:2]
            self.frame[y:y + h, x:x + w] = self.I_SHI.image

    def record_click(self, x, y, control_name=None):
        self.clicks.append((control_name, x, y))

    def screenshot(self):
        self.screenshots += 1
        self.device.image = self.frame


class EntryNavigationTest(unittest.TestCase):
    def test_visible_entry_on_cooldown_never_refreshes(self):
        task = EntryTask()
        task.interval_timer[task.I_SHI.name] = Timer(0.8).reset()
        self.assertFalse(task._operate_entry_buttons(task.buttons))
        self.assertEqual(task.clicks, [])
        task.interval_timer[task.I_SHI.name].clear()
        self.assertTrue(task._operate_entry_buttons(task.buttons))
        self.assertEqual([c[0] for c in task.clicks], [task.I_SHI.name])

    def test_visible_entry_clicked_without_refresh_or_extra_screenshot(self):
        task = EntryTask()
        self.assertTrue(task._operate_entry_buttons(task.buttons))
        self.assertEqual(task.screenshots, 1)
        self.assertEqual([c[0] for c in task.clicks], [task.I_SHI.name])

    def test_missing_entry_refreshes_then_relocates_next_frame(self):
        task = EntryTask(visible=False)
        self.assertFalse(task._operate_entry_buttons(task.buttons))
        self.assertEqual([c[0] for c in task.clicks], [task.buttons[1].name])
        task.frame = EntryTask(position=(1170, 310)).frame
        self.assertTrue(task._operate_entry_buttons(task.buttons))
        self.assertEqual([c[0] for c in task.clicks], [task.buttons[1].name, task.I_SHI.name])
        _, x, y = task.clicks[-1]
        self.assertTrue(1170 <= x <= 1203 and 310 <= y <= 341)

    def test_page_recognition_does_not_consume_entry_click_interval(self):
        task = EntryTask()
        self.assertTrue(task.ui_page_appear(page_main, interval=0.8))
        self.assertNotIn(task.I_SHI.name, task.interval_timer)
        self.assertTrue(task._operate_entry_buttons(task.buttons))
        self.assertEqual([c[0] for c in task.clicks], [task.I_SHI.name])


if __name__ == '__main__':
    unittest.main()
