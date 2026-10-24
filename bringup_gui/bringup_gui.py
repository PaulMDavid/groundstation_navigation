#!/usr/bin/env python3
"""Ground station panel for the robot's staged Nav2 bringup.

Talks to app_bringup_manager on the robot over plain ROS 2 topics/services:
shows every stage, its checks and containers, and has one big button that
brings the stack up or restarts it from the first stage that isn't working.
"""
import json
import sys
import threading
import time

import rclpy
from PyQt5 import QtCore, QtGui, QtWidgets
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

STALE_AFTER = 3.0  # seconds without a status message before the robot counts as gone

COLORS = {
    'pending': '#6b7280', 'stopped': '#6b7280', 'blocked': '#475569',
    'starting': '#f59e0b', 'ready': '#22c55e', 'warn': '#fb923c', 'failed': '#ef4444',
}
OVERALL_TEXT = {
    'idle': 'Idle', 'bringing_up': 'Bringing up…', 'ready': 'Ready',
    'failed': 'Something failed', 'stopping': 'Stopping…',
}


class RosBridge(QtCore.QObject):
    """rclpy in a background thread; everything reaches Qt through signals."""
    status = QtCore.pyqtSignal(dict)
    logs = QtCore.pyqtSignal(dict)
    reply = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        rclpy.init()
        self.node = Node('bringup_gui')
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.node.create_subscription(String, '/bringup/status',
                                      lambda m: self.status.emit(json.loads(m.data)), latched)
        self.node.create_subscription(String, '/bringup/logs',
                                      lambda m: self.logs.emit(json.loads(m.data)), 10)
        self.log_req = self.node.create_publisher(String, '/bringup/log_request', 10)
        self.clients = {name: self.node.create_client(Trigger, f'/bringup/{name}')
                        for name in ('go', 'stop')}
        threading.Thread(target=rclpy.spin, args=(self.node,), daemon=True).start()

    def call(self, name):
        client = self.clients[name]
        if not client.service_is_ready():
            self.reply.emit(f'/bringup/{name}: manager not reachable')
            return
        future = client.call_async(Trigger.Request())
        future.add_done_callback(
            lambda f: self.reply.emit(f'/bringup/{name}: {f.result().message}'))

    def request_logs(self, container):
        self.log_req.publish(String(data=container))


def dot(color, size=14):
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setBrush(QtGui.QColor(color))
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QtGui.QIcon(pix)


