"""wavi media — viewer header parsing, file typing, and the download loops
against a fake viewer / fake chat + Chrome downloads (no browser)."""
import base64
import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from wavi.media import (
    _ext_for,
    _slug,
    document_when,
    download_chat_documents,
    download_chat_media,
    parse_size,
    parse_viewer_when,
)

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
        self.handlers, self.path = {}, None

    def state(self):
        if not self.open:
            return None
        it = self.items[self.i]
        return {"header": it["header"], "video": it.get("video"), "image": it.get("image"),
                "thumb": it.get("thumb")}

    async def evaluate(self, js, *args):
        if "querySelectorAll(" in js and "return els.length" in js:
            return 1
        if "scrollIntoView" in js:
            return {"x": 1, "y": 2}
        if "media-viewer-modal" in js and "aria-label" in js:     # viewer's download button
            it = self.items[self.i]
            guid = f"g{self.i}"
            self.handlers["Browser.downloadWillBegin"]({"guid": guid})
            (self.path / guid).write_bytes(it["data"])
            self.handlers["Browser.downloadProgress"]({"guid": guid, "state": "completed"})
            return True
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
    cdp = MagicMock()
    cdp.on = lambda ev, fn: viewer.handlers.__setitem__(ev, fn)

    async def send(method, params):
        if params.get("downloadPath"):
            viewer.path = __import__("pathlib").Path(params["downloadPath"])
    cdp.send = AsyncMock(side_effect=send)
    cdp.detach = AsyncMock()
    page.context.browser.new_browser_cdp_session = AsyncMock(return_value=cdp)
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


UNFETCHED = {"header": ["Leandro", "Ayer a la(s) 10:55 p. m."], "thumb": 'url("data:image/jpeg;base64,AAA")',
             "data": b"\x00\x00\x00\x20ftypmp42" + b"u" * 80}


@pytest.mark.asyncio
async def test_video_wa_has_not_fetched_is_saved_with_the_viewer_button(tmp_path):
    """RuGIAR 2026-10-26: forwarded HD videos show 'No se puede reproducir'
    — no src. They used to end the walk ('no hay videos')."""
    entries = await download_chat_media(_session([VIDEO, UNFETCHED, PHOTO]), tmp_path, today=TODAY)
    assert [e["kind"] for e in entries] == ["video", "video", "image"]
    assert entries[1]["file"].startswith("2026-10-07_2255_leandro_") and entries[1]["file"].endswith(".mp4")
    assert (tmp_path / entries[1]["file"]).read_bytes() == UNFETCHED["data"]
    assert not (tmp_path / ".partial").exists()


# ── documents ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("ZIP•510 MB", 510 << 20),
    ("PDF • 45 B", 45),
    ("XLSX•1,5 MB", int(1.5 * (1 << 20))),
    ("sin tamaño", None),
])
def test_parse_size(text, expected):
    assert parse_size(text) == expected


def test_document_when_from_pill_and_time():
    assert document_when({"pill": "Hoy", "time": "2:25 p. m."}, TODAY) == datetime(2026, 10, 8, 14, 25)
    assert document_when({"pill": "5/10/2026", "time": "9:01"}, TODAY) == datetime(2026, 10, 5, 9, 1)
    assert document_when({"pill": None, "time": "9:01"}, TODAY) is None


class FakeChat:
    """A chat whose rendered rows are a window of DOCS (oldest → newest) that
    scrolling up moves; clicking a document makes 'Chrome' download it —
    straight away, or (preview=True, like PDFs) once the preview's button is
    pressed, or (unprepared=True, like a big zip WA hasn't fetched) only on
    the second click."""

    WINDOW = 2

    def __init__(self, docs):
        self.docs, self.bottom, self.preview_open = docs, len(docs), None
        self.handlers, self.path = {}, None

    def visible(self):
        return self.docs[max(0, self.bottom - self.WINDOW):self.bottom]

    def emit(self, doc):
        guid = "guid-" + doc["id"]
        self.handlers["Browser.downloadWillBegin"]({"guid": guid})
        (self.path / guid).write_bytes(doc["data"])
        self.handlers["Browser.downloadProgress"](
            {"guid": guid, "state": "completed", "receivedBytes": len(doc["data"])})

    async def evaluate(self, js, *args):
        if "document-thumb" in js and "firstPill" in js:
            vis = self.visible()
            docs = [{k: d[k] for k in ("id", "file", "size", "time", "pill", "out", "sender")} for d in vis]
            return {"docs": docs, "firstPill": vis[0]["pill"] if vis else None}
        if "scrollIntoView" in js:
            self.target = next(d for d in self.docs if d["id"] == args[0])
            return {"x": 1, "y": 2, "text": self.target["file"]}
        if "media-viewer-modal" in js:
            if self.preview_open:
                self.emit(self.preview_open)
                return True
            return False
        raise AssertionError(js[:60])

    async def click(self, x, y):
        self.clicks = getattr(self, "clicks", 0) + 1
        if self.target.pop("unprepared", False):
            return
        if self.target.get("preview"):
            self.preview_open = self.target
        else:
            self.emit(self.target)

    async def send(self, method, params):
        if params.get("downloadPath"):
            self.path = __import__("pathlib").Path(params["downloadPath"])
        self.behavior = params["behavior"]


