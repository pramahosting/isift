from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.services.policy import eligible, count_words
from app.services.transcript_utils import parse_vtt

def ev(**kw):
    result={"isCancelled":False,"isAllDay":False,"sensitivity":"normal","responseStatus":{"response":"accepted"}}
    result.update(kw)
    return result

def test_accepted_and_tentative_are_eligible():
    assert eligible(ev())
    assert eligible(ev(responseStatus={"response":"tentativelyAccepted"}))

def test_declined_private_cancelled_and_all_day_are_excluded():
    assert not eligible(ev(responseStatus={"response":"declined"}))
    assert not eligible(ev(sensitivity="private"))
    assert not eligible(ev(isCancelled=True))
    assert not eligible(ev(isAllDay=True))

def test_briefing_word_counter_counts_rendered_whitespace_words():
    assert count_words("Good morning\n• 9:00 AM — Planning") == 7

def test_vtt_parser_preserves_time_and_text():
    parsed=parse_vtt("WEBVTT\n\n00:00:01.200 --> 00:00:02.500\n<v Alex>We should review the plan.</v>\n")
    assert parsed[0]["start"]==1.2
    assert parsed[0]["end"]==2.5
    assert parsed[0]["speaker"]=="Alex"
    assert parsed[0]["text"]=="We should review the plan."

def test_sydney_day_boundaries_respect_daylight_saving():
    tz=ZoneInfo("Australia/Sydney")
    date=datetime(2026,10,4).date()
    start=datetime.combine(date,datetime.min.time(),tzinfo=tz)
    end=datetime.combine(date+timedelta(days=1),datetime.min.time(),tzinfo=tz)
    assert (end.timestamp()-start.timestamp())==23*3600

def test_sydney_day_boundaries_cover_fall_back_day():
    tz=ZoneInfo("Australia/Sydney")
    date=datetime(2026,4,5).date()
    start=datetime.combine(date,datetime.min.time(),tzinfo=tz)
    end=datetime.combine(date+timedelta(days=1),datetime.min.time(),tzinfo=tz)
    assert (end.timestamp()-start.timestamp())==25*3600


def test_setup_status_lists_required_items():
    import asyncio
    from app.api.routes_admin import setup_status
    out = asyncio.run(setup_status(user=None))
    keys = {i["key"] for i in out["items"]}
    assert {"password", "ai", "zoom", "turn", "https"} <= keys
    assert isinstance(out["ready"], bool)


def test_missing_timezone_database_does_not_crash(monkeypatch):
    import zoneinfo
    from app.core import tz
    def boom(name): raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {name}")
    monkeypatch.setattr(tz, "ZoneInfo", boom)
    z = tz.zone("Australia/Sydney")
    from datetime import datetime
    assert datetime.now(z).utcoffset() is not None


def test_device_timezone_header_is_validated():
    from app.core import tz
    tz.set_request_zone("Asia/Tokyo"); assert str(tz.request_zone()) == "Asia/Tokyo"
    for bad in ("../../etc/passwd", "Not/AZone", "", "x" * 100, "Asia/Tokyo; drop"):
        tz.set_request_zone(bad); assert tz.request_zone() is None
