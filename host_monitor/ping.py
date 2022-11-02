import atexit
import subprocess as sp
import sys
from threading import Lock

atexit_lock = Lock()


class PingLinux(object):
    def __init__(self, host):
        with atexit_lock:
            atexit.register(self.terminate)
        self.process = sp.Popen("ping -n -W 1 -s 1 -O {}".format(host).split(), stdout=sp.PIPE, stderr=sp.PIPE,
                                encoding='utf8')

    def read(self):
        while True:
            line = self.process.stdout.readline().strip()
            if "ttl" in line:
                return True
            else:
                return False

    def terminate(self):
        self.process.terminate()

    def __del__(self):
        self.terminate()


class PingWindows(object):
    def __init__(self, host):
        startupinfo = sp.STARTUPINFO()
        startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
        self.process = sp.Popen("ping -w 100 -l 1 -t {}".format(host).split(),
                                stdout=sp.PIPE, stderr=sp.PIPE, shell=False, creationflags=sp.SW_HIDE,
                                startupinfo=startupinfo, encoding='utf8')
        atexit.register(self.terminate)

    def read(self):
        while True:
            line = self.process.stdout.readline().strip()
            if __debug__: print(line)
            if "TTL" in line:
                return True
            else:
                return False

    def terminate(self):
        self.process.terminate()


if sys.platform == "win32":
    Ping = PingWindows
else:
    Ping = PingLinux
