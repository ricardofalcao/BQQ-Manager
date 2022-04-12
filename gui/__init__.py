import asyncio
from asyncio import Task
from datetime import datetime
from math import floor
from typing import List

from PySide2.QtGui import QIntValidator, QColor, QPalette, QStandardItemModel, QStandardItem, QIcon
from PySide2.QtWidgets import (QPushButton,
                               QVBoxLayout, QWidget, QHBoxLayout, QListWidget, QSplitter, QFrame, QGridLayout,
                               QGroupBox, QLabel, QSpacerItem, QSizePolicy, QProgressBar, QTimeEdit, QLineEdit,
                               QListWidgetItem, QAbstractItemView, QTableWidget, QHeaderView, QTableWidgetItem,
                               QCheckBox, QTreeView, QFileIconProvider, QMenu, QErrorMessage, QMessageBox, QFileDialog)
from PySide2.QtCore import Qt, Slot, QTime, QDir
from qasync import asyncSlot

from ble import Device, Scanner
from utils.dialogs import QAsyncMessageBox, QAsyncFileDialog


class MainWidget(QWidget):
    ble_device: Device

    device_list: QListWidget
    device_list_frame: QFrame
    empty_device: QFrame
    empty_device_label: QLabel
    content_frame: QFrame

    time_sync_button: QPushButton
    scan_button: QPushButton

    time_value: QLabel

    battery_value: QProgressBar
    battery_voltage: QLabel

    id_edit: QLineEdit
    frame_edit: QLineEdit

    imu_acceleration_x: QLabel
    imu_acceleration_y: QLabel
    imu_acceleration_z: QLabel

    imu_gyro_x: QLabel
    imu_gyro_y: QLabel
    imu_gyro_z: QLabel

    device_label: QLabel
    firmware_value: QLabel

    alarms_time: List[QTimeEdit] = [None] * 12
    alarms_duration: List[QTimeEdit] = [None] * 12

    file_icon_provider: QFileIconProvider
    files_root: QStandardItem
    files_progress: QProgressBar
    files_text: QLabel
    files_refresh_button: QPushButton

    def __init__(self, ble_scanner: Scanner):
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

        splitter.setSizes([150, 500, 500])

        layout.addWidget(splitter)

        self.setLayout(layout)

        #
        ble_scanner.scan_started.connect(lambda: self.update_scan_button(True))
        ble_scanner.scan_finished.connect(lambda: self.update_scan_button(False))

        #
        ble_scanner.device_found.connect(self.add_device)
        # ble_scanner.device_disconnected.connect(self.remove_device)

    #
    #
    #

    @Slot(Device)
    def add_device(self, device: Device):
        item = QListWidgetItem(self.device_list)
        device.list_widget = item
        device.list_widget_label = QLabel(device.name)

        item.device = device
        self.device_list.addItem(item)
        self.device_list.setItemWidget(item, device.list_widget_label)

    @Slot(Device)
    def update_device(self, device: Device):
        self.ble_device = device

        if device.name:
            device.list_widget_label.setText(device.name)

        self.set_battery(device.battery)
        self.set_device_firmware(device.firmware)
        self.set_device_label(device.name)

        if device.dtime_changed:
            device.dtime_changed = False
            self.set_device_time(device.dtime)

        self.set_imu(device.imu_acceleration, device.imu_gyro)

        if device.settings_changed:
            device.settings_changed = False
            self.set_settings(device.settings)

        if device.alarms_changed:
            device.alarms_changed = False
            self.set_alarms(device.alarms)

        if device.folders_changed:
            device.folders_changed = False
            self.set_files(device.folders)

        self.files_refresh_button.setDisabled(device.folders_disabled)

        self.files_text.setText(device.folders_message)
        self.files_progress.setValue(device.folders_progress * 100)

    @asyncSlot(QListWidgetItem, QListWidgetItem)
    async def select_device(self, current, previous):
        self.empty_device.setVisible(True)
        self.content_frame.setVisible(False)

        loop = asyncio.get_event_loop()

        if previous:
            self.empty_device_label.setText('Disconnecting from previous device...')
            if previous.device.runtask is not None:
                previous.device.runtask.cancel()

                previous.device.runtask = None

            previous.device.updated.disconnect()
            await previous.device.disconnect_device()

        if current:
            self.empty_device_label.setText('Connecting to selected device...')
            current.device.updated.connect(self.update_device)

            try:
                await current.device.connect_device()

                current.device.runtask = loop.create_task(current.device.run())

                self.update_device(current.device)
                self.empty_device.setVisible(False)
                self.content_frame.setVisible(True)
            except Exception as ex:
                self.remove_device(current.device)
                self.empty_device_label.setText('Could not connect to device.')

    def remove_device(self, device: Device):
        self.ble_scanner.devices.pop(device.client.address)

        if device.list_widget:
            self.device_list.takeItem(self.device_list.row(device.list_widget))

        if len(self.device_list.selectedItems()) == 0:
            self.empty_device.setVisible(True)
            self.content_frame.setVisible(False)

    def set_battery(self, value: int):
        valuef = value / 100.0
        self.battery_value.setValue(max((valuef - 3.3) / (4.2 - 3.3), 0) * 100.0)
        self.battery_voltage.setText("{:.1f} V".format(valuef))

    def set_device_time(self, time: datetime):
        now = datetime.now()

        palette = self.time_sync_button.palette()
        if abs((now - time).total_seconds()) > 5:
            palette.setColor(QPalette.Button, QColor(Qt.red))
        else:
            palette.setColor(QPalette.Button, QColor(Qt.green))

        self.time_sync_button.setAutoFillBackground(True)
        self.time_sync_button.setPalette(palette)
        self.time_sync_button.update()

        if time == datetime.min:
            self.time_value.setText("unknown")
        else:
            self.time_value.setText(time.strftime("%d/%m/%Y %H:%M:%S"))

    def set_device_firmware(self, firmware: str):
        self.firmware_value.setText(firmware)

    def set_device_label(self, label: str):
        self.device_label.setText(label)

    def set_settings(self, settings):
        # if not self.id_edit.hasFocus():
        self.id_edit.setText(str(settings[0]))

        # if not self.frame_edit.hasFocus():
        self.frame_edit.setText(str(settings[1]))

    def set_imu(self, imu_acceleration, imu_gyro):
        self.imu_acceleration_x.setText("X: %.2f" % imu_acceleration[0])
        self.imu_acceleration_y.setText("Y: %.2f" % imu_acceleration[1])
        self.imu_acceleration_z.setText("Z: %.2f" % imu_acceleration[2])

        self.imu_gyro_x.setText("X: %.2f" % imu_gyro[0])
        self.imu_gyro_y.setText("Y: %.2f" % imu_gyro[1])
        self.imu_gyro_z.setText("Z: %.2f" % imu_gyro[2])

    def set_alarms(self, alarms):
        for i, alarm in enumerate(alarms):
            self.alarms_time[i].setTime(QTime(alarm.hour, alarm.minute))
            self.alarms_duration[i].setTime(QTime(floor(alarm.duration / 60), alarm.duration % 60))

    def set_files(self, folders):
        self.files_root.removeRows(0, self.files_root.rowCount())

        for folder in folders:
            folderItem = QStandardItem(self.file_icon_provider.icon(QFileIconProvider.Folder), folder.name)
            folderItem.setEditable(False)
            folderItem.setData(2)

            for file in folder.children:
                fileItem = QStandardItem(self.file_icon_provider.icon(QFileIconProvider.File), file.name)
                fileItem.setEditable(False)
                fileItem.setData(3)
                folderItem.appendRow(fileItem)

            self.files_root.appendRow(folderItem)

    #
    #
    #

    async def sync_device_time(self, time: datetime):
        if self.ble_device:
            t = time.strftime('%H,%M,%S,%d,%m,%y')
            self.ble_device.send_cmd(f"synctime:{t}")

    async def refresh_device_settings(self):
        if self.ble_device:
            self.ble_device.send_cmd("getsettings")

    async def set_device_settings(self):
        if self.ble_device:
            self.ble_device.send_cmd(f"setsettings:{self.id_edit.text()},{self.frame_edit.text()}")

    async def reset_imu(self):
        if self.ble_device:
            self.ble_device.send_cmd("imureset")

    async def calibrate_imu(self):
        if self.ble_device:
            self.ble_device.send_cmd("imucalib")

    @asyncSlot()
    async def refresh_alarms(self):
        if self.ble_device:
            self.ble_device.send_cmd("alarmGET")

    @asyncSlot()
    async def clear_all_alarms(self):
        if self.ble_device:
            command = 'alarmSET:'
            for i in range(12):
                command += "0,0,0,0,"

            self.ble_device.send_cmd(command[:-1])

    @asyncSlot()
    async def refresh_files(self):
        if self.ble_device and not self.ble_device.folders_pending:
            self.ble_device.folders_pending = True
            self.files_root.removeRows(0, self.files_root.rowCount())
            self.ble_device.send_cmd("gnfolders:*")

    @asyncSlot()
    async def update_alarms(self):
        if self.ble_device:
            command = 'alarmSET:'
            for i in range(12):
                time = self.alarms_time[i].time()
                duration = self.alarms_duration[i].time()
                durationMinutes = duration.hour() * 60 + duration.minute()
                command += f"{1 if durationMinutes > 0 else 0},{time.hour()},{time.minute()},{durationMinutes},"

            self.ble_device.send_cmd(command[:-1])

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

        self.empty_device_label = QLabel(
            "Please select a device from the device list\nIf the device is not found, please wait a few seconds before scanning again")
        self.empty_device_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_device_label)

        self.empty_device.setLayout(layout)

    def create_device_list(self):
        self.device_list_frame = QFrame()

        layout = QVBoxLayout()

        self.device_list = QListWidget()
        self.device_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.device_list.currentItemChanged.connect(self.select_device)

        layout.addWidget(self.device_list)

        self.scan_button = QPushButton("")
        self.scan_button.clicked.connect(
            lambda: asyncio.run_coroutine_threadsafe(self.ble_scanner.scan_ble_devices(), asyncio.get_event_loop()))

        layout.addWidget(self.scan_button)

        self.device_list_frame.setLayout(layout)

    def create_content_frame(self):
        self.content_frame = QFrame()

        layout = QGridLayout()
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

        def status():
            status_box = QGroupBox("Status")
            layout_box = QVBoxLayout()

            grid_box = QGridLayout()
            grid_box.addWidget(QLabel("Device time:"), 0, 0)

            self.time_value = QLabel()
            self.time_value.setAlignment(Qt.AlignRight)
            grid_box.addWidget(self.time_value, 0, 1)

            self.time_sync_button = QPushButton("Sync")
            self.time_sync_button.clicked.connect(
                lambda: asyncio.run_coroutine_threadsafe(self.sync_device_time(datetime.now()),
                                                         asyncio.get_event_loop()))

            grid_box.addWidget(self.time_sync_button, 1, 0, 1, 2)

            grid_box.addItem(QSpacerItem(0, 1, QSizePolicy.Fixed, QSizePolicy.Expanding), 3, 0)

            layout_box.addItem(grid_box)

            grid_box = QGridLayout()
            grid_box.setHorizontalSpacing(10)
            grid_box.addWidget(QLabel("Battery:"), 0, 0, 1, 1)

            self.battery_voltage = QLabel("0.0 V")
            self.battery_voltage.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid_box.addWidget(self.battery_voltage, 0, 2)

            layout_box.addItem(grid_box)

            self.battery_value = QProgressBar(maximum=100)
            self.battery_value.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.set_battery(0)

            layout_box.addWidget(self.battery_value)

            layout_box.addStretch()

            status_box.setLayout(layout_box)
            layout.addWidget(status_box, 0, 0)

        status()

        def imu():
            imu_box = QGroupBox("IMU")
            layout_box = QVBoxLayout()

            grid_box = QGridLayout()
            grid_box.setHorizontalSpacing(15)
            grid_box.addWidget(QLabel("Acceleration:"), 0, 0, 1, 1)

            self.imu_acceleration_x = QLabel("X: 0.0")
            self.imu_acceleration_y = QLabel("Y: 0.0")
            self.imu_acceleration_z = QLabel("Z: 0.0")
            grid_box.addWidget(self.imu_acceleration_x, 0, 2)
            grid_box.addWidget(self.imu_acceleration_y, 0, 3)
            grid_box.addWidget(self.imu_acceleration_z, 0, 4)

            # grid_box.addItem(QSpacerItem(1, 0, QSizePolicy.Expanding, QSizePolicy.Fixed), 0, 1, 2, 1)

            grid_box.addWidget(QLabel("Gyroscope:"), 1, 0, 1, 2)

            self.imu_gyro_x = QLabel("X: 0.0")
            self.imu_gyro_y = QLabel("Y: 0.0")
            self.imu_gyro_z = QLabel("Z: 0.0")
            grid_box.addWidget(self.imu_gyro_x, 1, 2)
            grid_box.addWidget(self.imu_gyro_y, 1, 3)
            grid_box.addWidget(self.imu_gyro_z, 1, 4)

            layout_box.addItem(grid_box)

            reset_button = QPushButton("Reset")
            reset_button.clicked.connect(
                lambda: asyncio.run_coroutine_threadsafe(self.reset_imu(), asyncio.get_event_loop()))
            layout_box.addWidget(reset_button)

            calib_button = QPushButton("Calibrate")
            calib_button.clicked.connect(
                lambda: asyncio.run_coroutine_threadsafe(self.calibrate_imu(), asyncio.get_event_loop()))
            # layout_box.addWidget(calib_button)

            layout_box.addStretch()

            imu_box.setLayout(layout_box)
            layout.addWidget(imu_box, 0, 1)

        imu()

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

            update_button = QPushButton("Update")

            def update_button_click():
                self.id_edit.clearFocus()
                self.frame_edit.clearFocus()
                asyncio.run_coroutine_threadsafe(self.set_device_settings(), asyncio.get_event_loop())

            update_button.clicked.connect(update_button_click)
            layout_box.addWidget(update_button)

            def refresh_button_click():
                self.id_edit.clearFocus()
                self.frame_edit.clearFocus()
                asyncio.run_coroutine_threadsafe(self.refresh_device_settings(), asyncio.get_event_loop())

            refresh_button = QPushButton("Refresh")
            refresh_button.clicked.connect(refresh_button_click)
            layout_box.addWidget(refresh_button)

            layout_box.addStretch()

            settings_box.setLayout(layout_box)
            layout.addWidget(settings_box, 0, 2)

        settings()

        def actions():
            actions_box = QGroupBox("Misc")
            layout_box = QVBoxLayout()

            layout_box.addStretch()

            self.device_label = QLabel()
            self.device_label.setAlignment(Qt.AlignRight)
            self.set_device_label("unknown")
            layout_box.addWidget(self.device_label)

            self.firmware_value = QLabel()
            self.firmware_value.setAlignment(Qt.AlignRight)
            self.set_device_firmware("unknown")
            layout_box.addWidget(self.firmware_value)

            actions_box.setLayout(layout_box)
            layout.addWidget(actions_box, 1, 2)

        actions()

        def alarm():
            actions_box = QGroupBox("Alarms")
            layout_box = QVBoxLayout()

            tableWidget = QTableWidget(12, 2)
            tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tableWidget.setFocusPolicy(Qt.NoFocus)
            tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
            tableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
            tableWidget.setSelectionMode(QAbstractItemView.NoSelection)
            tableWidget.setHorizontalHeaderLabels(["Time", "Duration"])

            tableWidget.setStyleSheet("""
                QTableWidget::item { margin: 1px 0px; vertical-align: middle; }
                """)
            for i in range(12):
                cell_widget = QWidget()
                cell_layout = QVBoxLayout();
                timeEdit = QTimeEdit()
                timeEdit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                timeEdit.setFrame(QFrame.NoFrame)

                self.alarms_time[i] = timeEdit

                cell_layout.addWidget(timeEdit)
                cell_layout.setAlignment(Qt.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_widget.setLayout(cell_layout)

                tableWidget.setCellWidget(i, 0, cell_widget)

                cell_widget = QWidget()
                cell_layout = QVBoxLayout();
                durationEdit = QTimeEdit()
                durationEdit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                durationEdit.setFrame(QFrame.NoFrame)

                self.alarms_duration[i] = durationEdit

                cell_layout.addWidget(durationEdit)
                cell_layout.setAlignment(Qt.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_widget.setLayout(cell_layout)
                tableWidget.setCellWidget(i, 1, durationEdit)

            header = tableWidget.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.Stretch)

            layout_box.addWidget(tableWidget)

            update_button = QPushButton("Update")
            update_button.clicked.connect(self.update_alarms)
            layout_box.addWidget(update_button)

            refresh_button = QPushButton("Refresh")
            refresh_button.clicked.connect(self.refresh_alarms)
            layout_box.addWidget(refresh_button)

            clear_all_button = QPushButton("Clear All")
            clear_all_button.clicked.connect(self.clear_all_alarms)
            layout_box.addWidget(clear_all_button)

            actions_box.setLayout(layout_box)
            layout.addWidget(actions_box, 1, 0, 2, 1)

        alarm()

        def files():
            actions_box = QGroupBox("Files")
            layout_box = QVBoxLayout()

            tree_view = QTreeView()
            tree_view.setDragEnabled(False)
            tree_view.setContextMenuPolicy(Qt.CustomContextMenu)

            self.file_icon_provider = QFileIconProvider()

            model = QStandardItemModel()
            model.setHorizontalHeaderLabels(['Name'])

            self.files_root = model.invisibleRootItem()

            # test = QStandardItem(icon_provider.icon(QFileIconProvider.Folder), "Teste")

            tree_view.setModel(model)
            layout_box.addWidget(tree_view)

            self.files_refresh_button = QPushButton("Refresh")
            self.files_refresh_button.clicked.connect(self.refresh_files)
            layout_box.addWidget(self.files_refresh_button)

            footer_grid = QGridLayout()
            self.files_progress = QProgressBar()
            footer_grid.addWidget(self.files_progress, 0, 0)

            self.files_text = QLabel("")
            self.files_text.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            footer_grid.addWidget(self.files_text, 0, 1)
            footer_grid.setColumnStretch(0, 1)
            footer_grid.setColumnStretch(1, 1)
            layout_box.addItem(footer_grid)

            actions_box.setLayout(layout_box)
            layout.addWidget(actions_box, 1, 1)

            @Slot()
            def menuClick(pos):
                index = tree_view.indexAt(pos)
                if not index.isValid():
                    return

                it = model.itemFromIndex(index)

                menu = QMenu()

                if it.data() == 2:
                    delete_action = menu.addAction("&Delete")
                    download_action = menu.addAction("&Download")

                    action = menu.exec_(tree_view.viewport().mapToGlobal(pos))

                    if action == delete_action:
                        self.ble_device.delete_folder(it.text())
                    elif action == download_action:
                        target_path = QFileDialog.getExistingDirectory(None, 'Select destination folder')
                        self.ble_device.download_folder(it.text(), target_path)
                elif it.data() == 3:
                    download_action = menu.addAction("&Download")
                    action = menu.exec_(tree_view.viewport().mapToGlobal(pos))
                    if action == download_action:
                        folder = it.parent().text()
                        target_path, extension = QFileDialog.getSaveFileName(None, 'Select destination file', f'{folder}_{it.text()}.csv', 'CSV files (*.csv)')
                        if not target_path.endswith('.csv'):
                            target_path += '.csv'

                        self.ble_device.download_file(folder, it.text(), target_path)

            tree_view.customContextMenuRequested.connect(menuClick)

        files()

        self.content_frame.setLayout(layout)
