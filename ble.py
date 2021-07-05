import asyncio
import threading
import time
from datetime import datetime
from logging import log

from PySide2 import QtCore
from PySide2.QtCore import Signal, QObject, QThread
from PySide2.QtWidgets import QListWidgetItem

from bleak import BleakScanner, BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

UART_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
UART_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# All BLE devices have MTU of at least 23. Subtracting 3 bytes overhead, we can
# safely send 20 bytes at a time to any device supporting this service.
UART_SAFE_SIZE = 20


#
#
#

class BLEScanner(QThread):
    pass


class Device(QThread):
    pass


class Device(QThread):
    name: str
    client: BleakClient
    connect_task: asyncio.Task = None

    updated: Signal = Signal(Device)
    queued_commands = []

    list_widget: QListWidgetItem = None

    dtime: datetime = datetime.min
    alarm_time: datetime = datetime.min

    battery: int = 0
    firmware: str = 'unknown'

    settings = (0, 0)
    settings_changed: bool = True

    imu_acceleration = (0, 0, 0)
    imu_gyro = (0, 0, 0)

    def __init__(self, scanner: BLEScanner, ble: BLEDevice):
        QThread.__init__(self, None)

        self.scanner = scanner
        self.ble = ble
        self.name = ble.name
        self.read_buffer = ''
        self.running = False
        self.connected = False

    #
    #
    #

    async def _send_cmd(self, command: str):
        if not self.running:
            return

        command = command + "\n"

        while len(command) > UART_SAFE_SIZE:
            await self.client.write_gatt_char(UART_CHAR_UUID, bytearray((command[0:UART_SAFE_SIZE]).encode()))
            command = command[UART_SAFE_SIZE:-1]

        if len(command) > 0:
            await self.client.write_gatt_char(UART_CHAR_UUID, bytearray((command + "\n").encode()))

    async def send_cmd(self, command: str):
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

        if command == "ping":
            await self.send_cmd("pong")

            if not self.connected:
                self.scanner.device_connected.emit(self)
                self.connected = True
        elif command == "time":
            self.dtime = datetime.strptime(split[1], '%H,%M,%S,%d,%m,%y')
        elif command == "battery":
            self.battery = int(int(split[1]) / 420.0 * 100)
        elif command == "firmware":
            self.firmware = split[1]
        elif command == "getsettings":
            split2 = split[1].split(",")
            self.settings = (int(split2[0]), int(split2[1]))
            self.settings_changed = True
        elif command == "setsettings":
            if split[1] == "ok":
                await self.send_cmd("getsettings")
        elif command == "imudata":
            split2 = split[1].split(",")
            self.imu_acceleration = (float(split2[0]), float(split2[1]), float(split2[2]))
            self.imu_gyro = (float(split2[3]), float(split2[4]), float(split2[5]))

        self.updated.emit(self)

    #
    #
    #

    async def handle_rx(self, _: int, data: bytearray):
        command = data.decode()

        result = command.find('\n')

        while result != -1:
            self.read_buffer += command[0:result]
            await self.receive_cmd(self.read_buffer)
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

        self.exit()

        self.scanner.device_disconnected.emit(self)
        if self.ble.address in self.scanner.devices:
            del self.scanner.devices[self.ble.address]

    def _sleep(self, _time: float):
        time.sleep(_time)

        if len(self.queued_commands) > 0:
            for i in range(len(self.queued_commands)):
                command = self.queued_commands[0]
                asyncio.run(self._send_cmd(command))
                self.queued_commands.remove(command)
                time.sleep(_time)

    def run(self):
        while self.running:
            asyncio.run(self._send_cmd("gettime"))
            self._sleep(0.5)
            asyncio.run(self._send_cmd("battery"))
            self._sleep(0.5)
            asyncio.run(self._send_cmd("imudata"))
            self._sleep(0.5)
            asyncio.run(self._send_cmd("firmware"))
            self._sleep(0.5)
            asyncio.run(self._send_cmd("getsettings"))
            self._sleep(0.5)

    #
    #
    #

    async def connect_device(self):
        if self.running:
            return

        self.client = BleakClient(self.ble, disconnected_callback=self.handle_disconnect, loop=asyncio.get_event_loop())

        self.running = True

        self.updated.emit(self)

        self.connect_task = asyncio.create_task(self.client.connect())
        await self.connect_task

        await self.client.start_notify(UART_CHAR_UUID, self.handle_rx)

        self.start()

    async def disconnect_device(self):
        self.running = False

        if self.connect_task:
            self.connect_task.cancel()

        await self.client.disconnect()


#
#
#

class BLEScanner(QThread):
    devices = {}

    scanner: BleakScanner = None
    scanning_task: asyncio.Task = None
    running = False

    scan_started = Signal()
    scan_finished = Signal()

    device_connected = Signal(Device)
    device_disconnected = Signal(Device)

    def __init__(self, loop):
        QThread.__init__(self, None)

        self.loop = loop

    def run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def device_found_callback(self, device: BLEDevice, adv: AdvertisementData):
        if device.address in self.devices:
            if device.name:
                self.devices[device.address].name = device.name
                await self.devices[device.address].connect_device()

            return

        if UART_SERVICE_UUID.lower() not in adv.service_uuids:
            return

        print("NEW device " + device.name + " - " + device.address)

        new_device = Device(self, device)
        self.devices[device.address] = new_device

    async def scan_ble_devices(self):
        if self.running:
            return

        await self.disconnect_devices()

        print("Scanning for devices")
        self.running = True
        self.scan_started.emit()

        self.scanner = BleakScanner(detection_callback=self.device_found_callback)
        await self.scanner.start()

        self.scanning_task = asyncio.create_task(asyncio.sleep(10))
        await self.scanning_task

        await self.scanner.stop()
        self.scanner = None

        print("Finished scanning")
        self.running = False
        self.scan_finished.emit()

    async def stop_ble_scan(self):
        if self.scanner:
            await self.scanner.stop()
            self.scanner = None

            if self.scanning_task:
                self.scanning_task.cancel()

    async def disconnect_devices(self):
        l = list(self.devices.values())

        for i in range(len(self.devices)):
            device = l[0]
            print("Disconnect " + device.name)
            await device.disconnect_device()
