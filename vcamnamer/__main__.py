"""
__main__.py – CLI entry point for vcamnamer.

Usage
-----
  python -m vcamnamer          # open GUI
  vcamnamer                    # open GUI (after pip install)
  sudo vcamnamer --apply       # apply rules without opening GUI
  sudo vcamnamer --reset-rules # remove app-generated udev rules
  vcamnamer --list             # list detected virtual cameras (no GUI)
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vcamnamer",
        description="Rename OBS / v4l2loopback virtual cameras via udev symlinks.",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List detected virtual cameras and exit (no GUI).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply saved mappings as udev rules and exit (requires root).",
    )
    p.add_argument(
        "--reset-rules",
        action="store_true",
        dest="reset_rules",
        help="Remove app-generated udev rules and exit (requires root).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        from vcamnamer.device_detector import enumerate_devices

        devices = enumerate_devices()
        virtual = [d for d in devices if d.is_virtual]
        if not virtual:
            print("No virtual cameras detected.")
            return 0
        print(f"{'Node':<16} {'Driver':<18} {'Card'}")
        print("-" * 60)
        for dev in virtual:
            print(f"{dev.node:<16} {dev.driver:<18} {dev.card}")
        return 0

    if args.apply:
        from vcamnamer.mapping_store import MappingStore
        from vcamnamer.rule_applier import apply_rules

        store = MappingStore()
        mappings = store.all()
        if not mappings:
            print("No custom mappings saved. Nothing to apply.")
            return 1
        try:
            apply_rules(mappings)
            print(f"udev rules applied for {len(mappings)} device(s).")
            print("Symlinks are available under /dev/vcam/")
            return 0
        except PermissionError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if args.reset_rules:
        from vcamnamer.rule_applier import remove_rules, rules_file_exists

        if not rules_file_exists():
            print("No app-generated rules file found. Nothing to remove.")
            return 0
        try:
            remove_rules()
            print("udev rules removed. App-managed symlinks cleaned up.")
            return 0
        except PermissionError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    # Default: open GUI
    try:
        from vcamnamer.gui import run_gui
    except ImportError as exc:
        print(
            f"ERROR: Could not import GUI: {exc}\n"
            "Make sure tkinter is installed: sudo apt-get install python3-tk",
            file=sys.stderr,
        )
        return 1

    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
