import asyncio
import json
import os
import sys
from asyncio import Task
from datetime import datetime

from PySide2.QtCore import QObject, Signal
from PySide2.QtWidgets import QLabel, QListWidgetItem, QMessageBox
from bleak import BleakScanner, BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from utils import Alarm, LogFolder, LogFile, human_readable_size
from utils.dialogs import QAsyncMessageBox

UART_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
UART_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
# All BLE devices have MTU of at least 23. Subtracting 3 bytes overhead, we can
# safely send 20 bytes at a time to any device supporting this service.
UART_SAFE_SIZE = 20


class Device(QObject):
    pass


class Scanner(QObject):
    pass


class Device(QObject):
    name: str
    client: BleakClient

    runtask: Task = None

    updated = Signal(Device)
    queued_commands = []

    list_widget: QListWidgetItem = None
    list_widget_label: QLabel = None

    dtime: datetime = datetime.min
    dtime_changed: bool = True

    alarm_time: datetime = datetime.min

    battery: int = 0
    firmware: str = 'unknown'

    settings = (0, 0)
    settings_changed: bool = True

    imu_acceleration = (0, 0, 0)
    imu_gyro = (0, 0, 0)

    alarms = [Alarm()] * 12
    alarms_changed: bool = False

    folders = []

    folders_index = 0
    folders_disabled = True
    folders_changed = False
    folders_pending = False
    folders_error = False
    folders_progress = 0
    folders_message = ""

    folder_pending_delete = ""

    download_size = 0
    download_written = 0
    download_file_stream = None

    def __init__(self, scanner: Scanner, ble: BLEDevice):
        QObject.__init__(self)

        self.scanner = scanner
        self.ble = ble
        self.name = ble.name if len(ble.name) > 0 else ble.address
        self.read_buffer = ''
        self.running = False

    #
    #
    #

    def delete_folder(self, folder):
        self.folder_pending_delete = folder
        self.send_cmd(f"delfolder:{folder},*")

    def download_file(self, folder, file, target_path):
        print(f'getslog:/{folder}/{file}')

        self.download_file_stream = open(target_path, 'w')
        print(target_path)
        self.send_cmd(f'getslog:/{folder}/{file}')

    async def _send_cmd(self, command: str):
        if not self.running:
            return

        command = command + "\n"

        while len(command) > UART_SAFE_SIZE:
            await self.client.write_gatt_char(UART_CHAR_UUID, bytearray((command[0:UART_SAFE_SIZE]).encode()))

            command = command[UART_SAFE_SIZE:]
            await asyncio.sleep(0.1)

        if len(command) > 0:
            await self.client.write_gatt_char(UART_CHAR_UUID, bytearray(command.encode()))

    def send_cmd(self, command: str):
        if not self.running:
            return

        self.queued_commands.append(command)

    #
    #
    #

    async def receive_cmd(self, data: str):
        split = data.split(":")
        command = split[0]
        print(f"Received: {data} {command}")

        try:
            if command == "ping":
                self.send_cmd("pong")
            elif command == "time":
                self.dtime = datetime.strptime(split[1], '%H,%M,%S,%d,%m,%y')
                self.dtime_changed = True
            elif command == "battery":
                self.battery = int(split[1])
            elif command == "firmware":
                self.firmware = split[1]
            elif command == "getsettings":
                split2 = split[1].split(",")
                self.settings = (int(split2[0]), int(split2[1]))
                self.settings_changed = True
            elif command == "setsettings":
                if split[1] == "ok":
                    self.send_cmd("getsettings")
            elif command == "imudata":
                split2 = split[1].split(",")
                self.imu_acceleration = (float(split2[0]), float(split2[1]), float(split2[2]))
                self.imu_gyro = (float(split2[3]), float(split2[4]), float(split2[5]))
            elif command == "info":
                split2 = split[1].split(",")

                self.battery = int(split2[0])
                self.dtime = datetime.strptime(','.join(split2[1:7]), '%H,%M,%S,%d,%m,%y')
                self.dtime_changed = True
                self.imu_acceleration = (float(split2[7]), float(split2[8]), float(split2[9]))
                self.imu_gyro = (float(split2[10]), float(split2[11]), float(split2[12]))
            elif command == "alarm":
                split2 = split[1].split(",")
                args = split2[1:]  # ignore 'all'
                for i in range(12):
                    self.alarms[i] = Alarm(int(args[i * 4 + 1]), int(args[i * 4 + 2]), int(args[i * 4 + 3]),
                                           args[i * 4 + 0] == '1')

                print(self.alarms)

                self.alarms_changed = True
            elif command == "alarmSET":
                if split[1] == "OK":
                    self.send_cmd("alarmGET")
            elif command == "delfolder":
                split2 = split[1].split(",")

                if split2[0] == "ok":
                    self.folders = [i for i in self.folders if i.name != self.folder_pending_delete]
                    self.folders_changed = True
                else:
                    print('Fail')

                self.folder_pending_delete = ""
            elif command == "gnfolders":
                split2 = split[1].split(",")

                self.folders = [0] * int(split2[1])
                self.send_cmd("getnamefolders:*")
            elif command == "namefolder":
                split2 = split[1].split(",")
                folderId = int(split2[1])

                self.folders_progress = (folderId + 1) / len(self.folders) * 0.5
                self.folders_message = f"Received folder {split2[2]} {folderId + 1}/{len(self.folders)}"

                self.folders[folderId] = LogFolder(split2[2], [])

                if folderId + 1 < len(self.folders):
                    self.send_cmd("getnamefolders:*")
                else:
                    self.folders_index = 0
                    folder = self.folders[self.folders_index]
                    self.send_cmd(f"gnfiles:{folder.name},*")

            elif command == "gnfiles":
                split2 = split[1].split(",")
                folder = self.folders[self.folders_index]

                folder.children = [0] * int(split2[1])
                self.send_cmd(f"getnamefiles:*")

            elif command == "namefiles":
                split2 = split[1].split(",")
                fileId = int(split2[1])
                folder = self.folders[self.folders_index]

                self.folders_progress = 0.5 + (fileId + 1) / len(folder.children) * 0.5
                self.folders_message = f"Received file {fileId + 1}/{len(folder.children)}"

                folder.children[fileId] = LogFile(split2[2])

                if fileId + 1 < len(folder.children):
                    self.send_cmd(f"getnamefiles:*")
                elif self.folders_index + 1 < len(self.folders):
                    self.folders_index = self.folders_index + 1
                    folder = self.folders[self.folders_index]
                    self.send_cmd(f"gnfiles:{folder.name},*")
                else:
                    self.folders_pending = False
                    self.folders_changed = True

            elif command == "getslog":
                split2 = split[1].split(",")
                self.download_size = int(split2[0])
                self.download_written = 0
                self.folders_progress = 0

                self.send_cmd(f"startlog:*")

            elif command == "getflog":
                buf = split[1][0:-4]
                self.download_written = self.download_written + self.download_file_stream.write(buf.replace('~', '\n'))
                self.send_cmd(f"getflog:ok,*")

                print(f"{self.download_written} / {self.download_size}")
                self.folders_progress = self.download_written / self.download_size
                self.folders_message = f"{human_readable_size(self.download_written)}/{human_readable_size(self.download_size)}"

            elif command.startswith("endlog"):
                self.folders_message = 'Finished!'

                self.download_file_stream.flush()
                self.download_file_stream.close()


        except Exception as e:
            print(e)

        self.updated.emit(self)

    #
    #
    #

    async def handle_rx(self, _: int, data: bytearray):
        command = data.decode()
        # print("RX: " + command + " - " + ("".join("{:02x} ".format(x) for x in data)))

        result = command.find('\n')

        while result != -1:
            self.read_buffer += command[0:result]

            try:
                await self.receive_cmd(self.read_buffer)
            except Exception:
                pass

            self.read_buffer = ''

            command = command[result:-1]
            result = command.find('\n')

        self.read_buffer += command

    #
    #
    #

    def handle_disconnect(self, _: BleakClient):
        self.running = False
        print("Device was disconnected, goodbye.")

        if self.ble.address in self.scanner.devices:
            self.scanner.device_disconnected.emit(self)

    async def _sleep(self, _time: float):
        await asyncio.sleep(_time)

        if len(self.queued_commands) > 0:
            for i in range(len(self.queued_commands)):
                command = self.queued_commands[0]
                await self._send_cmd(command)
                self.queued_commands.remove(command)
                await asyncio.sleep(_time)

    async def run(self):
        tick = 0
        tick_duration = 0.2

        self.folders_disabled = True

        await self._sleep(tick_duration * 2)
        await self._send_cmd("info")
        await self._sleep(tick_duration * 2)
        await self._send_cmd("getsettings")
        await self._sleep(tick_duration * 2)
        await self._send_cmd("alarmGET")
        await self._sleep(tick_duration * 2)
        await self._send_cmd("firmware")
        await self._sleep(tick_duration * 2)
        await self._send_cmd("alarmGET")
        await self._sleep(tick_duration * 2)

        self.folders_disabled = False

        while self.running:
            # await self._send_cmd("info")
            await self._sleep(tick_duration)

            if tick % 10 == 0:
                await self._send_cmd("info")
                await self._sleep(tick_duration)

            tick = tick + 1

    #
    #
    #

    async def connect_device(self):
        if self.running:
            return

        print("Connecting device " + self.name)

        self.running = True
        self.client = BleakClient(self.ble, disconnected_callback=self.handle_disconnect)

        self.updated.emit(self)

        await self.client.connect()
        await self.client.start_notify(UART_CHAR_UUID, self.handle_rx)
        await self._send_cmd('pong')

    async def disconnect_device(self):
        if not self.running:
            return

        self.running = False
        self.scanner.device_disconnecting.emit(self)

        if self.client.is_connected:
            await self.client.disconnect()

        if self.ble.address in self.scanner.devices:
            self.scanner.device_disconnected.emit(self)


