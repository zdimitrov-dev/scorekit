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


def test_sibling_movement_ranks_below_the_exact_match_but_is_kept():
    # Op.28 No.6 is not what was asked for, but it *is* the same set — the soft-narrow
    # policy keeps it as a discoverable neighbour, well beneath the exact hit.
    q = "Prelude Op 28 No 4"
    exact = match_score(_card("Chopin - Prelude Op. 28 No. 4"), q)
    sibling = match_score(_card("Chopin - Prelude Op. 28 No. 6"), q)
    assert exact == 1.0
    assert DROP_THRESHOLD <= sibling < exact


def test_scores_are_granular_not_bucketed():
    # A flat score collapses "Best match" into its tiebreak; near-misses must separate.
    q = "Chopin Op 48 No 1"
    scores = [
        match_score(_card("Chopin - Nocturne Op. 48 No. 1"), q),
        match_score(_card("Seong-Jin Cho - Nocturne in C minor Op. 48 No. 1"), q),
        match_score(_card("Chopin Nocturne Op. 48"), q),
    ]
    assert len(set(scores)) == len(scores)


def test_artist_query_matches_on_author():
    """Regression: searching an artist returned nothing. YouTube gave nine correct Birru
    uploads and the filter dropped all nine, because "Birru" is the channel and never
    appears in a video title."""
    cards = [
        _card("just the way you are - bruno mars", author="Birru"),
        _card("clair de lune but it's 3am", author="Birru"),
        _card("the part of hamnet where you cry", author="Birru"),
    ]
    assert all(match_score(c, "Birru") == 1.0 for c in cards)
    kept, dropped = annotate_and_filter(cards, "Birru")
    assert (len(kept), dropped) == (3, 0)


def test_shortened_artist_names_still_match():
    """Regression: "Kat Cordova" dropped 11 of 12 correct results, because an exact
    contiguous run was required and "kat" is not "katherine". People type names short."""
    cards = [
        _card("Hans Zimmer - Interstellar EPIC PIANO SUITE", author="Katherine Cordova"),
        _card("The Odyssey - Odysseus (Reimagined)", author="Katherine Cordova"),
    ]
    assert all(match_score(c, "Kat Cordova") == 1.0 for c in cards)
    kept, dropped = annotate_and_filter(cards, "Kat Cordova")
    assert (len(kept), dropped) == (2, 0)


def test_author_match_stays_precise():
    # a partial overlap with a channel name must NOT rescue a card the title rejected,
    # or the filter loses the precision it exists for
    c = _card("Beethoven — Moonlight Sonata", author="Piano Tutorials")
    assert match_score(c, "Chopin Nocturne") == 0.0

    # the composer's surname alone does not make every upload by them a phrase match
    c = _card("Some Unrelated Work", author="Frédéric Chopin")
    assert match_score(c, "Chopin Nocturne") < DROP_THRESHOLD

    # order matters, and a prefix needs enough characters to mean something
    assert match_score(_card("x", author="Cordova Katherine"), "Kat Cordova") == 0.0
    assert match_score(_card("x", author="Katherine Cordova"), "Ka Cordova") == 0.0


def test_author_does_not_inflate_ordinary_piece_queries():
    # scores for piece queries must be unchanged by the author path
    performance = _card("Debussy - Clair de Lune", author="Rousseau")
    assert match_score(performance, "Clair de Lune", "Debussy") == 1.0
    lesser = _card("Au Clair de la Lune, Op.41", source="imslp", author="Jāzeps Vītols")
    assert DROP_THRESHOLD <= match_score(lesser, "Clair de Lune", "Debussy") < 1.0


def test_annotate_and_filter_records_source_rank():
    cards = [_card("Debussy - Clair de Lune"), _card("Clair de Lune (live)")]
    kept, _ = annotate_and_filter(cards, "Clair de Lune", "Debussy")
    assert [c.metadata["rank"] for c in kept] == [0, 1]


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
