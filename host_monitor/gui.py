import sys
import types
from threading import Thread

from PyQt5.QtCore import *
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import *

from host_monitor.config import config, args
from host_monitor.host import Host, VPN

application = QApplication(sys.argv)


def flag_set(flags, flag):
    return int(flags) & int(flag) == flag


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
    colors = {
        None: QColor("#577e77"),
        False: QColor("#b32a22"),
        True: QColor("#32a35f"),
    }

    icons = {
        None: QStyle.SP_MessageBoxQuestion,
        False: QStyle.SP_DialogCancelButton,
        True: QStyle.SP_DialogApplyButton,
    }

    def __init__(self, name, address):
        QWidget.__init__(self)
        self.name = name
        self.address = address
        self.setText("<big><b>{}</b></big><br/><small>{}</small>".format(name, address))
        self.setAlignment(Qt.AlignCenter)

        layout = QHBoxLayout()
        self.setLayout(layout)
        layout.setAlignment(Qt.AlignRight)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setStretch(0, 0)

        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        layout.addWidget(self.icon)

        self.init_icons()
        self.current_up = None
        self.set_up(None)

    def showEvent(self, event):
        self.set_up(self.current_up)

    def init_icons(self):
        if not isinstance(self.icons[None], int):
            return
        for key, icon in self.icons.items():
            icon = self.style().standardIcon(icon)
            icon = icon.pixmap(QSize(16, 16))
            self.icons[key] = icon

    def set_up(self, value):
        self.current_up = value
        if self.isVisible():
            self.icon.setPixmap(self.icons[value])
            color = self.colors[value].name()
            self.setStyleSheet(f"background-color: {color}")


class HostMiniLabel(QWidget):
    def __init__(self):
        QWidget.__init__(self)

    def set_up(self, value):
        set_bg_color(self, HostLabel.colors[value])


class VPNLabel(HostLabel):
    modes = {
        Qt.CheckState.Checked: "auto",
        Qt.CheckState.Unchecked: "disconnect",
        Qt.CheckState.PartiallyChecked: "ignore",
    }

    def __init__(self, name, address, vpn):
        super().__init__(name, address)

        self.vpn = vpn

        self.checkbox = QCheckBox()
        self.checkbox.setTristate(True)
        self.checkbox.setCheckState({v: k for k, v in self.modes.items()}[self.vpn.mode])
        self.checkbox.setToolTip("""VPN connection mode.
 * Unchecked = Disconnect
 * Part-checked = Ignore
 * Checked = Auto-connect""")
        self.checkbox.stateChanged.connect(self.checked_changed)
        self.layout().insertWidget(0, self.checkbox)

    def checked_changed(self, state):
        self.vpn.mode = self.modes[state]


class MiniWindow(QWidget):
    clicked = pyqtSignal()
    enter = pyqtSignal()
    leave = pyqtSignal()

    def __init__(self):
        QWidget.__init__(self, None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)

        size = config['settings']['mini_size']
        self.setFixedSize(*size)
        self.set_position()

        layout = QGridLayout()
        layout.setSpacing(0)
        self.setLayout(layout)
        self.setContentsMargins(0, 0, 0, 0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.labels = {}

        self.show()
        self.raise_()

        self.timer_raise = QTimer()
        self.timer_raise.setInterval(max(int(config['settings']['mini_raise_time'] * 1000), 100))
        self.timer_raise.timeout.connect(self.raise_)
        self.timer_raise.start()

        self.timer_move = QTimer()
        self.timer_move.setInterval(max(int(config['settings']['mini_raise_time'] * 1000), 100) * 60)
        self.timer_move.timeout.connect(self.set_position)
        self.timer_move.start()

    def addLabel(self, host_id):
        label = self.labels[host_id] = HostMiniLabel()
        self.layout().addWidget(label, 0, len(self.labels) - 1)
        return label

    def set_up(self, name, value):
        self.labels[name].set_up(value)

    def set_position(self):
        position = list(config['settings']['mini_position'])
        if position[0] < 0: position[0] = application.desktop().screenGeometry().width() + position[0]
        if position[1] < 0: position[1] = application.desktop().screenGeometry().height() + position[1]
        self.move(*position)

    def mouseReleaseEvent(self, event):
        self.clicked.emit()

    def enterEvent(self, event):
        self.enter.emit()

    def leaveEvent(self, event):
        self.leave.emit()


class MainWindow(QWidget):
    run_on_gui_signal = pyqtSignal(types.FunctionType, tuple, dict)
    ping_changed_signal = pyqtSignal(Thread, object)

    NORMAL = 'normal'
    HIDDEN = 'hidden'
    PREVIEW = 'preview'

    def __init__(self):
        super(MainWindow, self).__init__()
        self.is_previewing = False

        self.setWindowTitle('Host monitor')
        self.setMinimumWidth(config['settings']['width'])

        self.setStyleSheet("""
        MainWindow {
             background: #2b3f3b;
        }
        HostLabel {
            font-size: 12pt; 
            font-family: Consolas, Monospace, TypeWriter, Courier; 
            font-weight: bold; 
            color: black;
            margin: 0 0;
            padding: 0 5;
            background: #2b3f3b;
        }
        QCheckBox {
            margin: 0 0;
        }
        """)

        self.run_on_gui_signal.connect(self.run_on_gui_slot)
        self.ping_changed_signal.connect(self.ping_changed_slot)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        self.setLayout(layout)

        self.mini_window = MiniWindow()
        self.mini_window.clicked.connect(self.restore)
        self.mini_window.enter.connect(self.preview)
        self.mini_window.leave.connect(self.close_preview)

        self.labels = {}
        self.hosts = {}

        for group_id, host_group in enumerate(config['groups']):

            if group_id > 0:
                spacer = QWidget()
                spacer.setFixedHeight(10)
                layout.addWidget(spacer)

            for definition in host_group['hosts']:
                type = definition['type']

                if type == 'internet-monitor':
                    name = 'INTERNET'
                    address = definition['address']
                    host_id = (group_id, name)
                    label = HostLabel(name, address)
                    host = Host(host_id, address)

                elif type == 'vpn':
                    name = definition['name']
                    vpn_ip = definition['assigned_ip']
                    exclude_ips = definition['exclude_ips']
                    ping_ip = definition['ping_ip']
                    vpn_connect = definition['connect']
                    vpn_disconnect = definition['disconnect']
                    mode = definition['mode']
                    host_id = (group_id, name)
                    host = VPN(host_id, exclude_ips, vpn_ip, ping_ip, vpn_connect, vpn_disconnect, mode)
                    label = VPNLabel(name, "VPN", host)

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
                self.hosts[host_id] = host

        self.showNormal()
        self.center()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.close_preview()

        for host in self.hosts.values():
            host.start()

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

    @pyqtSlot(Host, object)
    def ping_changed_slot(self, host, up):
        if args.verbose and isinstance(host, VPN):
            print(f"{host.__class__.__name__} '{host.id[1]}' up state: {up}")
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

    def get_host(self, group=None, name=None, ip=None):
        if group and name and (group, name) in self.hosts:
            return self.hosts[group, name]

        if name:
            for (host_group, host_name), host in self.hosts.items():
                if host_name == name:
                    return host

        if ip:
            for host in self.hosts.values():
                if getattr(host, "address", None) == ip:
                    return host

        return None


gui = MainWindow()


def run_app():
    return application.exec_()
