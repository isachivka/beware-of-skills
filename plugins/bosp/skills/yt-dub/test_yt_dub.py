"""Tests for yt-dub's part plan and file naming. No network."""
import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = os.path.join(tempfile.mkdtemp(), "yt_dub_mod.py")
shutil.copy(os.path.join(HERE, "yt-dub"), tmp)
spec = importlib.util.spec_from_file_location("yt_dub_mod", tmp)
yd = importlib.util.module_from_spec(spec)
sys.modules["yt_dub_mod"] = yd
spec.loader.exec_module(yd)


def test_plan_short_video_is_one_part():
    assert yd.plan(3600) == [(0, 3600)]


def test_plan_parts_cover_video_and_stay_under_limit():
    for dur in (yd.LIMIT, yd.LIMIT + 1, 18951, 40000):
        parts = yd.plan(dur)
        assert all(length <= yd.LIMIT for _, length in parts)
        assert parts[0][0] == 0 and sum(length for _, length in parts) == dur
        assert all(a + la == b for (a, la), (b, _) in zip(parts, parts[1:]))
    assert len(yd.plan(18951)) == 2


def test_safe_name():
    assert yd.safe_name('DHH: AI / Linux "x"') == "DHH  AI   Linux  x"
