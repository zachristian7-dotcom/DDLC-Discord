"""Deterministic, relevance-aware participant selection for group conversations."""
import random
import re


def _tokens(text):
    return set(re.findall(r"[a-z']+", (text or "").lower()))


def _interest_score(character, message):
    """Small lexical relevance signal; never overrides a direct addressee."""
    interests = character.get("interests", [])
    profile_words = set()
    for item in interests:
        profile_words.update(_tokens(str(item)))
    ignored = {"about", "their", "there", "which", "would", "could", "should", "thing", "things", "really", "because"}
    return len((_tokens(message) & profile_words) - ignored)


def select_participants(message_id, available, addressed, message, profiles, max_group=3):
    """Return a stable selection shared by all bot accounts for one Discord message.

    Direct addressees are mandatory. For group messages, relevance influences
    selection, while a message-ID seed keeps every bot's decision identical.
    """
    available = list(dict.fromkeys(name.lower() for name in available))
    addressed = [name.lower() for name in addressed if name.lower() in available]
    if not available:
        return []

    rng = random.Random(int(message_id))
    if addressed:
        selected = list(addressed)
        candidates = [name for name in available if name not in selected]
        ranked = sorted(
            candidates,
            key=lambda name: (_interest_score(profiles.get(name, {}), message), rng.random()),
            reverse=True,
        )
        # At most two additional voices; relevance is a preference, not a mandate.
        extra_count = min(len(ranked), rng.choices([0, 1, 2], weights=[45, 40, 15], k=1)[0])
        if extra_count:
            selected.extend(ranked[:extra_count])
        return selected

    scores = {name: _interest_score(profiles.get(name, {}), message) for name in available}
    # Pick one lead, giving interested characters a modest advantage without
    # making topic matching deterministic or turning profiles into hard rules.
    weights = [1.0 + min(scores[name], 4) * 0.45 for name in available]
    lead = rng.choices(available, weights=weights, k=1)[0]
    remaining = [name for name in available if name != lead]
    desired = min(len(available), rng.choices([1, 2, 3], weights=[48, 40, 12], k=1)[0], max_group)
    if desired == 1:
        return [lead]

    # Relevant characters are considered first; random tie-breaking remains stable.
    remaining.sort(key=lambda name: (scores[name], rng.random()), reverse=True)
    return [lead] + remaining[: desired - 1]
