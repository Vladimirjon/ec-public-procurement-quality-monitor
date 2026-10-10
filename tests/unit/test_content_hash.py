"""Feature raw-evidence-store (F1), AC1, outcome O1: the content hash value object.

`ContentHash` identifies bytes by their SHA-256 as 64 lowercase hexadecimal
characters. It is an immutable value: equal and hashable by value. Everything
that is not exactly 64 lowercase hex characters is rejected with `ValueError`.
"""

import pytest

from ec_procurement_quality.domain.content_hash import ContentHash

# Standard SHA-256 test vectors (FIPS 180-2) for b"abc" and b"".
ABC_HEXDIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_HEXDIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_of_computes_sha256_of_the_given_bytes() -> None:
    assert ContentHash.of(b"abc").hexdigest == ABC_HEXDIGEST


def test_of_empty_content_is_the_sha256_of_nothing() -> None:
    assert ContentHash.of(b"").hexdigest == EMPTY_HEXDIGEST


def test_building_from_a_valid_hexdigest_keeps_it_as_given() -> None:
    assert ContentHash(ABC_HEXDIGEST).hexdigest == ABC_HEXDIGEST


def test_hashes_of_the_same_bytes_are_equal_and_hash_alike() -> None:
    first = ContentHash.of(b"abc")
    second = ContentHash.of(b"abc")

    assert first == second
    assert hash(first) == hash(second)


def test_hash_built_from_text_equals_hash_computed_from_bytes() -> None:
    assert ContentHash(ABC_HEXDIGEST) == ContentHash.of(b"abc")


def test_hashes_of_different_bytes_are_different() -> None:
    assert ContentHash.of(b"abc") != ContentHash.of(b"abd")


def test_equal_hashes_are_the_same_set_and_dict_key() -> None:
    first = ContentHash.of(b"abc")
    second = ContentHash(ABC_HEXDIGEST)

    assert len({first, second}) == 1
    assert {first: "x"}[second] == "x"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(ABC_HEXDIGEST.upper(), id="uppercase"),
        pytest.param(ABC_HEXDIGEST[:1].upper() + ABC_HEXDIGEST[1:], id="mixed-case"),
        pytest.param(ABC_HEXDIGEST[:63], id="63-characters"),
        pytest.param(ABC_HEXDIGEST + "a", id="65-characters"),
        pytest.param("z" * 64, id="not-hex"),
        pytest.param("", id="empty"),
        pytest.param("a" * 63 + "\n", id="64-characters-ending-in-newline"),
        pytest.param(" " + ABC_HEXDIGEST[:63], id="64-characters-with-leading-space"),
        pytest.param("0x" + ABC_HEXDIGEST[:62], id="hex-prefix"),
    ],
)
def test_invalid_hexdigest_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        ContentHash(value)


def test_hexdigest_cannot_be_reassigned() -> None:
    content_hash = ContentHash.of(b"abc")

    # "An exception": the intent does not fix which type signals immutability.
    with pytest.raises(Exception):  # noqa: B017
        setattr(content_hash, "hexdigest", EMPTY_HEXDIGEST)  # noqa: B010

    assert content_hash.hexdigest == ABC_HEXDIGEST
