# USB 平板副屏

把一台 Android 平板变成电脑的**有线副屏**：USB 连接、无需 Wi-Fi，走 Sunshine 串流；
电脑端自动创建虚拟显示器、自动处理 GNOME 的录屏授权与变更弹窗，并把鼠标键盘转发到平板。

整个工具由 **VibeFlow 工作流**驱动：常驻程序负责判断与调度，连接/断开等动作由独立的
工作流完成，所有流程都能单独校验、单独执行、单独审阅。

面向 Ubuntu（GNOME/Mutter）的完整自动化方案：安装时创建虚拟副屏（重启生效），插上平板即自动建屏、启动 Sunshine 串流、
处理系统授权与"保留更改"弹窗、转发鼠标键盘，并让平板反向共享电脑网络。

串流方案基于 **Sunshine**（电脑端串流服务）与 **Moonlight**（平板端播放器）：电脑把扩展桌面
编码后经 USB 网络推给平板，平板上的 Moonlight 解码显示并回传操作。

---

## 功能

- **插上即用**：虚拟副屏由安装流程一次性创建；平板插上后自动启用与串流，拔掉后自动撤销
- **命令行与状态**：`usb-tablet` 提供状态查询、开关副屏、重连、安装/回滚等操作
- **控制面板**：应用列表中的「USB 平板副屏」提供图形界面，可查看状态、开关副屏、重连与看日志
- **可回滚**：安装前自动备份用户单元与配置，可一键还原

## 查看项目架构

项目根目录的 **`vibeflow-preview.html`** 是离线可浏览的架构视图：双击打开即可看到全部工作流、
节点、数据流与历史快照，无需启动任何服务。逐工作流的详细文档在
`usb_tablet_display/docs/*-architecture.jsonc` 与 `usb_tablet_maintenance/docs/*-architecture.jsonc`；
文字版总览见 [docs/工作流说明.md](docs/工作流说明.md)。

## 目录结构

```
nodes/                       两个 root 共用的业务节点（设置、状态、设备探测、副屏判断）
plugins/                     （可选）项目级治理插件
usb_tablet_display/          日常运行 root
  configs/                   daemon / connect / disconnect / internet
  nodes/                     串流、会话、决策、请求等私有节点
  nodeset_types/             常驻循环的可复用子图
usb_tablet_maintenance/      维护 root
  configs/                   status / display-check / guard-check / install
  nodes/                     汇总状态、安装操作等私有节点
services/                    三个 systemd 用户单元模板（含 @ROOT@ 占位符）
cli/                         usb-tablet 命令行入口与联网运行器
gnome-shell-ext/             自动确认显示器变更的 GNOME 扩展
gui/                         GTK4 控制面板源码
desktop/                     桌面入口模板（安装时写入应用列表）
install/                     tablet.toml 模板
vendor/gnirehtet/            随项目分发的反向联网程序
docs/                        架构文档、部署清单、迁移与验收记录
tools/verify.sh              一键门禁
tests/                       行为级测试
```

## 依赖

**需要用户自己安装（安装器不代劳）**

| 依赖 | 用途 |
|---|---|
| Python ≥ 3.11 | 运行 VibeFlow 与工具（需要 `tomllib`） |
| PyGObject（`python3-gi`） | 与 GNOME 的 D-Bus 交互 |
| adb（platform-tools）+ udev 规则 | 访问平板；没有 udev 规则时需要 sudo |
| Sunshine | 串流服务端，需先运行过一次以生成 portal token |
| GNOME Shell / Mutter | 副屏布局与录屏授权 |
| NetworkManager | 需要名为 `android-usb-direct` 的连接 |
| 平板侧 Moonlight | 投屏客户端 |
| 平板 USB 调试 | 在开发者选项里打开并授权本机 |
| Sunshine 至少运行过一次 | 生成录屏授权（portal token），并让系统出现可用的虚拟副屏 |

**随项目分发（无需额外安装）**：VibeFlow 内核、gnirehtet、GNOME 扩展、`usb-tablet` 命令行与控制面板。

