#!/usr/bin/env python3
"""Diagnose Chrome cookie-key availability: keyring vs Local State."""
import json
import os

# 1. Compare Local State encrypted_key between real + snapshot profiles
for name, path in (
    ("real", "/home/final-flash1/.config/google-chrome/Local State"),
    ("snapshot", "/home/final-flash1/.config/google-chrome-cdp/Local State"),
):
    try:
        d = json.load(open(path))
        k = d.get("os_crypt", {}).get("encrypted_key", "")
        print(f"{name} Local State encrypted_key: len={len(k)} prefix={k[:12]!r}")
    except Exception as e:
        print(f"{name} Local State: ERROR {e}")

# 2. Try to read the keyring entry
try:
    import secretstorage

    bus = secretstorage.dbus_init()
    col = secretstorage.get_default_collection(bus)
    if col.is_locked():
        print("KEYRING: default collection is LOCKED")
    else:
        print("KEYRING: collection unlocked")
        found = False
        for item in col.get_all_items():
            label = item.get_label()
            if "Chrome" in label or "chrome" in label:
                found = True
                try:
                    pw = item.get_secret()
                    print(f"  entry: {label!r} secret len={len(pw)} prefix={pw[:8]!r}")
                except Exception as e:
                    print(f"  entry: {label!r} get_secret error: {e}")
        if not found:
            print("  (no Chrome-named keyring entries found)")
except ImportError:
    print("secretstorage not installed")
except Exception as e:
    print(f"KEYRING access error: {e}")
