"""Selected telegram-mcp helpers (Apache-2.0); see UPSTREAM.md.

Modified integration: no MCP runtime, client construction or implicit sends.
"""
from datetime import datetime, timezone
import mimetypes
import os
import struct
from typing import Any, Iterable, Optional, Union

from telethon import types
from telethon.errors import FloodWaitError
# Runtime's get_marked_id replaced with Telethon's equivalent public helper.
from telethon.utils import get_peer_id as get_marked_id


# upstream: telegram_mcp/runtime.py:1219-1224 (modified: environment-only,
# no import-time configuration or mutable runtime fallback)
def get_effective_allowed_chat_ids():
    return _parse_allowed_chat_ids(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS"))



# upstream: telegram_mcp/runtime.py:127-151 (verbatim)
def parse_schedule_date(
    schedule_date: Union[str, int],
) -> tuple[Optional[datetime], Optional[str]]:
    """Return (datetime, None) for a usable schedule_date, or (None, error message).

    Accepts an ISO-8601 string or a Unix timestamp; naive datetimes are UTC.
    """
    try:
        if isinstance(schedule_date, int):
            dt = datetime.fromtimestamp(schedule_date, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(schedule_date).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None, (
            "schedule_date could not be parsed. Use an ISO-8601 date/time or Unix timestamp."
        )

    now = datetime.now(timezone.utc)
    if dt <= now:
        return None, (
            f"schedule_date must be in the future (got {dt.isoformat()}, now {now.isoformat()})."
        )
    return dt, None


# upstream: telegram_mcp/runtime.py:1158-1207 (verbatim)
def _parse_allowed_chat_ids(
    raw: Optional[Union[str, Iterable[Union[int, str]]]],
) -> Optional[set[Union[int, str]]]:
    """Parse TELEGRAM_ALLOWED_CHAT_IDS into a set of allowed IDs and usernames.

    Supports comma-separated integer IDs (e.g. '12345678,-100123456789') and
    usernames/handles (e.g. '@mychat,other_channel').
    Also automatically indexes marked variants for bare integers and vice versa
    so that both marked IDs (-100...) and bare positive IDs match.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        tokens = [t.strip() for t in raw.split(",") if t.strip()]
    elif isinstance(raw, (list, tuple, set)):
        tokens = [str(t).strip() for t in raw if str(t).strip()]
    else:
        return None

    if not tokens:
        return None

    allowed: set[Union[int, str]] = set()
    for token in tokens:
        try:
            val = int(token)
            allowed.add(val)
            # If negative supergroup: -100XXXXXXXXXX
            if str(val).startswith("-100") and len(str(val)) > 4:
                try:
                    channel_id = int(str(val)[4:])
                    allowed.add(channel_id)
                except ValueError:
                    pass
            # If positive bare ID: add supergroup (-100...) and group (-) variants
            elif val > 0:
                allowed.add(-1000000000000 - val)
                allowed.add(-val)
            elif val < 0:
                # Basic group negative ID: -XXXXXX
                allowed.add(-val)
        except ValueError:
            clean_handle = token.lstrip("@").strip().lower()
            if clean_handle:
                allowed.add(clean_handle)

    return allowed if allowed else None


# upstream: telegram_mcp/runtime.py:1232-1271 (modified: get_marked_id resolves to telethon.utils.get_peer_id)
def is_chat_allowed(chat_identifier: Any, entity: Any = None) -> bool:
    """Check whether a chat identifier or entity is permitted by the allowlist.

    If allowlist is not enabled, always returns True.
    """
    allowed = get_effective_allowed_chat_ids()
    if allowed is None:
        return True

    if chat_identifier is not None:
        if isinstance(chat_identifier, int):
            if chat_identifier in allowed:
                return True
        elif isinstance(chat_identifier, str):
            try:
                int_id = int(chat_identifier)
                if int_id in allowed:
                    return True
            except ValueError:
                clean = chat_identifier.lstrip("@").strip().lower()
                if clean and clean in allowed:
                    return True

    if entity is not None:
        try:
            marked_id = get_marked_id(entity)
            if marked_id in allowed:
                return True
        except Exception:
            pass

        bare_id = getattr(entity, "id", None)
        if isinstance(bare_id, int) and bare_id in allowed:
            return True

        username = getattr(entity, "username", None)
        if username and str(username).lower() in allowed:
            return True

    return False


# upstream: telegram_mcp/runtime.py:1274-1281 (verbatim)
def check_chat_access(chat_identifier: Any, entity: Any = None) -> Optional[str]:
    """Return an error message if chat access is restricted, or None if allowed."""
    if not is_chat_allowed(chat_identifier, entity):
        return (
            f"Access to chat '{chat_identifier}' is restricted by privacy policy "
            "(TELEGRAM_ALLOWED_CHAT_IDS)."
        )
    return None


# upstream: telegram_mcp/runtime.py:1304-1309 (verbatim)
def _is_flood_wait(error: Exception) -> bool:
    """True for Telethon FloodWaitError."""
    try:
        return isinstance(error, FloodWaitError)
    except Exception:  # telethon missing or moved — not this helper's problem
        return False


# upstream: telegram_mcp/tools/media.py:48-58 (verbatim)
def _video_send_attributes(path: str):
    """Real DocumentAttributeVideo for a video file, so clips do not go out 1x1/0:00.

    Telethon fills in dimensions and duration only with hachoir (GPL, not a
    dependency here); without them every video is sent as w=1 h=1 duration=0,
    which squashes portrait clips in clients. Returns None for non-videos and
    for containers the parser cannot read, falling back to Telethon's defaults.
    """
    if not (mimetypes.guess_type(path)[0] or "").startswith("video/"):
        return None
    return _mp4_video_attributes(path)


# upstream: telegram_mcp/tools/media.py:61-77 (verbatim)
def _mp4_video_attributes(path: str):
    """Parse an MP4/MOV container for duration and display dimensions.

    mvhd carries the duration; tkhd the track dimensions plus the display
    matrix, so a 90-degree-rotated phone video (stored 1920x1080) is reported
    as 1080x1920 — the rotation hachoir ignores. Any malformed structure
    returns None.
    """
    try:
        with open(path, "rb") as media_file:
            media_file.seek(0, os.SEEK_END)
            moov = _find_box(media_file, 0, media_file.tell(), b"moov")
            if moov is None:
                return None
            return _parse_moov(media_file, *moov)
    except (OSError, struct.error):
        return None


# upstream: telegram_mcp/tools/media.py:80-103 (verbatim)
def _find_box(media_file, start: int, end: int, wanted: bytes):
    """(payload_start, payload_end) of the first child box named `wanted`."""
    offset = start
    while offset + 8 <= end:
        media_file.seek(offset)
        header = media_file.read(8)
        if len(header) < 8:
            return None
        size, box_type = struct.unpack(">I4s", header)
        payload_start = offset + 8
        if size == 1:
            large = media_file.read(8)
            if len(large) < 8:
                return None
            size = struct.unpack(">Q", large)[0]
            payload_start = offset + 16
        elif size == 0:
            size = end - offset
        if size < payload_start - offset:
            return None
        if box_type == wanted:
            return payload_start, min(offset + size, end)
        offset += size
    return None


# upstream: telegram_mcp/tools/media.py:106-132 (verbatim)
def _parse_moov(media_file, start: int, end: int):
    timescale = duration = None
    dimensions = None
    offset = start
    while offset + 8 <= end:
        media_file.seek(offset)
        header = media_file.read(8)
        if len(header) < 8:
            return None
        size, box_type = struct.unpack(">I4s", header)
        if size < 8:
            return None
        box_end = min(offset + size, end)
        if box_type == b"mvhd":
            timescale, duration = _parse_mvhd(media_file, offset + 8, box_end)
        elif box_type == b"trak" and dimensions is None:
            dimensions = _parse_trak(media_file, offset + 8, box_end)
        offset = box_end
    if not timescale or duration is None or dimensions is None:
        return None
    return types.DocumentAttributeVideo(
        round_message=False,
        w=dimensions[0],
        h=dimensions[1],
        duration=int(round(duration / timescale)),
        supports_streaming=True,
    )


# upstream: telegram_mcp/tools/media.py:135-146 (verbatim)
def _parse_mvhd(media_file, start: int, end: int):
    media_file.seek(start)
    data = media_file.read(min(32, end - start))
    if data and data[0] == 1:
        if len(data) < 32:
            return None, None
        timescale, duration = struct.unpack_from(">IQ", data, 20)
    else:
        if len(data) < 20:
            return None, None
        timescale, duration = struct.unpack_from(">II", data, 12)
    return timescale, duration


# upstream: telegram_mcp/tools/media.py:149-163 (verbatim)
def _parse_trak(media_file, start: int, end: int):
    offset = start
    while offset + 8 <= end:
        media_file.seek(offset)
        header = media_file.read(8)
        if len(header) < 8:
            return None
        size, box_type = struct.unpack(">I4s", header)
        if size < 8:
            return None
        box_end = min(offset + size, end)
        if box_type == b"tkhd":
            return _parse_tkhd(media_file, offset + 8, box_end)
        offset = box_end
    return None


# upstream: telegram_mcp/tools/media.py:166-184 (verbatim)
def _parse_tkhd(media_file, start: int, end: int):
    media_file.seek(start)
    data = media_file.read(min(96, end - start))
    if data and data[0] == 1:
        if len(data) < 96:
            return None
        matrix_at, width_at = 52, 88
    else:
        if len(data) < 84:
            return None
        matrix_at, width_at = 40, 76
    matrix_a, _b, _c, matrix_d = struct.unpack_from(">4i", data, matrix_at)
    width = struct.unpack_from(">I", data, width_at)[0] >> 16
    height = struct.unpack_from(">I", data, width_at + 4)[0] >> 16
    if not width or not height:
        return None
    if matrix_a == 0 and matrix_d == 0:  # a 90/270-degree display matrix
        width, height = height, width
    return width, height


# upstream: telegram_mcp/tools/media.py:220-329 (modified: explicit client/entity,
# preuploaded file and adapter attributes; return message; no MCP/album/topic,
# fixed plain MP4 streaming options; errors propagate without retry)
async def send_scheduled_file(client, entity, path, caption, dt, *,
                              uploaded=None, attributes=None):
    if attributes is None:
        attribute = _video_send_attributes(str(path))
        attributes = [attribute] if attribute is not None else None
    return await client.send_file(
        entity, uploaded if uploaded is not None else str(path), caption=caption,
        schedule=dt, parse_mode=None, mime_type='video/mp4',
        force_document=False, supports_streaming=True, attributes=attributes,
    )


# upstream: telegram_mcp/tools/messages.py:1047-1105 (modified: explicit client,
# entity and parsed datetime; return message; plain text without link preview;
# no MCP decorators, connection management or error-to-string conversion)
async def send_scheduled_text(client, entity, text, dt):
    return await client.send_message(
        entity, text, schedule=dt, parse_mode=None, link_preview=False,
    )
