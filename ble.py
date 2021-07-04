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
    thread: threading.Thread

    updated: Signal = Signal(Device)

    list_widget: QListWidgetItem

    dtime: datetime = datetime.min
    alarm_time: datetime = datetime.min

    battery: int = 0
    firmware: str = 'unknown'

    def __init__(self, scanner: BLEScanner, ble: BLEDevice):
        QThread.__init__(self, None)

        self.scanner = scanner
        self.ble = ble
        self.name = ble.name
        self.read_buffer = ''
        self.running = False

    #
    #
    #

    async def send_cmd(self, command: str):
        await self.client.write_gatt_char(UART_CHAR_UUID, bytearray((command + "\n").encode()))

    #
    #
    #

    async def receive_cmd(self, data: str):
        split = data.split(":")
        command = split[0]
        print(f"Received: {data} {command}")

        if command == "ping":
            await self.send_cmd("pong")
        elif command == "time":
            self.dtime = datetime.strptime(split[1], '%H,%M,%S,%d,%m,%y')
        elif command == "battery":
            self.battery = int(int(split[1]) / 420.0 * 100)
        elif command == "firmware":
            self.firmware = split[1]

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

    def run(self):
        while self.running:
            asyncio.run(self.send_cmd("gettime"))
            time.sleep(0.5)
            asyncio.run(self.send_cmd("battery"))
            time.sleep(0.5)
            asyncio.run(self.send_cmd("firmware"))
            time.sleep(0.5)

    #
    #
    #

    async def connect_device(self):
        self.client = BleakClient(self.ble, disconnected_callback=self.handle_disconnect)

        self.running = True
        self.scanner.device_connected.emit(self)
        self.scanner.devices[self.ble.address] = self

        self.scanner.device_updated.emit(self)

        await self.client.connect()

        await self.client.start_notify(UART_CHAR_UUID, self.handle_rx)

        self.start()

    async def disconnect_device(self):
        self.running = False

        await self.client.disconnect()


#
#
#

class BLEScanner(QThread):
    devices = {}

    scanner: BleakScanner
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

    async def scan_ble_devices(self):
        if self.running:
            return

        await self.disconnect_devices()

        print("Scanning for devices")
        self.running = True
        self.scan_started.emit()

        self.scanner = BleakScanner()
        await self.scanner.start()
        await asyncio.sleep(5)
        await self.scanner.stop()

        print("Finished scanning")
        self.running = False
        self.scan_finished.emit()

        for device in self.scanner.discovered_devices:
            if device.address not in self.devices:
                print("NEW device " + device.name + " - " + device.address)

                new_device = Device(self, device)

                await new_device.connect_device()

    async def stop_ble_scan(self):
        await self.scanner.stop()

    async def disconnect_devices(self):
        l = list(self.devices.values())

        for i in range(len(self.devices)):
            device = l[0]
            print("Disconnect " + device.name)
            await device.disconnect_device()
