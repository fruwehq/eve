from __future__ import annotations

import pytest

from eve_sdk.semver import SemverError, satisfies


class TestCommaRange:
    def test_comma_range_inclusive(self) -> None:
        assert satisfies("4.0", ">=4.0,<5.0")
        assert satisfies("4.5", ">=4.0,<5.0")

    def test_comma_range_below(self) -> None:
        assert not satisfies("3.9", ">=4.0,<5.0")

    def test_comma_range_at_upper(self) -> None:
        assert not satisfies("5.0", ">=4.0,<5.0")

    def test_comma_range_with_patch(self) -> None:
        assert satisfies("4.0.1", ">=4.0,<5.0")
        assert satisfies("4.5.3", ">=4.0,<5.0")


class TestCaretRange:
    def test_caret_major(self) -> None:
        assert satisfies("4.0", "^4.0")
        assert satisfies("4.5", "^4.0")
        assert satisfies("4.9.9", "^4.0")

    def test_caret_excludes_next_major(self) -> None:
        assert not satisfies("5.0", "^4.0")

    def test_caret_excludes_below(self) -> None:
        assert not satisfies("3.9", "^4.0")

    def test_caret_minor(self) -> None:
        assert satisfies("0.2.0", "^0.2.0")
        assert satisfies("0.2.5", "^0.2.0")
        assert not satisfies("0.3.0", "^0.2.0")


class TestExactMatch:
    def test_exact_major_minor(self) -> None:
        assert satisfies("4.0", "4.0")

    def test_exact_full(self) -> None:
        assert satisfies("4.0.0", "4.0.0")

    def test_exact_rejects_different_minor(self) -> None:
        assert not satisfies("4.1", "4.0")

    def test_exact_rejects_different_major(self) -> None:
        assert not satisfies("5.0", "4.0")

    def test_explicit_equals(self) -> None:
        assert satisfies("4.0", "=4.0")


class TestComparison:
    def test_gte(self) -> None:
        assert satisfies("4.0", ">=4.0")
        assert satisfies("5.0", ">=4.0")
        assert not satisfies("3.9", ">=4.0")

    def test_gt(self) -> None:
        assert satisfies("4.1", ">4.0")
        assert not satisfies("4.0", ">4.0")

    def test_lte(self) -> None:
        assert satisfies("4.0", "<=4.0")
        assert satisfies("3.9", "<=4.0")
        assert not satisfies("4.1", "<=4.0")

    def test_lt(self) -> None:
        assert satisfies("3.9", "<4.0")
        assert not satisfies("4.0", "<4.0")


class TestTilde:
    def test_tilde_major_minor(self) -> None:
        assert satisfies("4.0", "~4.0")
        assert satisfies("4.0.9", "~4.0")
        assert not satisfies("4.1", "~4.0")


class TestError:
    def test_empty_range(self) -> None:
        with pytest.raises(SemverError):
            satisfies("4.0", "")

    def test_invalid_version(self) -> None:
        with pytest.raises(SemverError):
            satisfies("abc", ">=4.0")

    def test_invalid_range(self) -> None:
        with pytest.raises(SemverError):
            satisfies("4.0", "xyz")
