## 这里是约定哪些是需要更新的     ./script_test.py 是对应的测试

## 拾此一瞬活动适配

进入路径：庭院 → 拾此一瞬活动主页 → 磐长故地地图 → 已开放区域的挑战页。
`as/pages.json` 定义各层识别和入口，`page.py` 定义双向导航。

本期只适配 `pass`，默认运行顺序为 `pass`；已有配置中的 `ap`、`ap100`、`boss` 会跳过。
地图挑战无法切换门票种类，不操作旧的消耗模式切换按钮。

- 优先五倍且活动门票至少 5 张时点击困难，否则点击简单。困难免费五倍，
  不读取/消耗五倍券，也不点击五倍勾选框。每场返回后重新读取门票，少于 5 张立即改为简单。
- 简单/困难按钮同时显示，切换后连续两帧识别挑战消耗为 1/5 张才继续。
- 地图上的怪物头像随区域变化，因此匹配公共红色“战斗”旗帜，而不是头像。
  `as_battle_node.png` 在地图范围搜索，`RuleImage.match()` 更新点击位置。
  只截取旗帜文字，排除头像、进度百分比和周围光效，入口移动后仍可识别。
  选择当前可见且匹配成功的入口；区域结束回到地图后重新定位。
- 模式无法确认时不会点击挑战。挑战次数仍按实际战斗场数统计，五倍战斗算 1 场。

旧 `anniversary_timesx5` 字段保留兼容已保存的配置，本期 PASS 不受此开关影响。
资源变动应编辑 JSON 后使用 `AssetsExtractor('tasks/ActivityShikigami').extract()` 生成 `assets.py`。



## 关于页面导航（`./as/page.json`文件）

#### 图片 `shi` 表示进入到活动的主页面，截图的时候往上截图一点，因为快结束的时候图片下方会显示还有多少小时结束

![image-20251220103009134](https://runhey-img-stg1.oss-cn-chengdu.aliyuncs.com/img3/202512201030265.png)

#### 图片`to_battle_main` 和 `to_battle_boss` 分别表示进入默认的挑战界面和boss挑战界面

![image-20251220103500219](https://runhey-img-stg1.oss-cn-chengdu.aliyuncs.com/img3/202512201035354.png)

#### 图片`check_battle_main` 表示到达了这个默认战斗界面       |  `battle_main_to_records`表示从这里进入式神录来切换御魂

#### 图片`check_battle_boss`  和 `battle_boss_to_records` 类似的

![image-20251220104003594](https://runhey-img-stg1.oss-cn-chengdu.aliyuncs.com/img3/202512201040758.png)

#### 可能需要更新的如 `back_green`、 `red_exit` 和 `skip_button`  这些表示退出的时候碰到的时候会出现的

#### OAS 内部有一个专门的类来存放通用的图片。  路径在`./tasks/GlobalGame/ui`  有需要直接使用

![image-20251220104718877](https://runhey-img-stg1.oss-cn-chengdu.aliyuncs.com/img3/202512201047907.png)

## 关于活动切换（`./as/image.json`文件）

#### 图片 `climb_mode_pass` 门票爬塔标志 | `climb_mode_ap` 体力爬塔标志 | `climb_mode_switch` 切换门票爬塔和体力爬塔按钮

![climb_mode_pass](https://raw.githubusercontent.com/AzurTian/ImgBed/master/blog/climb_mode_pass.png)

![climb_mode_ap](https://raw.githubusercontent.com/AzurTian/ImgBed/master/blog/1.png)

![climb_mode_switch](https://raw.githubusercontent.com/AzurTian/ImgBed/master/blog/2.png)


## 关于战斗更新 （`./fire/ocr.json`文件）

#### OCR `remain_ap`  表示体力模式下剩余多少次数  `fire` 表示点击挑战

![image-20251220111306772](https://runhey-img-stg1.oss-cn-chengdu.aliyuncs.com/img3/202512201113931.png)

活动币模式下 `remain_pass`  和 boss 模式下也是类似

![image-20251220111505769](https://runhey-img-stg1.oss-cn-chengdu.aliyuncs.com/img3/202512201115927.png)

