import requests
import json


resp = requests.get("https://pastebin.com/raw/tK9f0EWK")
resp.raise_for_status()
commands = resp.text

output = {}
current_heading = None
current_command = None
for line in commands.split("\n"):
    line = line.replace("\r", "")
    if not line:
        continue
    if line.startswith("#"):  # Command group
        current_heading = line[6:len(line)-6]
        output.update({current_heading: {"commands": {}, "description": []}})
        continue
    elif current_heading is None:  # Beginning of the pastebin
        continue
    if line.startswith("!"):  # Command and its description
        cmd = line.split(" - ")[0]
        cmd = cmd.replace("<", "&lt;")
        cmd = cmd.replace(">", "&gt;")
        current_command = cmd
        output[current_heading]['commands'].update({cmd: [line.split(" - ")[1]]})
    elif not output[current_heading]['commands']:  # Command group description
        output[current_heading]['description'].append(line)
    else:  # Command description on another line
        output[current_heading]['commands'][current_command].append(line)

with open("commands.json", "w") as f:
    json.dump(output, f)
