# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

import random
from time import sleep

from cached_property import cached_property
from datetime import datetime
from datetime import timedelta, time
from module.base.timer import Timer
from module.exception import TaskEnd
from module.logger import logger
from tasks.BondlingFairyland.assets import BondlingFairylandAssets
from tasks.BondlingFairyland.battle import BondlingBattle
from tasks.BondlingFairyland.config import BondlingMode, BondlingClass, BondlingSwitchSoul, BondlingConfig, UserStatus
from tasks.BondlingFairyland.config_battle import BattleConfig
from tasks.BondlingFairyland.general_invite import GeneralInvite
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul, switch_parser
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_bondling_fairyland, page_shikigami_records, page_mall
from tasks.RichMan.assets import RichManAssets


class BondlingNumberMax(Exception):
    pass


""" 契灵 """


class ScriptTask(GameUi, GeneralInvite, GeneralRoom, BondlingBattle, SwitchSoul, BondlingFairylandAssets, RichManAssets):
    ball_pos_list = [None, None, None, None, None]  # 用于记录每一个位置的球是否出现
    first_catch = True  # 用于记录是否是第一次捕捉

    def run(self):
        cong = self.config.bondling_fairyland
        bondling_config = cong.bondling_config
        search_and_catch = bondling_config.bondling_mode == BondlingMode.MODE5

        if search_and_catch and bondling_config.user_status != UserStatus.ALONE:
            raise ValueError(f'Now is search and catch mode, but user status is not alone, current: '
                             f'{bondling_config.user_status.value}')

        # 新策略中 limit_num 表示目标契灵刷取数，不再用于契忆检查。
        if bondling_config.check_enable and not search_and_catch:
            logger.hr('第一步, 检查契忆数量', 2)
            self.ui_get_current_page()
            self.ui_goto(page_mall, confirm_wait=2.5)
            self.ui_click(self.I_MALL_SCCALES, self.I_MALL_SCCALES_CHECK)
            self.ui_click(self.I_MALL_BONDLINGS_SURE, self.I_MALL_BONDLINGS_ON)
            MAX_COUNT = bondling_config.limit_num
            cu, re, total = self.O_BL_CHECK_MONEY.ocr(self.device.image)
            if cu >= MAX_COUNT:
                logger.info(f'契忆数量: {cu} 大于 {MAX_COUNT}')
                self.ui_get_current_page()
                self.ui_goto(page_main)
                self.set_next_run(task='BondlingFairyland', finish=True, success=True)
                raise TaskEnd
            logger.info(f'契忆数量: {cu} 小于 {MAX_COUNT}, 继续任务')
        logger.hr('第二步, 切换御魂', 2)
        if not search_and_catch:
            self.switch_soul()
        else:
            logger.info('Search and catch mode will switch soul after checking the target position')
        logger.hr('第三步, 前往契灵主界面', 2)
        self.ui_goto_page(page_bondling_fairyland)
        logger.hr('第四步, 开始战斗准备', 2)
        self.current_count = 0
        self.limit_count = bondling_config.limit_count  # 默认limit_count值
        logger.hr('Goto bondling area')
        self.goto_ball_area(BondlingClass.get_index(cong.bondling_config.bondling_stone_class))

        if cong.bondling_config.bondling_mode == BondlingMode.MODE1:  # model1只刷探查
            if cong.bondling_config.user_status != UserStatus.ALONE:
                raise ValueError(f'Now is model1, but user status is not alone, current: {cong.bondling_config.user_status.value}')
            self.run_search(cong.bondling_config)
            self.ui_goto_page(page_main)
            self.set_next_run(task='BondlingFairyland', finish=True, success=True)
            raise TaskEnd
        match cong.bondling_config.user_status:
            case UserStatus.handoff1:
                self.limit_count //= 2
                self.switch_ball()
            case UserStatus.handoff2:
                self.limit_count //= 2
                self.run_member()
                self.current_count = 0
                self.ui_get_current_page()
                self.ui_goto(page_bondling_fairyland)
                self.switch_ball()
            case UserStatus.LEADER | UserStatus.ALONE:
                self.switch_ball()
            case UserStatus.MEMBER:
                self.run_member()
            case _:
                logger.error(f'Unknown user status: {cong.bondling_config.user_status}')

    def run_leader(self):
        """  点击 求援， 组队模式  """
        logger.hr('Start run leader', 2)
        success = True
        is_first = True
        while 1:
            def create_bond_team():
                click_count = 0
                while 1:
                    self.screenshot()
                    if self.appear(self.I_GI_IN_ROOM):
                        return True
                    # 求援后可能出现式盘数量上限确认弹窗
                    if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                        sleep(1)
                        continue
                    if click_count >= 6:
                        logger.error('Click fire failed')
                        logger.error(
                            'You might need to check your bondling number. It most possibly arrived to the max 500')
                        raise BondlingNumberMax
                    if self.check_and_invite(True):
                        continue
                    if self.appear(self.I_CREATE_TEAM, interval=1):
                        self.ensure_private()
                        if self.appear_then_click(self.I_CREATE_TEAM, interval=2):
                            logger.info('Wait up to 5s for bondling room after creating team')
                            enter_timer = Timer(5).start()
                            while not enter_timer.reached():
                                self.screenshot()
                                if self.appear(self.I_GI_IN_ROOM) or self.is_in_room(is_screenshot=False):
                                    logger.info('Bondling room entered after creating team')
                                    return True
                                if self.appear(self.I_BALL_HELP) or self.appear(self.I_CREATE_TEAM):
                                    break
                        continue
                    # 求援
                    if self.appear(self.I_BALL_AREA, interval=1):
                        return False
                    if self.appear(self.I_BALL_HELP, interval=1):
                        cu, res, total = self.O_B_BALL_NUMBER.ocr(self.device.image)
                        logger.info(f'ball is cu {cu}, total {total}')
                        if cu <= 0 and total == 99:
                            logger.info('ball is not enough')
                            return False
                        if self.appear_then_click(self.I_BALL_HELP, interval=2):
                            sleep(1)
                            click_count += 1
                            continue

            self.screenshot()

            if success:
                is_first = True
                if not create_bond_team():
                    return True

            self.check_and_invite(True)

            if self.current_count >= self.limit_count:
                if self.appear(self.I_GI_IN_ROOM):
                    # 次数达到也要邀请好友进房间,然后退出,不然队员无法判断是否完成契灵,出现异常
                    self.run_invite(config=self.config.bondling_fairyland.invite_config, is_first=is_first, is_over=False)
                    # 等待三秒让队员进房间,避免队员没进房间出现异常
                    sleep(3)
                    logger.info(f'契灵次数:{self.current_count}已完成,退出')
                    break

            if datetime.now() - self.start_time >= self.limit_time:
                if self.appear(self.I_GI_IN_ROOM):
                    logger.info('bondling_fairyland time limit out')
                    break

            if self.appear(self.I_GI_IN_ROOM):
                # 点击挑战
                if not is_first:
                    if self.run_invite(config=self.config.bondling_fairyland.invite_config):
                        success = self.run_battle(self.config.bondling_fairyland.battle_config, limit_count=self.limit_count)
                    else:
                        # 邀请失败，退出任务
                        logger.warning('Invite failed and exit this bondling_fairyland task')
                        success = False
                        break

                # 第一次会邀请队友
                if is_first:
                    if not self.run_invite(config=self.config.bondling_fairyland.invite_config, is_first=True):
                        logger.warning('Invite failed and exit this bondling_fairyland task')
                        success = False
                        break
                    else:
                        is_first = False
                        success = self.run_battle(self.config.bondling_fairyland.battle_config, limit_count=self.limit_count)
                        continue
        # 当结束或者是失败退出循环的时候只有两个UI的可能，在房间或者是在组队界面
        # 如果在房间就退出
        if self.exit_room():
            pass
        # 如果在组队界面就退出
        if self.exit_team():
            pass

        self.ui_get_current_page()
        self.ui_goto(page_bondling_fairyland)
        # 引用配置
        if UserStatus.handoff1 == self.config.bondling_fairyland.bondling_config.user_status:
            self.current_count = 0
            self.run_member()
        self.ui_get_current_page()
        self.ui_goto(page_main)
        self.set_next_run(task='BondlingFairyland', finish=True, success=True)
        raise TaskEnd

    def run_member(self):
        logger.hr('Start run member', 2)
        self.ui_get_current_page()
        # 开始等待队长拉人
        wait_time = self.config.bondling_fairyland.invite_config.wait_time
        wait_timer = Timer(wait_time.minute * 60)
        wait_timer.start()
        success = True

        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')

        while 1:

            self.screenshot()

            if wait_timer.reached():
                logger.info(f"队员等待超时:{wait_timer.current()}, 退出")
                break

            # if self.current_count >= self.limit_count:
            #     logger.info('Orochi count limit out')
            #     breakpush_n
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('BondlingFairyland time limit out')
                break

            if self.check_then_accept():
                continue

            if self.is_in_room():
                logger.info("契灵：已经在组队房间中")
                if self.wait_battle(wait_time=self.config.bondling_fairyland.invite_config.wait_time):
                    self.run_battle(self.config.bondling_fairyland.battle_config, limit_count=self.limit_count)
                    wait_timer.reset()
                    # 进入战斗流程
                    self.device.stuck_record_add('BATTLE_STATUS_S')
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            elif self.check_take_over_battle(False, config=self.config.bondling_fairyland.battle_config):
                wait_timer.reset()
                # 进入战斗流程
                self.device.stuck_record_add('BATTLE_STATUS_S')
                continue

        while 1:
            # 有一种情况是本来要退出的，但是队长邀请了进入的战斗的加载界面
            if self.appear(self.I_GI_HOME) or self.appear(self.I_GI_EXPLORE) or self.appear(self.I_BALL_AREA) or self.appear(self.I_BALL_HELP) :
                break
            # 如果可能在房间就退出
            if self.exit_room():
                pass
            # 如果还在战斗中，就退出战斗
            if self.exit_battle():
                pass
                # 引用配置
        if UserStatus.MEMBER == self.config.bondling_fairyland.bondling_config.user_status:
            self.ui_get_current_page()
            self.ui_goto(page_main)
            self.set_next_run(task='BondlingFairyland', finish=True, success=True)
            raise TaskEnd

    def switch_ball(self):
        logger.hr('Start switch ball', 2)
        cong = self.config.bondling_fairyland

        bondling_config = cong.bondling_config
        battle_config = cong.battle_config

        logger.info(f'抓捕契灵: [{bondling_config.bondling_stone_class}] ')
        idx = BondlingClass.get_index(bondling_config.bondling_stone_class)
        current_ball_index = idx if idx is not None else 1
        capture_setting_checked = False
        search_and_catch = bondling_config.bondling_mode == BondlingMode.MODE5
        target_catch_count = 0
        target_catch_limit = bondling_config.limit_num
        soul_stage = None

        if search_and_catch:
            logger.info(f'Target bondling catch limit: {target_catch_limit}')
            if target_catch_limit <= 0:
                logger.warning('Target bondling catch limit is not greater than 0, exit')

        while 1:
            if search_and_catch and target_catch_count >= target_catch_limit:
                logger.info(f'Target bondling catch limit reached: {target_catch_count}/{target_catch_limit}')
                break
            if not self.in_search_ui(screenshot=True):
                self.ui_get_current_page()
                self.ui_goto(page_bondling_fairyland)
                continue
            if bondling_config.bondling_mode != BondlingMode.MODE1:
                # 新策略在探查与契灵战斗之间切换各自的御魂预设。
                if search_and_catch:
                    next_soul_stage = 'bondling' if self.bondling_appeared(current_ball_index) else 'search'
                    if soul_stage != next_soul_stage:
                        if cong.bondling_switch_soul.enable:
                            returned_directly = self.switch_soul(next_soul_stage)
                            if not returned_directly:
                                self.ui_goto_page(page_bondling_fairyland)
                                self.goto_ball_area(current_ball_index)
                            # 往返式神录后重新判定目标，避免用旧画面状态选错战斗套装。
                            soul_stage = next_soul_stage
                            continue
                        soul_stage = next_soul_stage
                if self.ball_click(current_ball_index):
                    logger.info(f'Current ball index: {current_ball_index} ')
                else:
                    if self.run_stone(bondling_config.bondling_stone_enable):
                        continue
                    elif (bondling_config.bondling_search_enable or search_and_catch) \
                            and bondling_config.user_status == UserStatus.ALONE:
                        if self.run_search(bondling_config, target_index=current_ball_index):
                            logger.info('Bondling search finish, try to run catch')
                            continue
                        else:
                            break  # 时间到了或次数到了直接退出
                    else:
                        logger.info('No bondling stone, exit')
                        break
                # 检查结契设置
                if not capture_setting_checked:
                    self.capture_setting(bondling_config.bondling_mode)
                    capture_setting_checked = True
                try:
                    # 执行捕捉
                    if self.run_catch(bondling_config, battle_config):
                        logger.info(f'Catch successful and current ball number: {current_ball_index} ')
                        if search_and_catch:
                            target_catch_count += 1
                            logger.info(f'Target bondling catch progress: '
                                        f'{target_catch_count}/{target_catch_limit}')
                    else:
                        break
                except BondlingNumberMax:
                    logger.error('Bondling number max, exit')
                    break
            else:
                # 否则就是模式1
                break

        # 退出的时候如果是在结契的界面，要退回到探查界面
        while 1:
            self.screenshot()
            if self.in_search_ui():
                break
            if self.in_catch_ui():
                self.appear_then_click(self.I_BACK_Y, interval=1)
        logger.info('BondlingFairyland task finished')

        self.ui_get_current_page()
        self.ui_goto(page_main)
        self.set_next_run(task='BondlingFairyland', finish=True, success=True)
        raise TaskEnd

    def run_stone(self, bondling_stone_enable: bool):
        """
        使用结契石 进行召唤 契灵
        :param bondling_stone_enable:
        :return:
        (0) 不开启使用结契石，(探查界面)返回False
        (1) 没有结契石了，(探查界面)返回False
        """
        # 没有启用使用石头购买契灵或者当前不在购买界面则直接退出
        if not bondling_stone_enable or not self.appear(self.I_STONE_SURE):
            self.ui_click_until_disappear(self.I_STONE_CLOSE, interval=1.2)
            return False
        cu, res, total = self.O_B_STONE_NUMBER.ocr(self.device.image)
        # 如果没有石头了
        if cu == 0 and cu + res == total:
            self.ui_click_until_disappear(self.I_STONE_CLOSE, interval=1.2)
            logger.warning(f'已经没有鸣契石召唤契灵了')
            return False
        while 1:
            self.screenshot()
            if not self.appear(self.I_STONE_SURE):
                sleep(random.uniform(1.5, 2))  # 等待购买后的动画, 否则已经买了但是下次再点击还会出现该界面
                return True
            for i in range(3):
                if self.appear_then_click(self.I_BUY_PLUS, interval=1):
                    sleep(0.5)
            if self.appear_then_click(self.I_GI_SURE, interval=1):
                continue
            if self.appear_then_click(self.I_STONE_SURE, interval=1):
                continue

    def run_search(self, bondling_config: BondlingConfig, target_index: int = None, limit_cnt: int = None):
        """
        运行探查
        :param target_index: 目标契灵序号，设置后每次探查都会检查对应固定位置是否已刷出
        :param limit_cnt: 最多探查次数
        :return:
        (1) 超出战斗的次数的了，(探查页面)返回False
        (2) 超过时间限制了，(探查页面)返回False
        (3) 目标契灵已刷出，(探查界面)返回True
        (4) 达到limit_cnt次或四个位置已满, (探查界面)返回True
        """
        self.lock_team()
        while 1:
            # 检查是不是在探查界面，
            if not self.in_search_ui(screenshot=True):
                continue
            # 新版契灵为固定四个位置，下方加号消失表示目标契灵已刷出
            if target_index is not None and self.bondling_appeared(target_index):
                logger.info(f'Target bondling appeared, index: {target_index}')
                return True
            # 检查是否打满limit_cnt次
            if limit_cnt is not None and limit_cnt <= 0:
                return True
            # 检查是否有挑战次数
            if self.current_count >= bondling_config.limit_count:
                logger.warning(f'No challenge count, exit')
                return False
            # 检查是否到了限制时间
            if datetime.now() - self.start_time >= self.limit_time:
                logger.warning(f'No time, exit')
                return False
            if self.click_search():
                self.run_general_battle(self.general_battle_config)
                if limit_cnt is not None:
                    limit_cnt = limit_cnt - 1
                    logger.info(f'Remain search battle: {limit_cnt}')
            else:
                logger.warning(f'Full four bondling positions')
                return True

    def run_catch(self, bondling_config: BondlingConfig, battle_config: BattleConfig):
        """
        执行捕捉的(确保进入了结契界面)
        :return:
        (1) 盘子没了，返回False (退出页面是结契界面)
        (2) 时间到了，返回False (退出页面是结契界面)
        (3) 挑战次数到了，返回False (退出页面是结契界面)
        (4) 捕获成功，返回True (退出页面是捕获的页面)
        """
        logger.hr('Start run catch', 2)
        self.lock_team()

        def check_plate_number():
            match bondling_config.bondling_mode:
                case BondlingMode.MODE2 | BondlingMode.MODE5:
                    target_plate = self.O_B_LOW_NUMBER
                case BondlingMode.MODE3:
                    target_plate = self.O_B_MEDIUM_NUMBER
                case BondlingMode.MODE4:
                    target_plate = self.O_B_HIGH_NUMBER
                case _:
                    logger.error('Invalid bondling mode')
                    return False
            self.screenshot()
            cu, res, total = target_plate.ocr(self.device.image)
            if cu == 0 and cu + res == total:
                logger.warning(f'No plate number, exit')
                return False
            return True

        def check_ball_number():
            self.screenshot()
            cu, res, total = self.O_B_BALL_NUMBER.ocr(self.device.image)
            if cu == 0 and cu + res == total and total == 99:
                logger.warning(f'No ball number, exit')
                return False
            return True

        # 检查盘子
        if not check_plate_number():
            return False
        # 检查抓捕契灵剩余数量
        if not check_ball_number():
            return False

        # 开始执行循环
        success = True
        logger.hr(f'开始执行战斗循环', 2)
        while 1:
            self.screenshot()

            if self.appear(self.I_BALL_AREA):
                return True

            # 如果不在结契界面，就等待
            if not self.in_catch_ui():
                continue

            # 检查是否有盘子
            if not check_plate_number():
                logger.warning(f'No plate number, exit')
                return False
            # 检查是否有挑战次数
            if self.current_count >= bondling_config.limit_count:
                logger.warning(f'No challenge count, exit')
                return False
            # 检查是否到了限制时间
            if datetime.now() - self.start_time >= self.limit_time:
                logger.warning(f'No time, exit')
                return False

            # 引用配置
            cong = self.config.bondling_fairyland
            match cong.bondling_config.user_status:
                case UserStatus.ALONE:
                    self.run_alone()
                    self.run_battle(battle_config, limit_count=self.limit_count)
                case _:
                    if self.run_leader():
                        return success

    def is_room_dead(self) -> bool:
        # 如果在探索界面或者是出现在组队界面，那就是可能房间死了
        sleep(0.5)
        if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
            sleep(0.5)
            if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                return True
        return False

    def get_bondling_click_target(self, index: int):
        """获取契灵固定位置的点击区域。"""
        if not 1 <= index <= 8:
            raise ValueError(f'Bondling index must be between 1 and 8, current: {index}')
        targets = {
            1: self.C_STONE_1,
            2: self.C_STONE_2,
            3: self.C_STONE_3,
            4: self.C_STONE_4,
        }
        return targets[(index - 1) % 4 + 1]

    def get_bondling_plus_target(self, index: int):
        """获取契灵固定位置下方的加号识别资源。"""
        targets = {
            1: self.I_BF_AREA1_ITEM_1,
            2: self.I_BF_AREA1_ITEM_2,
            3: self.I_BF_AREA1_ITEM_3,
            4: self.I_BF_AREA1_ITEM_4,
            5: self.I_BF_AREA2_ITEM_1,
            6: self.I_BF_AREA2_ITEM_2,
            7: self.I_BF_AREA2_ITEM_3,
            8: self.I_BF_AREA2_ITEM_4,
        }
        try:
            return targets[index]
        except KeyError as exc:
            raise ValueError(f'Bondling index must be between 1 and 8, current: {index}') from exc

    def bondling_appeared(self, index: int, check_count: int = 3, check_interval: float = 0.3) -> bool:
        """
        多帧检查契灵位置下方的加号。
        任意一帧出现加号都表示未刷出，只有连续多帧都没有加号才判定已刷出。
        """
        if check_count < 1:
            raise ValueError(f'check_count must be greater than 0, current: {check_count}')
        plus_target = self.get_bondling_plus_target(index)
        for current in range(check_count):
            if self.appear(plus_target):
                return False
            if current < check_count - 1:
                sleep(check_interval)
                self.screenshot()
        return True

    def ball_click(self, index: int) -> bool:
        """
        点击对应契灵，进入结契战斗界面。
        如果下方加号存在，会点击原区域打开购买页面并返回False。
        :param index:
        :return:
        """
        click_target = self.get_bondling_click_target(index)
        click_count = 0
        logger.info(f'Click ball index: {index}')
        while 1:
            self.screenshot()
            if self.appear(self.I_BALL_HELP):
                return True
            # 加号因动画未命中时可能误判为已刷出；点击后出现购买页则立即纠正
            if self.appear(self.I_STONE_SURE) or self.appear(self.I_STONE_CLOSE):
                logger.info(f'Purchase UI appeared, bondling has not appeared, index: {index}')
                return False
            if not self.bondling_appeared(index):
                logger.info(f'Bondling has not appeared, click purchase entrance, index: {index}')
                self.click(click_target)
                # 保留弹窗截图给run_stone判断是否进入购买页面
                purchase_timer = Timer(3).start()
                while not purchase_timer.reached():
                    self.screenshot()
                    if self.appear(self.I_STONE_SURE) or self.appear(self.I_STONE_CLOSE):
                        break
                return False
            if click_count >= 3:
                return False
            # 点击
            if self.click(click_target, interval=1):
                click_count += 1

    def goto_ball_area(self, index: int):
        """进入契灵对应地域,最终在探查界面"""
        def get_click_area(ind: int):
            """获取对应契灵地域点击位置"""
            if 1 <= ind <= 4:  # 平安京
                return self.C_AREA_1
            if 5 <= ind <= 8:  # 逢魔之原
                return self.C_AREA_2
            return None
        # 进入地域页面
        while True:
            self.screenshot()
            if self.appear(self.I_CHECK_AREA, interval=0.6):
                break
            if self.appear_then_click(self.I_BALL_AREA, interval=1.2):
                continue
        # 点击对应地域并返回契灵主界面
        self.ui_click(get_click_area(index), self.I_BALL_AREA, interval=0.8)

    def capture_setting(self, mode: BondlingMode) -> None:
        """
        第一次进入任务的时候触发这一项方法：为了确保用户的选择默认是正确的
        在结契的跳转页面，进入结契设置，按照模式来勾选
        :param mode:
        :return:
        """
        if mode == BondlingMode.MODE1:
            return None
        logger.info(f'Capture setting mode: {mode}')
        self.ui_click(self.I_CLICK_CAPTION, self.I_CAPTION_ENSURE, interval=1)  # 打开结契设置
        self.ui_click(self.I_C_AUTO_FALSE, self.I_C_AUTO_TRUE, interval=1)  # 自动结契
        self.ui_click(self.I_C_MINIMAL_MODE_DISABLE, self.I_C_MINIMAL_MODE_ENABLE, interval=0.8)  # 极简模式

        target_true = None
        target_false = None
        target_first = None
        target_continuous = None
        if mode == BondlingMode.MODE3:
            target_true = self.I_C_MIDUM_TRUE
            target_false = self.I_C_MIDUM_FALSE
            target_first = self.I_C_FIRST_ENABLE
            target_continuous = self.I_C_CONTINUOUS_ENABLE
        elif mode in [BondlingMode.MODE2, BondlingMode.MODE5]:
            target_true = self.I_C_LOW_TRUE
            target_false = self.I_C_LOW_FALSE
            target_first = self.I_C_FIRST_DISABLE
            target_continuous = self.I_C_CONTINUOUS_DISABLE
        elif mode == BondlingMode.MODE4:  # 高级盘子不需要设置连续结契和羁绊式神
            target_true = self.I_C_HIGH_TRUE
            target_false = self.I_C_HIGH_FALSE
        if target_true is not None:  # 切换盘子
            self.ui_click(target_false, target_true, interval=1)
        if target_continuous is not None:  # 是否连续结契
            self.ui_click_until_disappear(target_continuous, interval=1)
        if target_first is not None:  # 是否使用羁绊式神
            self.ui_click_until_disappear(target_first, interval=1)
        # 点击确定退出
        self.ui_click_until_disappear(self.I_CAPTION_ENSURE, interval=1)
        return None

    def enter_shikigami_records(self, timeout: int = 15) -> bool:
        """
        从契灵探查界面进入式神录。
        先等待入口图片出现，再持续点击直到图片消失。
        :return:
        """
        timeout_timer = Timer(timeout).start()
        while 1:
            self.screenshot()
            if self.appear(self.I_BF_RECORDS):
                logger.info('Bondling shikigami records entrance appeared')
                self.ui_click_until_disappear(self.I_BF_RECORDS, interval=1)
                logger.info('Bondling shikigami records entrance disappeared')
                return True
            if timeout_timer.reached():
                logger.warning('Enter shikigami records from bondling page timeout')
                return False

    def exit_shikigami_records_to_bondling(self, timeout: int = 20) -> bool:
        """从队伍预设原路退回契灵探查界面。"""
        timeout_timer = Timer(timeout).start()
        while 1:
            self.screenshot()
            if self.in_search_ui():
                logger.info('Returned to bondling page from shikigami records')
                return True
            if timeout_timer.reached():
                logger.warning('Return to bondling page from shikigami records timeout')
                return False
            if self.ocr_appear(self.O_SS_TEAM_PRESET_TITLE) \
                    or self.ocr_appear(self.O_SS_RECORDS_TITLE):
                self.click(self.C_SOU_RECORDS_BACK, interval=1)
                continue

    def lock_team(self):
        """
        锁定队伍(在探查或者是结契的界面)
        :return:
        """
        while 1:
            self.screenshot()
            if self.appear(self.I_BALL_LOCK):
                break
            if self.appear(self.I_BF_LOCK):
                break
            if self.appear_then_click(self.I_BALL_UNLOCK, interval=1):
                continue
            if self.appear_then_click(self.I_BF_UNLOCK, interval=1):
                continue

    def get_bondling_class(self) -> BondlingClass or None:
        """
        获取契灵的种类 (这个不应该一开始就调用因为这些会有出场动画)
        :return:
        """
        self.screenshot()
        if self.appear(self.I_TOMB_GUARD):
            return BondlingClass.TOMB_GUARD
        elif self.appear(self.I_SNOWBALL):
            return BondlingClass.SNOWBALL
        elif self.appear(self.I_LITTLE_KURO):
            return BondlingClass.LITTLE_KURO
        elif self.appear(self.I_AZURE_BASAN, threshold=0.7):
            return BondlingClass.AZURE_BASAN
        return None

    @cached_property
    def limit_time(self) -> timedelta:
        if not self.config.bondling_fairyland.bondling_config.limit_time:
            return timedelta(minutes=20)
        limit_time = self.config.bondling_fairyland.bondling_config.limit_time
        return timedelta(hours=limit_time.hour, minutes=limit_time.minute, seconds=limit_time.second)

    def run_alone(self):
        """
        单人 挑战， 主要是结契时的挑战
        """
        click_count = 0
        while 1:
            self.screenshot()
            if not self.appear(self.I_BALL_FIRE, threshold=0.7):
                break
            if self.appear_then_click(self.I_BALL_FIRE, interval=1):
                click_count += 1
                continue
            if click_count >= 6:
                logger.error('Click fire failed')
                logger.error('You might need to check your bondling number. It most possibly arrived to the max 500')
                raise BondlingNumberMax
            # 某些活动的时候出现 “选择共鸣的阴阳师”
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue

    def wait_battle(self, wait_time: time) -> bool:
        """
        在房间等待,(要求保证在房间里面) 队长开启战斗
        如果队长跑路了，或者的等待了很久还没开始
        :return: 如果成功进入战斗（反正就是不在房间 ）返回 True
                 如果失败了，（退出房间）返回 False
        """
        wait_second = wait_time.second + wait_time.minute * 60
        self.timer_wait = Timer(wait_second)
        self.timer_wait.start()
        logger.info(f'Wait battle {wait_second} seconds')
        success = True
        while 1:
            self.screenshot()

            # 如果自己在探索界面或者是庭院，那就是房间已经被销毁了
            if self.appear(self.I_GI_HOME) or self.appear(self.I_GI_EXPLORE) or self.appear(self.I_BALL_AREA) or self.appear(self.I_BALL_HELP):
                logger.warning('Room destroyed')
                success = False
                break

            if self.timer_wait.reached():
                logger.warning('Wait battle time out')
                success = False
                break

            if self.appear(self.I_EXIT):
                success = True
                logger.info("契灵：已经在战斗场景中")
                break

        # 调出循环只有这些可能性：
        # 1. 进入战斗（ui是战斗）
        # 2. 队长跑路（自己还是在房间里面）
        # 3. 等待时间到没有开始（还是在房间里面）
        # 4. 房间的时间到了被迫提出房间（这个时候来到了探索界面）
        if not success:
            logger.info('Leave room')
            self.exit_room()

        return success

    def exit_team(self) -> bool:
        """
        在组队界面 退出组队的界面， 返回到庭院或者是你一开始进入的入口
        :return:
        """
        if self.appear(self.I_CHECK_TEAM):
            logger.info('Exit team ui')
            while 1:
                self.screenshot()
                if not self.appear(self.I_CHECK_TEAM):
                    return True
                if self.appear_then_click(self.I_GR_BACK_YELLOW, interval=0.5):
                    continue

    def in_catch_ui(self, screenshot=False) -> bool:
        """
        判断是否在结契的总界面
        :return:
        """
        if screenshot:
            self.screenshot()
        return self.appear(self.I_BALL_FIRE)

    def in_search_ui(self, screenshot=False) -> bool:
        """
        判断是否在探查的总界面
        :return:
        """
        if screenshot:
            self.screenshot()
        return self.appear(self.I_BF_STORE)

    def click_search(self) -> bool:
        """
        点击探查
        :return: 如果四个位置满了就返回False。如果进入战斗不出现点击按钮则返回True
        """
        count = 0
        while 1:
            self.screenshot()
            if count >= 3:
                return False
            if not self.appear(self.I_BF_SEARSH):
                return True
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            if self.appear_then_click(self.I_BF_SEARSH, interval=2):
                count += 1
                continue
        return False

    def check_then_accept(self) -> bool:
        """
        队员接受邀请
        :return:
        """
        if not self.appear(self.I_I_ACCEPT):
            return False
        if self.appear(self.I_I_ACCEPT_JY):
            logger.info('appear accept_jy')
            return False
        logger.info('Click accept')

        accept_timer = Timer(5)
        accept_timer.start()
        logger.info("识别到队长邀请，准备点击接受....")
        while 1:
            self.screenshot()

            if accept_timer.reached():
                logger.info(f"队员点击接受超时:{accept_timer.current()}, 退出")
                break

            if self.is_in_room():
                logger.info("契灵：已经在组队房间中")
                return True
            # 被秒开
            # https://github.com/runhey/OnmyojiAutoScript/issues/230
            if self.appear(GeneralBattleAssets.I_EXIT):
                logger.info("已经在战斗场景中")
                return False
            if self.appear_then_click(self.I_I_NO_DEFAULT, interval=1):
                continue
            if self.appear_then_click(self.I_GI_SURE, interval=1):
                continue
            if self.appear_then_click(self.I_I_ACCEPT_DEFAULT, interval=1):
                continue
            if self.appear_then_click(self.I_I_ACCEPT, interval=1):
                continue
        return True

    @cached_property
    def general_battle_config(self):
        gbc = GeneralBattleConfig()
        gbc.lock_team_enable = True
        gbc.preset_enable = False
        gbc.green_enable = False
        gbc.random_click_swipt_enable = False
        return gbc

    def switch_soul(self, stage: str = None):
        def do_switch_soul(ts: str, g: str | int, te: str | int):
            if ts is None:
                raise ValueError(f'Invalid switch soul config on {bondling_config.bondling_stone_class.value}')
            if ts == 'int':
                self.run_switch_soul((g, te))
            if ts == 'str':
                self.run_switch_soul_by_name(g, te)
        cong = self.config.bondling_fairyland
        if not cong.bondling_switch_soul.enable:
            return False
        bondling_config = cong.bondling_config
        bondling_switch_soul = cong.bondling_switch_soul
        direct_entry = bondling_config.bondling_mode == BondlingMode.MODE5 and stage is not None
        if not direct_entry or not self.enter_shikigami_records():
            direct_entry = False
            self.ui_goto_page(page_shikigami_records)
        # 新策略按当前战斗阶段切换，启动时默认先切探查套装。
        if bondling_config.bondling_mode == BondlingMode.MODE5:
            switch_name = 'search_switch' if stage in [None, 'search'] else None
            if stage == 'bondling':
                type_str, (group, team) = bondling_switch_soul.get_switch_by_enum(
                    bondling_config.bondling_stone_class)
            elif switch_name is not None:
                type_str, (group, team) = bondling_switch_soul.get_switch_by_name(switch_name)
            else:
                raise ValueError(f'Invalid search and catch soul stage: {stage}')
            do_switch_soul(type_str, group, team)
            if direct_entry:
                return self.exit_shikigami_records_to_bondling()
            return False
        # 单刷探查配置
        if bondling_config.bondling_mode == BondlingMode.MODE1:
            type_str, (group, team) = bondling_switch_soul.get_switch_by_name('search_switch')
            do_switch_soul(type_str, group, team)
            return False
        # 刷契灵配置
        type_str, (group, team) = bondling_switch_soul.get_switch_by_enum(bondling_config.bondling_stone_class)
        do_switch_soul(type_str, group, team)
        # 启用了刷契灵时开启探查且是单人模式
        if bondling_config.bondling_search_enable and bondling_config.user_status == UserStatus.ALONE:
            type_str, (group, team) = bondling_switch_soul.get_switch_by_name('search_switch')
            do_switch_soul(type_str, group, team)
        return False


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    config = Config('oas1')
    device = Device(config)
    t = ScriptTask(config, device)
    # t.run()
    t.ui_get_current_page()
    t.ui_goto(page_bondling_fairyland)
    # image = task.screenshot()

    # con = config.bondling_fairyland
    # task.lock_team()
    # t.switch_ball()
    # t.run_stone(True,BondlingClass.TOMB_GUARD)
    # task.run_invite(config=config.bondling_fairyland.invite_config, is_over=False, is_first=True)
