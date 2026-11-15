"""Write two subtitle files from invented words and timestamps."""

from pathlib import Path

from caption_timing import TimedWord, group_words, render_ass, render_srt


def main() -> None:
    words = [
        TimedWord("Hello", 0.0, 0.4),
        TimedWord(",", 0.4, 0.45),
        TimedWord("world", 0.5, 0.95),
        TimedWord("!", 0.95, 1.0),
        TimedWord("A", 1.5, 1.65),
        TimedWord("small", 1.7, 2.0),
        TimedWord("example", 2.05, 2.55),
        TimedWord(".", 2.55, 2.6),
    ]
    cues = group_words(words, max_words=4, max_chars=32)
    output = Path("demo-output")
    output.mkdir(exist_ok=True)
    for name, content in [("example.srt", render_srt(cues)),
                          ("example.ass", render_ass(cues))]:
        with (output / name).open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    print("Wrote demo-output/example.srt and demo-output/example.ass")


if __name__ == "__main__":
    main()
