from scorekit.normalize import normalize_slug


def test_composer_and_title():
    assert normalize_slug("Clair de Lune", "Debussy") == "debussy-clair-de-lune"


def test_title_only():
    assert normalize_slug("Für Elise") == "fur-elise"


def test_strips_punctuation_and_accents():
    assert normalize_slug("Nocturne, Op. 9 No. 2", "Chopin") == "chopin-nocturne-op-9-no-2"


def test_collapses_separators():
    assert normalize_slug("  Gymnopédie   No.1  ", "Satie") == "satie-gymnopedie-no-1"
