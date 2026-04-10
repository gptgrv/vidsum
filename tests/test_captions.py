from __future__ import annotations

from vidsum.captions import _parse_json3_caption, _select_caption


def test_parse_json3_caption_events() -> None:
    transcript = _parse_json3_caption(
        """{
  "events": [
    {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "hello"}, {"utf8": " world"}]},
    {"tStartMs": 3000, "dDurationMs": 1000, "segs": [{"utf8": "\\n"}]},
    {"tStartMs": 4000, "dDurationMs": 1500, "segs": [{"utf8": "next"}, {"utf8": " line"}]}
  ]
}""",
        language="en",
        duration_seconds=10,
    )

    assert transcript.language == "en"
    assert transcript.duration_seconds == 10
    assert [(s.start, s.end, s.text) for s in transcript.segments] == [
        (1.0, 3.0, "hello world"),
        (4.0, 5.5, "next line"),
    ]


def test_select_caption_prefers_english_json3_manual_subtitles() -> None:
    caption = _select_caption(
        {
            "subtitles": {
                "en": [
                    {"ext": "vtt", "url": "https://example.com/manual.vtt"},
                    {"ext": "json3", "url": "https://example.com/manual.json3"},
                ]
            },
            "automatic_captions": {
                "en-orig": [{"ext": "json3", "url": "https://example.com/auto.json3"}]
            },
        }
    )

    assert caption == {
        "url": "https://example.com/manual.json3",
        "ext": "json3",
        "language": "en",
        "source": "youtube-subtitles",
    }
