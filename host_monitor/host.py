import shlex
import socket
import subprocess as sp
import sys
from datetime import datetime
from threading import Thread
from time import sleep

from host_monitor.config import args
from host_monitor.ping import Ping


class Host(Thread):
    def __init__(self, id, address, start=False):
        super(Host, self).__init__()
        self.id = id
        self.address = address
        self.daemon = True
        self.state = None
        self.ping = Ping(address)
        if start:
            self.start()

    def run(self):
        from host_monitor.gui import gui
        sleep(1)
        while True:
            try:
                ping_success = self.ping.read()
                if ping_success != self.state:
                    if self.id:
                        gui.ping_changed_signal.emit(self, ping_success)
                    self.state = ping_success
            except Exception:
                pass


class VPN(Thread):
    check_timeout = 1
    command_wait = 10
    internet_connection_checks = 3
    vpn_pings = 5

    def __init__(self, id, exclude_ips, vpn_ip, ping_ip, connect, disconnect, mode):
        super(VPN, self).__init__()
        self.id = id
        self.exclude_ips = exclude_ips
        self.vpn_ip = vpn_ip
        self.pinger = ping_ip
        self.internet_monitor = None
        self.connect = connect
        self.disconnect = disconnect
        self.daemon = True
        self.mode = mode
        self.state = None  # states: disconnected, connecting, connected, disconnecting
        self.last_command_time = datetime(2000, 1, 1)

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

    def is_vpn_running(self, ips):
        # vpn ip assigned
        if not any(ip.startswith(self.vpn_ip) for ip in ips):
            return False

        if not self.pinger:
            return True

        # ping inside vpn
        for i in range(self.vpn_pings):
            if i > 0:
                sleep(self.check_timeout)
            if self.pinger.state:
                return True

        return False

    def run(self):
        from host_monitor.gui import gui

        self.internet_monitor = gui.get_host(name="INTERNET")

        if self.pinger:
            self.pinger = gui.get_host(ip=self.pinger) or Host(None, self.pinger, True)

        while True:
            sleep(self.check_timeout)
            try:
                internet = self.is_internet_connected()

                ips = self.ip_addresses()
                vpn_running = self.is_vpn_running(ips)
                command_waiting = (datetime.now() - self.last_command_time).total_seconds() < self.command_wait

                if self.mode == "auto":
                    shall_vpn = not self.have_excluded_ip(ips)
                elif self.mode == "disconnect":
                    shall_vpn = False
                elif self.mode == "connect":
                    shall_vpn = True
                else:
                    raise Exception("Unknown VPN mode")

                if shall_vpn and vpn_running and self.state != 'connected':
                    self.state = 'connected'
                    gui.ping_changed_signal.emit(self, True)
                elif not shall_vpn and not vpn_running and self.state != 'disconnected':
                    self.state = 'disconnected'
                    gui.ping_changed_signal.emit(self, False)
                elif shall_vpn and not vpn_running and (self.state != 'connecting' or not command_waiting) and internet:
                    gui.ping_changed_signal.emit(self, None)
                    if args.verbose:
                        print(f"Starting VPN {self.id}")
                    self.state = 'connecting'
                    self.run_command(self.connect)
                elif not shall_vpn and vpn_running and (self.state != 'disconnecting' or not command_waiting):
                    gui.ping_changed_signal.emit(self, None)
                    if args.verbose:
                        print(f"Stopping VPN {self.id}")
                    self.state = 'disconnecting'
                    self.run_command(self.disconnect)

            except Exception:
                pass

    def run_command(self, command):
        if sys.platform == 'win32':
            startupinfo = sp.STARTUPINFO()
            startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
        else:
            startupinfo = None

        command = shlex.split(command)

        self.last_command_time = datetime.now()

        process = sp.Popen(command,
                           stdout=sp.DEVNULL, stderr=sp.DEVNULL, shell=False, creationflags=sp.SW_HIDE,
                           startupinfo=startupinfo, encoding='utf8')

        ret_code = process.wait()

        return ret_code == 0
