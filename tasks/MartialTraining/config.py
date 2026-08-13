# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import time, timedelta

from pydantic import Field, field_validator

from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler


class TrainingConfig(ConfigBase):
    """修行合训的门票顺序和停止条件。"""

    limit_time: Time = Field(default=Time(minute=30), description='limit_time_help')
    run_sequence: str = Field(default='normal,special', description='martial_training_run_sequence_help')
    normal_enable: bool = Field(default=True, description='normal_enable_help')
    normal_limit: int = Field(default=50, ge=0, description='normal_limit_help')
    special_enable: bool = Field(default=True, description='special_enable_help')
    special_limit: int = Field(default=50, ge=0, description='special_limit_help')

    @field_validator('run_sequence', mode='before')
    @classmethod
    def validate_run_sequence(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError('run_sequence must be a string')
        modes = [item.strip().lower() for item in value.split(',') if item.strip()]
        if not modes:
            raise ValueError('run_sequence cannot be empty')
        invalid = [item for item in modes if item not in {'normal', 'special'}]
        if invalid:
            raise ValueError('run_sequence only supports normal and special')
        if len(modes) != len(set(modes)):
            raise ValueError('run_sequence cannot contain duplicate modes')
        return ','.join(modes)

    @property
    def run_sequence_v(self) -> list[str]:
        return [item.strip() for item in self.run_sequence.split(',') if item.strip()]

    @property
    def limit_time_v(self) -> timedelta:
        if isinstance(self.limit_time, time):
            return timedelta(
                hours=self.limit_time.hour,
                minutes=self.limit_time.minute,
                seconds=self.limit_time.second,
            )
        return self.limit_time


class MartialTrainingBattleConfig(GeneralBattleConfig):
    # 修行合训可以在挑战页预先锁定阵容，默认开启后准备页会自动开战。
    lock_team_enable: bool = Field(default=True, description='lock_team_enable_help')


class MartialTraining(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    training_config: TrainingConfig = Field(default_factory=TrainingConfig)
    fire_boss_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    soul_boss_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    other_boss_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    battle_config: MartialTrainingBattleConfig = Field(default_factory=MartialTrainingBattleConfig)
