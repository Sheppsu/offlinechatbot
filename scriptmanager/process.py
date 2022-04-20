import os
import subprocess
from .exception import ProcessAlreadyExistsError, ProcessDoesNotExistError
from time import perf_counter
import select


__all__ = (
    'Script',
)


class Script:
    valid_types = ["py"]

    def __init__(self, run_with, path, name=None, restart_on_error=True):
        if name is None:
            name = '.'.join(os.path.split(path)[-1].split('.')[:-1])

        # Checks
        if not os.path.exists(path):
            raise FileNotFoundError("That file does not exist.")
        if os.path.split(path)[-1].split('.')[-1].lower() not in self.valid_types:
            raise ValueError("This file does not have a valid file type. Valid file types consist of the following: "+", ".join(self.valid_types))

        # Attributes
        self.run_with = run_with
        self.path = path
        self.name = name
        self.restart_on_error = restart_on_error
        self.active = False
        self.process = None
        self.last_restart = perf_counter()-60

    def start(self):
        self._create_process()
        self.last_restart = perf_counter()
        self.active = True

    def stop(self):
        self._stop_process()
        self.process = None
        self.active = False

    def _create_process(self):
        if self.process is not None:
            raise ProcessAlreadyExistsError("Cannot create more than one process in a Script object.")
        self.process = Process(self.run_with, self.path)
        self.process.create()

    def _stop_process(self):
        if self.process is None:
            raise ProcessDoesNotExistError("There is no process to stop.")
        self.process.kill()

    def check_process(self):
        if self.process is None:
            raise ProcessDoesNotExistError("There is no process to check.")
        lines = list(self.process.communicate())
        if not self.process.is_running:
            print(self.name+" is not longer running.")
            self.stop()
            if self.restart_on_error and perf_counter()-self.last_restart > 60:
                print("Now restarting "+self.name)
                self.start()
        return lines


class Process:
    def __init__(self, run_with, path):
        self.run_with = run_with
        self.path = path

        self.process = None

    def create(self):
        if self.process is not None:
            raise ProcessAlreadyExistsError("The process has already been created.")
        try:
            self.process = subprocess.Popen([self.run_with, self.path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='utf-8')
        except OSError as e:
            print(e)

    def kill(self):
        if self.process is None:
            raise ProcessDoesNotExistError("There is no process to kill.")
        self.process.kill()

    def communicate(self):
        if self.process is None:
            raise ProcessDoesNotExistError("There is no process to communicate with.")
        if not self.is_running:
            yield self.process.stderr.read()
        while True:
            r, _, _ = select.select([self.process.stdout], [], [], 0)
            if self.process.stdout in r:
                out = self.process.stdout.readline()
                yield out + "\n"
            else:
                break

    @property
    def is_running(self):
        return self.process.poll() is None
