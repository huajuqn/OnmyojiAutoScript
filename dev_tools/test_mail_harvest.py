"""邮件领取状态流程测试，不连接设备或保存用户配置。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tasks.Restart.login import LoginHandler


class MailTask(LoginHandler):
    def __init__(self, stage='mail'):
        self.stage = stage
        self.controls = []
        self.frames = 0
        self.transition = 0
        self.device = SimpleNamespace(click=self.record_click)
        self.interval_timer = {}

    def screenshot(self):
        self.frames += 1
        assert self.frames < 50, '邮件流程未结束'
        if self.stage == 'transition':
            self.transition += 1
            if self.transition == 2:
                self.stage = 'reward'

    def appear(self, target, **kwargs):
        visible = {
            'mail': [self.I_HARVEST_MAIL_TITLE, self.I_HARVEST_MAIL_ALL],
            'confirm': [self.I_HARVEST_MAIL_CONFIRM],
            'reward': [self.I_UI_REWARD],
            'idle': [self.I_HARVEST_MAIL_TITLE, self.I_LOGIN_RED_CLOSE],
        }
        return target in visible.get(self.stage, [])

    def record_click(self, x, y, control_name=None):
        self.controls.append(control_name)
        self.stage = {
            self.I_HARVEST_MAIL_ALL.name: 'confirm',
            self.I_HARVEST_MAIL_CONFIRM.name: 'transition',
            self.I_UI_REWARD.name: 'idle',
            self.I_LOGIN_RED_CLOSE.name: 'closed',
        }[control_name]


class MailHarvestTest(unittest.TestCase):
    def run_mail(self, stage):
        task = MailTask(stage)

        class PhaseTimer:
            def __init__(self, limit):
                self.limit = limit

            def start(self):
                return self

            reset = start

            def reached(self):
                return self.limit == 2 and task.stage == 'idle'

        with patch('tasks.Restart.login.Timer', PhaseTimer):
            self.assertTrue(task.harvest_mail())
        self.assertEqual(task.stage, 'closed')
        return task

    def test_collect_confirm_wait_animation_reward_close(self):
        task = self.run_mail('mail')
        self.assertEqual(task.controls, [task.I_HARVEST_MAIL_ALL.name,
                         task.I_HARVEST_MAIL_CONFIRM.name, task.I_UI_REWARD.name,
                         task.I_LOGIN_RED_CLOSE.name])

    def test_resume_confirmation(self):
        task = self.run_mail('confirm')
        self.assertEqual(task.controls[0], task.I_HARVEST_MAIL_CONFIRM.name)

    def test_resume_reward(self):
        task = self.run_mail('reward')
        self.assertEqual(task.controls, [task.I_UI_REWARD.name, task.I_LOGIN_RED_CLOSE.name])

    def test_empty_mailbox(self):
        task = self.run_mail('idle')
        self.assertEqual(task.controls, [task.I_LOGIN_RED_CLOSE.name])


if __name__ == '__main__':
    unittest.main()
