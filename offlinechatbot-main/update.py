import json


with open('gamba.json', 'r') as f:
    data = json.load(f)

for user in data:
    if 'settings' not in data[user]:
        data[user].update({'settings': {'receive': True}})

with open('gamba.json', 'w') as f:
    json.dump(data, f)
