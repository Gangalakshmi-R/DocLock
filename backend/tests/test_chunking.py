import pytest

from app.services.chunking import split_chunks


def test_empty_and_whitespace_text_give_no_chunks():
    assert split_chunks("") == []
    assert split_chunks("   \n\t ") == []


def test_short_text_is_a_single_chunk():
    chunks = split_chunks("Hello world.", 1000, 150)
    assert chunks == [("Hello world.", 0, 12)]


def test_offsets_point_back_into_the_original_text():
    text = " ".join(f"word{i}." for i in range(600))
    for chunk, start, end in split_chunks(text, 300, 50):
        assert text[start:end].strip() == chunk


def test_chunks_respect_the_size_limit_and_cover_the_text():
    text = "Sentence number one is here. " * 200
    chunks = split_chunks(text, 400, 60)
    assert all(len(c) <= 400 for c, _, _ in chunks)
    assert chunks[0][1] == 0
    assert chunks[-1][2] == len(text)


def test_consecutive_chunks_overlap():
    text = "alpha beta gamma delta epsilon " * 100
    chunks = split_chunks(text, 200, 40)
    for (_, _, prev_end), (_, next_start, _) in zip(chunks, chunks[1:]):
        assert next_start < prev_end


def test_prefers_paragraph_then_sentence_boundaries():
    text = ("A" * 300 + "\n\n" + "B" * 300 + ". " + "C" * 300)
    first = split_chunks(text, 650, 50)[0][0]
    assert first.endswith("A" * 300) or first.endswith("B" * 300 + ".")  # never cuts a run of letters mid-way


def test_text_without_any_spaces_still_terminates():
    chunks = split_chunks("x" * 5000, 1000, 100)
    assert len(chunks) >= 5
    assert chunks[-1][2] == 5000


@pytest.mark.parametrize("size,overlap", [(0, 0), (-5, 0), (100, 100), (100, 150), (100, -1)])
def test_invalid_parameters_raise(size, overlap):
    with pytest.raises(ValueError):
        split_chunks("some text", size, overlap)
