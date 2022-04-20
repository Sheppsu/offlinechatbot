import threading
from time import sleep
import os
from datetime import datetime, timedelta


class ScriptRunner(threading.Thread):
    def __init__(self, log_path, tz=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.log_path = log_path
        self.log_file = None
        self.tz = tz

        self.active_scripts = []
        self.running = True

    def run(self):
        while self.running:
            for script in self.active_scripts:
                for out in script.check_process():
                    if out == "\n":
                        continue
                    self._log(out, script.name)
                sleep(1)  # read below
            sleep(10)  # Make sure the program is not beating the hell out of the CPU + let other threads run
        print("Cleaning up...")
        self._cleanup()
        print("Stopped!")

    def stop(self):
        self.running = False
        self._stop_all_active_scripts()

    def manage_script(self, script):
        if not script.active:
            script.start()
        self.active_scripts.append(script)

    def get_script_by_name(self, name):
        for script in self.active_scripts:
            if script.name == name:
                return script

    def get_logs_for_script(self, name, index=-1):
        return os.listdir(os.path.join(self.log_path, name))[index]

    def _cleanup(self):
        self._stop_all_active_scripts()

    def _stop_script(self, script):
        if not script.active:
            return
        script.restart_on_error = False
        for out in script.check_process():
            self._log(out, script.name)
        if script.active:
            script.stop()

    def _stop_all_active_scripts(self):
        for script in self.active_scripts:
            self._stop_script(script)
        self.active_scripts = []

    def _log(self, log, name):
        print(log)
        path = os.path.join(self.log_path, name)
        if not os.path.isdir(path):
            os.mkdir(path)
        if self.log_file is None:
            self.log_file = os.path.join(path, f"logfile_"+datetime.now(tz=self.tz).strftime('%d_%m_%YT%H_%M_%S')+".log")
            with open(self.log_file, 'w') as f:
                f.write(log)
            return
        with open(self.log_file, 'a') as f:
            f.write(log)

