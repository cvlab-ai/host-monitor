import shlex
import socket
import subprocess as sp
import sys
from threading import Thread
from time import sleep

from host_monitor.config import args
from host_monitor.ping import Ping


class Host(Thread):
    def __init__(self, id, address):
        super(Host, self).__init__()
        self.id = id
        self.address = address
        self.daemon = True
        self.state = None
        self.ping = Ping(address)
        self.start()

    def run(self):
        from host_monitor.gui import gui
        sleep(1)
        while True:
            try:
                ping_success = self.ping.read()
                if ping_success != self.state:
                    gui.ping_changed_signal.emit(self, ping_success)
                    self.state = ping_success
            except Exception:
                pass


class VPN(Thread):
    check_timeout = 1
    command_wait = 10
    internet_connection_checks = 3

    def __init__(self, id, exclude_ips, vpn_ip, connect, disconnect, internet_monitor, mode):
        super(VPN, self).__init__()
        self.id = id
        self.exclude_ips = exclude_ips
        self.vpn_ip = vpn_ip
        self.connect = connect
        self.disconnect = disconnect
        self.internet_monitor = internet_monitor
        self.daemon = True
        self.mode = mode
        self.start()

    @staticmethod
    def ip_addresses():
        return set([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")])

    def have_excluded_ip(self, ips):
        for exclude_ip in self.exclude_ips:
            for ip in ips:
                if ip.startswith(exclude_ip):
                    return True
        return False

    def is_internet_connected(self):
        if not self.internet_monitor:
            return True

        for i in range(self.internet_connection_checks):
            if i > 0:
                sleep(self.check_timeout)
            if not self.internet_monitor.state:
                return False

        return True

    def run(self):
        from host_monitor.gui import gui

        last_running = None
        while True:
            sleep(self.check_timeout)
            try:
                internet = self.is_internet_connected()

                ips = self.ip_addresses()
                vpn_running = any(ip.startswith(self.vpn_ip) for ip in ips)

                if self.mode == "auto":
                    if not internet:
                        continue
                    shall_vpn = not self.have_excluded_ip(ips)
                elif self.mode == "disconnect":
                    shall_vpn = False
                elif self.mode == "connect":
                    if not internet:
                        continue
                    shall_vpn = True
                else:
                    raise Exception("Unknown VPN mode")

                if vpn_running != shall_vpn:
                    if shall_vpn:
                        if args.verbose:
                            print(f"Starting VPN {self.id}")
                        self.run_command(self.connect)
                    else:
                        if args.verbose:
                            print(f"Stopping VPN {self.id}")
                        self.run_command(self.disconnect)

                if vpn_running != last_running:
                    gui.ping_changed_signal.emit(self, vpn_running)
                    last_running = vpn_running

            except Exception:
                pass

    def run_command(self, command):
        if sys.platform == 'win32':
            startupinfo = sp.STARTUPINFO()
            startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
        else:
            startupinfo = None

        command = shlex.split(command)

        process = sp.Popen(command,
                           stdout=sp.DEVNULL, stderr=sp.DEVNULL, shell=False, creationflags=sp.SW_HIDE,
                           startupinfo=startupinfo, encoding='utf8')

        ret_code = process.wait()

        sleep(self.command_wait)

        return ret_code == 0