class MainWindow(QtWidgets.QWidget):
    def __init__(self, ros):
        super().__init__()
        self.ros = ros
        self.snapshot = None
        self.last_status = 0.0
        self.selected = None
        self.setWindowTitle('Nav2 bringup')
        self.resize(1200, 780)

        # header: connection + overall state + buttons
        self.conn = QtWidgets.QLabel()
        self.overall = QtWidgets.QLabel('—')
        self.overall.setStyleSheet('font-size: 22px; font-weight: 600;')
        self.go_btn = QtWidgets.QPushButton('BRING UP / RECOVER')
        self.go_btn.setMinimumSize(300, 90)
        self.go_btn.setStyleSheet(
            'QPushButton { background: #dc2626; color: white; font-size: 22px; font-weight: 700;'
            ' border-radius: 45px; border: 4px solid #7f1d1d; }'
            'QPushButton:hover { background: #ef4444; }'
            'QPushButton:pressed { background: #991b1b; }'
            'QPushButton:disabled { background: #4b5563; border-color: #374151; }')
        self.go_btn.setToolTip('Starts everything, or restarts from the first stage that is '
                               'not ready. Not an emergency stop.')
        self.go_btn.clicked.connect(lambda: self.ros.call('go'))
        self.stop_btn = QtWidgets.QPushButton('Stop all')
        self.stop_btn.clicked.connect(self.confirm_stop)

        status_col = QtWidgets.QVBoxLayout()
        status_col.addWidget(self.conn)
        status_col.addWidget(self.overall)
        header = QtWidgets.QHBoxLayout()
        header.addLayout(status_col, 1)
        header.addWidget(self.stop_btn, 0, QtCore.Qt.AlignBottom)
        header.addWidget(self.go_btn)

        # left: stages
        self.stage_list = QtWidgets.QListWidget()
        self.stage_list.setIconSize(QtCore.QSize(18, 18))
        self.stage_list.setWordWrap(True)
        self.stage_list.setStyleSheet('QListWidget::item { padding: 8px; }')
        self.stage_list.currentRowChanged.connect(self.on_select)
        self.stage_list.itemClicked.connect(
            lambda item: setattr(self, 'selected', self.stage_list.row(item)))

        # right: details of the selected stage
        self.detail_title = QtWidgets.QLabel()
        self.detail_title.setStyleSheet('font-size: 16px; font-weight: 600;')
        self.detail_msg = QtWidgets.QLabel()
        self.detail_msg.setWordWrap(True)
        self.detail_msg.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.checks = self.table(['Check', 'Value', 'Hint'])
        self.containers = self.table(['Container', 'Status', 'Exit code', 'Restarts'])
        self.log_pick = QtWidgets.QComboBox()
        fetch = QtWidgets.QPushButton('Fetch last 200 lines')
        fetch.clicked.connect(self.fetch_logs)
        log_bar = QtWidgets.QHBoxLayout()
        log_bar.addWidget(QtWidgets.QLabel('Logs:'))
        log_bar.addWidget(self.log_pick, 1)
        log_bar.addWidget(fetch)
        self.log_view = self.mono()

        detail = QtWidgets.QVBoxLayout()
        detail.addWidget(self.detail_title)
        detail.addWidget(self.detail_msg)
        detail.addWidget(self.checks, 2)
        detail.addWidget(self.containers, 1)
        detail.addLayout(log_bar)
        detail.addWidget(self.log_view, 3)
        detail_w = QtWidgets.QWidget()
        detail_w.setLayout(detail)

        split = QtWidgets.QSplitter()
        split.addWidget(self.stage_list)
        split.addWidget(detail_w)
        split.setSizes([380, 820])

        self.events = self.mono()
        self.events.setMaximumHeight(150)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(header)
        root.addWidget(split, 1)
        root.addWidget(QtWidgets.QLabel('Events'))
        root.addWidget(self.events)

        ros.status.connect(self.on_status)
        ros.logs.connect(self.on_logs)
        ros.reply.connect(lambda text: self.local_event(text))
        timer = QtCore.QTimer(self)
        timer.timeout.connect(self.refresh_connection)
        timer.start(500)
        self.refresh_connection()

    @staticmethod
    def table(headers):
        t = QtWidgets.QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setStretchLastSection(True)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        return t

    @staticmethod
    def mono():
        w = QtWidgets.QPlainTextEdit()
        w.setReadOnly(True)
        w.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        return w

    def confirm_stop(self):
        if QtWidgets.QMessageBox.question(
                self, 'Stop all', 'Stop every bringup container on the robot?') \
                == QtWidgets.QMessageBox.Yes:
            self.ros.call('stop')

    def local_event(self, text):
        self.events.appendPlainText(f'{time.strftime("%H:%M:%S")}  [gui] {text}')

    def refresh_connection(self):
        age = time.time() - self.last_status
        alive = age < STALE_AFTER
        if alive:
            self.conn.setText('● robot connected')
            self.conn.setStyleSheet('color: #22c55e;')
        else:
            seen = f'last status {age:.0f} s ago' if self.last_status else 'never heard from it'
            self.conn.setText(f'● no contact with bringup manager ({seen})')
            self.conn.setStyleSheet('color: #ef4444; font-weight: 600;')
        self.go_btn.setEnabled(alive)
        self.stop_btn.setEnabled(alive)

    def on_status(self, snap):
        self.snapshot = snap
        self.last_status = time.time()
        overall = snap['overall']
        self.overall.setText(f'{OVERALL_TEXT.get(overall, overall)}   ·   project {snap["project"]}')
        self.overall.setStyleSheet('font-size: 22px; font-weight: 600; color: %s;' % {
            'ready': '#22c55e', 'failed': '#ef4444', 'bringing_up': '#f59e0b',
        }.get(overall, 'palette(text)'))

        stages = snap['stages']
        if self.stage_list.count() != len(stages):
            self.stage_list.clear()
            self.stage_list.addItems([s['title'] for s in stages])
        for i, s in enumerate(stages):
            item = self.stage_list.item(i)
            optional = '' if s['required'] else '  (optional)'
            item.setText(f'{s["title"]}{optional}\n{s["state"].upper()}'
                         + (f' — {s["message"]}' if s['message'] else ''))
            item.setIcon(dot(COLORS.get(s['state'], '#6b7280')))

        # follow the first failure automatically until the user picks something
        if self.selected is None:
            failed = next((i for i, s in enumerate(stages) if s['state'] == 'failed'), 0)
            self.stage_list.setCurrentRow(failed)
        else:
            self.stage_list.setCurrentRow(self.selected)
            self.show_stage(self.selected)

        lines = [f'{time.strftime("%H:%M:%S", time.localtime(e["t"]))}  '
                 f'[{e["level"]}] {e["text"]}' for e in snap['events']]
        text = '\n'.join(lines)
        if self.events.property('robot_text') != text:
            self.events.setProperty('robot_text', text)
            self.events.setPlainText(text)
            self.events.verticalScrollBar().setValue(self.events.verticalScrollBar().maximum())

    def on_select(self, row):
        if row >= 0 and self.snapshot:
            self.show_stage(row)

    def show_stage(self, row):
        s = self.snapshot['stages'][row]
        self.detail_title.setText(f'{s["title"]} — {s["state"].upper()}')
        self.detail_title.setStyleSheet('font-size: 16px; font-weight: 600; color: %s;'
                                        % COLORS.get(s['state'], '#6b7280'))
        self.detail_msg.setText(s['message'] or '')

        self.checks.setRowCount(len(s['checks']))
        for r, c in enumerate(s['checks']):
            name = QtWidgets.QTableWidgetItem(c['label'])
            name.setIcon(dot({True: '#22c55e', None: '#f59e0b'}.get(c['ok'], '#ef4444'), 12))
            self.checks.setItem(r, 0, name)
            self.checks.setItem(r, 1, QtWidgets.QTableWidgetItem(c['value']))
            self.checks.setItem(r, 2, QtWidgets.QTableWidgetItem(c['hint']))
        self.checks.resizeColumnsToContents()

        self.containers.setRowCount(len(s['containers']))
        for r, c in enumerate(s['containers']):
            name = QtWidgets.QTableWidgetItem(c['name'])
            name.setIcon(dot('#22c55e' if c['status'] == 'running' else '#ef4444', 12))
            self.containers.setItem(r, 0, name)
            self.containers.setItem(r, 1, QtWidgets.QTableWidgetItem(c['status']))
            self.containers.setItem(r, 2, QtWidgets.QTableWidgetItem(
                '' if c['exit_code'] is None else str(c['exit_code'])))
            self.containers.setItem(r, 3, QtWidgets.QTableWidgetItem(str(c['restarts'])))
        self.containers.resizeColumnsToContents()

        names = [c['name'] for c in s['containers']]
        if [self.log_pick.itemText(i) for i in range(self.log_pick.count())] != names:
            self.log_pick.clear()
            self.log_pick.addItems(names)
        # logs captured at failure time arrive with the status; show them unprompted
        if s['logs'] and self.log_view.property('stage') != (row, s['started_at']):
            self.log_view.setProperty('stage', (row, s['started_at']))
            self.log_view.setPlainText('\n\n'.join(
                f'===== {name} (at failure) =====\n' + '\n'.join(lines)
                for name, lines in s['logs'].items()))

    def fetch_logs(self):
        if self.log_pick.currentText():
            self.ros.request_logs(self.log_pick.currentText())

    def on_logs(self, msg):
        self.log_view.setProperty('stage', None)
        self.log_view.setPlainText(f'===== {msg["container"]} (live) =====\n'
                                   + '\n'.join(msg['lines']))
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    ros = RosBridge()
    win = MainWindow(ros)
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
