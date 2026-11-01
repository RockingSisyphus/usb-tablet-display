import GLib from 'gi://GLib';
import Gio from 'gi://Gio';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const MARKER_MAX_AGE_SECONDS = 30;

function markerPath() {
    return GLib.build_filenamev([
        GLib.get_home_dir(),
        '.cache',
        'usb-tablet-display',
        'auto-accept-display-change',
    ]);
}

export default class AndroidTabletAutoKeepDisplay extends Extension {
    enable() {
        // WindowManager binds _confirmDisplayChange to this signal during its
        // construction. Replacing Main.wm._confirmDisplayChange after that
        // point does not replace the callback already connected on GNOME 50.
        this._shellwm = Main.wm._shellwm;
        this._confirmDisplayChangeId = this._shellwm.connect(
            'confirm-display-change', () => {
                if (!this._shouldAutoAccept())
                    return;

                GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                try {
                    this._shellwm.complete_display_change(true);
                    // The stock signal handler has already opened its dialog.
                    // Completing Mutter's change alone leaves that dialog's
                    // timeout armed, so it later reverts the layout. Close the
                    // top modal dialog to cancel its countdown as the Keep
                    // Changes button would.
                    Main.modalActorFocusStack.at(-1)?.actor?.close();
                    this._removeMarker();
                    console.log(`${this.uuid}: accepted display change`);
                } catch (error) {
                    logError(error, `${this.uuid}: failed to accept display change`);
                }
                    return GLib.SOURCE_REMOVE;
                });
            });
    }

    disable() {
        if (this._confirmDisplayChangeId)
            this._shellwm.disconnect(this._confirmDisplayChangeId);
        this._confirmDisplayChangeId = null;
        this._shellwm = null;
    }

    _shouldAutoAccept() {
        try {
            const file = Gio.File.new_for_path(markerPath());
            const info = file.query_info(
                'time::modified',
                Gio.FileQueryInfoFlags.NONE,
                null);
            const modified = info.get_modification_date_time();
            if (!modified)
                return false;

            const age = GLib.DateTime.new_now_local().to_unix() - modified.to_unix();
            return age >= 0 && age <= MARKER_MAX_AGE_SECONDS;
        } catch {
            return false;
        }
    }

    _removeMarker() {
        try {
            Gio.File.new_for_path(markerPath()).delete(null);
        } catch {
            // The marker is best-effort; stale files age out.
        }
    }
}
