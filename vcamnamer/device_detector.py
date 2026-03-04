"""
device_detector.py – Enumerate /dev/video* devices and read V4L2 metadata.

Uses the VIDIOC_QUERYCAP ioctl to obtain the card name, driver, and bus_info
for each video node without requiring v4l2-utils to be installed.
OBS virtual cameras use the 'v4l2loopback' kernel module; we detect them by
checking the driver field returned by VIDIOC_QUERYCAP.
"""

from __future__ import annotations

import ctypes
import fcntl
import glob
import os
import struct
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# V4L2 VIDIOC_QUERYCAP ioctl constants
# ---------------------------------------------------------------------------

# struct v4l2_capability layout (kernel uapi/linux/videodev2.h)
#   u8 driver[16]
#   u8 card[32]
#   u8 bus_info[32]
#   u32 version
#   u32 capabilities
#   u32 device_caps
#   u32 reserved[3]
# Total size: 16 + 32 + 32 + 4 + 4 + 4 + 12 = 104 bytes

_VIDIOC_QUERYCAP_FMT = "16s32s32sIII12x"
_VIDIOC_QUERYCAP_SIZE = struct.calcsize(_VIDIOC_QUERYCAP_FMT)

# ioctl number: _IOR('V', 0, struct v4l2_capability)
# _IOR = (2 << 30) | (ord('V') << 8) | (0) | (size << 16)
_IOC_READ = 2
_VIDIOC_QUERYCAP = (
    (_IOC_READ << 30) | (ord("V") << 8) | 0 | (_VIDIOC_QUERYCAP_SIZE << 16)
)

# Drivers used by v4l2loopback (the kernel module that OBS virtual cam uses)
_LOOPBACK_DRIVERS = frozenset({"v4l2loopback"})

# Additional heuristics: card names often contain these strings for OBS.
# Note: avoid single words like "cam" that appear in real device names such as "camera".
_OBS_CARD_HINTS = ("obs", "v4l2loopback", "dummy", "loopback")


@dataclass
class VideoDevice:
    """Represents a single /dev/videoN device with its V4L2 metadata."""

    node: str  # e.g. "/dev/video0"
    driver: str  # e.g. "v4l2loopback"
    card: str  # e.g. "Dummy video device (0x0000)"
    bus_info: str  # e.g. "platform:v4l2loopback-000"
    is_virtual: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.is_virtual = _is_virtual(self.driver, self.card, self.bus_info)

    @property
    def index(self) -> int:
        """Return the numeric index of the /dev/videoN node."""
        try:
            return int(os.path.basename(self.node).replace("video", ""))
        except ValueError:
            return -1


def _is_virtual(driver: str, card: str, bus_info: str) -> bool:
    """
    Determine whether a device is a v4l2loopback (virtual) camera.

    Primary check: driver == 'v4l2loopback'.
    Secondary check: card or bus_info contain well-known loopback hints
    (useful when the driver string is truncated or unexpected).
    """
    drv = driver.lower()
    if drv in _LOOPBACK_DRIVERS:
        return True
    combined = (card + " " + bus_info).lower()
    return any(hint in combined for hint in _OBS_CARD_HINTS)


def _query_device(node: str) -> Optional[VideoDevice]:
    """
    Open a video node and call VIDIOC_QUERYCAP.

    Returns a VideoDevice on success, or None if the device cannot be opened
    or does not support VIDIOC_QUERYCAP (e.g. it is a radio or metadata node).
    """
    try:
        fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        buf = ctypes.create_string_buffer(_VIDIOC_QUERYCAP_SIZE)
        fcntl.ioctl(fd, _VIDIOC_QUERYCAP, buf)
        driver, card, bus_info, _ver, _caps, _dcaps = struct.unpack(
            _VIDIOC_QUERYCAP_FMT, buf.raw
        )
        return VideoDevice(
            node=node,
            driver=driver.rstrip(b"\x00").decode("utf-8", errors="replace"),
            card=card.rstrip(b"\x00").decode("utf-8", errors="replace"),
            bus_info=bus_info.rstrip(b"\x00").decode("utf-8", errors="replace"),
        )
    except OSError:
        return None
    finally:
        os.close(fd)


def enumerate_devices(dev_glob: str = "/dev/video*") -> List[VideoDevice]:
    """
    Return a list of VideoDevice objects for all /dev/video* nodes.

    Nodes that cannot be queried (e.g. no permission, non-capture devices)
    are silently skipped.
    """
    devices: List[VideoDevice] = []
    for path in sorted(glob.glob(dev_glob)):
        dev = _query_device(path)
        if dev is not None:
            devices.append(dev)
    return devices


def list_virtual_devices(dev_glob: str = "/dev/video*") -> List[VideoDevice]:
    """Return only the virtual (loopback) devices."""
    return [d for d in enumerate_devices(dev_glob) if d.is_virtual]
