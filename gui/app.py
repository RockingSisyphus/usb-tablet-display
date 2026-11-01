"""USB 平板副屏控制面板（GTK4 + libadwaita），通过命令行与后台服务交互。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "cli" / "main.py")]
UNITS = ["usb-tablet-daemon.service", "usb-tablet-coordinator.service",
         "usb-tablet-internet.service"]

LABELS = {
    "present": "已连接", "absent": "未连接", "unknown": "未知",
    "device": "已授权", "unauthorized": "等待平板授权", "offline": "离线",
    "unavailable": "不可用", "enabled": "已启用", "disabled": "已关闭",
    "connecting": "连接中", "connected": "已连接", "failed": "失败",
    "waiting": "等待中", "idle": "服务就绪，客户端未串流",
    "ok": "可用", "disconnected": "未连接", "ready": "就绪",
    "sink": "电脑为平板供电", "source": "方向异常：平板向外供电",
    "usb": "USB 直连",
}

ROWS = (("usb", "USB 平板"), ("adb", "USB 调试"), ("display", "副屏输出"),
        ("stream", "客户端串流"), ("internet", "电脑提供的网络"),
        ("usb_interface", "USB 网卡"), ("serial", "平板序列号"))


def cli(*args, timeout=90):
    done = subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=timeout)
    return done.returncode, done.stdout, done.stderr


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="USB 平板副屏",
                         default_width=620, default_height=660)
        self.busy = False
        self.refreshing = False
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        self.banner = Gtk.Label(wrap=True, margin_start=20, margin_end=20, margin_bottom=12)
        box.append(self.banner)

        page = Adw.PreferencesPage()
        controls = Adw.PreferencesGroup(title="连接管理")
        self.automatic = Adw.SwitchRow(title="自动启用副屏",
                                       subtitle="平板插上后自动建立副屏与串流")
        self.automatic.connect("notify::active", self.toggle)
        controls.add(self.automatic)
        buttons = Gtk.Box(spacing=8, margin_top=12, margin_bottom=12, homogeneous=True)
        for title, action in (("立即启用", "enable"), ("本次关闭", "disable"),
                              ("重新连接", "reconnect")):
            button = Gtk.Button(label=title)
            button.connect("clicked", lambda _, a=action: self.request(a))
            buttons.append(button)
        controls.add(buttons)
        controls.add(Gtk.Label(label="关闭副屏后仍保留网络与供电；关闭窗口不会停止后台服务。",
                               wrap=True, xalign=0))
        page.add(controls)

        group = Adw.PreferencesGroup(title="设备状态")
        self.rows = {}
        for key, title in ROWS:
            row = Adw.ActionRow(title=title, subtitle="读取中")
            self.rows[key] = row
            group.add(row)
        page.add(group)

        logs = Adw.PreferencesGroup(title="诊断")
        self.error = Gtk.Label(wrap=True, selectable=True, xalign=0, label="暂无错误")
        logs.add(self.error)
        button = Gtk.Button(label="查看最近日志", margin_top=8)
        button.connect("clicked", self.show_logs)
        logs.add(button)
        page.add(logs)
        box.append(page)
        self.set_content(box)
        self.timer = GLib.timeout_add_seconds(3, self.refresh)
        self.refresh()

    def request(self, action, value=None):
        args = [action] if value is None else [action, "on" if value else "off"]
        try:
            code, _out, err = cli(*args, timeout=30)
            self.banner.set_text("请求已提交，正在更新状态" if code == 0 else (err.strip() or "请求失败"))
        except (OSError, subprocess.TimeoutExpired) as error:
            self.banner.set_text(str(error))
        self.refresh()

    def toggle(self, *_):
        if not self.refreshing:
            self.request("set-auto", self.automatic.get_active())

    def refresh(self):
        if self.busy:
            return GLib.SOURCE_CONTINUE
        self.busy = True

        def worker():
            try:
                code, out, err = cli("status", "--json", timeout=120)
                data = json.loads(out) if code == 0 and out.strip() else {}
                error = "" if code == 0 else (err.strip() or "状态读取失败")
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                data, error = {}, str(exc)
            GLib.idle_add(self.apply, data, error)
            return False

        import threading
        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def apply(self, data, error):
        self.busy = False
        self.refreshing = True
        self.automatic.set_active(bool(data.get("auto_enabled", True)))
        self.refreshing = False
        for key, row in self.rows.items():
            value = data.get(key, "unknown")
            row.set_subtitle(LABELS.get(str(value), str(value)))
        self.error.set_text(error or "暂无错误")
        if not data:
            self.banner.set_text("后台服务可能未运行；请检查 usb-tablet-daemon 单元。")
        return GLib.SOURCE_REMOVE

    def show_logs(self, *_):
        dialog = Gtk.Window(title="平板副屏日志", transient_for=self,
                            default_width=820, default_height=480)
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(view)
        dialog.set_child(scroll)
        args = ["journalctl", "--user"]
        for unit in UNITS:
            args += ["-u", unit]
        args += ["-n", "120", "--no-pager"]
        try:
            done = subprocess.run(args, capture_output=True, text=True, timeout=20)
            view.get_buffer().set_text(done.stdout or done.stderr)
        except (OSError, subprocess.TimeoutExpired) as exc:
            view.get_buffer().set_text(str(exc))
        dialog.present()


def main():
    app = Adw.Application(application_id="local.usbtablet.Display")
    app.connect("activate", lambda application: (application.get_active_window()
                                                 or Window(application)).present())
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    raise SystemExit(main())
