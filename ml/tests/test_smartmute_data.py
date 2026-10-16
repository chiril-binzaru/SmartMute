"""Tests for smartmute_data.py on synthetic rows (fake data only)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import smartmute_data as sd  # noqa: E402

SYNTHETIC = Path(__file__).resolve().parents[1] / "testdata" / "notification_log_synthetic.csv"

ROWS = pd.DataFrame([
    # Telegram call: messenger's own package, CallStyle template.
    {"app_package": "org.telegram.messenger", "raw_template": "android.app.Notification$CallStyle",
     "raw_category": "call", "message_text": "Incoming call"},
    # Dialer missed call: no template, category missed_call.
    {"app_package": "com.google.android.dialer", "raw_template": "", "raw_category": "missed_call",
     "message_text": "Missed call"},
    # Normal text message.
    {"app_package": "org.telegram.messenger", "raw_template": "android.app.Notification$MessagingStyle",
     "raw_category": "msg", "message_text": "see you at 7"},
])


def flags(df: pd.DataFrame) -> list[bool]:
    return [sd.is_call_notification(r.raw_template, r.raw_category, r.app_package) for r in df.itertuples()]


def test_only_calls_flagged():
    assert flags(ROWS) == [True, True, False]
    assert sd.call_rows(ROWS).tolist() == [True, True, False]


def test_signals_work_alone():
    """A CallStyle template or a call category is enough; no package list needed."""
    assert sd.is_call_notification("android.app.Notification$CallStyle", "", "com.viber.voip")
    assert sd.is_call_notification("", "call", "com.whatsapp")
    assert not sd.is_call_notification("android.app.Notification$MessagingStyle", "msg", "com.viber.voip")


def test_dialer_package_fallback(monkeypatch):
    monkeypatch.setattr(sd, "DIALER_PACKAGES", {"com.example.dialer"})
    assert sd.is_call_notification("", "", "com.example.dialer")
    assert not sd.is_call_notification("", "", "com.example.other")


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA])
def test_missing_values_are_not_calls(missing):
    assert not sd.is_call_notification(missing, missing, missing)


def test_drop_calls_counts():
    kept, dropped = sd.drop_calls(ROWS)
    assert dropped == 2 and kept["message_text"].tolist() == ["see you at 7"]


def test_call_rows_without_raw_columns(monkeypatch):
    """The manual dataset may lack raw_* columns: then only the package fallback can flag a row."""
    no_raw = ROWS[["app_package", "message_text"]]
    monkeypatch.setattr(sd, "DIALER_PACKAGES", set())
    assert sd.call_rows(no_raw).tolist() == [False, False, False]
    monkeypatch.setattr(sd, "DIALER_PACKAGES", {"com.google.android.dialer"})
    assert sd.call_rows(no_raw).tolist() == [False, True, False]


def test_configured_dialer_packages():
    """Every package in the real DIALER_PACKAGES is flagged on its own, with no other signal."""
    assert sd.DIALER_PACKAGES, "DIALER_PACKAGES is empty"
    for package in sd.DIALER_PACKAGES:
        assert sd.is_call_notification("", "", package), package
    for messenger in ("org.telegram.messenger", "com.viber.voip", "com.whatsapp"):
        assert messenger not in sd.DIALER_PACKAGES  # every message from it would pass through


def test_load_export_drops_calls():
    everything = sd.load_export(SYNTHETIC, include_calls=True)
    training = sd.load_export(SYNTHETIC)
    assert len(everything) - len(training) == 2
    assert not sd.call_rows(training).any()
