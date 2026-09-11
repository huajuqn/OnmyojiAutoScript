# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum, auto
from time import sleep
from datetime import datetime, timedelta
import cv2
import numpy as np
import random
from typing import Any
from cached_property import cached_property

from module.atom.image import RuleImage
from module.atom.click import RuleClick
from module.atom.ocr import RuleOcr
from module.base.protect import random_sleep
from module.base.timer import Timer
from module.exception import GameStuckError, TaskEnd
from module.logger import logger

from tasks.base_task import BaseTask
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.ActivityShikigami.config import SwitchSoulConfig, GeneralBattleConfig, ActivityShikigami
from tasks.Component.BaseActivity.base_activity import BaseActivity
from tasks.Component.BaseActivity.config_activity import GeneralClimb
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
import tasks.Component.GeneralBattle.config_general_battle
import tasks.ActivityShikigami.page as game


def _prepare_image_for_ocr(image: np.ndarray, asset: RuleOcr) -> np.ndarray:
    image_copy = image.copy()
    x, y, w, h = asset.roi
    roi_to_process = image_copy[y:y + h, x:x + w]
    if len(roi_to_process.shape) == 3:
        gray_image = cv2.cvtColor(roi_to_process, cv2.COLOR_BGR2GRAY)
    else:
        gray_image = roi_to_process
    # 自适应二值化
    _, binary_norm = cv2.threshold(gray_image, 127, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    _, binary_inv = cv2.threshold(gray_image, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if cv2.countNonZero(binary_norm) < cv2.countNonZero(binary_inv):
        binary_correct = binary_norm
    else:
        binary_correct = binary_inv
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    dilated_image = cv2.dilate(binary_correct, kernel, iterations=1)
    # 找轮廓
    contours, _ = cv2.findContours(dilated_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    processed_roi_content = None
    if contours:
        all_points = np.concatenate(contours, axis=0)
        bx, by, bw, bh = cv2.boundingRect(all_points)
        processed_roi_content = binary_correct[by:by + bh, bx:bx + bw]
    centered_roi = np.full((h, w), 255, dtype=np.uint8)  # 255代表白色
    if processed_roi_content is not None:
        content_h, content_w = processed_roi_content.shape
        if content_h <= h and content_w <= w:
            # 计算居中粘贴的位置，放到中间
            start_y = (h - content_h) // 2
            start_x = (w - content_w) // 2
            paste_area = centered_roi[start_y:start_y + content_h, start_x:start_x + content_w]
            paste_area[processed_roi_content == 255] = 0
        else:
            logger.warning(f"Content for asset '{asset.name}' is larger than ROI. Skipping centering.")
            # 内容过大，直接使用原始二值图的反转作为结果
            centered_roi = cv2.bitwise_not(binary_correct)
    else:
        logger.warning(f"No content found in ROI for asset: {asset.name}. ROI will be blank.")
    processed_roi_bgr = cv2.cvtColor(centered_roi, cv2.COLOR_GRAY2BGR)
    image_copy[y:y + h, x:x + w] = processed_roi_bgr
    return image_copy


class LimitTimeOut(Exception):
    pass


class LimitCountOut(Exception):
    pass


class StateMachine(BaseTask):
    run_idx: int = 0  # 当前爬塔类型
    _count_map = None

    @cached_property
    def conf(self) -> GeneralClimb:
        return self.config.model.activity_shikigami

    @property
    def climb_type(self) -> str:
        if self.run_idx >= len(self.conf.general_climb.run_sequence_v):
            return self.conf.general_climb.run_sequence_v[-1]
        return self.conf.general_climb.run_sequence_v[self.run_idx]

    @property
    def count_map(self) -> dict[str, int]:
        """
        :return: key: climb type, value: run count
        """
        if not getattr(self, "_count_map", None):
            self._count_map = {climb_type: 0 for climb_type in self.conf.general_climb.run_sequence_v}
        return self._count_map

    # ----------------------------------------------------
    def put_status(self):
        """
        更新全局状态
        """

        def get_count(self) -> int:
            return self.count_map[self.climb_type]

        def get_limit(self) -> int:
            limit = getattr(self.conf.general_climb, f'{self.climb_type}_limit', 0)
            return 0 if not limit else limit

        # 超过运行时间
        if self.limit_time is not None and datetime.now() - self.start_time >= self.limit_time:
            logger.info(f"Climb type {self.climb_type} time out")
            raise LimitTimeOut
        # 次数达到限制
        if get_count(self) >= get_limit(self):
            logger.info(f"Climb type {self.climb_type} count limit reached")
            raise LimitCountOut

    def switch_next(self):
        """
        切换下一种爬塔类型
        :return: True 切换成功 or False
        """
        self.run_idx += 1
        if self.run_idx >= len(self.conf.general_climb.run_sequence_v):
            logger.info('All climbing activities have been completed')
            return False
        # 切换爬塔类型了, 恢复所有状态
        self.current_count = 0
        logger.hr(f'Climb switch to {self.climb_type}', 2)
        return True


class ScriptTask(StateMachine, GameUi, BaseActivity, SwitchSoul, ActivityShikigamiAssets):
    """
    更新前请先看 ./README.md
    """

    def _handle_daily_supply(self, skip_first_screenshot: bool = True) -> bool:
        """处理每日进入活动时连续出现的补给与奖励弹窗。"""
        self.maybe_screenshot(skip_first_screenshot)
        handled = False

        if self.appear(self.I_DAYLY_REWARD):
            logger.hr('Handle daily activity supply', 2)
            while self.appear(self.I_DAYLY_REWARD):
                self.random_reward_click()
                self.screenshot()
            handled = True

            # 奖励动画结束后才会出现补给总览的关闭按钮。
            wait_exit = Timer(5).start()
            while not wait_exit.reached() and not self.appear(self.I_RED_EXIT2):
                self.screenshot()

        if self.appear(self.I_RED_EXIT2):
            self.ui_click_until_disappear(self.I_RED_EXIT2, interval=1)
            handled = True

        if handled:
            # 弹窗消失不代表主页动画已经稳定；在此期间禁止通用未知页逻辑点击左上返回。
            self.wait_until_appear(
                self.I_TO_BATTLE_MAIN,
                skip_first_screenshot=True,
                wait_time=5
            )

        return handled

    def try_close_unknown_page(self, skip_screenshot: bool = True):
        """处理页面导航期间遮挡活动页面的补给或战斗奖励弹窗。"""
        if self._handle_daily_supply(skip_first_screenshot=skip_screenshot):
            logger.info('Daily activity supply popup handled')
            return True
        if self.appear(self.I_GET_AWARD):
            logger.info('Activity reward popup handled during page recovery')
            self.random_reward_click(exclude_click=[self.C_RANDOM_TOP, self.C_RANDOM_LEFT])
            return True
        return super().try_close_unknown_page(skip_screenshot=True)

    def run(self) -> None:
        self.limit_time: timedelta = self.conf.general_climb.limit_time_v
        #
        for climb_type in self.conf.general_climb.run_sequence_v:
            # 进入到活动的主页面，不是具体的战斗页面
            self.ui_get_current_page()
            self.ui_goto(game.page_climb_act)
            self._handle_daily_supply(skip_first_screenshot=False)
            try:
                method_func = getattr(self, f'_run_{climb_type}')
                method_func()
            except LimitCountOut as e:
                self.ui_click(self.I_UI_BACK_YELLOW, stop=self.I_TO_BATTLE_MAIN, interval=1)
            except LimitTimeOut as e:
                break
            finally:
                # 切换下一个爬塔类型
                self.switch_next()

        # 返回庭院
        logger.hr("Exit Shikigami", 2)
        self.ui_get_current_page(False)
        self.ui_goto(game.page_main)
        if self.conf.general_climb.active_souls_clean:
            self.set_next_run(task='SoulsTidy', success=False, finish=False, target=datetime.now())
        self.set_next_run(task="ActivityShikigami", success=True)
        raise TaskEnd

    def _run_pass(self):
        """
            更新前请先看 ./README.md
        """
        logger.hr(f'Start run climb type PASS', 1)
        self.enter_climb_challenge()
        self.switch_soul(self.I_SHISHENLU, self.I_FIRE_BUTTON)
        self.switch_climb_mode_in_game('pass')

        ocr_limit_timer = Timer(1).start()
        click_limit_timer = Timer(4).start()
        while 1:
            self.screenshot()
            self.put_status()
            # --------------------------------------------------------------
            if (self.appear_then_click(self.I_UI_CONFIRM, interval=0.5)
                    or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=0.5)):
                continue
            if self.ui_reward_appear_click():
                continue
            if not ocr_limit_timer.reached():
                continue
            ocr_limit_timer.reset()
            if not self.appear(self.I_FIRE_BUTTON):
                continue
            self.switch_climb_mode_in_game(self.climb_type)
            #  --------------------------------------------------------------
            self.lock_team(self.conf.general_battle)
            remain_tickets = self.check_tickets_enough()
            if remain_tickets <= 0:
                logger.warning(f'No tickets left, wait for next time')
                break
            if not self.switch_timesx5(remain_tickets):
                raise GameStuckError('活动五倍模式未确认，停止点击挑战')
            if self.conf.general_climb.random_sleep:
                random_sleep(probability=0.2)
            if self.start_battle():
                continue
            logger.warning('门票模式未能进入战斗，停止当前爬塔模式')
            break

        self.ui_click(self.I_UI_BACK_YELLOW, stop=self.I_TO_BATTLE_MAIN, interval=1)

    def _run_ap(self):
        """
            更新前请先看 ./README.md
        """
        logger.hr(f'Start run climb type AP')
        self.enter_climb_challenge()
        self.switch_soul(self.I_SHISHENLU, self.I_FIRE_BUTTON)
        self.switch_climb_mode_in_game('ap')

        ocr_limit_timer = Timer(1).start()
        while 1:
            self.screenshot()
            self.put_status()
            # --------------------------------------------------------------
            if not ocr_limit_timer.reached():
                continue
            ocr_limit_timer.reset()
            if not self.appear(self.I_FIRE_BUTTON):
                continue
            self.switch_climb_mode_in_game(self.climb_type)
            #  --------------------------------------------------------------
            self.lock_team(self.conf.general_battle)
            remain_tickets = self.check_tickets_enough()
            if remain_tickets <= 0:
                logger.warning(f'No tickets left, wait for next time')
                break
            if not self.switch_timesx5(remain_tickets):
                raise GameStuckError('体力五倍模式未确认，停止点击挑战')
            if self.conf.general_climb.random_sleep:
                random_sleep(probability=0.2)
            if self.start_battle():
                continue
            logger.warning('体力模式未能进入战斗，停止当前爬塔模式')
            break

        self.ui_click(self.I_UI_BACK_YELLOW, stop=self.I_TO_BATTLE_MAIN, interval=1)

    def _run_boss(self):
        """
        更新前请先看 ./README.md
        """
        logger.hr(f'Start run climb type BOSS')

        self.ui_clicks([self.I_TO_BATTLE_BOSS],
                       stop=self.I_CHECK_BATTLE_BOSS, interval=1)


        while 1:
            self.screenshot()
            self.put_status()
            # --------------------------------------------------------------
            if not self.ocr_appear(self.O_FIRE):
                self.appear_then_click(self.I_CHECK_BATTLE_BOSS, interval=4)
                continue

            if self.conf.general_climb.random_sleep:
                random_sleep(probability=0.2)
            if self.start_battle():
                continue
            logger.warning('Boss 模式未能进入战斗，停止当前爬塔模式')
            break

        self.ui_click(self.I_UI_BACK_YELLOW, stop=self.I_TO_BATTLE_BOSS, interval=1)

    def _run_ap100(self):
        """
        更新前请先看 ./README.md
        """
        logger.hr(f'Start run climb type AP100')

    def start_battle(self) -> bool:
        """点击挑战并运行通用战斗。

        :return: True 表示已进入并处理战斗；False 表示多次点击后仍未进入战斗。
        """
        click_times, max_times = 0, random.randint(4, 8)
        while 1:
            self.screenshot()
            if self.is_in_battle(False):
                break
            if click_times >= max_times:
                logger.warning(f'Climb {self.climb_type} cannot enter after {click_times} attempts')
                return False
            if (self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1) or
                    self.appear_then_click(self.I_UI_CONFIRM, interval=1) ):
                continue
            if self.appear_then_click(self.I_FIRE_BUTTON, interval=2):
                click_times += 1
                logger.info(f'Try click fire, remain times[{max_times - click_times}]')
                continue
        # 运行战斗
        self.run_general_battle(config=self.get_general_battle_conf())
        return True

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        # 通用战斗结束判断
        self.device.stuck_record_add("BATTLE_STATUS_S")
        self.device.click_record_clear()
        logger.info(f"Start {self.climb_type} battle process")
        self.count_map[self.climb_type] = self.current_count
        for btn in (self.C_RANDOM_LEFT, self.C_RANDOM_RIGHT, self.C_RANDOM_TOP, self.C_RANDOM_BOTTOM):
            btn.name = "BATTLE_RANDOM"
        ok_cnt, max_retry = 0, 8
        real_battle_seen = False
        while 1:
            sleep(random.uniform(0.5, 1.5))
            self.screenshot()
            # 达到最大重试次数则直接交给上层处理
            if ok_cnt > max_retry:
                break
            # 点击准备后游戏偶尔不会真正开战。通用战斗会在此时进入等待
            # 结果的流程，因此仅在活动任务内补充开战阶段的恢复处理。
            if ok_cnt == 0:
                if self.is_in_real_battle(False):
                    real_battle_seen = True
                elif self.is_in_prepare(False):
                    if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=0.8):
                        logger.warning('Activity battle is still preparing, retry prepare')
                    continue
                elif self.appear(self.I_FIRE_BUTTON):
                    if not real_battle_seen:
                        # 本次没有消耗门票，也不能占用用户配置的挑战次数。
                        self.current_count = max(0, self.current_count - 1)
                        self.count_map[self.climb_type] = self.current_count
                        logger.warning('Activity battle did not start, retry challenge')
                    else:
                        logger.warning('Activity battle returned without reward result')
                    self.device.stuck_record_clear()
                    return True
            # 识别到挑战说明已经退出战斗
            if ok_cnt > 0 and self.appear(self.I_FIRE_BUTTON):
                logger.info('Activity challenge page restored after battle')
                self.device.stuck_record_clear()
                return True
            # 战斗失败
            if self.appear(self.I_FALSE):
                logger.warning("Battle failed")
                self.ui_click_until_smt_disappear(self.random_reward_click(click_now=False), self.I_FALSE, interval=1.5)
                return False
            # 战斗成功
            if self.appear_then_click(self.I_WIN, interval=2):
                # 新版奖励弹窗可能不再包含旧的通用奖励素材。记录已经出现过
                # 胜利状态，奖励关闭后只要挑战按钮恢复即可结束战斗等待。
                ok_cnt = max(ok_cnt, 1)
                continue
            # 当前活动胜利后会额外弹出“获得奖励”窗口。该窗口不包含通用
            # 战利品素材，必须先点击空白区域关闭，随后才能回到挑战页。
            if self.appear(self.I_GET_AWARD):
                logger.info('Activity reward popup detected')
                self.random_reward_click(exclude_click=[self.C_RANDOM_TOP, self.C_RANDOM_LEFT])
                # 弹窗可能一次点击就消失。将奖励阶段直接置为已确认，确保
                # 过渡动画期间仍会继续点击，并最终等待挑战按钮重新出现。
                ok_cnt = max(ok_cnt, 4)
                continue
            # 出现奖励标识，或战利品总览提示“点击屏幕继续”
            if self.appear(self.I_REWARD) or self.appear(self.I_REWARD_PURPLE_SNAKE_SKIN) or \
                    self.appear(self.I_REWARD_GOLD) or self.appear(self.I_REWARD_GOLD_SNAKE_SKIN) or \
                    self.appear(self.O_CONTINUE_CLICK):
                self.random_reward_click(exclude_click=[self.C_RANDOM_TOP, self.C_RANDOM_LEFT])
                ok_cnt += 1
                continue
            # 已经不在战斗中了, 且奖励也识别过了, 则随机点击
            if ok_cnt > 3 and not self.is_in_battle(False):
                self.random_reward_click(exclude_click=[self.C_RANDOM_TOP, self.C_RANDOM_LEFT])
                self.device.stuck_record_clear()
                ok_cnt += 1
                continue
            # 战斗中随机滑动
            if ok_cnt == 0 and random_click_swipt_enable:
                self.random_click_swipt()
        return True

    def switch_soul(self, enter_button: RuleImage, cur_img: RuleImage):
        conf = self.conf.switch_soul_config
        enable_switch = getattr(conf, f"enable_switch_{self.climb_type}", False)
        enable_by_name = getattr(conf, f"enable_switch_{self.climb_type}_by_name", False)
        if not enable_switch and not enable_by_name:
            logger.info(f'Skip switch soul for {self.climb_type}: corresponding switch is disabled')
            return
        logger.hr('Start switch soul', 2)
        conf.validate_switch_soul()
        # 当前活动标题“神威破障”会被宽松的“式神录”OCR误命中，不能把
        # OCR 作为点击入口前的停止条件。先确保入口图片确实被点击并消失，
        # 再等待式神录页面完成加载。
        if not self.wait_until_appear(enter_button, wait_time=5):
            logger.warning('Shikigami records entry not found, skip switching souls')
            return
        self.ui_click_until_disappear(enter_button, interval=1)
        if not self.wait_until_appear(self.O_CHECK_RECORDS_TITLE, wait_time=10):
            logger.warning('Shikigami records page did not appear, skip switching souls')
            return
        if enable_by_name:
            group, team = getattr(conf, f"{self.climb_type}_group_team_name").split(",")
            self.run_switch_soul_by_name(group, team)
        elif enable_switch:
            group_team = getattr(conf, f"{self.climb_type}_group_team")
            self.run_switch_soul(group_team)
        self.ui_click(self.I_UI_BACK_YELLOW, stop=cur_img, interval=1)

    def enter_climb_challenge(self):
        """依次确认新增的战斗主页与挑战页，支持从任一层恢复导航。"""
        if self.conf.general_climb.anniversary_timesx5:
            self.ui_get_current_page(False)
            self.ui_goto(game.page_climb_challenge)
            if not self.wait_until_appear(self.I_FIRE_BUTTON, wait_time=8):
                raise GameStuckError('已进入活动挑战页，但未识别到挑战按钮')
        else:
            self.ui_clicks([self.I_TO_BATTLE_MAIN, self.I_TO_BATTLE_MAIN_2],
                           stop=self.I_FIRE_BUTTON, interval=1)

    def switch_climb_mode_in_game(self, mode: str = 'ap'):
        map_check = {
            'ap': self.I_CLIMB_MODE_AP,
            'pass': self.I_CLIMB_MODE_PASS,
        }
        if self.appear(map_check[mode]):
            return
        # 困难只支持活动门票；先退回简单，再切换普通体力模式。
        if (self.conf.general_climb.anniversary_timesx5 and mode == 'ap'
                and self.appear(self.I_CLIMB_MODE_PASS)):
            if not self.switch_pass_difficulty(False):
                raise GameStuckError('切换体力模式前无法确认简单模式')
        logger.info(f'Switch climb mode to {mode}')
        if not self.ui_click(self.I_CLIMB_MODE_SWITCH, stop=map_check[mode], interval=1.9, timeout=10):
            raise GameStuckError(f'无法确认活动消耗模式: {mode}')

    def lock_team(self, battle_conf: GeneralBattleConfig):
        """
        根据配置判断当前爬塔类型是否锁定阵容, 并执行锁定或解锁
        """
        enable_preset = getattr(battle_conf, f"enable_{self.climb_type}_preset", False)
        if not enable_preset:
            logger.info(f'Lock {self.climb_type} team')
            self.ui_click(self.I_UNLOCK, stop=self.I_LOCK, interval=1.5)
            return
        logger.info(f'Unlock {self.climb_type} team')
        self.ui_click(self.I_LOCK, stop=self.I_UNLOCK, interval=1.5)

    def check_tickets_enough(self) -> int:
        """
        判断当前爬塔门票是否足够
        :return: 当前爬塔类型的剩余门票数量
        """
        logger.hr(f'Check {self.climb_type} tickets')
        if not self.wait_until_appear(self.I_FIRE_BUTTON, wait_time=3):
            logger.warning(f'Detect fire fail, try reidentify')
            return 0
        self.screenshot()
        remain_times = 0
        if self.climb_type == 'pass':
            remain_times = self.O_REMAIN_PASS.ocr_digit(self.device.image)
        if self.climb_type == 'ap':
            remain_times = self.O_REMAIN_AP.ocr_quantity(self.device.image)
            normal_tickets = self.O_REMAIN_AP_PASS.ocr(self.device.image)
            logger.info(f'常规挑战资源: 体力={remain_times}, 门票={normal_tickets}')
            # AP 每次需要 6 体力和 1 张常规门票，返回可执行的单倍次数。
            remain_times = min(remain_times // 6, normal_tickets)
        if self.climb_type == 'boss':
            _, remain_times, _ = self.O_REMAIN_BOSS.ocr_digit_counter(self.device.image)
        if self.climb_type == 'ap100':
            remain_times = self.O_REMAIN_AP100.ocr_digit(self.device.image)
        return remain_times

    def switch_timesx5(self, remain_tickets: int) -> bool:
        """根据配置、5倍挑战券和活动门票数量切换5倍挑战。"""
        if self.conf.general_climb.anniversary_timesx5 and self.climb_type == 'pass':
            # PASS 免费五倍不消耗五倍券，也不操作 AP 的五倍开关。
            enable = self.conf.general_climb.prefer_timesx5 and remain_tickets >= 5
            logger.info(f'周年庆门票模式: 门票={remain_tickets}, 困难五倍={enable}')
            return self.switch_pass_difficulty(enable)
        remain_timesx5 = self.O_REMAIN_TIMESX5.ocr_digit(self.device.image)
        prefer_timesx5 = self.conf.general_climb.prefer_timesx5
        enable_timesx5 = prefer_timesx5 and remain_timesx5 > 0 and remain_tickets - 5 >= 0
        logger.info(
            f'5x challenge decision: prefer={prefer_timesx5}, '
            f'coupons={remain_timesx5}, tickets={remain_tickets}, enable={enable_timesx5}'
        )

        target = self.I_TIMESX5_TRUE if enable_timesx5 else self.I_TIMESX5_FALSE
        if self.appear(target):
            return True

        current = self.I_TIMESX5_FALSE if enable_timesx5 else self.I_TIMESX5_TRUE
        if not self.appear(current):
            logger.warning('Cannot identify current 5x challenge state')
            return False
        return self.ui_click(current, stop=target, interval=1, timeout=5)

    def switch_pass_difficulty(self, hard: bool) -> bool:
        """两个难度按钮始终都在；通过实际消耗 1/5 张确认选中状态。"""
        target_cost = 5 if hard else 1
        button = self.C_HARD_MODE if hard else self.C_EASY_MODE
        timer = Timer(10).start()
        confirmed = 0
        while not timer.reached():
            self.screenshot()
            if not self.appear(self.I_FIRE_BUTTON) or not self.appear(self.I_CLIMB_MODE_PASS):
                confirmed = 0
                continue
            cost = self.O_CHALLENGE_COST.ocr(self.device.image)
            if cost == target_cost:
                confirmed += 1
                if confirmed >= 2:
                    return True
                continue
            confirmed = 0
            if self.appear(self.I_EASY_MODE) or self.appear(self.I_HARD_MODE):
                self.click(button, interval=1)
        logger.warning(f'无法确认门票挑战消耗为 {target_cost} 张')
        return False

    def get_general_battle_conf(self) -> tasks.Component.GeneralBattle.config_general_battle.GeneralBattleConfig:
        from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig as gbc
        self.conf.validate_switch_preset()
        enable_preset = getattr(self.conf.general_battle, f'enable_{self.climb_type}_preset', False)
        group, team = getattr(self.conf.switch_soul_config, f'{self.climb_type}_group_team').split(',')
        return gbc(lock_team_enable=not enable_preset,
                   preset_enable=enable_preset,
                   preset_group=group if enable_preset else 1,
                   preset_team=team if enable_preset else 1,
                   green_enable=getattr(self.conf.general_battle, f'enable_{self.climb_type}_green', False),
                   green_mark=getattr(self.conf.general_battle, f'{self.climb_type}_green_mark'),
                   random_click_swipt_enable=getattr(self.conf.general_battle, f'enable_{self.climb_type}_anti_detect',
                                                     False), )

    def random_reward_click(self, exclude_click: list = None, click_now: bool = True) -> RuleClick:
        """
        随机点击
        :param exclude_click: 排除的点击位置
        :param click_now: 是否立即点击
        :return: 随机的点击位置
        """
        options = [self.C_RANDOM_LEFT, self.C_RANDOM_RIGHT, self.C_RANDOM_TOP, self.C_RANDOM_BOTTOM]
        if exclude_click:
            options = [option for option in options if option not in exclude_click]
        target = random.choice(options)
        if click_now:
            self.click(target, interval=1.8)
        return target


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
