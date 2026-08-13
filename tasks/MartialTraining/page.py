# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from tasks.GameUi.page import Page, page_main
from tasks.MartialTraining.assets import MartialTrainingAssets as MTA
from tasks.Component.RightActivity.assets import RightActivityAssets as RAA


# 武道大会活动主页，页面上可见“修行合训”入口。
page_martial_training_event = Page(MTA.I_TRAINING_ENTRY)
page_martial_training_event.link(button=MTA.I_HOME_BUTTON, destination=page_main)
# The courtyard activity icons rotate. This follows ActivityShikigami's
# established page-link convention: try the target first, otherwise click the
# carousel toggle until the target comes into view.
page_main.link(
    button=[MTA.I_ACTIVITY_ENTRY, RAA.I_TOGGLE_BUTTON],
    destination=page_martial_training_event,
)

# 修行合训的搜索鬼王页面。
page_martial_training = Page(MTA.I_TRAINING_PAGE)
page_martial_training.link(button=MTA.I_HOME_BUTTON, destination=page_main)
page_martial_training_event.link(button=MTA.I_TRAINING_ENTRY, destination=page_martial_training)
