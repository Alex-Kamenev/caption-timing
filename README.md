# caption-timing

A small, reusable caption timing and grouping component. It accepts timed words or cues and returns plain SRT or minimal ASS text. The example uses invented text and timestamps.

Released under the [MIT License](LICENSE).

## Origin

Adapted from personal media tooling, then isolated and revised with AI assistance for this release. This standalone adaptation was prepared in November 2026.

## Scope

- Frozen `TimedWord` and `Cue` dataclasses with validated timing and text.
- Punctuation-aware grouping with word, character and pause limits.
- Integer millisecond/centisecond timestamp formatting with rounding carry.
- Plain SRT and fixed-header ASS output, returned as strings.

Runtime code uses only the Python standard library and requires Python 3.10 or later. There are no provider, API or model integrations, bundled fonts, media assets or rendering engines.

## Try the synthetic example

Run these commands from this directory; installing the package is unnecessary:

```console
python -m unittest discover -s tests -v
python -m examples.synthetic
```

The example writes `demo-output/example.srt` and `demo-output/example.ass`. Output is UTF-8 with LF newlines. These generated files are ignored by Git.

```python
from caption_timing import TimedWord, group_words, render_srt

words = [
    TimedWord("Hello", 0, 0.4),
    TimedWord(",", 0.4, 0.45),
    TimedWord("world!", 0.5, 1.0),
]
cues = group_words(words, max_words=7, max_chars=42, max_gap=0.8)
print(render_srt(cues))
```

## Timing contract

Times are nonnegative, finite seconds supplied as built-in `int` or `float` values. Booleans, strings and objects requiring conversion are rejected. Each word or cue must have `end > start`. Input sequences must already be ordered and nonoverlapping; adjacent intervals are allowed. The utility never sorts input or extends a cue to invent duration.

Timestamps use decimal-spelling, half-up rounding to integer ticks: SRT uses milliseconds and ASS uses centiseconds. Carry is applied before formatting, so `59.9995` seconds becomes `00:01:00,000` in SRT, and `59.995` becomes `0:01:00.00` in ASS. A positive interval that rounds to zero duration at the selected format's resolution raises `ValueError`.

`TimedWord` accepts a single token. `Cue` accepts text containing spaces. Both normalize whitespace and reject empty text, remaining control characters and surrogates. Writers accept `Cue` sequences; `group_words` accepts `TimedWord` sequences. Generators are supported.

## Grouping behavior

Punctuation-only tokens are joined to a neighboring token while preserving their timing span. Opening punctuation attaches to the following word; other punctuation normally attaches to the preceding word. Sentence-ending punctuation ends a group. This is a simple heuristic, not language analysis; abbreviations and ambiguous quotation marks may require caller-controlled cues.

Groups split when the next token would exceed `max_words` or `max_chars`, or when a pause is greater than `max_gap`. The character limit includes joining spaces. A single token longer than the character limit is kept whole. There is no syllable splitting, line balancing or forced reading-speed policy.

## Output safety and limits

SRT text is HTML-escaped, so supplied tags are not emitted as subtitle formatting. Text is flattened to one line per cue, preventing blank-line or new-event injection. Subtitle-player interpretation of escaped entities varies.

ASS output has a fixed header and style. Only bounded integer dimensions and font size are configurable. The generic `sans-serif` family is a system font reference; no font file is provided. Backslashes and braces in caption text are replaced with visibly similar fullwidth characters (`＼`, `｛`, `｝`) so supplied ASS override tags and escape commands remain text. **This replacement is deliberately lossy.** Commas remain valid in the final text field. No raw ASS styles, effects, header strings or font names are accepted.

Tests cover timing boundaries, validation, grouping and output structure/injection resistance. They do not establish rendering behavior in any particular subtitle player. Review the generated files in the intended renderer before use; this component does not inspect or run that renderer.
