"""Contact-masking filter unit tests (must-test, incl. full-width/kana edges)."""

from __future__ import annotations

import pytest

from app.services.masking import MASK, mask_contact_info


@pytest.mark.parametrize(
    "text",
    [
        "電話番号は09012345678です",          # 11 digits inline
        "090-1234-5678 にかけて",             # hyphenated
        "０９０１２３４５６７８",                # full-width digits
        "0 9 0 1 2 3 4 5 6 7 8",              # spaced digits
        "（090）1234-5678",                    # full-width parens
        "0312345678",                          # 10-digit landline
    ],
)
def test_phone_numbers_are_masked(text: str) -> None:
    result = mask_contact_info(text)
    assert result.was_filtered is True
    assert MASK in result.text


@pytest.mark.parametrize(
    "text",
    [
        "taro@example.com まで",
        "taro.yamada+jobs@mail.co.jp",
        "taro＠example.com",  # full-width @
    ],
)
def test_emails_are_masked(text: str) -> None:
    result = mask_contact_info(text)
    assert result.was_filtered is True
    assert "@" not in result.text and "＠" not in result.text


@pytest.mark.parametrize(
    "text",
    [
        "LINEで連絡しよう",
        "lineやってる？",
        "Line ID 教えて",
        "ライン交換しよ",
        "らいんで",
        "ＬＩＮＥ",
        "TEL ください",
        "電話して",
    ],
)
def test_contact_keywords_are_masked(text: str) -> None:
    result = mask_contact_info(text)
    assert result.was_filtered is True
    assert MASK in result.text


@pytest.mark.parametrize(
    "text",
    [
        "明日はよろしくお願いします",
        "日当18000円で大丈夫です",       # wage digits (<10) stay
        "8:00に現場集合で",              # time stays
        "2024年4月1日スタート",          # date digits broken by kanji
        "オンラインではなく現場です",      # 'online' kana must not trip LINE
        "deadline は明日です",            # 'deadline' must not trip LINE
    ],
)
def test_clean_messages_pass_through(text: str) -> None:
    result = mask_contact_info(text)
    assert result.was_filtered is False
    assert result.text == text


def test_partial_masking_keeps_surrounding_text() -> None:
    result = mask_contact_info("電話は09012345678です")
    assert result.was_filtered is True
    assert "です" in result.text
    assert "09012345678" not in result.text
