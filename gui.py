import asyncio
from datetime import datetime
from time import strftime, gmtime, struct_time

from PySide2.QtGui import QIntValidator
from PySide2.QtWidgets import (QPushButton,
                               QVBoxLayout, QWidget, QHBoxLayout, QListWidget, QSplitter, QFrame, QGridLayout,
                               QGroupBox, QLabel, QSpacerItem, QSizePolicy, QProgressBar, QTimeEdit, QLineEdit,
                               QListWidgetItem, QAbstractItemView)
from PySide2.QtCore import Qt, QTime, Slot

import ble


class BLEWidget(QWidget):
    device_list: QListWidget
    device_list_frame: QFrame
    empty_device: QFrame
    content_frame: QFrame

    scan_button: QPushButton

    time_value: QLabel

    alarm_value: QLabel
    alarm_edit: QTimeEdit

    battery_value: QProgressBar

    id_edit: QLineEdit
    frame_edit: QLineEdit

    firmware_value: QLabel

    def __init__(self, ble_scanner: ble.BLEScanner):
        QWidget.__init__(self)

        self.ble_scanner = ble_scanner

        self.create_device_list()
        self.create_empty_device()
        self.create_content_frame()

        layout = QHBoxLayout()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.device_list_frame)
        splitter.addWidget(self.empty_device)
        splitter.addWidget(self.content_frame)

        self.empty_device.setVisible(True)
        self.content_frame.setVisible(False)

        splitter.setSizes([200, 500, 500])

        layout.addWidget(splitter)

        self.setLayout(layout)

    #
    #
    #

    @Slot(ble.Device)
    def add_device(self, device: ble.Device):
        item = QListWidgetItem(self.device_list)
        device.list_widget = item

        item.device = device
        self.device_list.addItem(item)
        self.device_list.setItemWidget(item, QLabel(device.name))

    @Slot(ble.Device)
    def update_device(self, device: ble.Device):
        self.set_battery(device.battery)
        self.set_device_firmware(device.firmware)
        self.set_device_time(device.dtime)
        self.set_alarm_time(device.alarm_time)

    @Slot(QListWidgetItem, QListWidgetItem)
    def select_device(self, current, previous):
        if previous:
            previous.device.updated.disconnect(self.update_device)

        if current:
            current.device.updated.connect(self.update_device)

            self.update_device(current.device)
            self.empty_device.setVisible(False)
            self.content_frame.setVisible(True)

    @Slot(ble.Device)
    def remove_device(self, device: ble.Device):
        if device.list_widget:
            self.device_list.takeItem(self.device_list.row(device.list_widget))

        if len(self.device_list.selectedItems()) == 0:
            self.empty_device.setVisible(True)
            self.content_frame.setVisible(False)

    def set_battery(self, value: int):
        self.battery_value.setValue(value)

    def set_device_time(self, time: datetime):
        if time == datetime.min:
            self.time_value.setText("unknown")
        else:
            self.time_value.setText(time.strftime("%d/%m/%Y %H:%M:%S"))

    def set_device_firmware(self, firmware: str):
        self.firmware_value.setText(firmware)

    def set_alarm_time(self, time: datetime):
        if time == datetime.min:
            self.alarm_value.setText("unknown")
            self.alarm_edit.setTime(QTime(0, 0, 0))
        else:
            self.alarm_value.setText(time.strftime("%d/%m/%Y %H:%M:%S"))
            self.alarm_edit.setTime(QTime(time.hour, time.minute, time.second))

    #
    #
    #

    def update_scan_button(self, value: bool):
        self.scan_button.setEnabled(not value)

        if not value:
            self.scan_button.setText("Scan nearby devices")
        else:
            self.scan_button.setText("Scanning devices...")

    def create_empty_device(self):
        self.empty_device = QFrame()
        layout = QVBoxLayout()

        label = QLabel("Please select a device from the device list")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.empty_device.setLayout(layout)

    def create_device_list(self):
        self.device_list_frame = QFrame()

        layout = QVBoxLayout()

        self.device_list = QListWidget()
        self.device_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.device_list.currentItemChanged.connect(self.select_device)

        layout.addWidget(self.device_list)

        self.scan_button = QPushButton("")
        self.scan_button.clicked.connect(lambda: asyncio.run_coroutine_threadsafe(self.ble_scanner.scan_ble_devices(), asyncio.get_event_loop()))

        layout.addWidget(self.scan_button)

        self.device_list_frame.setLayout(layout)

    def create_content_frame(self):
        self.content_frame = QFrame()

        layout = QGridLayout()

        def time():
            time_box = QGroupBox("Time")
            layout_box = QGridLayout()

            layout_box.addWidget(QLabel("Device time:"), 0, 0)

            self.time_value = QLabel()
            self.time_value.setAlignment(Qt.AlignRight)
            layout_box.addWidget(self.time_value, 0, 1)

            layout_box.addWidget(QPushButton("Sync"), 1, 0, 1, 2)

            layout_box.addItem(QSpacerItem(0, 1, QSizePolicy.Fixed, QSizePolicy.Expanding), 3, 0)

            time_box.setLayout(layout_box)
            layout.addWidget(time_box, 0, 0)

        time()

        def alarm():
            alarm_box = QGroupBox("Alarm")
            layout_box = QGridLayout()

            layout_box.addWidget(QLabel("Current wake-up time:"), 0, 0)

            self.alarm_value = QLabel()
            self.alarm_value.setAlignment(Qt.AlignRight)

            self.alarm_edit = QTimeEdit()

            layout_box.addWidget(self.alarm_value, 0, 1)
            layout_box.addWidget(self.alarm_edit, 1, 0, 1, 2)

            update_button = QPushButton("Update")
            layout_box.addWidget(update_button, 2, 0, 2, 2)

            layout_box.addItem(QSpacerItem(0, 1, QSizePolicy.Fixed, QSizePolicy.Expanding), 4, 0)

            alarm_box.setLayout(layout_box)
            layout.addWidget(alarm_box, 1, 0)

        alarm()

        def status():
            status_box = QGroupBox("Status")
            layout_box = QVBoxLayout()

            layout_box.addWidget(QLabel("Battery:"))

            self.battery_value = QProgressBar(maximum=100)
            self.battery_value.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.set_battery(0)

            layout_box.addWidget(self.battery_value)

            layout_box.addStretch()

            status_box.setLayout(layout_box)
            layout.addWidget(status_box, 0, 1, 2, 1)

        status()

        def settings():
            settings_box = QGroupBox("Settings")
            layout_box = QVBoxLayout()

            layout_box.addWidget(QLabel("ID:"))

            self.id_edit = QLineEdit()
            self.id_edit.setValidator(QIntValidator(bottom=0))
            self.id_edit.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            layout_box.addWidget(self.id_edit)

            layout_box.addWidget(QLabel("Frame:"))

            self.frame_edit = QLineEdit()
            self.frame_edit.setValidator(QIntValidator(bottom=0))
            self.frame_edit.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            layout_box.addWidget(self.frame_edit)

            layout_box.addWidget(QPushButton("Update"))
            layout_box.addWidget(QPushButton("Refresh"))

            layout_box.addStretch()

            settings_box.setLayout(layout_box)
            layout.addWidget(settings_box, 2, 0)

        settings()

        def firmware():
            firmware_box = QGroupBox("Firmware")
            layout_box = QGridLayout()

            layout_box.addWidget(QLabel("Device firmware:"), 0, 0)

            self.firmware_value = QLabel()
            self.firmware_value.setAlignment(Qt.AlignRight)
            self.set_device_firmware("unknown")
            layout_box.addWidget(self.firmware_value, 0, 1)

            layout_box.addItem(QSpacerItem(0, 1, QSizePolicy.Fixed, QSizePolicy.Expanding), 2, 0)

            firmware_box.setLayout(layout_box)
            layout.addWidget(firmware_box, 2, 1)

        firmware()

        self.content_frame.setLayout(layout)
