"""wavi media — viewer header parsing, file typing, and the download loop
against a fake viewer (no browser)."""
import base64
import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from wavi.media import _ext_for, _slug, download_chat_media, parse_viewer_when

TODAY = date(2026, 10, 8)


@pytest.mark.parametrize("line,expected", [
    ("Hoy a la(s) 11:26 a. m.", datetime(2026, 10, 8, 11, 26)),
    ("5/10/2026 a la(s) 3:51 p. m.", datetime(2026, 10, 5, 15, 51)),
    ("Ayer a la(s) 9:02 p. m.", datetime(2026, 10, 7, 21, 2)),
    ("Yesterday at 9:02 PM", datetime(2026, 10, 7, 21, 2)),
    ("1.0×", None),
])
def test_parse_viewer_when(line, expected):
    assert parse_viewer_when(line, TODAY) == expected


def test_ext_from_magic_bytes():
    assert _ext_for(b"\x00\x00\x00\x20ftypmp42", "video") == ".mp4"
    assert _ext_for(b"\xff\xd8\xff\xe0", "image") == ".jpg"
    assert _ext_for(b"\x89PNG\r\n\x1a\n", "image") == ".png"


def test_slug_is_ascii():
    assert _slug("Matías Becerro") == "matias_becerro"


class FakeViewer:
    """Media viewer stand-in: ITEMS newest → oldest; ArrowLeft moves older
    and is a no-op on the oldest, like WA's."""

    def __init__(self, items):
        self.items, self.i, self.open = items, 0, False

    def state(self):
        if not self.open:
            return None
        it = self.items[self.i]
        return {"header": it["header"], "video": it.get("video"), "image": it.get("image")}

    async def evaluate(self, js, *args):
        if "querySelectorAll(" in js and "return els.length" in js:
            return 1
        if "scrollIntoView" in js:
            return {"x": 1, "y": 2}
        if "media-viewer-modal" in js:
            return self.state()
        if "Range" in js:
            data = self.items[self.i]["data"]
            return {"status": 206, "range": f"bytes 0-{len(data) - 1}/{len(data)}",
                    "b64": base64.b64encode(data).decode()}
        raise AssertionError(js[:60])


def _session(items):
    viewer = FakeViewer(items)
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=viewer.evaluate)
    page.wait_for_timeout = AsyncMock()

    async def click(x, y):
        viewer.open = True
    page.mouse.click = AsyncMock(side_effect=click)

    async def press(key):
        if key == "ArrowLeft" and viewer.i < len(items) - 1:
            viewer.i += 1
    page.keyboard.press = AsyncMock(side_effect=press)
    s = MagicMock()
    s._page = page
    s.fetch_blob = AsyncMock(side_effect=lambda url: items[viewer.i]["data"])
    return s


VIDEO = {"header": ["Matias", "Hoy a la(s) 11:26 a. m."], "video": "https://web.whatsapp.com/stream/video?key=A",
         "data": b"\x00\x00\x00\x20ftypmp42" + b"v" * 100}
PHOTO = {"header": ["Vito Bagni", "5/10/2026 a la(s) 3:51 p. m."], "image": "blob:x",
         "data": b"\xff\xd8\xff\xe0" + b"i" * 50}
OLD = {"header": ["Vito Bagni", "1/9/2026 a la(s) 9:00 a. m."], "image": "blob:y",
       "data": b"\xff\xd8\xff\xe0" + b"o" * 50}


@pytest.mark.asyncio
async def test_downloads_newest_to_oldest_and_writes_manifest(tmp_path):
    s = _session([VIDEO, PHOTO])
    entries = await download_chat_media(s, tmp_path, today=TODAY)
    assert [e["kind"] for e in entries] == ["video", "image"]
    assert entries[0]["file"].startswith("2026-10-08_1126_matias_") and entries[0]["file"].endswith(".mp4")
    assert (tmp_path / entries[0]["file"]).read_bytes() == VIDEO["data"]
    manifest = json.loads((tmp_path / "media.json").read_text())
    assert len(manifest) == 2


@pytest.mark.asyncio
async def test_stops_before_from_date(tmp_path):
    s = _session([VIDEO, PHOTO, OLD])
    entries = await download_chat_media(s, tmp_path, from_date=date(2026, 10, 1), today=TODAY)
    assert len(entries) == 2


@pytest.mark.asyncio
async def test_type_filter_and_rerun_skips_known(tmp_path):
    entries = await download_chat_media(_session([VIDEO, PHOTO]), tmp_path, kinds=("video",), today=TODAY)
    assert [e["kind"] for e in entries] == ["video"]
    again = await download_chat_media(_session([VIDEO, PHOTO]), tmp_path, today=TODAY)
    assert [e["kind"] for e in again] == ["image"]          # video already there


@pytest.mark.asyncio
async def test_limit(tmp_path):
    entries = await download_chat_media(_session([VIDEO, PHOTO, OLD]), tmp_path, limit=1, today=TODAY)
    assert len(entries) == 1
