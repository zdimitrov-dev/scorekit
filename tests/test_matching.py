from scorekit.matching import DROP_THRESHOLD, annotate_and_filter, match_score
from scorekit.models import Card


def _card(title, source="youtube", author=None):
    return Card(source=source, external_id=title, url="u", title=title, author=author)


def test_exact_phrase_scores_top():
    c = _card("Debussy - Clair de Lune", author="Rousseau")
    assert match_score(c, "Clair de Lune", "Debussy") == 1.0  # phrase + composer


def test_phrase_without_composer_still_high():
    # a legit lo-fi cover that never names the composer
    c = _card("clair de lune but it's 3am", author="Birru")
    assert match_score(c, "Clair de Lune", "Debussy") == 1.0  # contiguous phrase


def test_same_words_not_phrase_scores_lower_but_kept():
    # "Au clair de la lune" has the words but not the contiguous phrase, and a
    # different composer — a lesser/related work we keep, ranked below the real one.
    c = _card("Au Clair de la Lune, Op.41", source="imslp", author="Jāzeps Vītols")
    s = match_score(c, "Clair de Lune", "Debussy")
    assert 0.35 <= s < 1.0


def test_unrelated_scores_zero():
    c = _card("Beethoven — Moonlight Sonata")
    assert match_score(c, "Clair de Lune", "Debussy") == 0.0


def test_imslp_real_work_gets_composer_boost():
    c = _card("Clair de lune", source="imslp", author="Claude Debussy")
    assert match_score(c, "Clair de Lune", "Debussy") == 1.0


def test_opus_number_disambiguates():
    # a bare opus query must reject a *different* opus that shares the common words
    q = "Op 48 No 1"
    right = _card("F. Chopin: Nocturne in C minor, Op.48 No.1")
    wrong = _card("Album for the Young Op.68 No.1")
    assert match_score(right, q) == 1.0
    assert match_score(wrong, q) < DROP_THRESHOLD


def test_annotate_and_filter_drops_and_scores():
    cards = [
        _card("Debussy - Clair de Lune"),                 # 1.0 keep
        _card("Au Clair de la Lune", source="imslp", author="Erik Satie"),  # ~0.5 keep
        _card("Totally Unrelated Song"),                  # 0.0 drop
    ]
    kept, dropped = annotate_and_filter(cards, "Clair de Lune", "Debussy")
    assert dropped == 1
    assert [c.title for c in kept] == ["Debussy - Clair de Lune", "Au Clair de la Lune"]
    assert all("match_score" in c.metadata for c in kept)
    assert kept[0].metadata["match_score"] >= kept[1].metadata["match_score"]
