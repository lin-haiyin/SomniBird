# 从姿态到抓取

## 先回答三个问题

1. 机械臂没有发现固件内置的“休眠/撤销历史”。`moveJ` 接收目标关节角，执行后不会自动记住可撤销的动作栈。
2. 官方 SDK 有轨迹记录和回放，但那是按时间记录的 JSONL，不是断电后自动回退。回放前仍要确认路径和环境。
3. 本项目把记忆放在工程文件中：一个命名姿态就是 `joints_rad[6] + gripper_rad`。执行前保存当前反馈快照，必要时可以从快照恢复。

## 姿态、角度和夹爪的表达

- `joints_rad`: J1 到 J6 的六个关节角，单位是弧度。
- `gripper_rad`: 夹爪电机角度，官方便捷接口默认开位是 `1.6`、合位是 `0.0`；实际开合幅度要以本机机构和限位为准。
- `duration`: `moveJ` 从当前状态到目标状态的运动时间，单位是秒，不是距离。
- 夹爪速度和力矩限制由 `gripper_control(pos, vel, max_tqu)` 的第二、第三个参数给出。

不要先猜一个“标准零位”或全零姿态。先读取本机反馈，在现场确认姿态安全后运行 `save-current` 保存命名姿态。

## 第一条可用动作链

```text
sleep -> pre_grasp -> approach -> grasp -> lift -> place -> release
```

每个节点先是一个经过检查的命名姿态，动作链再由 Python 按顺序调用。`approach` 和 `lift` 应尽量使用经过验证的中间点，避免从任意位置直接大幅跳到目标位。对象、夹具和桌面改变后，相关姿态必须重新确认。

## 应用层场景复用

连续示教文件是动作的“原始数据”，应用层不应把几千个采样点硬编码进业务代码。`scripts/scene_manager.py` 提供四个入口：

```text
list       查看已录制场景
validate   检查时间戳、六轴点位、夹爪范围和可能丢帧
register   将已检查轨迹登记为有描述的场景
replay     预览或显式执行场景
```

典型流程：

```bash
python scripts/arm_action.py record blanket_scene1 --feel adaptive
python scripts/scene_manager.py validate blanket_scene1
python scripts/scene_manager.py register blanket_scene1 "盖被子"
python scripts/scene_manager.py replay blanket_scene1 --execute
```

## 持续植物摆动（程序化动作）

植物摆动不是 JSONL 回放：JSONL 有固定帧数和结束时间；植物模式以 `plant` 命名姿态为基准，在循环中实时计算 J1/J2/J3/J5 的正弦目标，因此可以一直运行到收到停止请求。当前默认参数是周期 2.20 秒、J1/J2/J3 总摆幅 10°/8°/8°、J5 总摆幅 35°、J5 延迟 0.5 秒。

默认夹爪也会按每个周期执行一次平滑开合：`2.0 -> 0.0`，夹爪速度为 `1.0 rad/s`。可用 `--gripper-open`、`--gripper-close` 和 `--gripper-velocity` 覆盖，开合范围为官方 `[0, 2] rad`。

```bash
python scripts/plant_mode.py start
python scripts/plant_mode.py status
python scripts/plant_mode.py stop
```

也可以从统一场景入口调用：

```bash
python scripts/scene_manager.py plant start
python scripts/scene_manager.py plant status
python scripts/scene_manager.py plant stop
```

HTTP 应用层对应接口为 `POST /api/scenes/plant/start`、`GET /api/scenes/plant/status` 和 `POST /api/scenes/plant/stop`。

`stop` 会让循环退出，再平滑回到 `sleep`；不会把当前摆动点当作新的姿态保存。日志和状态在 `runtime/`，同一时间只允许一个 plant 进程占用 SDK。参数可在启动时覆盖，例如 `--period 1.9 --j5-total 35`。

`validate` 是点位准确性的第一道门：它不会替操作者判断碰撞，但会报告时间倒退、非法关节值、夹爪越界和采样跳变。登记后的场景才进入应用层候选列表。

## 两三天的落地顺序

### 第一天：只做状态和姿态

1. 运行 `check_connection.py`，确认 7 个电机在线且故障码为 0。
2. 让操作员确认一个真实的机械安全休眠姿态，然后运行 `save-current sleep`。
3. 用 `show` 和不带 `--execute` 的 `move` 预览目标，先做小关节变化。
4. 对每次实际执行保留 `records/` 下的前置快照。

### 第二天：固定物体、无视觉抓取

建立并逐个确认 `pre_grasp/approach/grasp/lift/place/release`。先只抓固定位置的物体；夹爪闭合用低速和低力矩，遇到异常立即 `Ctrl+C` 或断电。

### 第三天：普通 USB 相机

相机先只做 OpenCV 2D 任务，例如颜色/轮廓或 ArUco 标记，输出图像中的目标中心和方向。将像素坐标通过一次标定映射到工作平面坐标，再选择已验证的抓取姿态。普通单目相机没有可靠深度，不能直接复用 RealSense/GraspNet 的深度流程；目标高度变化时需要额外测距或限制工作平面。

## 现有命令

```bash
python scripts/pose_bookmark.py list
python scripts/pose_bookmark.py save-current sleep
python scripts/pose_bookmark.py move sleep
python scripts/pose_bookmark.py move sleep --execute
python scripts/pose_bookmark.py restore records/<snapshot>.json --execute
```

所有运动命令都要求显式 `--execute`。默认最大单关节变化阈值是 `0.8 rad`；只有检查过路径后才使用 `--allow-large`。本项目不会调用零点校准脚本，也不会把“休眠姿态”写入电机零点。
# 动作状态机

## 可重复点头动作

`scripts/nod_action.py` 将一次趣味互动动作封装为固定序列：

```text
sleep（J1..J6、夹爪=0°）
  -> 身体姿态（J2=50°，J3=45°）
  -> J4 上下摆动（默认 ±25°，2 次）
  -> 默认回到 sleep2（可用 --return-pose sleep 覆盖）
```

运行：

```bash
python scripts/nod_action.py
```

可调参数示例：

```bash
python scripts/nod_action.py --cycles 3 --amplitude-deg 20 --nod-duration 1.5
```

这里将“点头”解释为 J4 的俯仰摆动，将 J2/J3 解释为身体姿态。若实物观察到 J4 的方向与期望相反，只需交换 `nod_up` 和 `nod_down` 的正负号；不需要重写动作框架。

## 归零的含义

本项目中的“归零”是向 SDK 发送目标角度 `[0,0,0,0,0,0]`（以及夹爪 `0`），让各电机运动到当前配置定义的编码器零位。它不是重新标定电机零点，也不是无路径规划地瞬间跳转。

从任意当前姿态归零，SDK 会按关节目标和设定时间运动；因此仍然需要考虑运动路径、限位和周边干涉。`nod_action.py` 先归零再进入身体姿态，动作结束后再次归零。

## 睡眠娱乐场景 2：手机干预

`scripts/phone_intervention_action.py` 封装了“睡觉时还在玩手机，机械臂插入人与手机之间并开合夹爪”的动作：

```text
当前姿态 -> sleep
  -> J2=100°、J3=75°、J4=15°、J6=+90°
  -> 夹爪大开/大合 3 次
  -> sleep
```

默认夹爪开位为官方常用 `1.6 rad`（约 91.7°），合位为 `0 rad`。J6 的 `+90°` 是本项目对“逆时针”的暂定符号约定；如果现场观察方向相反，将脚本中的 `90.0` 改为 `-90.0` 即可。

运行：

```bash
python scripts/phone_intervention_action.py
```
