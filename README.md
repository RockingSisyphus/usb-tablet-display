# USB 平板副屏

把一台 Android 平板变成电脑的**有线副屏**：USB 连接、无需 Wi-Fi，走 Sunshine 串流；
电脑端自动创建虚拟显示器、自动处理 GNOME 的录屏授权与变更弹窗，并把鼠标键盘转发到平板。

整个工具由 **VibeFlow 工作流**驱动：常驻程序负责判断与调度，连接/断开等动作由独立的
工作流完成，所有流程都能单独校验、单独执行、单独审阅。

---

## 功能

- **插上即用**：平板插上电脑后自动建立副屏与串流；拔掉后自动撤销虚拟显示器
- **不崩桌面**：移除虚拟显示器前一定先停串流（避免 GNOME 在投屏中删除显示器导致会话崩溃）
- **全自动授权**：自动登记 Sunshine 的录屏授权、自动确认 GNOME 的显示器变更弹窗
- **自动联网**：平板通过 USB 反向共享电脑网络（gnirehtet），断线后由常驻程序自动拉起
- **命令行与状态**：`usb-tablet` 提供状态查询、开关副屏、重连、安装/回滚等操作
- **控制面板**：应用列表中的「USB 平板副屏」提供图形界面，可查看状态、开关副屏、重连与看日志
- **可回滚**：安装前自动备份用户单元与配置，可一键还原

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

**随项目分发（无需额外安装）**：VibeFlow 内核、gnirehtet、GNOME 扩展、`usb-tablet` 命令行。

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
