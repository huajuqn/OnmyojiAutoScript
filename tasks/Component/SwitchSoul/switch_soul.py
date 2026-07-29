# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from typing import Union

from module.atom.click import RuleClick
from module.atom.long_click import RuleLongClick
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.exception import GameStuckError
from tasks.base_task import BaseTask
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from tasks.Component.GeneralInvite.config_invite import InviteConfig, InviteNumber, FindMode
from tasks.Component.SwitchSoul.assets import SwitchSoulAssets
from module.logger import logger


def switch_parser(switch_str: str) -> tuple:
    switch_list = switch_str.split(',')
    if len(switch_list) != 2:
        raise ValueError('Switch_str must be 2 length')
    return int(switch_list[0]), int(switch_list[1])


class SwitchSoul(BaseTask, SwitchSoulAssets):

    def run_switch_soul(self, target: tuple | list[tuple] | str):
        """
        保证在式神录的界面
        :return:
        """
        if isinstance(target, str):
            try:
                target = switch_parser(target)
            except ValueError:
                logger.error('Switch soul config error')
                return
        self.click_preset()
        self.switch_souls(target)

    def click_preset(self) -> None:
        """
        点击预设
        :return:
        """
        timeout = Timer(30).start()
        while 1:
            self.screenshot()
            # “队伍预设”是进入成功后的固定状态，不依赖式神录皮肤颜色。
            if self.ocr_appear(self.O_SS_TEAM_PRESET_TITLE):
                break
            # 只有识别到式神录及“预设”文字时才点击，点击位置来自 OCR 结果。
            if self.ocr_appear(self.O_SS_RECORDS_TITLE):
                if self.ocr_appear_click(self.O_SS_PRESET_BUTTON, interval=3):
                    continue
            if timeout.reached():
                raise GameStuckError('进入队伍预设界面超时')
            sleep(0.3)
        logger.info('Entered team preset in switch soul')

    def _switch_team(self, action: RuleClick, description: str,
                     target_ocr: RuleOcr = None) -> bool:
        """
        根据当前界面状态完成一次御魂预设切换。

        队伍预设界面出现时点击对应行；确认弹窗出现时点击“确定”；
        确认弹窗消失且重新识别到队伍预设界面后视为成功。
        """
        timeout = Timer(20).start()
        click_count = 0
        confirm_seen = False
        confirm_click_count = 0
        confirm_clear_timer = None
        click_wait = None

        while 1:
            self.screenshot()

            if self.ocr_appear(self.O_SS_SWITCH_CONFIRM):
                confirm_seen = True
                confirm_clear_timer = None
                if self.ocr_appear_click(self.O_SS_SWITCH_CONFIRM, interval=0.8):
                    confirm_click_count += 1
                    logger.info(f'Switch soul confirmation {confirm_click_count}: {description}')
                # 弹窗动画期间背景中的“队伍预设”仍可被识别，必须等弹窗真正消失。
                sleep(0.2)
                continue

            if self.ocr_appear(self.O_SS_TEAM_PRESET_TITLE):
                if confirm_seen:
                    # 阴阳师已装备的契灵会在第一次确认后继续弹出二次确认。
                    # 两层弹窗之间会短暂露出预设页，稳定等待后再判定全部完成。
                    if confirm_clear_timer is None:
                        confirm_clear_timer = Timer(2).start()
                    if confirm_clear_timer.reached():
                        logger.info(f'Switch soul confirmed after {confirm_click_count} confirmation(s): {description}')
                        return True
                    sleep(0.2)
                    continue
                # 点击后等待弹窗出现。若连续三次点击都没有弹窗且页面未跳转，
                # 游戏表示该套装已经装备，沿用旧逻辑按成功处理。
                if click_wait is not None and not click_wait.reached():
                    sleep(0.2)
                    continue
                if click_count >= 3:
                    logger.info(f'Soul preset already equipped: {description}')
                    return True
                if click_count < 3:
                    if target_ocr is None:
                        self.click(action)
                        clicked = True
                    else:
                        clicked = self.ocr_appear_click_by_rule(target_ocr, action)
                    if clicked:
                        click_count += 1
                        click_wait = Timer(1.5).start()
                        sleep(0.3)
                        continue

            if timeout.reached():
                logger.warning(f'Switch soul timeout: {description}')
                return False
            sleep(0.3)

    def switch_soul_one(self, group: int, team: int) -> None:
        """
        设置一个队伍的预设御魂
        :param group: 只能是[1-7]
        :param team: 只能是[1-4]
        :return:
        """

        def get_group_asset(group: int) -> RuleClick:
            match = {
                1: self.C_SOU_GROUP_1,
                2: self.C_SOU_GROUP_2,
                3: self.C_SOU_GROUP_3,
                4: self.C_SOU_GROUP_4,
                5: self.C_SOU_GROUP_5,
                6: self.C_SOU_GROUP_6,
                7: self.C_SOU_GROUP_7,
            }
            return match[group]

        def get_team_asset(team: int) -> RuleClick:
            match = {
                1: self.C_SOU_SWITCH_1,
                2: self.C_SOU_SWITCH_2,
                3: self.C_SOU_SWITCH_3,
                4: self.C_SOU_SWITCH_4,
            }
            return match[team]

        # 滑动至分组最上层(分組過多, 导致第一个分组显示不全)
        cur_text = ""
        while 1:
            self.screenshot()
            compare1 = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
            ocr_text = str([result.ocr_text for result in compare1])
            # 相等时 滑动到最上层
            if cur_text == ocr_text:
                break
            cur_text = ocr_text
            # 向上滑动
            self.swipe(self.S_SS_GROUP_SWIPE_UP, 1.5)
            # 等待滑动动画
            sleep(0.5)

        if group < 1 or group > 7:
            raise ValueError('Switch soul_one group must be in [1-7]')
        if team < 1 or team > 4:
            raise ValueError('Switch soul_one team must be in [1-4]')
        # 这一步是选择组
        target_click = get_group_asset(group)
        # 2023.8.5 修改为无反馈的点击切换
        for i in range(2):
            self.click(target_click)
            sleep(0.5)
        # 四个操作按钮布局固定，颜色随皮肤变化，因此只使用按钮区域点击。
        target_team = get_team_asset(team)
        if not self._switch_team(target_team, f'group {group} team {team}'):
            raise GameStuckError(f'切换御魂失败：分组 {group}，队伍 {team}')
        logger.info(f'Switch soul_one group {group} team {team}')

    def switch_souls(self, target: tuple or list[tuple]) -> None:
        """
        切换御魂
        :param target: [(1, 1), (2, 2), (3, 3), (4, 4)]  或者是单独的一个元组(4, 4) 第一个是组, 第二个是队伍
        :return:
        """
        if isinstance(target, tuple):
            target = [target]
        for group, team in target:
            group = int(group)
            team = int(team)
            self.switch_soul_one(group, team)

    def exit_shikigami_records(self) -> None:
        """
        退出式神录的界面
        :return:
        """
        while 1:
            self.screenshot()
            if not self.ocr_appear(self.O_SS_RECORDS_TITLE):
                break
            if self.click(self.C_SOU_RECORDS_BACK, interval=3.5):
                continue
        logger.info('Exit shikigami records')

    def run_switch_soul_by_name(self, groupName, teamName):
        """
        保证在式神录的界面
        :return:
        """
        if isinstance(groupName, str) and isinstance(teamName, str):
            self.click_preset()
            self.switch_soul_by_name(groupName, teamName)

    def switch_soul_by_name(self, groupName, teamName):
        """
        保证在式神录的界面
        :return:
        """
        logger.hr('Switch soul by name')
        # 滑动至分组最上层
        last_group_text = ''
        while 1:
            self.screenshot()
            compare1 = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
            now_group_text = str([result.ocr_text for result in compare1])
            if now_group_text == last_group_text:
                break
            self.swipe(self.S_SS_GROUP_SWIPE_UP, 2)
            sleep(2.5)
            last_group_text = now_group_text
        logger.info('Swipe to top of group')

        # 判断有无目标分组
        while 1:
            self.screenshot()
            # 获取当前分组名
            results = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
            text1 = [result.ocr_text for result in results]
            # 判断当前分组有无目标分组
            result = set(text1).intersection({groupName})
            # 有则跳出检测
            if result and len(result) > 0:
                break
            self.swipe(self.S_SS_GROUP_SWIPE_DOWN)
            sleep(1.5)
        logger.info('Swipe down to find target group')

        # 选中分组
        while 1:
            self.screenshot()
            self.O_SS_GROUP_NAME.keyword = groupName
            if self.ocr_appear_click(self.O_SS_GROUP_NAME):
                break
        logger.info(f'Select group {groupName}')

        # 滑动至阵容最上层
        last_team_text = ''
        while 1:
            self.screenshot()
            compare1 = self.O_SS_TEAM_NAME.detect_and_ocr(self.device.image)
            now_team_text = str([result.ocr_text for result in compare1])
            # 向上滑动
            if now_team_text == last_team_text:
                break
            self.swipe(self.S_SS_TEAM_SWIPE_DOWN, 1.5)
            sleep(2)
            last_team_text = now_team_text
        logger.info('Swipe to top of team')

        # 判断当前分组有无目标阵容
        while 1:
            self.screenshot()
            # 获取当前阵容名
            results = self.O_SS_TEAM_NAME.detect_and_ocr(self.device.image)
            text1 = [result.ocr_text for result in results]
            # 判断当前分组有无目标阵容
            result = set(text1).intersection({teamName})
            # 有则跳出检测
            if result and len(result) > 0:
                break
            self.swipe(self.S_SS_TEAM_SWIPE_UP, 0.3)
        logger.info('Swipe up to find target team')

        # 选中分组
        while 1:
            self.screenshot()
            self.O_SS_TEAM_NAME.keyword = teamName
            if self.ocr_appear_click(self.O_SS_TEAM_NAME):
                break
        logger.info(f'Select team {teamName}')
        # 切换御魂。横坐标使用固定按钮区域，纵坐标跟随 OCR 到的队伍名称。
        self.O_SS_TEAM_NAME.keyword = teamName
        if not self._switch_team(self.C_SOU_TEAM_SELECT,
                                 f'group {groupName} team {teamName}',
                                 target_ocr=self.O_SS_TEAM_NAME):
            raise GameStuckError(f'切换御魂失败：分组 {groupName}，队伍 {teamName}')
        logger.info(f'Switch soul_one group {groupName} team {teamName}')

    def ocr_appear_click_by_rule(self,
                                 target: RuleOcr,
                                 action: Union[RuleClick, RuleLongClick] = None,
                                 interval: float = None,
                                 duration: float = None) -> bool:
        """
        ocr识别目标，如果目标存在，则触发动作
        :param target:
        :param action:
        :param interval:
        :param duration:
        :return:
        """
        appear = self.ocr_appear(target, interval)

        if not appear:
            return False

        x1, y1, w1, h1 = target.area
        x, _ = action.coord()

        self.device.click(x=x, y=int(y1 + h1 / 2), control_name=target.name)
        return True


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    s = SwitchSoul(c, d)

    s.click_preset()
    # s.switch_soul_one(4, 1)
    # s.switch_soul_by_name('契灵', '茨球')
    s.switch_soul_by_name('默认分组', '队伍5')
