"""
Tests for vcamnamer.device_detector

We cannot open real /dev/video* nodes in CI, so we mock the ioctl call
and glob expansion.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

from vcamnamer.device_detector import (
    VideoDevice,
    _VIDIOC_QUERYCAP_FMT,
    _is_virtual,
    enumerate_devices,
    list_virtual_devices,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cap_buf(driver: str, card: str, bus_info: str) -> bytes:
    """Build a fake VIDIOC_QUERYCAP buffer."""
    return struct.pack(
        _VIDIOC_QUERYCAP_FMT,
        driver.encode().ljust(16, b"\x00")[:16],
        card.encode().ljust(32, b"\x00")[:32],
        bus_info.encode().ljust(32, b"\x00")[:32],
        0x00060000,  # version
        0x85200001,  # capabilities
        0x85200001,  # device_caps
    )


# ---------------------------------------------------------------------------
# _is_virtual tests
# ---------------------------------------------------------------------------


class TestIsVirtual:
    def test_v4l2loopback_driver(self):
        assert _is_virtual("v4l2loopback", "Dummy video device", "platform:v4l2loopback-000")

    def test_driver_case_insensitive(self):
        # driver check is lower-cased
        assert _is_virtual("V4L2LOOPBACK", "", "")

    def test_obs_in_card(self):
        assert _is_virtual("snd_aloop", "OBS Virtual Camera", "")

    def test_virtual_in_card_not_a_hint(self):
        # "virtual" alone in card name is NOT a reliable hint (too broad)
        assert not _is_virtual("some_driver", "Virtual Webcam", "")

    def test_loopback_in_bus_info(self):
        assert _is_virtual("other", "", "platform:loopback-000")

    def test_real_webcam_not_virtual(self):
        assert not _is_virtual("uvcvideo", "Integrated Camera", "usb-0000:00:14.0-5")

    def test_empty_strings_not_virtual(self):
        assert not _is_virtual("", "", "")


# ---------------------------------------------------------------------------
# VideoDevice tests
# ---------------------------------------------------------------------------


class TestVideoDevice:
    def test_is_virtual_set_on_init(self):
        dev = VideoDevice(
            node="/dev/video0",
            driver="v4l2loopback",
            card="Dummy video device",
            bus_info="platform:v4l2loopback-000",
        )
        assert dev.is_virtual is True

    def test_real_device_not_virtual(self):
        dev = VideoDevice(
            node="/dev/video2",
            driver="uvcvideo",
            card="Integrated Camera",
            bus_info="usb-0000:00:14.0-5",
        )
        assert dev.is_virtual is False

    def test_index_extracted_correctly(self):
        dev = VideoDevice("/dev/video3", "v4l2loopback", "", "")
        assert dev.index == 3

    def test_index_fallback(self):
        dev = VideoDevice("/dev/videoX", "v4l2loopback", "", "")
        assert dev.index == -1


# ---------------------------------------------------------------------------
# enumerate_devices / list_virtual_devices tests
# ---------------------------------------------------------------------------


def _patched_open(node, *a, **kw):
    return 42  # fake fd


def _patched_ioctl(fd, request, buf):
    # Simulate a v4l2loopback device for all nodes
    data = _make_cap_buf("v4l2loopback", "Dummy video device", "platform:v4l2loopback-000")
    buf.raw = data


def _patched_close(fd):
    pass


@patch("vcamnamer.device_detector.glob.glob", return_value=["/dev/video0", "/dev/video1"])
@patch("vcamnamer.device_detector.os.open", side_effect=_patched_open)
@patch("vcamnamer.device_detector.fcntl.ioctl", side_effect=_patched_ioctl)
@patch("vcamnamer.device_detector.os.close", side_effect=_patched_close)
def test_enumerate_devices_returns_all(mock_close, mock_ioctl, mock_open, mock_glob):
    devices = enumerate_devices()
    assert len(devices) == 2
    assert devices[0].node == "/dev/video0"
    assert devices[1].node == "/dev/video1"
    assert all(d.driver == "v4l2loopback" for d in devices)


@patch("vcamnamer.device_detector.glob.glob", return_value=["/dev/video0", "/dev/video1"])
@patch("vcamnamer.device_detector.os.open", side_effect=_patched_open)
@patch("vcamnamer.device_detector.fcntl.ioctl", side_effect=_patched_ioctl)
@patch("vcamnamer.device_detector.os.close", side_effect=_patched_close)
def test_list_virtual_devices_filters_virtual(mock_close, mock_ioctl, mock_open, mock_glob):
    devices = list_virtual_devices()
    assert all(d.is_virtual for d in devices)


@patch("vcamnamer.device_detector.glob.glob", return_value=["/dev/video0"])
@patch("vcamnamer.device_detector.os.open", side_effect=OSError("no permission"))
def test_enumerate_devices_skips_unopenable(mock_open, mock_glob):
    devices = enumerate_devices()
    assert devices == []


@patch("vcamnamer.device_detector.glob.glob", return_value=[])
def test_enumerate_devices_empty(mock_glob):
    assert enumerate_devices() == []


def _patched_ioctl_fail(fd, request, buf):
    raise OSError("not a v4l2 device")


@patch("vcamnamer.device_detector.glob.glob", return_value=["/dev/video0"])
@patch("vcamnamer.device_detector.os.open", side_effect=_patched_open)
@patch("vcamnamer.device_detector.fcntl.ioctl", side_effect=_patched_ioctl_fail)
@patch("vcamnamer.device_detector.os.close", side_effect=_patched_close)
def test_enumerate_devices_skips_non_v4l2(mock_close, mock_ioctl, mock_open, mock_glob):
    devices = enumerate_devices()
    assert devices == []
