"""context 모듈의 순수 헬퍼 테스트 (네트워크 없음)."""

from stock_quant.context import _capitalized_phrases, _clip


def test_extracts_proper_nouns_longest_first():
    phrases = _capitalized_phrases("Will New York City exceed 90F by June 1?")
    assert phrases[0] == "New York City"   # 가장 긴 고유명사 우선
    assert "June" in phrases


def test_drops_leading_question_word():
    # "Will" 같은 의문사는 제외돼야 한다.
    assert "Will" not in _capitalized_phrases("Will Bitcoin hit 100k?")
    assert "Bitcoin" in _capitalized_phrases("Will Bitcoin hit 100k?")


def test_no_proper_nouns_returns_empty():
    assert _capitalized_phrases("will it rain tomorrow?") == []


def test_clip_caps_length_and_collapses_whitespace():
    assert _clip("a\n\n  b   c") == "a b c"
    assert len(_clip("x " * 1000)) <= 600
