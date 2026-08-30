# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum  # type: ignore
from datetime import datetime, time  # type: ignore
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time, TimeDelta
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class Layer(str, Enum):
    YANWU: str = "鬼兵演武"
    MIJING: str = "兵藏秘境"
    CHUANCHENG: str = "传承试炼"
    MENGXU: str = "梦虚秘境"


class SkillMode(str, Enum):
    PVE = 'PVE'
    PVP = 'PVP'


MIJING_SKILLS = ('八华斩', '无畏', '暴击伤害', '默认祝福', '默认属性')
MENGXU_SKILLS = ('同调祝福', '韵迟祝福', '弥天祝福', '叠辉祝福', '敛神祝福', '速度祝福')


def _validate_skill_priority(value: str, allowed_skills: tuple[str, ...]) -> str:
    """规范并校验技能优先级，确保每个已支持技能恰好出现一次。"""
    if not isinstance(value, str):
        raise ValueError('技能优先级必须是字符串')

    skills = [skill.strip() for skill in value.replace('＞', '>').split('>') if skill.strip()]
    duplicated = sorted({skill for skill in skills if skills.count(skill) > 1})
    unknown = [skill for skill in skills if skill not in allowed_skills]
    missing = [skill for skill in allowed_skills if skill not in skills]
    if duplicated or unknown or missing or len(skills) != len(allowed_skills):
        details = []
        if duplicated:
            details.append(f"重复：{', '.join(duplicated)}")
        if unknown:
            details.append(f"未知：{', '.join(unknown)}")
        if missing:
            details.append(f"缺少：{', '.join(missing)}")
        raise ValueError(f"技能优先级配置无效（{'；'.join(details)}）")
    return ' > '.join(skills)


class HeroTestConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    # 副本选择
    layer: Layer = Field(
        default=Layer.YANWU,
        description="选择要打的关卡。\n兵藏秘境升级顺序八华斩->无畏 -> 暴击伤害 -> 默认祝福 -> 默认属性\n"
                    "藤原道长矩阵博士攻略:https://www.bilibili.com/opus/1162129635334422531",
    )
    skill_mode: SkillMode = Field(
        default=SkillMode.PVE,
        description="技能本技能偏向。兵藏秘境和梦虚秘境会分别使用下方对应的 PVE/PVP 技能优先级。",
    )
    mijing_pve_skill_priority: str = Field(
        default='八华斩 > 无畏 > 暴击伤害 > 默认祝福 > 默认属性',
        description="兵藏秘境 PVE 技能优先级。使用“>”分隔，排在左侧的技能优先选择；必须包含全部五项且不能重复。",
    )
    mijing_pvp_skill_priority: str = Field(
        default='八华斩 > 无畏 > 暴击伤害 > 默认祝福 > 默认属性',
        description="兵藏秘境 PVP 技能优先级。使用“>”分隔，排在左侧的技能优先选择；必须包含全部五项且不能重复。",
    )
    mengxu_pve_skill_priority: str = Field(
        default='同调祝福 > 韵迟祝福 > 弥天祝福 > 叠辉祝福 > 敛神祝福 > 速度祝福',
        description="梦虚秘境 PVE 技能优先级。使用“>”分隔，排在左侧的技能优先选择；必须包含全部六项且不能重复。",
    )
    mengxu_pvp_skill_priority: str = Field(
        default='同调祝福 > 韵迟祝福 > 弥天祝福 > 叠辉祝福 > 敛神祝福 > 速度祝福',
        description="梦虚秘境 PVP 技能优先级。使用“>”分隔，排在左侧的技能优先选择；必须包含全部六项且不能重复。",
    )

    @field_validator('mijing_pve_skill_priority', 'mijing_pvp_skill_priority')
    @classmethod
    def validate_mijing_skill_priority(cls, value: str) -> str:
        return _validate_skill_priority(value, MIJING_SKILLS)

    @field_validator('mengxu_pve_skill_priority', 'mengxu_pvp_skill_priority')
    @classmethod
    def validate_mengxu_skill_priority(cls, value: str) -> str:
        return _validate_skill_priority(value, MENGXU_SKILLS)

    def skill_priority(self, layer: Layer) -> list[str]:
        """按副本和技能偏向返回已校验的技能优先级。"""
        priority_field = {
            (Layer.MIJING, SkillMode.PVE): self.mijing_pve_skill_priority,
            (Layer.MIJING, SkillMode.PVP): self.mijing_pvp_skill_priority,
            (Layer.MENGXU, SkillMode.PVE): self.mengxu_pve_skill_priority,
            (Layer.MENGXU, SkillMode.PVP): self.mengxu_pvp_skill_priority,
        }.get((layer, self.skill_mode))
        if priority_field is None:
            return []
        return [skill.strip() for skill in priority_field.split('>')]
    # 限制时间
    limit_time: Time = Field(default=Time(minute=30), description="limit_time_help")
    # 限制次数
    limit_count: int = Field(default=100, description="limit_count_help")
    # 是否开启经验加成
    exp_50_buff_enable_help: bool = Field(default=False, description="打开经验50%加成")
    exp_100_buff_enable_help: bool = Field(
        default=False, description="打开经验100%加成"
    )


class HeroTest(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    herotest: HeroTestConfig = Field(default_factory=HeroTestConfig)
    general_battle: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    switch_soul_config: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
