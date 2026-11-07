import json
from pathlib import Path

CHARACTER_DIR = Path(__file__).parent.parent / "characters"


def load_character(name):
    filename = CHARACTER_DIR / f"{name.lower()}.json"

    with open(filename, "r", encoding="utf-8") as file:
        character = json.load(file)

    return character


def load_all_characters():
    names = ["sayori", "natsuki", "yuri", "monika"]

    characters = {}

    for name in names:
        characters[name] = load_character(name)

    return characters


if __name__ == "__main__":
    characters = load_all_characters()

    for name, character in characters.items():
        print("=" * 35)
        print("Character:", character["name"])
        print("Personality:")

        for trait in character["personality"]:
            print("-", trait)

    print("=" * 35)
    print("All four character profiles loaded!")
