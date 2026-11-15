"""Synthetic boundary and safety tests; no private package imports or fixtures."""

from dataclasses import FrozenInstanceError
from decimal import localcontext
import unittest

from caption_timing import (
    Cue, TimedWord, format_ass_time, format_srt_time, group_words,
    render_ass, render_srt,
)


class TimestampTests(unittest.TestCase):
    def test_srt_rounds_half_up_and_carries_across_minutes_and_hours(self):
        for seconds, expected in [
            (0, "00:00:00,000"), (0.0005, "00:00:00,001"),
            (59.9994, "00:00:59,999"), (59.9995, "00:01:00,000"),
            (3599.9995, "01:00:00,000"), (360000, "100:00:00,000"),
        ]:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_srt_time(seconds), expected)

    def test_ass_rounds_half_up_and_carries_across_minutes_and_hours(self):
        for seconds, expected in [
            (0, "0:00:00.00"), (0.005, "0:00:00.01"),
            (59.994, "0:00:59.99"), (59.995, "0:01:00.00"),
            (3599.995, "1:00:00.00"), (360000, "100:00:00.00"),
        ]:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_ass_time(seconds), expected)

    def test_rounding_does_not_depend_on_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(format_srt_time(3599.9995), "01:00:00,000")
            self.assertEqual(format_ass_time(3599.995), "1:00:00.00")

    def test_invalid_times_rejected_by_both_formatters(self):
        for formatter in (format_srt_time, format_ass_time):
            for value in (-1, float("nan"), float("inf"), -float("inf")):
                with self.subTest(formatter=formatter.__name__, value=value):
                    with self.assertRaises(ValueError):
                        formatter(value)
            for value in (True, False, "1", None, object()):
                with self.subTest(formatter=formatter.__name__, value=value):
                    with self.assertRaises(TypeError):
                        formatter(value)


class ValidationTests(unittest.TestCase):
    def test_dataclasses_are_immutable(self):
        for item in (TimedWord("word", 0, 1), Cue("some words", 0, 1)):
            with self.assertRaises(FrozenInstanceError):
                item.end = 2

    def test_invalid_intervals_rejected(self):
        for constructor in (TimedWord, Cue):
            for start, end in ((0, 0), (2, 1), (-1, 1),
                               (0, float("inf")), (float("nan"), 1)):
                with self.subTest(constructor=constructor.__name__, start=start, end=end):
                    with self.assertRaises(ValueError):
                        constructor("word", start, end)
            with self.assertRaises(TypeError):
                constructor("word", False, 1)

    def test_text_validation_and_whitespace_normalization(self):
        self.assertEqual(Cue("  line\r\n\nnext\tword  ", 0, 1).text, "line next word")
        self.assertEqual(TimedWord("  token  ", 0, 1).text, "token")
        for text in ("", " \n\t", "x\x00y", "x\x1by", "x\ud800y"):
            with self.subTest(text=repr(text)):
                with self.assertRaises(ValueError):
                    Cue(text, 0, 1)
        with self.assertRaises(ValueError):
            TimedWord("two words", 0, 1)
        with self.assertRaises(TypeError):
            Cue(123, 0, 1)

    def test_words_must_be_ordered_and_nonoverlapping(self):
        for words in ([TimedWord("late", 2, 3), TimedWord("early", 0, 1)],
                      [TimedWord("a", 0, 1), TimedWord("b", 0.9, 2)]):
            with self.assertRaises(ValueError):
                group_words(words)

    def test_cues_must_be_ordered_and_nonoverlapping(self):
        for renderer in (render_srt, render_ass):
            for cues in ([Cue("late", 2, 3), Cue("early", 0, 1)],
                         [Cue("a", 0, 1), Cue("b", 0.9, 2)]):
                with self.subTest(renderer=renderer.__name__, cues=cues):
                    with self.assertRaises(ValueError):
                        renderer(cues)

    def test_adjacent_intervals_and_generators_are_accepted(self):
        cues = group_words(TimedWord(text, i, i + 1) for i, text in enumerate(("a", "b")))
        self.assertEqual(cues, [Cue("a b", 0, 2)])
        self.assertIn("00:00:01,000 --> 00:00:02,000", render_srt(
            Cue(text, i, i + 1) for i, text in enumerate(("a", "b"))))

    def test_wrong_record_types_are_rejected(self):
        with self.assertRaises(TypeError):
            group_words([Cue("words", 0, 1)])
        for renderer in (render_srt, render_ass):
            with self.assertRaises(TypeError):
                renderer([TimedWord("word", 0, 1)])