### 虚拟副屏的前置条件与自动创建

虚拟副屏**不是 Sunshine 创建的**（Sunshine/Moonlight 只负责编码与播放），而是系统级的
**EDID 覆盖**：给一个实际未连接的 DP 接口喂入自造的 EDID，并强制其保持连接。

`install` 会自动检测并创建：

1. 检测：内核参数里已有 `drm.edid_firmware`，或 `/sys/class/drm/*-DP-*/status` 为 `connected`
2. 未就绪时写入 `install/edid/virtual-display.bin` 到 `/lib/firmware/edid/`
3. 在 `/etc/default/grub` 的 `GRUB_CMDLINE_LINUX_DEFAULT` 中补齐：
   `drm.edid_firmware=DP-1:edid/virtual-display.bin video=DP-1:e`
4. 执行 `sudo update-grub`

**需要 sudo 权限，且重启后才生效。** 自检（`usb-tablet install verify`）会报告
`virtual_display` 与 `sunshine_portal_token` 两项，缺失时给出明确提示。

## 目录结构

```
nodes/                       两个 root 共用的业务节点（设置、状态、设备探测、副屏判断）
plugins/                     （可选）项目级治理插件
usb_tablet_display/          日常运行 root
  configs/                   daemon / connect / disconnect / internet
  nodes/                     串流、会话、决策、请求等私有节点
  nodeset_types/             常驻循环的可复用子图
usb_tablet_maintenance/      维护 root
  configs/                   status / display-check / guard-check / install
  nodes/                     汇总状态、安装操作等私有节点
services/                    三个 systemd 用户单元模板（含 @ROOT@ 占位符）
cli/                         usb-tablet 命令行入口与联网运行器
gnome-shell-ext/             自动确认显示器变更的 GNOME 扩展
gui/                         GTK4 控制面板源码
desktop/                     桌面入口模板（安装时写入应用列表）
install/                     tablet.toml 模板
vendor/gnirehtet/            随项目分发的反向联网程序
docs/                        架构文档、部署清单、迁移与验收记录
tools/verify.sh              一键门禁
tests/                       行为级测试
```

## 依赖

**需要用户自己安装（安装器不代劳）**

| 依赖 | 用途 |
|---|---|
| Python ≥ 3.11 | 运行 VibeFlow 与工具（需要 `tomllib`） |
| PyGObject（`python3-gi`） | 与 GNOME 的 D-Bus 交互 |
| adb（platform-tools）+ udev 规则 | 访问平板；没有 udev 规则时需要 sudo |
| Sunshine | 串流服务端，需先运行过一次以生成 portal token |
| GNOME Shell / Mutter | 副屏布局与录屏授权 |
| NetworkManager | 需要名为 `android-usb-direct` 的连接 |
| 平板侧 Moonlight | 投屏客户端 |
| 平板 USB 调试 | 在开发者选项里打开并授权本机 |
| Sunshine 至少运行过一次 | 生成录屏授权（portal token），并让系统出现可用的虚拟副屏 |

**随项目分发（无需额外安装）**：VibeFlow 内核、gnirehtet、GNOME 扩展、`usb-tablet` 命令行与控制面板。

### 关于"副屏是否存在"的自动检测

- **安装脚本不会创建虚拟副屏**。虚拟副屏由 Sunshine 通过系统的屏幕录制门户（Portal）创建，
  系统里一旦存在就会一直保留（未启用时处于"未激活"状态）。
- `install all` 的自检会检查 **Sunshine 是否已安装、portal token 是否已生成**；缺少时会打印提示，
  让你先启动一次 Sunshine，而不是在首次连接时才失败。
- 运行期的连接流程会校验副屏是否可用：已存在就直接配置；**不存在时会自动启动一次 Sunshine
  让系统创建虚拟副屏，最多等 20 秒**，仍失败才报错并重试，不会静默假装成功。

## 安装

```bash
python3 cli/main.py install all
```

