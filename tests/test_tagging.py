from scorekit.tagging import CONFIDENT_MATCH, _surname, derive_tags, tag_rows


def _card(source="imslp", author=None, title=None, score=1.0, **meta):
    """A stored card row. ``score`` is the attribution match_score."""
    return {
        "source": source, "author": author, "title": title,
        "metadata": {**meta, "match_score": score},
    }


def test_surname_handles_both_imslp_spellings():
    assert _surname("Claude Debussy") == "debussy"
    assert _surname("Debussy, Claude") == "debussy"
    assert _surname("Frédéric Chopin") == "chopin"
    assert _surname("") == ""


def test_composer_comes_from_imslp_author_not_youtube_channel():
    # a YouTube channel is a *performer*; tagging it as the composer would poison
    # every recommendation built on the composer feature
    piece = {"title": "Clair de Lune", "composer": None}
    cards = [
        _card(source="youtube", author="Rousseau", title="Debussy - Clair de Lune"),
        _card(source="imslp", author="Claude Debussy", title="Clair de lune"),
    ]
    tags = derive_tags(piece, cards)
    assert ("composer", "debussy") in tags
    assert ("composer", "rousseau") not in tags


def test_era_prefers_the_curated_composer_table_over_imslp_style():
    # IMSLP files Debussy under "Early 20th century"; "impressionist" is the distinction
    # that actually matters for recommending, so the curated table wins.
    piece = {"title": "Clair de Lune", "composer": "Debussy"}
    tags = derive_tags(piece, [_card(piece_style="Early 20th century")])
    assert ("era", "impressionist") in tags
    assert ("style", "early 20th century") in tags   # kept as its own tag
    assert ("era", "modern") not in tags


def test_era_falls_back_to_imslp_style_for_an_unknown_composer():
    piece = {"title": "Something", "composer": "Someone Unlisted"}
    tags = derive_tags(piece, [_card(piece_style="Baroque")])
    assert ("era", "baroque") in tags


def test_era_falls_back_to_composer_when_unenriched():
    piece = {"title": "Clair de Lune", "composer": "Claude Debussy"}
    tags = derive_tags(piece, [_card(source="youtube", author="Rousseau")])
    assert ("era", "impressionist") in tags


def test_unknown_composer_yields_no_era():
    # a wrong era silently biases everything downstream — prefer no tag
    piece = {"title": "Something", "composer": "Nobody Inparticular"}
    tags = derive_tags(piece, [])
    assert not any(k == "era" for k, _ in tags)
    assert ("composer", "inparticular") in tags


def test_form_is_read_from_card_titles_when_the_query_lacks_it():
    # the piece title is whatever the user typed, which often names no form at all
    piece = {"title": "Chopin Op 48 No 1", "composer": "Chopin"}
    cards = [_card(source="youtube", title="Chopin - Nocturne Op. 48 No. 1")]
    tags = derive_tags(piece, cards)
    assert ("form", "nocturne") in tags


def test_multiple_forms_are_captured():
    piece = {"title": "Prelude and Fugue in C major", "composer": "Bach"}
    tags = derive_tags(piece, [])
    assert ("form", "prelude") in tags
    assert ("form", "fugue") in tags
    assert ("era", "baroque") in tags


def test_accented_and_cased_values_collapse():
    piece = {"title": "Gymnopédie No.1", "composer": "Satie"}
    cards = [_card(instrumentation="Piano"), _card(instrumentation="piano")]
    tags = derive_tags(piece, cards)
    assert ("form", "gymnopedie") in tags
    assert ("instrumentation", "piano") in tags
    assert len([1 for k, _ in tags if k == "instrumentation"]) == 1


def test_instrumentation_is_a_controlled_vocabulary_not_free_text():
    # IMSLP writes rosters with HTML in them; the raw string compares against nothing
    piece = {"title": "Clair de Lune", "composer": "Debussy"}
    roster = "''solo'': piano<br>''orchestra'': flutes, oboes + horns + timpani + strings"
    tags = derive_tags(piece, [_card(instrumentation=roster)])
    instruments = {v for k, v in tags if k == "instrumentation"}
    assert {"piano", "flute", "oboe", "horn", "orchestra"} <= instruments
    assert not any("<br>" in v for v in instruments)


def test_weak_matches_do_not_define_the_piece():
    """Regression: neighbours kept by the lenient attribution filter were describing
    the piece — tagging Debussy's "Clair de lune" a rag, and Beethoven's "Moonlight
    Sonata" with the composer of a guitar arrangement of it."""
    piece = {"title": "Clair de Lune", "composer": "Debussy"}
    cards = [
        _card(source="imslp", author="Claude Debussy", title="Clair de lune",
              score=1.0, instrumentation="piano", piece_style="Early 20th century"),
        # a loosely-related neighbour, kept for discovery but not this piece
        _card(source="imslp", author="Scott Joplin", title="Maple Leaf Rag",
              score=0.4, instrumentation="guitar", piece_style="Romantic"),
    ]
    tags = derive_tags(piece, cards)
    assert ("form", "rag") not in tags
    assert ("instrumentation", "guitar") not in tags
    assert ("style", "romantic") not in tags
    assert ("instrumentation", "piano") in tags


