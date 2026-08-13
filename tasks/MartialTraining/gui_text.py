from copy import deepcopy


TASK_NAME = 'MartialTraining'
TASK_LABEL = '修行合训'


SCHEDULER_ARGUMENTS = {
    'enable': ('启用任务', '将修行合训加入任务调度器'),
    'next_run': ('下一次运行时间', '任务调度器计算出的下一次运行时间'),
    'priority': ('任务优先级', '数字越小优先级越高，可设置为 1 至 15'),
    'success_interval': ('成功后运行间隔', '任务成功后，经过该时间再次执行'),
    'failure_interval': ('失败后运行间隔', '任务失败后，经过该时间再次执行'),
    'server_update': ('强制执行时间', '非默认 09:00:00 时，任务结束后按该时间安排下一次执行'),
    'delay_date': ('强制执行日期间隔', '设置在几天后按强制执行时间运行，默认为第二天'),
    'float_time': ('随机延迟时间', '在该时间范围内随机延迟，降低固定时间运行的特征'),
}

TRAINING_ARGUMENTS = {
    'limit_time': ('限制运行时间', '达到该运行时间后结束修行合训任务'),
    'run_sequence': ('门票执行顺序', '支持 normal（普通门票）和 special（特殊门票），使用英文逗号分隔'),
    'normal_enable': ('启用普通门票', '按设置顺序搜索并挑战普通门票鬼王'),
    'normal_limit': ('普通门票次数限制', '仅在成功搜索出鬼王后计数，已有鬼王不会重复计数'),
    'special_enable': ('启用特殊门票', '按设置顺序搜索并挑战特殊门票鬼王'),
    'special_limit': ('特殊门票次数限制', '仅在成功搜索出鬼王后计数，已有鬼王不会重复计数'),
}

SOUL_ARGUMENTS = {
    'enable': ('启用该功能', '是否为该类型 Boss 切换御魂预设'),
    'switch_group_team': (
        '御魂装配分组设置',
        '使用“预设组,预设队伍”格式，例如 1,2；预设组支持 1 至 7，预设队伍支持 1 至 4',
    ),
    'enable_switch_by_name': ('通过名称切换御魂预设', '通过 OCR 识别御魂分组名和队伍名进行切换'),
    'group_name': ('御魂分组名', '按名称切换时需要识别的御魂分组名称'),
    'team_name': ('队伍名', '按名称切换时需要识别的预设队伍名称'),
}

BATTLE_ARGUMENTS = {
    'lock_team_enable': ('锁定阵容', '锁定当前阵容；启用后无法同时使用预设队伍切换'),
    'preset_enable': ('启用切换预设队伍', '第一次进入战斗准备界面时切换队伍预设'),
    'preset_group': ('预设组序号', '可设置为 1 至 7'),
    'preset_team': ('预设队伍序号', '可设置为 1 至 5'),
    'green_enable': ('启用我方绿标', '战斗开始时点击设置的我方单位'),
    'green_mark': ('我方绿标位置', '可选左一、左二、左三、左四、左五或主阴阳师'),
    'random_click_swipt_enable': ('战斗时随机点击或滑动', '防封优化；此功能可能与绿标功能冲突'),
}


GUI_GROUPS = {
    'scheduler': ('任务调度设置', SCHEDULER_ARGUMENTS),
    'training_config': ('修行合训任务设置', TRAINING_ARGUMENTS),
    'fire_boss_soul': ('炽火 Boss 御魂设置', SOUL_ARGUMENTS),
    'soul_boss_soul': ('合魂 Boss 御魂设置', SOUL_ARGUMENTS),
    'other_boss_soul': ('其他 Boss 御魂设置', SOUL_ARGUMENTS),
    'battle_config': ('战斗设置', BATTLE_ARGUMENTS),
}

GROUP_NAMES = {label: name for name, (label, _) in GUI_GROUPS.items()}

VALUE_NAMES = {
    ('training_config', 'run_sequence'): {
        'normal': '普通门票',
        'special': '特殊门票',
    },
    ('battle_config', 'green_mark'): {
        'green_left1': '左一',
        'green_left2': '左二',
        'green_left3': '左三',
        'green_left4': '左四',
        'green_left5': '左五',
        'green_main': '主阴阳师',
    },
}


def normalize_task_name(task: str) -> str:
    if task in {TASK_NAME, TASK_LABEL, 'martial_training'}:
        return TASK_NAME
    return task


def display_task_name(task: str) -> str:
    return TASK_LABEL if task == TASK_NAME else task


def normalize_config_path(task: str, group: str = '', argument: str = '') -> tuple[str, str, str]:
    task = normalize_task_name(task)
    if task != TASK_NAME:
        return task, group, argument

    internal_group = GROUP_NAMES.get(group, group)
    group_config = GUI_GROUPS.get(internal_group)
    if group_config:
        _, arguments = group_config
        argument_names = {label: name for name, (label, _) in arguments.items()}
        argument = argument_names.get(argument, argument)
    return task, internal_group, argument


def _map_value(value, mapping: dict[str, str], reverse: bool = False):
    if hasattr(value, 'value'):
        value = value.value
    if reverse:
        mapping = {label: name for name, label in mapping.items()}
    if isinstance(value, str) and ',' in value:
        return ','.join(mapping.get(item.strip(), item.strip()) for item in value.split(','))
    return mapping.get(value, value)


def normalize_config_value(task: str, group: str, argument: str, value):
    task, group, argument = normalize_config_path(task, group, argument)
    if task == TASK_NAME:
        mapping = VALUE_NAMES.get((group, argument))
        if mapping:
            value = _map_value(value, mapping, reverse=True)
    return task, group, argument, value


def localize_gui_config(config: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Return Chinese display keys while keeping stored config keys unchanged."""
    localized = {}
    for group_name, items in config.items():
        group_label, arguments = GUI_GROUPS.get(group_name, (group_name, {}))
        localized_items = []
        for source_item in items:
            item = deepcopy(source_item)
            argument_name = item['name']
            label, help_text = arguments.get(argument_name, (argument_name, item.get('description', '')))
            item['name'] = label
            item['title'] = label
            value_mapping = VALUE_NAMES.get((group_name, argument_name))
            if value_mapping:
                item['default'] = _map_value(item['default'], value_mapping)
                item['value'] = _map_value(item['value'], value_mapping)
                if 'enumEnum' in item:
                    item['enumEnum'] = [_map_value(value, value_mapping) for value in item['enumEnum']]
            if help_text:
                item['description'] = help_text
            else:
                item.pop('description', None)
            localized_items.append(item)
        localized[group_label] = localized_items
    return localized
