import json


with open("genshin_list.txt", "r") as raw:

    formatted_data = {"3": [], "4": [], "5": []}
    current_star = None
    for line in raw.readlines():
        if len(line.strip()) == 0:
            continue
        if line[0].isdigit():
            current_star = line[0]
            continue
        elif current_star is None:
            continue

        formatted_data[current_star].append(line[:-1])

    with open("genshin.json", "w") as out:
        json.dump(formatted_data, out)
