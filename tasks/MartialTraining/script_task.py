# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
from datetime import datetime
from enum import Enum
from time import sleep

from module.base.timer import Timer
from module.exception import GameStuckError, TaskEnd
from module.logger import logger
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul, switch_parser
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main
from tasks.MartialTraining.assets import MartialTrainingAssets
from tasks.MartialTraining.page import page_martial_training


class TicketMode(str, Enum):
    NORMAL = 'normal'
    SPECIAL = 'special'


class BossType(str, Enum):
    FIRE = 'fire'
    SOUL = 'soul'
    OTHER = 'other'


class SearchResult(str, Enum):
    NOT_CLICKED = 'not_clicked'
    PENDING = 'pending'
    CONFIRMED = 'confirmed'


class TrainingAction(str, Enum):
    BOSS_PAGE = 'boss_page'
    SEARCH_LOCKED = 'search_locked'
    SEARCH_READY = 'search_ready'
    UNKNOWN = 'unknown'


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, MartialTrainingAssets):
    """武道大会“修行合训”任务。"""

    def run(self) -> None:
        self.conf = self.config.martial_training
        self.limit_time = self.conf.training_config.limit_time_v
        self.mode_counts = {mode: 0 for mode in TicketMode}
        self.current_soul_target = None
        self.task_success = True

        logger.hr('Martial Training', 1)
        self._normalize_initial_page()

        for mode_name in self.conf.training_config.run_sequence_v:
            mode = TicketMode(mode_name)
            if not self._mode_enabled(mode):
                logger.info(f'Skip disabled ticket mode: {mode.value}')
                continue
            if self._mode_limit(mode) <= 0:
                logger.info(f'Skip zero-limit ticket mode: {mode.value}')
                continue
            if not self._run_ticket_mode(mode):
                self.task_success = False
                break
            if self._time_limit_reached():
                break

        self._return_home()
        self.set_next_run(task='MartialTraining', success=self.task_success)
        raise TaskEnd('MartialTraining')

    def _normalize_initial_page(self) -> None:
        """Normalize a fresh/resumed task to the training page."""
        self.screenshot()
        # A task can be resumed while the boss detail overlay is still open.
        # Close it first so the locked search result is handled by the same
        # training-page loop as every other entry path.
        if self.appear(self.I_BOSS_PAGE):
            logger.info('Boss page found at task start; close it before resuming')
            if not self._close_boss_page():
                raise GameStuckError('Cannot close the initial boss page')
            self.ui_current = page_martial_training
        # Some courtyard skins are not covered by GameUi.I_CHECK_MAIN. The
        # activity entry itself is a task-specific, positive courtyard marker.
        elif self.appear(self.I_ACTIVITY_ENTRY):
            self.ui_current = page_main
            logger.info('Courtyard identified by Martial Training activity entry')
        else:
            self.ui_get_current_page(skip_first_screenshot=False)
        if not self.ui_goto(page_martial_training):
            raise GameStuckError('Cannot enter Martial Training page')

    # ------------------------------ task limits ------------------------------
    def _time_limit_reached(self) -> bool:
        if self.limit_time is None:
            return False
        reached = datetime.now() - self.start_time >= self.limit_time
        if reached:
            logger.info('Martial Training time limit reached')
        return reached

    def _mode_enabled(self, mode: TicketMode) -> bool:
        return bool(getattr(self.conf.training_config, f'{mode.value}_enable'))

    def _mode_limit(self, mode: TicketMode) -> int:
        return int(getattr(self.conf.training_config, f'{mode.value}_limit'))

    # ------------------------------ ticket loop ------------------------------
    def _run_ticket_mode(self, mode: TicketMode) -> bool:
        logger.hr(f'Start ticket mode: {mode.value}', 2)
        ocr_failures = 0
        boss_failures = 0
        pending_search = False
        pending_search_timer = None

        while True:
            self.screenshot()

            # A boss already found must be handled before checking the search
            # limit. This guarantees the last successful search is challenged.
            if self.appear(self.I_BOSS_PAGE):
                if pending_search:
                    self.mode_counts[mode] += 1
                    pending_search = False
                    pending_search_timer = None
                    logger.info(
                        f'{mode.value} search confirmed on boss page: '
                        f'{self.mode_counts[mode]}/{self._mode_limit(mode)}'
                    )
                if not self._handle_boss():
                    boss_failures += 1
                    if boss_failures >= 2:
                        logger.error('Boss challenge failed twice; stop safely')
                        return False
                else:
                    boss_failures = 0
                continue

            if self.appear(self.I_SEARCH_LOCKED):
                if pending_search:
                    self.mode_counts[mode] += 1
                    pending_search = False
                    pending_search_timer = None
                    logger.info(
                        f'{mode.value} delayed search confirmation: '
                        f'{self.mode_counts[mode]}/{self._mode_limit(mode)}'
                    )
                if not self._open_first_boss():
                    boss_failures += 1
                    if boss_failures >= 3:
                        logger.error('Cannot open the first boss after three attempts')
                        return False
                    continue
                if not self._handle_boss():
                    boss_failures += 1
                    if boss_failures >= 2:
                        logger.error('Boss challenge failed twice; stop safely')
                        return False
                else:
                    boss_failures = 0
                continue

            if pending_search:
                _, search_button, _ = self._ticket_assets(mode)
                if self.appear(self.I_TRAINING_PAGE) and self.appear(search_button):
                    logger.info('Search button returned without locking; retry the search')
                    pending_search = False
                    pending_search_timer = None
                elif pending_search_timer and pending_search_timer.reached():
                    logger.error('Search result stayed uncertain; stop to avoid duplicate consumption')
                    return False
                else:
                    sleep(0.3)
                    continue

            if not self.appear(self.I_TRAINING_PAGE):
                if not self._recover_training_page():
                    return False
                continue

            # The training-page marker appears before the boss card/search
            # control finishes its entrance animation. Wait for an actionable
            # state before checking limits or reading tickets. An existing
            # boss always has priority and consumes neither a ticket nor the
            # configured search count.
            action = self._wait_training_action()
            if action in {TrainingAction.BOSS_PAGE, TrainingAction.SEARCH_LOCKED}:
                logger.info(
                    f'Existing boss detected ({action.value}); '
                    'skip limits, ticket OCR and ticket-mode switching'
                )
                continue
            if action is TrainingAction.UNKNOWN:
                logger.warning('Training page action did not become ready')
                continue

            # Time and count limits only prevent a new search. Existing bosses
            # have already been routed to the boss-first branch above.
            if self._time_limit_reached():
                return True

            if self.mode_counts[mode] >= self._mode_limit(mode):
                logger.info(
                    f'{mode.value} search limit reached: '
                    f'{self.mode_counts[mode]}/{self._mode_limit(mode)}'
                )
                return True

            ticket_count = self._read_ticket_count(mode)
            if ticket_count is None:
                ocr_failures += 1
                logger.warning(f'Ticket OCR failed ({ocr_failures}/3): {mode.value}')
                if ocr_failures >= 3:
                    return False
                continue
            ocr_failures = 0
            logger.attr(f'{mode.value}_ticket_count', ticket_count)
            if ticket_count <= 0:
                logger.info(f'No {mode.value} tickets left')
                return True

            mode_ready = self._ensure_ticket_mode(mode)
            if mode_ready is None:
                logger.info('Existing boss appeared while switching ticket mode')
                continue
            if not mode_ready:
                logger.error(f'Cannot switch to ticket mode: {mode.value}')
                return False

            search_result = self._search_boss(mode)
            if search_result is SearchResult.NOT_CLICKED:
                logger.warning(f'Search did not enter locked state: {mode.value}')
                continue
            if search_result is SearchResult.PENDING:
                pending_search = True
                pending_search_timer = Timer(20).start()
                logger.warning(f'Search transition is still pending: {mode.value}')
                continue

            self.mode_counts[mode] += 1
            logger.info(
                f'{mode.value} search confirmed: '
                f'{self.mode_counts[mode]}/{self._mode_limit(mode)}'
            )

            if not self._open_first_boss():
                # The search count is already committed because the locked
                # state was observed. The next loop retries the existing boss.
                logger.warning('Search is locked, but the first boss is not ready yet')
                continue
            if not self._handle_boss():
                boss_failures += 1
                if boss_failures >= 2:
                    logger.error('Boss challenge failed twice; stop safely')
                    return False
            else:
                boss_failures = 0

        return True

    def _ticket_assets(self, mode: TicketMode):
        if mode is TicketMode.NORMAL:
            return self.I_TICKET_NORMAL, self.I_SEARCH_NORMAL, self.O_NORMAL_TICKET_COUNT
        return self.I_TICKET_SPECIAL, self.I_SEARCH_SPECIAL, self.O_SPECIAL_TICKET_COUNT

    def _wait_training_action(self) -> TrainingAction:
        """Wait for the animated training page to expose an actionable state."""
        timeout = Timer(8).start()
        while not timeout.reached():
            self.screenshot()
            if self.appear(self.I_BOSS_PAGE):
                return TrainingAction.BOSS_PAGE
            if self.appear(self.I_SEARCH_LOCKED):
                return TrainingAction.SEARCH_LOCKED
            if self.appear(self.I_SEARCH_NORMAL) or self.appear(self.I_SEARCH_SPECIAL):
                return TrainingAction.SEARCH_READY
            sleep(0.25)
        return TrainingAction.UNKNOWN

    def _ensure_ticket_mode(self, mode: TicketMode):
        _, search_button, _ = self._ticket_assets(mode)
        other_search_button = (
            self.I_SEARCH_SPECIAL
            if mode is TicketMode.NORMAL
            else self.I_SEARCH_NORMAL
        )
        timeout = Timer(25).start()
        while not timeout.reached():
            self.screenshot()
            # A boss may finish appearing between ticket OCR and mode
            # switching. Let the caller restart at the boss-first branch.
            if self.appear(self.I_BOSS_PAGE) or self.appear(self.I_SEARCH_LOCKED):
                return None
            # The two ticket icons are visually similar and can both match on
            # the same frame. Search buttons are mode-specific and are only
            # inspected here while search is unlocked.
            if self.appear(search_button):
                return True
            if self.appear(other_search_button) and self.appear_then_click(
                self.I_TICKET_SWITCH, interval=1.5
            ):
                sleep(0.5)
                continue
            if not self.appear(self.I_TRAINING_PAGE):
                return False
        return False

    def _read_ticket_count(self, mode: TicketMode):
        """Require two equal OCR samples so a transient frame is not trusted."""
        _, _, ocr = self._ticket_assets(mode)
        values = []
        for _ in range(4):
            self.screenshot()
            raw = ocr.ocr(image=self.device.image)
            match = re.search(r'\d+', str(raw).replace(',', ''))
            if match:
                value = int(match.group())
                values.append(value)
                if values.count(value) >= 2:
                    return value
            sleep(0.25)
        logger.warning(f'Unstable ticket OCR samples: {values}')
        return None

    def _search_boss(self, mode: TicketMode) -> SearchResult:
        _, search_button, _ = self._ticket_assets(mode)
        if not self.appear_then_click(search_button, interval=2):
            return SearchResult.NOT_CLICKED

        timeout = Timer(12).start()
        no_boss_logged = False
        while not timeout.reached():
            self.screenshot()
            if self.appear(self.I_SEARCH_LOCKED) or self.appear(self.I_BOSS_PAGE):
                return SearchResult.CONFIRMED
            if self.appear(self.I_NO_BOSS) and not no_boss_logged:
                logger.info('Boss slot is temporarily empty; waiting for search result')
                no_boss_logged = True
            # Searching has a full-screen transition animation. During that
            # animation neither the training-page marker nor the boss-page
            # marker is visible, so absence of the former is not a failure.
            sleep(0.3)
        # The click was sent, but a dynamic frame may have hidden the locked
        # template. The caller keeps a pending flag and commits the count only
        # if a later screenshot positively identifies the locked state.
        return SearchResult.PENDING

    def _open_first_boss(self) -> bool:
        timeout = Timer(12).start()
        while not timeout.reached():
            self.screenshot()
            if self.appear(self.I_BOSS_PAGE):
                return True
            # Boss names and portraits vary. Once search_locked is present,
            # the first result always occupies this fixed card slot.
            if self.appear(self.I_SEARCH_LOCKED):
                self.click(self.C_FIRST_BOSS_SLOT, interval=1.2)
                continue
            if self.appear(self.I_NO_BOSS):
                sleep(0.4)
                continue
            return False
        return False

    # ------------------------------- boss flow -------------------------------
    def _handle_boss(self) -> bool:
        boss_type = self._read_boss_type()
        if boss_type is None:
            logger.warning('Boss name OCR failed; close and reopen once')
            if not self._close_boss_page() or not self._open_first_boss():
                return False
            boss_type = self._read_boss_type()
            if boss_type is None:
                logger.error('Boss name OCR failed after reopening')
                return False

        logger.attr('boss_type', boss_type.value)
        soul_config = getattr(self.conf, f'{boss_type.value}_boss_soul')
        if not self._switch_boss_soul(soul_config):
            return False
        if not self._sync_team_lock():
            return False
        if not self._start_boss_battle():
            return False

        win = self.run_general_battle(self.conf.battle_config)
        returned = self._return_to_training_page()
        if not returned:
            return False
        if not win:
            logger.warning('Boss battle was not successful')
        return win

    def _read_boss_type(self):
        texts = []
        classified = []
        for _ in range(5):
            self.screenshot()
            raw = self.O_BOSS_NAME.ocr(image=self.device.image)
            text = re.sub(r'\s+', '', str(raw or ''))
            if text:
                texts.append(text)
                boss_type = self._classify_boss_text(text)
                classified.append(boss_type)
                # Every category requires two agreeing non-empty samples.
                stable = classified.count(boss_type) >= 2
                if stable:
                    logger.attr('boss_name', text)
                    return boss_type
            sleep(0.3)
        logger.warning(f'Unstable boss OCR samples: {texts}')
        return None

    @staticmethod
    def _classify_boss_text(text: str) -> BossType:
        # The soul boss can be truncated to “火·合/培火·合” by a dynamic
        # frame, so “合” is retained as its fallback marker. Fire bosses must
        # contain the complete, unambiguous “炽火” marker: 幽火、战火 and
        # every other X火姥姥 are distinct bosses and belong to OTHER.
        if '合' in text:
            return BossType.SOUL
        if '炽火' in text:
            return BossType.FIRE
        return BossType.OTHER

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        """Allow a 9-minute event battle plus its result transition."""
        default_long_timer = self.device.stuck_timer_long
        # The watchdog is checked before each screenshot. It must therefore be
        # slightly longer than the game's 9-minute cap, otherwise it can fire
        # before the forced result frame is captured.
        self.device.stuck_timer_long = Timer(570, count=570).start()
        logger.info('Martial Training battle watchdog set to 570 seconds')
        try:
            return super().battle_wait(random_click_swipt_enable)
        finally:
            # Never leak the event-specific timeout into subsequent tasks.
            self.device.stuck_record_clear()
            self.device.stuck_timer_long = default_long_timer
            self.device.stuck_timer_long.reset()

    def _soul_target(self, config: SwitchSoulConfig):
        if config.enable_switch_by_name:
            group = config.group_name.strip()
            team = config.team_name.strip()
            if not group or not team:
                raise ValueError('Soul group_name and team_name cannot be empty')
            return 'name', group, team
        if config.enable:
            group, team = switch_parser(config.switch_group_team)
            if not (1 <= group <= 7 and 1 <= team <= 4):
                raise ValueError('Soul preset index must be group 1-7 and team 1-4')
            return 'index', group, team
        return None

    def _switch_boss_soul(self, config: SwitchSoulConfig) -> bool:
        try:
            target = self._soul_target(config)
        except (TypeError, ValueError) as error:
            logger.error(f'Invalid boss soul configuration: {error}')
            return False
        if target is None:
            logger.info('Soul switching is disabled for this boss type')
            return True
        if target == self.current_soul_target:
            logger.info(f'Soul target is already active: {target[1:]}')
            return True
        if not self._enter_records_from_boss():
            return False

        if target[0] == 'name':
            self.run_switch_soul_by_name(target[1], target[2])
        else:
            self.run_switch_soul((target[1], target[2]))
        self.exit_shikigami_records()

        if not self.wait_until_appear(self.I_BOSS_PAGE, wait_time=15):
            logger.error('Did not return to boss page after switching souls')
            return False
        self.current_soul_target = target
        logger.info(f'Soul target switched successfully: {target[1:]}')
        return True

    def _enter_records_from_boss(self) -> bool:
        timeout = Timer(15).start()
        while not timeout.reached():
            self.screenshot()
            if self.ocr_appear(self.O_SS_RECORDS_TITLE):
                return True
            if self.appear_then_click(self.I_RECORDS_ENTRY, interval=1.2):
                continue
            if not self.appear(self.I_BOSS_PAGE):
                sleep(0.3)
        logger.error('Cannot enter Shikigami Records from boss page')
        return False

    def _sync_team_lock(self) -> bool:
        should_lock = bool(self.conf.battle_config.lock_team_enable)
        target = self.I_TEAM_LOCKED if should_lock else self.I_TEAM_UNLOCKED
        action = self.I_TEAM_UNLOCKED if should_lock else self.I_TEAM_LOCKED
        timeout = Timer(8).start()
        while not timeout.reached():
            self.screenshot()
            if self.appear(target):
                return True
            if self.appear_then_click(action, interval=1):
                continue
            if not self.appear(self.I_BOSS_PAGE):
                return False
        logger.error('Cannot synchronize team lock state')
        return False

    def _start_boss_battle(self) -> bool:
        timeout = Timer(15).start()
        while not timeout.reached():
            self.screenshot()
            if self.is_in_battle(False) or self.is_in_prepare(False):
                return True
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.8):
                continue
            # Fresh and interrupted bosses expose different challenge buttons,
            # but both buttons enter the same battle flow.
            if (
                self.appear_then_click(self.I_CHALLENGE, interval=1.2)
                or self.appear_then_click(self.I_CONTINUE_CHALLENGE, interval=1.2)
            ):
                continue
        logger.error('Boss challenge did not enter battle')
        return False

    # ------------------------------ page recovery ----------------------------
    def _close_boss_page(self) -> bool:
        timeout = Timer(10).start()
        while not timeout.reached():
            self.screenshot()
            if self.appear(self.I_TRAINING_PAGE) and not self.appear(self.I_BOSS_PAGE):
                return True
            if self.appear_then_click(self.I_BOSS_CLOSE, interval=1):
                continue
        return False

    def _return_to_training_page(self) -> bool:
        timeout = Timer(35).start()
        while not timeout.reached():
            self.screenshot()
            if self.appear_then_click(self.I_BOSS_CLOSE, interval=1):
                continue
            if self.appear(self.I_TRAINING_PAGE):
                self.ui_current = page_martial_training
                return True
            if self.appear_then_click(self.I_TRAINING_ENTRY, interval=1):
                continue
            if self.ui_reward_appear_click():
                continue
            sleep(0.3)
        logger.error('Cannot return to Martial Training page after battle')
        return False

    def _recover_training_page(self) -> bool:
        try:
            self.ui_get_current_page(skip_first_screenshot=False)
            return self.ui_goto(page_martial_training)
        except Exception as error:
            logger.error(f'Cannot recover Martial Training page: {error}')
            return False

    def _return_home(self) -> None:
        logger.hr('Exit Martial Training', 2)
        try:
            self.screenshot()
            if self.appear(self.I_BOSS_PAGE):
                self._close_boss_page()
                self.screenshot()
            if self.appear(self.I_HOME_BUTTON):
                timeout = Timer(15).start()
                while not timeout.reached():
                    self.screenshot()
                    if self.appear(self.I_ACTIVITY_ENTRY):
                        self.ui_current = page_main
                        return
                    if self.appear_then_click(self.I_HOME_BUTTON, interval=1):
                        continue
                logger.warning('Activity home button did not return to courtyard')
                return
            self.ui_get_current_page(skip_first_screenshot=False)
            self.ui_goto(page_main)
        except Exception as error:
            logger.warning(f'Cannot return to courtyard: {error}')