class Scanner(QObject):
    devices = {}

    scanning = False

    scan_started = Signal()
    scan_finished = Signal()

    disconnect_started = Signal()
    disconnect_finished = Signal()

    device_found = Signal(Device)
    device_disconnecting = Signal(Device)
    device_disconnected = Signal(Device)

    def __init__(self):
        QObject.__init__(self)

    async def scan_ble_devices(self):
        try:
            if self.scanning:
                return

            print("Scanning for devices")
            self.scanning = True
            self.scan_started.emit()

            devices = {}

            async def on_detect(_device: BLEDevice, adv: AdvertisementData):
                if _device.address in devices:
                    if len(_device.name) > 0:
                        devices[_device.address] = _device

                    return
                
                if UART_SERVICE_UUID.lower() not in adv.service_uuids:
                    return

                devices[_device.address] = _device

            async with BleakScanner(detection_callback=on_detect):
                await asyncio.sleep(5.0)

            print(self.devices.keys())
            for address, ble in devices.items():
                device = Device(self, ble)
                if address in self.devices:
                    continue

                self.devices[address] = device
                self.device_found.emit(device)
                
            print("Finished scanning")

            self.scanning = False
            self.scan_finished.emit()
        except Exception as ex:
            print(ex)

    #
    #
    #

    #
    #
    #
