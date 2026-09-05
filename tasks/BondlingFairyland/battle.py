# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta, datetime
from dataclasses import dataclass
from time import monotonic

import random

from module.server.i18n import I18n
from tasks.BondlingFairyland.config import BondlingMode
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.BondlingFairyland.assets import BondlingFairylandAssets
from tasks.BondlingFairyland.config_battle import BattleConfig

from module.logger import logger
from module.exception import GameStuckError, GameTooManyClickError




@dataclass
class CatchProgress:
    """单轮战斗进度，异常恢复时保留明确结算结果和连续结契次数。"""
    win: bool = False
    cap_cnt: int = 0
    reward: bool = False


class BondlingBattle(GeneralBattle, BondlingFairylandAssets):

    def run_battle(self, battle_config: BattleConfig, limit_count: int = None) -> bool:
        """
        :return: 如果结契成功返回True，否则返回False
        """
        logger.hr("General battle start", 2)
        self.current_count += 1
        logger.info(f'Current tasks: {I18n.trans_zh_cn(self.config.task.command)}')
        logger.info(f'Current count: {self.current_count} / {limit_count}')

        task_run_time = datetime.now() - self.start_time
        # 格式化时间，只保留整数部分的秒
        task_run_time_seconds = timedelta(seconds=int(task_run_time.total_seconds()))
        logger.info(f'Current times: {task_run_time_seconds} / {self.limit_time}')

        progress = CatchProgress()
        loaded = False
        recovery_deadline = None
        while True:
            try:
                if not loaded:
                    if self.check_load(recovery_deadline):
                        self.green_mark(battle_config.green_enable, battle_config.green_mark)
                    loaded = True
                return self.catch_battle_wait(
                    battle_config.random_click_swipt_enable, progress, recovery_deadline)
            except (GameStuckError, GameTooManyClickError) as exc:
                # 每轮只接管一次；再次卡住交回调度器，不能无限重置设备计时。
                if recovery_deadline is not None:
                    raise
                logger.warning(f'契灵战斗异常，尝试任务内页面恢复: {exc}')
                recovery_deadline = monotonic() + 120
                page = self.recover_catch_page()
                if page is None:
                    raise
                if page in ('catch', 'search', 'room'):
                    return progress.win
                if page in ('battle', 'prepare'):
                    progress.reward = False
                loaded = page != 'prepare'

    def catch_return_page(self):
        """仅识别可交回外层循环的页面，弹层不能当作主界面。"""
        if self.appear(self.I_STONE_SURE) or self.appear(self.I_STONE_CLOSE):
            return None
        if any(self.appear(rule) for rule in (
                self.I_CAP_SUCCESS, self.I_CAP_FAILURE, self.I_CAP_AGAIN, self.I_REWARD)):
            return None
        if self.appear(self.I_GI_IN_ROOM):
            return 'room'
        if self.appear(self.I_BALL_FIRE):
            return 'catch'
        if self.in_search_ui():
            return 'search'
        return None

    def catch_screenshot(self, deadline=None):
        """恢复后的总期限独立于点击操作，不会被点击重置。"""
        if deadline is not None and monotonic() >= deadline:
            raise GameStuckError('契灵战斗恢复超过 120 秒，交回全局异常处理')
        self.screenshot()

    def recover_catch_page(self):
        """最多观察 20 秒，连续两帧确认页面后交还对应处理流程。"""
        self.device.stuck_record_clear()
        self.device.click_record_clear()
        deadline = monotonic() + 20
        previous = None
        while monotonic() < deadline:
            self.screenshot()
            page = self.catch_return_page()
            if page is None:
                if any(self.appear(rule) for rule in (
                        self.I_CAP_SUCCESS, self.I_CAP_FAILURE, self.I_CAP_AGAIN,
                        self.I_BATTLE_FAIL_ABANDON, self.I_REWARD, self.I_WIN,
                        self.I_BATTLE_SUCCESS, self.I_BATTLE_FAIL)):
                    page = 'settlement'
                elif self.is_in_real_battle(is_screenshot=False):
                    page = 'battle'
                elif self.appear(self.I_BUFF):
                    page = 'prepare'
            if page is not None and page == previous:
                logger.info(f'契灵战斗页面恢复成功: {page}')
                return page
            previous = page
        logger.warning('契灵战斗页面恢复失败，交回全局异常处理')
        return None


    def check_load(self, deadline=None) -> bool:
        """
        检查战斗时候的加载动画
        如何是还在加载种，有那个要准备的按钮，就返回True
        如果已经进入战斗了，就返回False
        :return:
        """
        while 1:
            self.catch_screenshot(deadline)
            if self.catch_return_page() is not None:
                # 提前退回也交给战斗等待中的连续帧确认，不能卡在加载流程。
                return False
            if self.appear(self.I_BUFF):
                return True
            if self.appear(self.I_EXIT):
                return False

    def catch_battle_wait(self, random_click_swipt_enable: bool,
                          progress=None, deadline=None) -> bool:
        """
        重写一个 战斗等待
        :return: 如果捕获成功返回True，否则返回False
        """
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 有时候 只会点击 获得奖励和开始战斗
        # 战斗过程 随机点击和滑动 防封
        logger.info("Start battle process")
        if progress is None:
            progress = CatchProgress()
        bondling_mode = self.config.bondling_fairyland.bondling_config.bondling_mode
        # 低/中级式盘失败后均放弃本轮并重新挑战；仅高级式盘连续结契。
        cap_again = bondling_mode == BondlingMode.MODE4
        max_cap = 10
        previous_return = None
        while not progress.reward:
            # 捕获次数超过最大次数限制, 则不再进行捕获
            if progress.cap_cnt >= max_cap:
                cap_again = False
            self.catch_screenshot(deadline)
            page = self.catch_return_page()
            if page is not None:
                if page == previous_return:
                    logger.info(f'契灵战斗已返回 {page}，捕获成功: {progress.win}')
                    self.device.stuck_record_clear()
                    self.device.click_record_clear()
                    return progress.win
                previous_return = page
                # 待确认帧不点击胜利等低阈值素材，避免在挑战页误点。
                continue
            previous_return = None
            # 如果捕获成功
            if self.appear_then_click(self.I_CAP_SUCCESS, action=self.C_CAP_SUCCESS,  interval=1):
                progress.win = True
            # 连续结契捕获失败
            if self.appear_then_click(self.I_CAP_FAILURE, action=self.C_CAP_SUCCESS, interval=1):
                progress.win = False
            # 非连续结契且单次抓捕失败
            if not cap_again and self.appear_then_click(self.I_BATTLE_FAIL_ABANDON, interval=1):
                progress.win = False
            # 连续结契则继续结契
            if cap_again and self.appear_then_click(self.I_CAP_AGAIN, interval=1):
                self.device.click_record_clear()  # 需要10次结契因此清空点击记录
                progress.cap_cnt += 1
                continue
            # 如果领奖励
            if self.appear(self.I_REWARD, threshold=0.6):
                progress.reward = True
                break
            if self.appear_then_click(self.I_WIN, threshold=0.6):
                continue
            if self.appear_then_click(self.I_BATTLE_SUCCESS, threshold=0.6, interval=1):
                continue
            if self.appear_then_click(self.I_BATTLE_FAIL, threshold=0.6, interval=1):
                continue
            # 如果开启战斗过程随机滑动
            if random_click_swipt_enable:
                self.random_click_swipt()

        # 确定获得奖励 无论是胜利还是失败
        if progress.win:
            logger.info("Catch success")
        else:
            logger.info("Catch failure")
        previous_return = None
        while 1:
            self.catch_screenshot(deadline)
            page = self.catch_return_page()
            if page is not None:
                if page == previous_return:
                    self.device.stuck_record_clear()
                    self.device.click_record_clear()
                    break
                previous_return = page
                continue
            previous_return = None
            # 如果出现领奖励
            action_click = random.choice([self.C_REWARD_1, self.C_REWARD_2, self.C_REWARD_3])
            if self.appear_then_click(self.I_REWARD, action=action_click, interval=1.5):
                continue
            if self.appear_then_click(self.I_WIN, threshold=0.6):
                continue
            if self.appear_then_click(self.I_BATTLE_SUCCESS, threshold=0.6, interval=1):
                continue
            if self.appear_then_click(self.I_BATTLE_FAIL_ABANDON, interval=1):
                continue
            if self.appear_then_click(self.I_BATTLE_FAIL, threshold=0.6, interval=1):
                continue
            # 奖励消失也可能只是转场；等待明确返回页，异常时再进入页面恢复。
        logger.info("Get reward")
        return progress.win
