# USB 平板副屏（VibeFlow）

在 Ubuntu GNOME/Wayland 上把 Android 平板作为 USB 副屏。业务实现为 VibeFlow 工作流，
位于 `usb_tablet_display/`。

- 入口工作流：`daemon`（常驻）、`control`（CLI 契约）、`install`（部署/修复）。
- 双击 `vibeflow-preview.html` 打开离线预览；`python run.py review --config <workflow>` 生成审阅快照。
- 内核与使用者文档见 `kernel/docs/README.md`，开发入口见 `AGENTS.md`。

```bash
python run.py validate --config usb_tablet_display/configs/daemon.jsonc
python run.py run --config usb_tablet_display/configs/daemon.jsonc --input usb_tablet_display/probes/daemon.json
```

本发行包已移除 VibeFlow 自带的最小示例流程与 JavaScript 示例 root，仅保留实际业务 root。