依次完成：写入三个用户单元（协调服务 / 常驻程序 / 联网）→ 写 `~/.local/bin/usb-tablet`
→ 安装并启用 GNOME 扩展 → 生成并自动填充 `~/.config/usb-tablet-display/tablet.toml`
（`serial` 取 `adb devices` 中唯一设备，`host_name` 取当前主机名）→ 平板已连接时安装
gnirehtet App → 环境自检并列出缺失项。

其他安装动作：

```bash
usb-tablet install verify      # 只做环境自检
usb-tablet install backup      # 备份用户单元与配置
usb-tablet install restore     # 还原（配合 USB_TABLET_BACKUP 指定备份目录）
usb-tablet install quiesce     # 停止并停用本栈服务
```

缺少 `android-usb-direct` 时，自检会给出可直接执行的命令：

```bash
nmcli connection add type ethernet ifname '*' con-name android-usb-direct \
  ipv4.method auto ipv4.never-default yes ipv4.ignore-auto-routes yes \
  ipv4.ignore-auto-dns yes ipv6.method disabled
```

## 使用

```bash
usb-tablet status              # 平板 / 调试 / 副屏 / 串流 / 网络 状态
usb-tablet status --json       # 同上，JSON 输出
usb-tablet enable              # 打开副屏（交给常驻程序执行连接）
usb-tablet disable             # 关闭副屏（先停串流再撤销虚拟显示器）
usb-tablet reconnect           # 重建一次会话
usb-tablet set-auto off        # 关闭自动模式（插拔不再自动动作）
usb-tablet auto                # 恢复自动模式
usb-tablet logs                # 查看常驻程序日志
usb-tablet gui                 # 打开图形控制面板（应用列表里也有入口）
```

服务（systemd 用户单元）：

```bash
systemctl --user status  usb-tablet-daemon usb-tablet-coordinator usb-tablet-internet
systemctl --user restart usb-tablet-daemon
journalctl --user -u usb-tablet-daemon -f
```

配置文件：`~/.config/usb-tablet-display/tablet.toml`

| 字段 | 含义 |
|---|---|
| `serial` | 平板 adb 序列号 |
| `host_name` | Moonlight 中显示的电脑名 |
| `connector` | 虚拟副屏接口名，通常 `DP-1` |
| `app_id` | Moonlight 中该电脑条目的应用 ID |
| `connection` | NetworkManager 连接名 |
| `dns` | 平板使用的 DNS |

## 架构速览

- **常驻程序**（`daemon`）：每轮读取状态 → 检查平板 → 定期检查网络 → 处理用户命令 →
  判断是否正在投屏 → 决定"连接 / 断开 / 什么都不做"。
- **连接 / 断开**：独立工作流，由常驻程序通过 VibeFlow 协调服务异步调用，结果以结构化
  状态回传；连接失败会明确报错，不会假装成功。
- **维护类**（状态、检查副屏、保护检查、安装）：放在 `usb_tablet_maintenance` root，
  只做只读检查或部署，不影响日常会话。
- 详细说明见 [docs/工作流说明.md](docs/工作流说明.md) 与各工作流的 `docs/*-architecture.jsonc`。

## 开发

```bash
./tools/verify.sh                                  # 全量门禁：8 份工作流 + 质量检查 + 测试
python3 run.py validate   --config usb_tablet_display/configs/daemon.jsonc
python3 run.py architecture --config usb_tablet_display/configs/daemon.jsonc \
        --output usb_tablet_display/docs/daemon-architecture.jsonc
python3 run.py review     --config usb_tablet_display/configs/daemon.jsonc
python3 -m pytest tests/ -q
```

离线浏览全部工作流：打开 `vibeflow-preview.html`。

## 已知限制

1. 本栈只管理用户级单元与配置；系统级 udev / NetworkManager dispatcher / Sunshine dropin
   需要用户自行维护。
2. 联网以旧式 gnirehtet 客户端 App 作为平板端组件，需要设备上安装（安装器可自动装）。
3. 单次会话从插入到出画面约 1–2 分钟（Sunshine 启动 + 平板端登记 + 串流校验）。
4. 图形界面未迁移（`usb-tablet gui` 会提示）。