class GroupingTests(unittest.TestCase):
    def test_punctuation_attaches_and_retains_timing(self):
        words = [TimedWord("Hello", 0, 0.4), TimedWord(",", 0.4, 0.45),
                 TimedWord("world", 0.5, 0.9), TimedWord("!", 0.9, 1)]
        self.assertEqual(group_words(words), [Cue("Hello, world!", 0, 1)])

    def test_opening_and_closing_punctuation(self):
        words = [TimedWord("(", 0, 0.1), TimedWord("hello", 0.1, 0.9),
                 TimedWord(")", 0.9, 1)]
        self.assertEqual(group_words(words), [Cue("(hello)", 0, 1)])

    def test_all_punctuation_and_trailing_opening_are_not_lost(self):
        self.assertEqual(group_words([TimedWord("(", 0, 0.1), TimedWord(")", 0.1, 1)]),
                         [Cue("()", 0, 1)])
        self.assertEqual(group_words([TimedWord("word", 0, 0.5), TimedWord("(", 0.5, 1)]),
                         [Cue("word(", 0, 1)])

    def test_sentence_end_boundary_with_closing_quote(self):
        self.assertEqual(group_words([TimedWord("Done.”", 0, 1), TimedWord("Next", 1, 2)]),
                         [Cue("Done.”", 0, 1), Cue("Next", 1, 2)])

    def test_word_and_character_limits(self):
        words = [TimedWord(text, i, i + 1) for i, text in enumerate(("one", "two", "three"))]
        self.assertEqual(group_words(words, max_words=2),
                         [Cue("one two", 0, 2), Cue("three", 2, 3)])
        self.assertEqual(group_words(words, max_chars=6),
                         [Cue("one", 0, 1), Cue("two", 1, 2), Cue("three", 2, 3)])

    def test_gap_limit_is_strict_and_decimal_stable(self):
        words = [TimedWord("a", 0, 0.1), TimedWord("b", 0.9, 1)]
        self.assertEqual(group_words(words, max_gap=0.8), [Cue("a b", 0, 1)])
        self.assertEqual(group_words(words, max_gap=0.79),
                         [Cue("a", 0, 0.1), Cue("b", 0.9, 1)])

    def test_long_single_token_is_retained_intact(self):
        self.assertEqual(group_words([TimedWord("unbrokenword", 0, 1)], max_chars=3),
                         [Cue("unbrokenword", 0, 1)])

    def test_invalid_grouping_options(self):
        for option in ("max_words", "max_chars"):
            for value, error in ((0, ValueError), (-1, ValueError),
                                 (True, TypeError), (1.5, TypeError)):
                with self.subTest(option=option, value=value):
                    with self.assertRaises(error):
                        group_words([], **{option: value})
        for value in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                group_words([], max_gap=value)


class OutputTests(unittest.TestCase):
    def test_srt_layout_numbering_and_plain_text(self):
        result = render_srt([Cue("<b>A & B</b>", 0, 1), Cue("Next", 1, 2)])
        self.assertEqual(result, "1\n00:00:00,000 --> 00:00:01,000\n"
                         "&lt;b&gt;A &amp; B&lt;/b&gt;\n\n"
                         "2\n00:00:01,000 --> 00:00:02,000\nNext\n")

    def test_srt_text_cannot_create_an_extra_block(self):
        hostile = "hello\n\n9\r\n00:00:10,000 --> 00:00:20,000\r\nother"
        result = render_srt([Cue(hostile, 0, 1)])
        self.assertEqual(len(result.splitlines()), 3)
        self.assertNotIn("\n\n", result)
        self.assertIn("hello 9 00:00:10,000 --&gt; 00:00:20,000 other", result)

    def test_ass_text_cannot_inject_commands_headers_or_events(self):
        hostile = r"{\pos(0,0)}\N" + "\n[Events]\nDialogue: injected,with,commas"
        result = render_ass([Cue(hostile, 0, 1)])
        self.assertEqual(result.count("[Events]"), 2)  # One literal occurrence in the text field.
        self.assertEqual(sum(line == "[Events]" for line in result.splitlines()), 1)
        events = [line for line in result.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(len(events), 1)
        text = events[0].split(",", 9)[9]
        self.assertEqual(text, "｛＼pos(0,0)｝＼N [Events] Dialogue: injected,with,commas")
        for command_character in ("\\", "{", "}"):
            self.assertNotIn(command_character, text)

    def test_ass_fixed_header_fields_and_dimensions(self):
        result = render_ass([Cue("Hello, world", 0, 1)], width=640, height=360, font_size=24)
        self.assertIn("PlayResX: 640\nPlayResY: 360\n", result)
        style = next(line for line in result.splitlines() if line.startswith("Style:"))
        self.assertEqual(len(style.split(",")), 23)
        self.assertTrue(style.startswith("Style: Default,sans-serif,24,"))
        self.assertIn(",,Hello, world\n", result)

    def test_ass_geometry_and_header_injection_rejected(self):
        for field, max_value in (("width", 16384), ("height", 16384), ("font_size", 512)):
            for value, error in ((0, ValueError), (-1, ValueError), (max_value + 1, ValueError),
                                 (True, TypeError), ("1\n[Events]", TypeError)):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(error):
                        render_ass([], **{field: value})
        with self.assertRaises(TypeError):
            render_ass([], font="arbitrary")

    def test_collapsed_output_intervals_are_rejected_without_extension(self):
        with self.assertRaises(ValueError):
            render_srt([Cue("tiny", 0, 0.0004)])
        with self.assertRaises(ValueError):
            render_ass([Cue("tiny", 0, 0.004)])
        self.assertIn("00:00:00,001", render_srt([Cue("one millisecond", 0, 0.001)]))
        with self.assertRaises(ValueError):
            render_ass([Cue("one millisecond", 0, 0.001)])

    def test_empty_input(self):
        self.assertEqual(group_words([]), [])
        self.assertEqual(render_srt([]), "")
        self.assertIn("[Events]\n", render_ass([]))
        self.assertNotIn("Dialogue:", render_ass([]))


if __name__ == "__main__":
    unittest.main()
