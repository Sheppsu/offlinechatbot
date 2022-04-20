output = {"3*": [], "4*": [], "5*": []}

with open("genshin_list.txt", "r") as f:
    star = ""
    for line in f.readlines():
        if line[0] in ("3", "4", "5"):
            star = f"{line[0]}*"
            continue
        if line == "\n":
            continue

        output[star].append(line.split("\n")[0])

print(output)
