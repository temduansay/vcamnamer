# vcamnamer

A desktop GUI tool for Ubuntu that lets you rename existing OBS virtual camera (v4l2loopback) devices by creating persistent udev symlinks.

## What it can (and cannot) rename on Linux

**What it does:** Creates persistent `/dev/vcam/<YourName>` symlinks that point to the underlying `/dev/videoN` node. Applications can then open the device by the friendly symlink path (e.g. `/dev/vcam/OBS_Studio_Camera`).

**What it cannot do:** Linux does not expose an API to rename a `/dev/videoN` node in-place. The kernel device node name (e.g. `video0`) is fixed at module load time. vcamnamer works around this limitation via udev rules.

## Required packages / tools

| Package | Purpose | Install |
|---|---|---|
| `python3-tk` | Tkinter GUI | `sudo apt-get install python3-tk` |
| `udev` | Already on Ubuntu | pre-installed |
| `v4l2-utils` *(optional)* | CLI device inspection | `sudo apt-get install v4l2-utils` |
| OBS Studio + v4l2loopback | Virtual camera source | `sudo apt-get install obs-studio` |

The Python runtime dependencies are all standard-library modules (`tkinter`, `json`, `fcntl`, `ctypes`, `struct`). No third-party Python packages are required.

## Installation

```bash
# From the repository root
pip install .
# Or in editable / development mode
pip install -e .
```

## How to run the GUI

```bash
vcamnamer          # via installed script
# or
python -m vcamnamer
```

## How to apply names and verify results

1. Launch OBS and enable the Virtual Camera (Tools → Virtual Camera → Start).
2. Run `vcamnamer` – the GUI will list detected v4l2loopback devices.
3. Click a device row, type a custom name in the "Edit Custom Name" panel, then click **Set Name**.
4. Click **Apply Names** (this step requires `sudo` / root access).
   - You will be prompted if privileges are insufficient – run `sudo vcamnamer --apply` instead.
5. Verify the symlinks:
   ```bash
   ls -la /dev/vcam/
   # e.g.  /dev/vcam/OBS_Studio_Camera -> /dev/video0
   ```
6. Applications can now open the device at `/dev/vcam/OBS_Studio_Camera`.

### CLI usage

```bash
vcamnamer --list              # list detected virtual cameras (no GUI)
sudo vcamnamer --apply        # apply saved mappings as udev rules
sudo vcamnamer --reset-rules  # remove all app-managed rules and symlinks
```

### Mapping persistence

Custom names are saved to `~/.config/vcamnamer/mappings.json` and reloaded automatically on next launch.

### Rollback

Click **Reset / Remove Rules** in the GUI, or run:
```bash
sudo vcamnamer --reset-rules
```
This deletes `/etc/udev/rules.d/99-vcamnamer.rules` and re-triggers udev. Only app-generated files are affected; user/system udev rules are untouched.

## Running the tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Troubleshooting

### No virtual cameras detected

- Make sure OBS Virtual Camera is started (or v4l2loopback is loaded):
  ```bash
  lsmod | grep v4l2loopback
  ```
- Check that `/dev/video*` nodes exist:
  ```bash
  ls /dev/video*
  ```

### Permission denied when applying rules

The rules file is written to `/etc/udev/rules.d/` which requires root.  
Run with `sudo`:
```bash
sudo vcamnamer --apply
```

### udev rules applied but symlinks not visible

Reload udev manually:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=video4linux
```

### v4l2loopback not installed

```bash
sudo apt-get install v4l2loopback-dkms
sudo modprobe v4l2loopback
```

## Project structure

```
vcamnamer/
├── vcamnamer/
│   ├── __init__.py         # package version
│   ├── __main__.py         # CLI entry-point
│   ├── device_detector.py  # enumerate /dev/video*, detect virtual cams
│   ├── mapping_store.py    # JSON config persistence (XDG)
│   ├── rule_applier.py     # udev rule generation and management
│   └── gui.py              # Tkinter GUI layer
├── tests/
│   ├── test_device_detector.py
│   ├── test_mapping_store.py
│   └── test_rule_applier.py
└── pyproject.toml
```