def _chat_session(docs):
    chat = FakeChat(docs)
    cdp = MagicMock()
    cdp.on = lambda ev, fn: chat.handlers.__setitem__(ev, fn)
    cdp.send = AsyncMock(side_effect=chat.send)
    cdp.detach = AsyncMock()
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=chat.evaluate)
    page.wait_for_timeout = AsyncMock()
    page.mouse.click = AsyncMock(side_effect=chat.click)
    page.keyboard.press = AsyncMock()
    page.context.browser.new_browser_cdp_session = AsyncMock(return_value=cdp)
    s = MagicMock()
    s._page = page

    async def scroll_up():
        chat.bottom = max(chat.WINDOW, chat.bottom - 1)
    s.scroll_chat_up = AsyncMock(side_effect=scroll_up)
    s.is_chat_at_top = AsyncMock(side_effect=lambda: chat.bottom - chat.WINDOW <= 0)

    async def scroll_down(px):
        chat.bottom = min(len(chat.docs), chat.bottom + 1)
    s.scroll_chat_down = AsyncMock(side_effect=scroll_down)
    s.get_chat_scroll_state = AsyncMock(side_effect=lambda: {
        "scrollTop": chat.bottom, "clientHeight": 0, "scrollHeight": len(chat.docs) + 20})
    return s, chat


def _doc(i, file, pill, *, out=False, preview=False, data=None):
    return {"id": f"MSG{i}", "file": file, "size": "ZIP•1 MB", "time": f"{i}:00", "pill": pill,
            "out": out, "sender": None if out else "Matias Becerro", "preview": preview,
            "data": data or file.encode() * 10}


ZIP = _doc(9, "ITEC_Movimientos.zip", "Hoy")
PDF = _doc(8, "informe.pdf", "Hoy", out=True, preview=True)
XLS = _doc(7, "datos.xlsx", "5/10/2026")
OLD_DOC = _doc(6, "viejo.zip", "1/9/2026")


@pytest.mark.asyncio
async def test_documents_newest_first_with_original_names(tmp_path):
    s, chat = _chat_session([OLD_DOC, XLS, PDF, ZIP])
    entries = await download_chat_documents(s, tmp_path, today=TODAY, chat_name="Matias Becerro")
    assert [e["file"] for e in entries] == [
        "2026-10-08_0900_matias_becerro_ITEC_Movimientos.zip",
        "2026-10-08_0800_tu_informe.pdf",                     # via the preview's button
        "2026-10-05_0700_matias_becerro_datos.xlsx",
        "2026-09-01_0600_matias_becerro_viejo.zip",
    ]
    assert (tmp_path / entries[0]["file"]).read_bytes() == ZIP["data"]
    assert {e["kind"] for e in entries} == {"document"}
    assert not (tmp_path / ".partial").exists()
    assert chat.behavior == "default"                         # Chrome's downloads restored
    assert chat.bottom == 4                                   # chat left at the bottom
    assert len(json.loads((tmp_path / "media.json").read_text())) == 4


@pytest.mark.asyncio
async def test_documents_from_date_limit_and_rerun(tmp_path):
    entries = await download_chat_documents(
        _chat_session([OLD_DOC, XLS, PDF, ZIP])[0], tmp_path, from_date=date(2026, 10, 1), today=TODAY)
    assert [e["key"] for e in entries] == ["MSG9", "MSG8", "MSG7"]      # stops before 1/9

    again = await download_chat_documents(
        _chat_session([OLD_DOC, XLS, PDF, ZIP])[0], tmp_path, limit=1, today=TODAY)
    assert [e["key"] for e in again] == ["MSG6"]                        # the rest already there


@pytest.mark.asyncio
async def test_document_saved_on_the_second_click_once_prepared(tmp_path, monkeypatch):
    import wavi.media as media
    monkeypatch.setattr(media, "DOC_RECLICK_S", 0)
    s, chat = _chat_session([{**ZIP, "unprepared": True}])
    entries = await download_chat_documents(s, tmp_path, today=TODAY)
    assert [e["key"] for e in entries] == ["MSG9"]
    assert chat.clicks == 2


@pytest.mark.asyncio
async def test_document_not_delivered_is_skipped(tmp_path, monkeypatch):
    import wavi.media as media
    monkeypatch.setattr(media, "DOC_BEGIN_BASE_S", 0)
    monkeypatch.setattr(media, "DOC_BEGIN_PER_MB_S", 0)
    monkeypatch.setattr(media, "DOC_RECLICK_S", 0)
    s, chat = _chat_session([ZIP])
    chat.click = AsyncMock()                                  # WA never hands it over
    s._page.mouse.click = chat.click
    assert await download_chat_documents(s, tmp_path, today=TODAY) == []
    assert chat.behavior == "default"


@pytest.mark.asyncio
async def test_busy_document_is_never_clicked_again(tmp_path, monkeypatch):
    """While WA fetches, the bubble reads differently: a click then would
    cancel the fetch."""
    import time as _time

    import wavi.media as media
    monkeypatch.setattr(media, "DOC_RECLICK_S", 0)
    monkeypatch.setattr(media, "DOC_BEGIN_BASE_S", 0.05)
    s, chat = _chat_session([{**ZIP, "unprepared": True}])
    real = chat.evaluate

    async def busy_after_click(js, *args):
        r = await real(js, *args)
        if isinstance(r, dict) and "text" in r and getattr(chat, "clicks", 0):
            r["text"] = "ITEC_Movimientos.zip 12 de 510 MB"
        return r
    s._page.evaluate = AsyncMock(side_effect=busy_after_click)
    s._page.wait_for_timeout = AsyncMock(side_effect=lambda ms: _time.sleep(0.01))
    assert await download_chat_documents(s, tmp_path, today=TODAY) == []
    assert chat.clicks == 1
