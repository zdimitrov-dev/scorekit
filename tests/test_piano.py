"""Keeping the corpus piano-specific (YouTube only).

Every case here is a real result seen live. The risk is asymmetric — junk in the corpus is
annoying, silently dropping genuine piano results is worse — so the recall cases matter
more than the precision ones.
"""
from scorekit.models import Card
from scorekit.piano import filter_piano, is_piano


def _card(title, author=None, desc=""):
    return Card(
        source="youtube", external_id=title, url="u", title=title, author=author,
        metadata={"description_excerpt": desc},
    )


# --- must be kept -----------------------------------------------------------

def test_classical_piano_without_the_word_piano():
    """"Chopin - Nocturne op.9 No.2" never says piano — not in the title, not in the
    description. A keyword filter drops it; the piece it belongs to is the evidence."""
    c = _card("Chopin - Nocturne op.9 No.2", author="andrea romano",
              desc="Nocturne in E-flat major, Op. 9, No. 2 Played by Vadim Chaimovich")
    assert is_piano(c, "Chopin Nocturne Op 9 No 2", "Chopin")


def test_piano_transcription_of_an_orchestral_work():
    """Kassia's "Beethoven - Symphony No. 5" is a Liszt piano transcription; the
    identically-titled DW Classical upload is an orchestra. Only the description
    separates them, so piano evidence has to be checked before the rejection rules."""
    transcription = _card("Beethoven - Symphony No. 5", author="Kassia",
                          desc="Symphony No.5 in C minor, Op. 67 (Arr. F. Liszt for piano)")
    orchestra = _card("Beethoven: Symphony No. 5 Fate Symphony",
                      author="DW Classical Music", desc="Four iconic notes")
    assert is_piano(transcription, "Beethoven Symphony No 5", "Beethoven")
    assert not is_piano(orchestra, "Beethoven Symphony No 5", "Beethoven")


def test_a_pianists_bio_does_not_reject_their_recital():
    """Regression: a pianist's description named the orchestras he plays with, and
    "philharmonic" dropped his solo Grieg. Rejection reads the title and channel only."""
    c = _card("Lugansky - Grieg, Wedding Day at Troldhaugen, from Lyric Pieces",
              author="Enchanted Wanderer",
              desc="Nikolai Lugansky has appeared with the Berlin Philharmonic and ...")
    assert is_piano(c, "Grieg Wedding Day at Troldhaugen", "Grieg")


def test_contemporary_piano_composers_are_recognised():
    """Regression: Yiruma's own uploads of "River Flows in You" were dropped — no piano
    word anywhere, and he was missing from the composer vocabulary."""
    c = _card("Yiruma - River Flows in You", author="YirumaVEVO")
    assert is_piano(c, "Yiruma River Flows in You")


def test_artist_uploads_are_kept_on_piano_evidence():
    c = _card("Hans Zimmer - Interstellar EPIC PIANO SUITE", author="Katherine Cordova")
    assert is_piano(c, "Kat Cordova")


def test_sheet_music_tooling_counts_as_piano_evidence():
    # flowkey / musicnotes / Synthesia only ever surround piano content
    c = _card("Moving Forward", author="Katherine Cordova",
              desc="Sheet music ▶ musicnotes.com/l/BRchQ  Learn with flowkey")
    assert is_piano(c, "Kat Cordova")


# --- must be dropped --------------------------------------------------------

def test_non_music_results_are_dropped():
    """The reported failure: searching the pianist "Rousseau" also returns political
    philosophy, and anything let through lands in the corpus permanently."""
    for card in [
        _card("POLITICAL THEORY – Jean-Jacques Rousseau", author="The School of Life"),
        _card("18. Democracy and Participation: Rousseau", author="YaleCourses"),
    ]:
        assert not is_piano(card, "Rousseau")


def test_other_instruments_are_dropped():
    assert not is_piano(
        _card("Berlage Saxophone Quartet - Grieg Wedding Day at Troldhaugen"),
        "Grieg Wedding Day at Troldhaugen", "Grieg",
    )
    assert not is_piano(
        _card("Joshua Bell - Tchaikovsky - Violin Concerto in D major"),
        "violin concerto Tchaikovsky", "Tchaikovsky",
    )


def test_pop_and_unrelated_content_is_dropped():
    assert not is_piano(_card("Taylor Swift - Cruel Summer (Music Video)", author="Pop World"),
                        "Taylor Swift Cruel Summer")
    assert not is_piano(_card("The Best Gaming Laptops for 2026", author="Tom's Guide"),
                        "best gaming laptop 2026")
    assert not is_piano(_card("How to Change a Tire", author="ChrisFix"),
                        "how to change a tyre")


def test_a_band_performing_live_is_not_piano():
    assert not is_piano(_card("Coldplay - The Scientist (Live in Madrid 2011)",
                              author="Coldplay"), "Coldplay piano")


# --- shape ------------------------------------------------------------------

def test_filter_reports_how_many_were_dropped():
    cards = [
        _card("Chopin - Nocturne op.9 No.2", author="Rousseau", desc="piano"),
        _card("POLITICAL THEORY – Rousseau", author="The School of Life"),
    ]
    kept, dropped = filter_piano(cards, "Rousseau")
    assert (len(kept), dropped) == (1, 1)


def test_a_channel_proven_to_be_piano_vouches_for_its_other_uploads():
    """An artist search returns one channel's back catalogue, and a piano channel does not
    restate the instrument every time. Judging cards alone kept only the uploads that
    happen to mention it: Birru's "clair de lune but it's 3am" says nothing about a piano."""
    cards = [
        _card("Interstellar", author="Birru", desc="piano cover"),
        _card("Nuvole Bianche", author="Birru", desc="played on piano"),
        _card("clair de lune but it's 3am", author="Birru"),      # no evidence at all
        _card("the part of hamnet where you cry", author="Birru"),
    ]
    kept, dropped = filter_piano(cards, "Birru")
    assert (len(kept), dropped) == (4, 0)


def test_one_mention_does_not_vouch_for_a_whole_channel():
    # otherwise a single piano-adjacent upload would drag in an unrelated catalogue
    cards = [
        _card("Rousseau on music and nature", author="The School of Life", desc="piano"),
        _card("POLITICAL THEORY – Jean-Jacques Rousseau", author="The School of Life"),
    ]
    kept, dropped = filter_piano(cards, "Rousseau")
    assert (len(kept), dropped) == (1, 1)


def test_a_vouched_channel_still_cannot_smuggle_in_other_instruments():
    cards = [
        _card("Chopin Nocturne", author="ClassicalHub", desc="piano"),
        _card("Debussy Arabesque", author="ClassicalHub", desc="piano"),
        _card("Tchaikovsky Violin Concerto", author="ClassicalHub"),
    ]
    kept, _ = filter_piano(cards, "ClassicalHub")
    assert [c.title for c in kept] == ["Chopin Nocturne", "Debussy Arabesque"]


def test_a_card_with_no_text_is_dropped_rather_than_crashing():
    assert not is_piano(Card(source="youtube", external_id="x", url="u"), "Chopin")
