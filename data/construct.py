import json


def construct(length):  # length = Length per string
    strings = {}
    with open("all_words.json", "r") as f:
        words = [word.lower() for word in json.load(f)]
        for word in words:
            for combo in [word[index:index+length] for index in range(len(word)-(length-1))]:
                strings[combo] = 1 if combo not in strings else 1 + strings[combo]

        strings = {item[0]: item[1] for item in sorted(strings.items(), key=lambda item: item[1], reverse=True)}
        with open(f"{length}strings.json", "w") as out:
            json.dump(strings, out)


for length in (2, 3): construct(length)