def test_composer_vote_survives_a_derivative_works_arranger():
    """Regression: "Moonlight Sonata" came out as Ramón León Egea — the arranger IMSLP
    credits on a guitar transcription — because a lone IMSLP author was trusted."""
    piece = {"title": "Moonlight Sonata", "composer": None}
    cards = [
        _card(source="imslp", author="Ramón León Egea",
              title="Theme from Moonlight Sonata, Op.164"),
        _card(source="youtube", title="Beethoven - Moonlight Sonata (1st mvt)"),
        _card(source="youtube", title="Moonlight Sonata - Beethoven, played live"),
    ]
    tags = derive_tags(piece, cards)
    assert ("composer", "beethoven") in tags
    assert ("composer", "egea") not in tags
    assert ("era", "classical") in tags


def test_lone_imslp_author_is_not_trusted_without_corroboration():
    piece = {"title": "Chopin Nocturne", "composer": None}
    cards = [_card(source="imslp", author="Édouard Wolff", title="Homage à Chopin")]
    # the piece's own title names Chopin, which outranks a lone IMSLP author
    assert ("composer", "chopin") in derive_tags(piece, cards)

    unnamed = {"title": "Some Search", "composer": None}
    assert not any(k == "composer" for k, _ in derive_tags(unnamed, cards))


def test_a_single_incidental_mention_does_not_name_a_composer():
    """Regression: searching the artist "Birru" tagged the result Liszt, off one video
    titled "i hear a symphony if liszt composed it"."""
    piece = {"title": "Birru", "composer": None}
    cards = [
        _card(source="youtube", title="i hear a symphony if liszt composed it"),
        _card(source="youtube", title="glimpse of us if chopin composed it"),
        _card(source="youtube", title="the part of hamnet where you cry"),
    ]
    assert not any(k == "composer" for k, _ in derive_tags(piece, cards))

    # two mentions of the same name *is* evidence
    cards.append(_card(source="youtube", title="clair de lune if liszt composed it"))
    assert ("composer", "liszt") in derive_tags(piece, cards)


def test_a_lone_arrangement_does_not_redefine_the_work():
    """Regression: one ragtime cover tagged Debussy's "Clair de lune" a rag. An
    arrangement is a card about the piece, not a restatement of what the piece is."""
    piece = {"title": "Clair de Lune", "composer": "Debussy"}
    cards = [
        _card(source="youtube", title="Debussy: Suite bergamasque - III. Clair de lune"),
        _card(source="youtube", title="Debussy - Clair de Lune (Suite Bergamasque No. 3)"),
        _card(source="musescore", title="Clair De Lune in Ragtime (Debussy/DiGiorgi)"),
    ]
    tags = derive_tags(piece, cards)
    assert ("form", "suite") in tags     # two cards agree, and it is genuinely true
    assert ("form", "rag") not in tags   # one arrangement, outvoted


def test_form_in_the_piece_title_is_always_trusted():
    # the work's own name needs no corroboration
    tags = derive_tags({"title": "Moonlight Sonata", "composer": "Beethoven"}, [])
    assert ("form", "sonata") in tags


def test_confident_threshold_falls_back_when_nothing_qualifies():
    # a piece whose cards all scored modestly must still get tagged
    piece = {"title": "Gymnopedie", "composer": "Satie"}
    weak = [_card(title="Gymnopedie No.1", score=CONFIDENT_MATCH - 0.3, instrumentation="piano")]
    tags = derive_tags(piece, weak)
    assert ("instrumentation", "piano") in tags


def test_public_domain_when_any_card_is_free():
    piece = {"title": "Fur Elise", "composer": "Beethoven"}
    assert ("public_domain", "true") in derive_tags(
        piece, [_card(is_public_domain=False), _card(is_public_domain=True)]
    )
    assert ("public_domain", "true") not in derive_tags(piece, [_card(is_public_domain=False)])


def test_a_dominant_channel_becomes_the_creator_tag():
    # an artist search has no composer/era/form to speak of; without this it carries no
    # features at all and liking it can never influence the feed
    piece = {"title": "Patrik Pietschmann", "composer": None}
    cards = [
        _card(source="youtube", author="Patrik Pietschmann", title="DUNE - Main Theme"),
        _card(source="youtube", author="Patrik Pietschmann", title="Interstellar"),
        _card(source="youtube", author="Patrik Pietschmann", title="Phoenix"),
        _card(source="youtube", author="Peterson Piano Academy", title="Reacting to Patrik"),
    ]
    assert ("creator", "patrik pietschmann") in derive_tags(piece, cards)


def test_a_normal_spread_of_performers_yields_no_creator():
    piece = {"title": "Clair de Lune", "composer": "Debussy"}
    cards = [
        _card(source="youtube", author="Rousseau", title="Clair de Lune"),
        _card(source="youtube", author="Kassia", title="Clair de Lune"),
        _card(source="youtube", author="Lang Lang", title="Clair de Lune"),
    ]
    assert not any(k == "creator" for k, _ in derive_tags(piece, cards))


def test_bare_piece_produces_no_tags_rather_than_junk():
    assert derive_tags({"title": "Op 48", "composer": None}, []) == set()


def test_tag_rows_shape():
    rows = tag_rows("p1", {("era", "romantic"), ("composer", "chopin")})
    assert rows == [
        {"piece_id": "p1", "key": "composer", "value": "chopin"},
        {"piece_id": "p1", "key": "era", "value": "romantic"},
    ]
