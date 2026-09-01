"""The learned ranker: a supervised model trained on logged interactions.

Sits *beside* the hand-tuned content ranker in ``scorekit.recommend`` rather than replacing
it, so the two can be measured head to head on the same held-out interactions.
"""
