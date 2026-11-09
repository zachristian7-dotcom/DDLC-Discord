import unittest

from engine.participation import select_participants


PROFILES = {
    "sayori": {"interests": ["friendship", "games", "cute things"]},
    "natsuki": {"interests": ["manga", "baking", "cupcakes"]},
    "yuri": {"interests": ["literature", "horror fiction", "poetry"]},
    "monika": {"interests": ["poetry", "music", "creative writing"]},
}


class ParticipationTests(unittest.TestCase):
    def setUp(self):
        self.available = ["sayori", "natsuki", "yuri", "monika"]

    def test_selection_is_deterministic_for_one_message(self):
        first = select_participants(123456, self.available, [], "Let's talk about poetry", PROFILES)
        second = select_participants(123456, self.available, [], "Let's talk about poetry", PROFILES)
        self.assertEqual(first, second)

    def test_directly_addressed_character_is_always_selected(self):
        selected = select_participants(
            123456, self.available, ["natsuki"], "Hey Natsuki!", PROFILES
        )
        self.assertIn("natsuki", selected)

    def test_multiple_addressees_are_all_selected(self):
        selected = select_participants(
            123456, self.available, ["yuri", "monika"], "What do you think?", PROFILES
        )
        self.assertIn("yuri", selected)
        self.assertIn("monika", selected)

    def test_selection_has_no_duplicates(self):
        selected = select_participants(
            987654, self.available, [], "I have been reading a new horror novel", PROFILES
        )
        self.assertEqual(len(selected), len(set(selected)))
        self.assertGreaterEqual(len(selected), 1)
        self.assertLessEqual(len(selected), len(self.available))


if __name__ == "__main__":
    unittest.main()
