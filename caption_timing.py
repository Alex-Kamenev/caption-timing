"""Small, renderer-independent helpers for plain timed captions.

Times are seconds. Output timestamps round half-up to the format's resolution.
The writers deliberately provide no raw subtitle styling or header overrides.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from html import escape
import math
import re
from typing import Iterable
import unicodedata

TimeValue = int | float


def _time(value: TimeValue, field: str) -> TimeValue:
    # Do not coerce strings, booleans, or objects with custom conversion methods.
    if type(value) not in (int, float):
        raise TypeError(f"{field} must be an int or float number of seconds")
    if (type(value) is float and not math.isfinite(value)) or value < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return value


def _fraction(value: TimeValue) -> Fraction:
    # Decimal spelling avoids binary-float formatting surprises at half ticks.
    return Fraction(value) if type(value) is int else Fraction(str(value))


def _text(value: str) -> str:
    if type(value) is not str:
        raise TypeError("caption text must be a string")
    # Flatten whitespace so a cue cannot inject another subtitle/header line.
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("caption text must not be empty")
    if any(unicodedata.category(char) in {"Cc", "Cs"} for char in normalized):
        raise ValueError("caption text contains a control character or surrogate")
    return normalized


def _interval(start: TimeValue, end: TimeValue) -> None:
    _time(start, "start")
    _time(end, "end")
    if end <= start:
        raise ValueError("end must be greater than start")


@dataclass(frozen=True, slots=True)
class TimedWord:
    """One nonempty token and its positive-duration interval in seconds."""

    text: str
    start: TimeValue
    end: TimeValue

    def __post_init__(self) -> None:
        text = _text(self.text)
        if " " in text:
            raise ValueError("TimedWord text must contain one token")
        _interval(self.start, self.end)
        object.__setattr__(self, "text", text)


@dataclass(frozen=True, slots=True)
class Cue:
    """Plain caption text and a positive-duration interval in seconds.

    Whitespace is normalized to one line. Rendering is intentionally plain text.
    """

    text: str
    start: TimeValue
    end: TimeValue

    def __post_init__(self) -> None:
        _interval(self.start, self.end)
        object.__setattr__(self, "text", _text(self.text))


def _ordered(items: Iterable, item_type: type) -> list:
    result = list(items)
    previous_end = None
    for index, item in enumerate(result):
        if type(item) is not item_type:
            raise TypeError(f"item {index} must be a {item_type.__name__}")
        if previous_end is not None and item.start < previous_end:
            raise ValueError("intervals must be ordered and must not overlap")
        previous_end = item.end
    return result


def _positive_int(value: int, name: str, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value <= 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside its supported range")
    return value


def _ticks(seconds: TimeValue, units_per_second: int) -> int:
    _time(seconds, "seconds")
    value = _fraction(seconds) * units_per_second
    whole, remainder = divmod(value.numerator, value.denominator)
    return whole + int(2 * remainder >= value.denominator)


def _timestamp(ticks: int, resolution: int, separator: str, digits: int, hours: int) -> str:
    hour, remainder = divmod(ticks, resolution * 3600)
    minute, remainder = divmod(remainder, resolution * 60)
    second, fraction = divmod(remainder, resolution)
    return f"{hour:0{hours}d}:{minute:02d}:{second:02d}{separator}{fraction:0{digits}d}"


def format_srt_time(seconds: TimeValue) -> str:
    """Format seconds as HH:MM:SS,mmm, carrying rounded ticks across boundaries."""
    return _timestamp(_ticks(seconds, 1000), 1000, ",", 3, 2)


def format_ass_time(seconds: TimeValue) -> str:
    """Format seconds as H:MM:SS.cc, carrying rounded ticks across boundaries."""
    return _timestamp(_ticks(seconds, 100), 100, ".", 2, 1)


def _punctuation(token: str) -> bool:
    return all(unicodedata.category(char).startswith("P") for char in token)


def _opening(token: str) -> bool:
    return all(unicodedata.category(char) in {"Ps", "Pi"} for char in token)


def _merge_punctuation(words: list[TimedWord]) -> list[TimedWord]:
    merged: list[TimedWord] = []
    pending: list[TimedWord] = []
    for word in words:
        if _punctuation(word.text):
            if _opening(word.text) or not merged or pending:
                pending.append(word)
            else:
                previous = merged[-1]
                merged[-1] = TimedWord(previous.text + word.text, previous.start, word.end)
            continue
        if pending:
            word = TimedWord("".join(item.text for item in pending) + word.text,
                             pending[0].start, word.end)
            pending.clear()
        merged.append(word)
    if pending:
        suffix = "".join(item.text for item in pending)
        if merged:
            previous = merged[-1]
            merged[-1] = TimedWord(previous.text + suffix, previous.start, pending[-1].end)
        else:
            merged.append(TimedWord(suffix, pending[0].start, pending[-1].end))
    return merged


_SENTENCE_END = re.compile(r"[.!?…。！？؟][\"'”’»›)\]}]*$")


def group_words(
    words: Iterable[TimedWord], *, max_words: int = 7, max_chars: int = 42,
    max_gap: TimeValue = 0.8,
) -> list[Cue]:
    """Group nonoverlapping words using size, gap, and punctuation boundaries.

    Punctuation-only tokens attach to a neighbor. Opening punctuation attaches
    to the following word; other punctuation normally attaches to the previous
    word. Sentence punctuation is a best-effort boundary, not language analysis.
    A single token longer than max_chars remains intact; no timing is invented.
    """
    _positive_int(max_words, "max_words")
    _positive_int(max_chars, "max_chars")
    _time(max_gap, "max_gap")
    merged = _merge_punctuation(_ordered(words, TimedWord))
    cues: list[Cue] = []
    current: list[TimedWord] = []

    def flush() -> None:
        if current:
            cues.append(Cue(" ".join(word.text for word in current),
                            current[0].start, current[-1].end))
            current.clear()

    for word in merged:
        proposed = " ".join(item.text for item in current + [word])
        if current and (
            len(current) >= max_words or len(proposed) > max_chars
            or _fraction(word.start) - _fraction(current[-1].end) > _fraction(max_gap)
        ):
            flush()
        current.append(word)
        if _SENTENCE_END.search(word.text):
            flush()
    flush()
    return cues


def _render_interval(cue: Cue, resolution: int) -> tuple[int, int]:
    start, end = _ticks(cue.start, resolution), _ticks(cue.end, resolution)
    if end <= start:
        raise ValueError("cue collapses at this subtitle format's time resolution")
    return start, end


def render_srt(cues: Iterable[Cue]) -> str:
    """Return plain, numbered SRT. HTML-sensitive characters are escaped."""
    blocks: list[str] = []
    for index, cue in enumerate(_ordered(cues, Cue), start=1):
        start, end = _render_interval(cue, 1000)
        a = _timestamp(start, 1000, ",", 3, 2)
        b = _timestamp(end, 1000, ",", 3, 2)
        blocks.append(f"{index}\n{a} --> {b}\n{escape(cue.text, quote=False)}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


_ASS_LITERAL = str.maketrans({"\\": "＼", "{": "｛", "}": "｝"})


def render_ass(
    cues: Iterable[Cue], *, width: int = 1280, height: int = 720,
    font_size: int = 42,
) -> str:
    """Return minimal ASS with a fixed header and no user-supplied overrides.

    Backslashes/braces in caption text become visibly similar fullwidth glyphs,
    preventing them from being interpreted as ASS commands. This is deliberately
    lossy plain-text output, not an ASS-markup authoring API. No font is bundled.
    """
    _positive_int(width, "width", 16384)
    _positive_int(height, "height", 16384)
    _positive_int(font_size, "font_size", 512)
    events: list[str] = []
    for cue in _ordered(cues, Cue):
        start, end = _render_interval(cue, 100)
        a = _timestamp(start, 100, ".", 2, 1)
        b = _timestamp(end, 100, ".", 2, 1)
        text = cue.text.translate(_ASS_LITERAL)
        events.append(f"Dialogue: 0,{a},{b},Default,,0,0,0,,{text}")
    header = (
        "[Script Info]\nScriptType: v4.00+\nTitle: Captions\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,sans-serif,{font_size},&H00FFFFFF,&H000000FF,&H00000000,"
        "&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,40,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    return header + "\n".join(events) + ("\n" if events else "")


__all__ = ["TimedWord", "Cue", "group_words", "format_srt_time", "format_ass_time",
           "render_srt", "render_ass"]
