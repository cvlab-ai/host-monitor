#!/usr/bin/python3
# coding=utf-8

import atexit
import os.path
import shutil
import socket
import subprocess as sp
import sys
import types
from argparse import ArgumentParser
from collections import OrderedDict
from datetime import timedelta
from threading import Thread, Lock
from time import sleep

import yaml
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

application = QApplication(sys.argv)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('-t', '--time', help='Time between checks in seconds', default=1, type=float)
    return parser.parse_args()


def flag_set(flags, flag):
    return int(flags) & int(flag) == flag


args = parse_args()
atexit_lock = Lock()


def read_config():
    config_path = os.path.expanduser("~/.pinger.cfg")
    if not os.path.exists(config_path):
        default_path = os.path.normpath(f"{__file__}/../config_default.yaml")
        shutil.copy(default_path, config_path)
    return yaml.safe_load(open(config_path))


config = read_config()


class PingLinux(object):
    def __init__(self, host):
        with atexit_lock:
            atexit.register(self.terminate)
        self.process = sp.Popen("ping -n -W 1 -s 1 -O {}".format(host).split(), stdout=sp.PIPE, stderr=sp.PIPE)

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


class Host(Thread):
    time_delta = timedelta(seconds=args.time)

    def __init__(self, id, address):
        super(Host, self).__init__()
        self.id = id
        self.address = address
        self.daemon = True
        self.state = None
        self.ping = Ping(address)
        self.start()

    def run(self):
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

    def __init__(self, id, exclude_ips, vpn_ip, connect, disconnect, internet_monitor):
        super(VPN, self).__init__()
        self.id = id
        self.exclude_ips = exclude_ips
        self.vpn_ip = vpn_ip
        self.connect = connect
        self.disconnect = disconnect
        self.internet_monitor = internet_monitor
        self.daemon = True
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

    def run(self):
        last_running = None
        while True:
            sleep(self.check_timeout)
            try:
                if self.internet_monitor:
                    if not self.internet_monitor.state:
                        continue

                ips = self.ip_addresses()
                vpn_running = any(ip.startswith(self.vpn_ip) for ip in ips)
                shall_vpn = not self.have_excluded_ip(ips)

                if vpn_running != shall_vpn:
                    if shall_vpn:
                        # print(f"Starting VPN {self.id}")
                        self.run_command(self.connect)
                    else:
                        # print(f"Stopping VPN {self.id}")
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

        command = command.split()
        command = [c.replace("%SPACE%", " ") for c in command]

        process = sp.Popen(command,
                           stdout=sp.DEVNULL, stderr=sp.DEVNULL, shell=False, creationflags=sp.SW_HIDE,
                           startupinfo=startupinfo, encoding='utf8')

        ret_code = process.wait()

        sleep(self.command_wait)

        return ret_code == 0


def on_gui(func):
    def wrap(*args, **kwargs):
        gui.run_on_gui_signal.emit(func, args, kwargs)

    return wrap


def run_on_gui(func, *args, **kwargs):
    gui.run_on_gui_signal.emit(func, args, kwargs)


def set_bg_color(widget, color):
    widget.setAutoFillBackground(True)
    p = widget.palette()
    p.setColor(widget.backgroundRole(), color)
    widget.setPalette(p)


class HostLabel(QLabel):
    colors = {None: Qt.gray, True: Qt.darkGreen, False: Qt.red}

    def __init__(self, name, address):
        QWidget.__init__(self)
        self.name = name
        self.address = address
        self.setText("<big><b>{}</b></big><br/><small>{}</small>".format(name, address))

        self.set_up(None)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "font-size:12pt; font-family:Monospace, TypeWriter, Courier; font-weight:bold; color:black; margin:0 30; ")

    def set_up(self, value):
        # txt =  self.name + "\t" + ("UP" if value else "DOWN")
        # self.setText(txt)
        set_bg_color(self, self.colors[value])


class HostMiniLabel(QWidget):
    def __init__(self):
        QWidget.__init__(self)

    def set_up(self, value):
        set_bg_color(self, HostLabel.colors[value])


