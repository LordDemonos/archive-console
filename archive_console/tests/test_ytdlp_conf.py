from pathlib import Path

from app.yt_dlp_config_model import YtdlpUiModel
from app.yt_dlp_conf_io import (
    parse_conf,
    parse_conf_with_report,
    serialize_conf,
    tier_b_allowed,
)
from app.yt_dlp_presets import apply_builtin_preset


def test_parse_serialize_roundtrip_minimal():
    text = """# header comment
--verbose
--sleep-requests 4
--format best
"""
    m = parse_conf(text)
    assert m.verbose is True
    assert m.sleep_requests == 4.0
    assert m.format == "best"
    assert "header" in m.preserved_tail
    out = serialize_conf(m, preset_id="test")
    m2 = parse_conf(out)
    assert m2.verbose is True
    assert m2.sleep_requests == 4.0
    assert m2.format == "best"


def test_tier_b_blocked_cookie_key():
    assert not tier_b_allowed("cookies-from-browser", "chrome")


def test_tier_b_blocks_tier_a_sponsorblock():
    assert not tier_b_allowed("sponsorblock-remove", "all")


def test_tier_b_allows_write_pages():
    assert tier_b_allowed("write-pages", "")


def test_bom_and_short_o_paths():
    text = "\ufeff-o %(title)s.%(ext)s\n-P home:videos\n--format best\n"
    m, warns = parse_conf_with_report(text)
    assert not warns
    assert m.output == "%(title)s.%(ext)s"
    assert m.paths == "home:videos"
    assert m.format == "best"


def test_parse_warns_invalid_int():
    text = "--retries notanumber\n"
    m, warns = parse_conf_with_report(text)
    assert any("could not parse" in w for w in warns)
    assert m.retries is None
    assert "notanumber" in m.preserved_tail


def test_roundtrip_output_embed_sponsor():
    m0 = YtdlpUiModel(
        output="out/%(title)s.%(ext)s",
        format_sort="res:1080",
        embed_chapters=True,
        sponsorblock_remove="sponsor,intro",
        write_comments=False,
    )
    ser = serialize_conf(m0, preset_id="t")
    m1 = parse_conf(ser)
    assert m1.output == m0.output
    assert m1.format_sort == m0.format_sort
    assert m1.embed_chapters is True
    assert m1.sponsorblock_remove == "sponsor,intro"


def test_apply_balanced_preset():
    cur = YtdlpUiModel(verbose=True, sleep_requests=1.0).model_dump()
    out = apply_builtin_preset(cur, "balanced")
    m = YtdlpUiModel.model_validate(out)
    assert m.sleep_requests == 8.0
    assert m.verbose is False
