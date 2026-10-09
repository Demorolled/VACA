#!/usr/bin/env python3
"""keepalive-enter.py — press Enter now and then so the freebuff CLI never idles out.

The terminal is Ptyxis, which is Wayland-native, so X11 key injection
(XTEST / xdotool) does not reach it. GNOME's compositor publishes
`org.gnome.Mutter.RemoteDesktop` on the session bus, which synthesises input at
the compositor level — that *does* reach Wayland-native windows, and unlike
ydotool it needs no root and no uinput access.

That D-Bus interface hands out a session that lives only as long as the
connection that created it, so one `gdbus call` cannot create then use it: the
session is gone before the next call. This process therefore holds a single
connection for its whole life, which is also why it is a long-running script
rather than something you run once.

    python3 scripts/keepalive-enter.py --test       # one inert Left-Ctrl; proves it works
    python3 scripts/keepalive-enter.py              # Enter every 10 min (default)
    python3 scripts/keepalive-enter.py --interval 300
    python3 scripts/keepalive-enter.py --once       # a single Enter, then exit

The key goes to whatever window has focus, so leave the terminal focused (or
accept that a stray Enter lands wherever you are).
"""
from __future__ import annotations

import argparse
import signal
import sys
import time

import gi

gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_NAME = "org.gnome.Mutter.RemoteDesktop"
ROOT_PATH = "/org/gnome/Mutter/RemoteDesktop"
ROOT_IFACE = "org.gnome.Mutter.RemoteDesktop"
SESSION_IFACE = "org.gnome.Mutter.RemoteDesktop.Session"

# linux/input-event-codes.h
KEY_ENTER = 28
KEY_LEFTCTRL = 29

_stop = False


def _on_signal(_signum, _frame):
    global _stop
    _stop = True


class RemoteKeyboard:
    """A compositor input session; it dies with this object's bus connection."""

    def __init__(self) -> None:
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        out = self.bus.call_sync(
            BUS_NAME, ROOT_PATH, ROOT_IFACE, "CreateSession",
            None, GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        self.path = out.unpack()[0]
        self.bus.call_sync(
            BUS_NAME, self.path, SESSION_IFACE, "Start",
            None, None, Gio.DBusCallFlags.NONE, -1, None,
        )

    def tap(self, keycode: int) -> None:
        """Press and release one key."""
        for pressed in (True, False):
            self.bus.call_sync(
                BUS_NAME, self.path, SESSION_IFACE, "NotifyKeyboardKeycode",
                GLib.Variant("(ub)", (keycode, pressed)),
                None, Gio.DBusCallFlags.NONE, -1, None,
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="Press Enter periodically over D-Bus")
    ap.add_argument("--interval", type=float, default=600,
                    help="seconds between presses (default 600; the timeout is 45 min)")
    ap.add_argument("--once", action="store_true", help="send one Enter and exit")
    ap.add_argument("--test", action="store_true",
                    help="send one inert Left-Ctrl instead of Enter, to prove injection works")
    args = ap.parse_args()

    try:
        kb = RemoteKeyboard()
    except GLib.Error as e:
        print(f"❌ could not open a compositor input session: {e.message}", file=sys.stderr)
        if "AccessDenied" in e.message:
            print("   GNOME refused it — fall back to ydotool (needs sudo + /dev/uinput).",
                  file=sys.stderr)
        return 1

    print(f"✅ input session {kb.path} started")

    if args.test:
        kb.tap(KEY_LEFTCTRL)
        print("sent one Left-Ctrl (inert) — injection works")
        return 0

    if args.once:
        kb.tap(KEY_ENTER)
        print("sent one Enter")
        return 0

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    print(f"⏱  pressing Enter every {args.interval:g}s (ctrl-c to stop)")
    while not _stop:
        # Sleep in slices so a signal is acted on promptly rather than after the
        # whole interval.
        slept = 0.0
        while slept < args.interval and not _stop:
            slice_ = min(1.0, args.interval - slept)
            time.sleep(slice_)
            slept += slice_
        if _stop:
            break
        try:
            kb.tap(KEY_ENTER)
            print(f"  ⏎  enter sent ({time.strftime('%H:%M:%S')})", flush=True)
        except GLib.Error as e:
            # The session can be torn down (screen lock, compositor restart);
            # rebuild it rather than dying quietly and letting the CLI time out.
            print(f"  ⚠️  session lost ({e.message}) — reopening", flush=True)
            try:
                kb = RemoteKeyboard()
            except GLib.Error as e2:
                print(f"  ❌ reopen failed: {e2.message}", file=sys.stderr)
                return 1

    print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