class MiniWindow(QWidget):
    clicked = pyqtSignal()
    enter = pyqtSignal()
    leave = pyqtSignal()

    def __init__(self):
        QWidget.__init__(self, None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)

        position = list(config['settings']['mini_position'])
        if position[0] < 0: position[0] = application.desktop().screenGeometry().width() + position[0]
        if position[1] < 0: position[1] = application.desktop().screenGeometry().height() + position[1]

        size = config['settings']['mini_size']
        self.setFixedSize(*size)
        self.move(*position)

        layout = QGridLayout()
        layout.setSpacing(0)
        self.setLayout(layout)
        self.setContentsMargins(0, 0, 0, 0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.labels = {}

        self.show()

        self.timer = QTimer()
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.raise_)
        self.timer.start()

    def addLabel(self, host_id):
        label = self.labels[host_id] = HostMiniLabel()
        self.layout().addWidget(label, 0, len(self.labels) - 1)
        return label

    def set_up(self, name, value):
        self.labels[name].set_up(value)

    def mouseReleaseEvent(self, event):
        self.clicked.emit()

    def enterEvent(self, event):
        self.enter.emit()

    def leaveEvent(self, event):
        self.leave.emit()


class MainWindow(QWidget):
    run_on_gui_signal = pyqtSignal(types.FunctionType, tuple, dict)
    ping_changed_signal = pyqtSignal(Thread, bool)

    NORMAL = 'normal'
    HIDDEN = 'hidden'
    PREVIEW = 'preview'

    def __init__(self):
        super(MainWindow, self).__init__()

        self.is_previewing = False

        self.setObjectName("MainWindow")
        self.setWindowTitle('Pinger')
        # self.setGeometry(500, 400, 800, 600)

        self.run_on_gui_signal.connect(self.run_on_gui_slot)
        self.ping_changed_signal.connect(self.ping_changed_slot)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        self.setLayout(layout)

        self.mini_window = MiniWindow()
        self.mini_window.clicked.connect(self.restore)
        self.mini_window.enter.connect(self.preview)
        self.mini_window.leave.connect(self.close_preview)

        self.labels = OrderedDict()
        self.hosts = []

        internet_monitor = None

        for group_id, host_group in enumerate(config['groups']):

            for definition in host_group['hosts']:
                type = definition['type']

                if type == 'internet-monitor':
                    assert internet_monitor is None
                    name = 'INTERNET'
                    address = definition['address']
                    host_id = (group_id, name)
                    label = HostLabel(name, address)
                    host = Host(host_id, address)
                    internet_monitor = host

                elif type == 'vpn':
                    name = definition['name']
                    vpn_ip = definition['assigned_ip']
                    exclude_ips = definition['exclude_ips']
                    vpn_connect = definition['connect']
                    vpn_disconnect = definition['disconnect']
                    host_id = (group_id, name)
                    label = HostLabel(name, "VPN")
                    host = VPN(host_id, exclude_ips, vpn_ip, vpn_connect, vpn_disconnect, internet_monitor)

                elif type == 'host':
                    name = definition['name']
                    address = definition['address']
                    host_id = (group_id, name)
                    label = HostLabel(name, address)
                    host = Host(host_id, address)

                else:
                    raise Exception(f"Unknown host type: {type}")

                self.labels[host_id] = label
                layout.addWidget(label)

                self.mini_window.addLabel(host_id)
                self.hosts.append(host)

            spacer = QWidget()
            spacer.setFixedHeight(10)
            layout.addWidget(spacer)

        self.showNormal()
        self.center()

        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        if not __debug__:
            self.hide()

    @property
    def state(self):
        if not self.isVisible() or self.isMinimized():
            return self.HIDDEN
        elif flag_set(self.windowFlags(), Qt.Tool):
            return self.PREVIEW
        else:
            return self.NORMAL

    @pyqtSlot(types.FunctionType, tuple, dict)
    def run_on_gui_slot(self, func, args, kwargs):
        func(*args, **kwargs)

    @pyqtSlot(Host, bool)
    def ping_changed_slot(self, host, up):
        if __debug__: print(host, up)
        self.labels[host.id].set_up(up)
        self.mini_window.set_up(host.id, up)

    def center(self):
        frameGm = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        centerPoint = QApplication.desktop().screenGeometry(screen).center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())

    def closeEvent(self, event):
        application.quit()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if flag_set(self.windowState(), Qt.WindowMinimized):
                self.setWindowFlag(Qt.Tool, True)
                event.accept()

    def restore(self):
        self.setWindowFlag(Qt.Tool, False)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowState(Qt.WindowNoState)
        self.show()

    def preview(self):
        if self.state != self.HIDDEN: return

        self.setWindowFlag(Qt.Window, False)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowState(Qt.WindowNoState)

        self.show()
        self.raise_()

    def close_preview(self):
        if self.state != self.PREVIEW: return
        self.setWindowState(Qt.WindowMinimized)
        self.hide()


gui = MainWindow()


def run_app():
    return application.exec_()


if __name__ == '__main__':
    ret_code = run_app()
    sys.exit(ret_code)
