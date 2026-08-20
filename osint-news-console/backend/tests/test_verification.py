from app.verification import title_similarity


def test_similar_event_titles_match():
    score = title_similarity(
        "某国央行宣布下调基准利率",
        "某国央行今日宣布降低基准利率",
    )
    assert score >= 0.58


def test_unrelated_titles_do_not_match():
    score = title_similarity(
        "某国央行宣布下调基准利率",
        "新款手机处理器正式发布",
    )
    assert score < 0.58
