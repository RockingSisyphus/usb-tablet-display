# 日常运行 root

日常运行的三个工作流：`daemon`（常驻）、`connect`（连接）、`disconnect`（断开），
另加 `internet`（联网检查）。共用节点在项目级 `nodes/`，维护类工作流在
`usb_tablet_maintenance/`。

常用命令：

```bash
python run.py validate   --config usb_tablet_display/configs/daemon.jsonc
python run.py architecture --config usb_tablet_display/configs/daemon.jsonc \
        --output usb_tablet_display/docs/daemon-architecture.jsonc
python run.py run        --config usb_tablet_display/configs/daemon.jsonc \
        --input usb_tablet_display/probes/daemon.json
```

常驻入口以 `max_iterations: null` 循环；写入 `/tmp/usb-tablet-display/shutdown` 后，
循环会在下一轮退出。整体说明见项目根 `README.md`。
