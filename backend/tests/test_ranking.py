import pytest

from app.services import ranking


def test_tokenize_drops_stopwords_and_short_tokens_and_lowercases():
    assert ranking.tokenize("What is the Rent for Flat 4B?") == ["rent", "flat", "4b"]


def test_bm25_ranks_the_relevant_passage_first():
    docs = [
        "The tenant pays monthly rent of 18,500 rupees by the fifth of each month.",
        "Pets are not allowed inside the apartment premises.",
        "The security deposit equals three months of rent.",
    ]
    scores = ranking.bm25_scores("monthly rent amount", docs)
    assert ranking.rank_by_score(scores)[0] == 0


def test_bm25_gives_zero_when_no_terms_overlap():
    assert ranking.bm25_scores("quantum chromodynamics", ["pets are not allowed", "rent is due"]) == [0.0, 0.0]


def test_bm25_handles_empty_inputs():
    assert ranking.bm25_scores("rent", []) == []
    assert ranking.bm25_scores("the of and", ["rent due"]) == [0.0]  # query is all stopwords


def test_rare_terms_outweigh_common_ones():
    docs = ["alpha alpha alpha beta", "alpha gamma", "alpha delta", "alpha epsilon"]
    scores = ranking.bm25_scores("alpha gamma", docs)
    assert scores[1] == max(scores)


def test_rank_by_score_drops_non_positive_and_is_stable():
    assert ranking.rank_by_score([0.0, 2.0, 2.0, 1.0]) == [1, 2, 3]


def test_cosine_basics():
    assert ranking.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert ranking.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert ranking.cosine([], [1]) == 0.0
    assert ranking.cosine([1, 2], [1]) == 0.0  # length mismatch
    assert ranking.cosine([0, 0], [1, 1]) == 0.0


def test_reciprocal_rank_fusion_rewards_agreement():
    fused = ranking.reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    order = [item for item, _ in fused]
    assert set(order[:2]) == {"a", "b"}          # items both lists like come first
    assert order[2:] == ["c", "d"] or order[2:] == ["d", "c"]


def test_rrf_includes_items_found_by_only_one_ranker():
    fused = dict(ranking.reciprocal_rank_fusion([["a"], ["b"]]))
    assert set(fused) == {"a", "b"}
