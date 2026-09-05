## 这里是约定哪些是需要更新的     ./script_test.py 是对应的测试

## 十周年活动适配

进入路径：庭院 → 拾光永恒活动主页 → 亘地回响战斗主页 → 虚无精锐挑战页。
`as/pages.json` 定义各层识别和入口，`page.py` 定义双向导航。

`general_climb.anniversary_timesx5` 默认开启，配合原有 `prefer_timesx5` 使用：

- PASS：优先五倍且活动门票至少 5 张时点击困难，否则点击简单。困难免费五倍，
  不读取/消耗五倍券，也不点击五倍勾选框。每场返回后重新读取门票，少于 5 张立即改为简单。
- AP：每次消耗 6 体力及 1 张常规门票。优先五倍、五倍券大于 0、体力至少 30、
  常规门票至少 5 张时开启五倍，否则关闭。不足单次所需资源则结束本阶段。
- 简单/困难按钮同时显示，切换后连续两帧识别挑战消耗为 1/5 张才继续。
  从困难 PASS 切换 AP 时，先切简单，再切体力消耗模式。
- 模式无法确认时不会点击挑战。挑战次数仍按实际战斗场数统计，五倍战斗算 1 场。

后续恢复普通活动时，更新当期资源并关闭 `anniversary_timesx5`，恢复 PASS 使用五倍券的原规则。
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

