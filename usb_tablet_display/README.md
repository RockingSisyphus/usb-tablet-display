# USB 平板副屏（业务 root）

本 root 承载实际业务实现，替代 VibeFlow 发行包自带的最小示例。

## 目录

- `configs/`：三个入口工作流声明。`daemon.jsonc` 为常驻入口（无限循环），后续加入 `control.jsonc`、`install.jsonc`。
- `nodeset_types/`：可复用子图，daemon 与一次性入口共享。
- `nodes/`：业务 Node，按职责分目录；外部命令统一走 `nodes/io/run_cmd.py`。
- `probes/`：验证运行输入。
- `docs/`：生成的架构审阅文档。

## 常用命令

```bash
python run.py validate   --config usb_tablet_display/configs/daemon.jsonc
python run.py architecture --config usb_tablet_display/configs/daemon.jsonc --output usb_tablet_display/docs/daemon-architecture.jsonc
python run.py run        --config usb_tablet_display/configs/daemon.jsonc --input usb_tablet_display/probes/daemon.json
python run.py review     --config usb_tablet_display/configs/daemon.jsonc
```

`daemon` 以 `max_iterations: null` 常驻；写入 `shutdown` 标记文件后，循环在下一轮 tick 退出。
