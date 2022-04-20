from scriptmanager import Script, ScriptRunner
from time import sleep, perf_counter
from get_top_players import Client
import subprocess
from threading import Timer


Client().run()  # update list of top players

run_with = '/bin/python'
logs = 'logs'
scripts = [
    Script(run_with, "offlinechatbot-main/main.py", "Offline Chat Bot"), 
]

runner = ScriptRunner(logs)
for script in scripts:
    runner.manage_script(script)
runner.start()


def stop(runner):
    runner.stop()
    subprocess.run(['sudo', 'reboot'])


timer = Timer(604800, stop)
try:
    timer.start()
except KeyboardInterrupt:
    runner.stop()
    timer.cancel()

