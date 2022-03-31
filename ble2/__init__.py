import asyncio
import logging
from datetime import datetime

from PySide2.QtCore import QObject, Signal
from PySide2.QtWidgets import QLabel, QListWidgetItem
from bleak import BleakClient, BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

from utils import Alarm, LogFolder, LogFile, human_readable_size

UART_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
UART_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
# All BLE devices have MTU of at least 23. Subtracting 3 bytes overhead, we can
# safely send 20 bytes at a time to any device supporting this service.
UART_SAFE_SIZE = 20


class Device(QObject):
    info: BLEDevice
    client: BleakClient
    characteristic: BleakGATTCharacteristic

    logger = logging.Logger

    read_buffer = ''

    updated = Signal
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
    folders_changed = False
    folders_pending = False
    folders_error = False
    folders_progress = 0
    folders_message = ""

    folder_pending_delete = ""

    download_size = 0
    download_written = 0
    download_file_stream = None

    def __init__(self, ble: BLEDevice):
        QObject.__init__(self)

        self.info = ble
        self.logger = logging.getLogger(self.info.name)

    async def connect(self):
        self.client = BleakClient(self.info)
        self.client.set_disconnected_callback(self.on_disconnect)

        self.logger.info(f"Connecting...")

        try:
            await self.client.connect()

            self.characteristic = self.get_characteristic(UART_SERVICE_UUID, UART_CHAR_UUID)
            if self.characteristic is None:
                return False

            await self.client.start_notify(self.characteristic, self.on_data_rx)
            return True
        except BleakError as ex:
            self.logger.warning(ex)
            return False

    def get_characteristic(self, service_id, characteristic_id):
        service = next((s for s in self.client.services if s.uuid == service_id), None)

        if service is not None:
            return next((c for c in service.characteristics if c.uuid == characteristic_id), None)

    async def disconnect(self):
        self.logger.info(f"Disconnecting...")
        await self.client.disconnect()

    #
    #
    #

    async def fetch_data(self, data):
        await self.write('info')
        await asyncio.sleep(0.5)

    async def write(self, data):
        data = data + '\n'

        while len(data) > UART_SAFE_SIZE:
            await self.client.write_gatt_char(self.characteristic, bytearray((data[0:UART_SAFE_SIZE]).encode()))
            await asyncio.sleep(0.5)

            data = data[UART_SAFE_SIZE:]

        if len(data) > 0:
            await self.client.write_gatt_char(self.characteristic, bytearray(data.encode()))
            await asyncio.sleep(0.5)

    #
    #
    #

    async def process_message(self, message):
        print(message)
        __split = message.split(":")
        command = __split[0]

        try:
            if command == "ping":
                await self.write("pong")
            elif command == "time":
                self.dtime = datetime.strptime(__split[1], '%H,%M,%S,%d,%m,%y')
                self.dtime_changed = True
            elif command == "battery":
                self.battery = int(__split[1])
            elif command == "firmware":
                self.firmware = __split[1]
            elif command == "getsettings":
                split2 = __split[1].split(",")
                self.settings = (int(split2[0]), int(split2[1]))
                self.settings_changed = True
            elif command == "setsettings":
                if __split[1] == "ok":
                    await self.write("getsettings")
            elif command == "imudata":
                split2 = __split[1].split(",")
                self.imu_acceleration = (float(split2[0]), float(split2[1]), float(split2[2]))
                self.imu_gyro = (float(split2[3]), float(split2[4]), float(split2[5]))
            elif command == "info":
                split2 = __split[1].split(",")

                self.battery = int(split2[0])
                self.dtime = datetime.strptime(','.join(split2[1:7]), '%H,%M,%S,%d,%m,%y')
                self.dtime_changed = True
                self.imu_acceleration = (float(split2[7]), float(split2[8]), float(split2[9]))
                self.imu_gyro = (float(split2[10]), float(split2[11]), float(split2[12]))
            elif command == "alarm":
                split2 = __split[1].split(",")
                args = split2[1:] # ignore 'all'
                for i in range(12):
                    self.alarms[i] = Alarm(int(args[i*4 + 1]), int(args[i*4 + 2]), int(args[i*4 + 3]), args[i*4 + 0] == '1')

                self.alarms_changed = True
            elif command == "alarmSET":
                if __split[1] == "OK":
                    await self.write("alarmGET")
            elif command == "delfolder":
                split2 = __split[1].split(",")

                if split2[0] == "ok":
                    self.folders = [i for i in self.folders if i.name != self.folder_pending_delete]
                    self.folders_changed = True
                else:
                    print('Fail')

                self.folder_pending_delete = ""
            elif command == "gnfolders":
                split2 = __split[1].split(",")

                self.folders = [0] * int(split2[1])
                await self.write("getnamefolders:*")
            elif command == "namefolder":
                split2 = __split[1].split(",")
                folderId = int(split2[1])

                self.folders_progress = (folderId + 1) / len(self.folders) * 0.5
                self.folders_message = f"Received folder {split2[2]} {folderId + 1}/{len(self.folders)}"

                self.folders[folderId] = LogFolder(split2[2], [])

                if folderId + 1 < len(self.folders):
                    self.write("getnamefolders:*")
                else:
                    self.folders_index = 0
                    folder = self.folders[self.folders_index]
                    await self.write(f"gnfiles:{folder.name},*")

            elif command == "gnfiles":
                split2 = __split[1].split(",")
                folder = self.folders[self.folders_index]

                folder.children = [0] * int(split2[1])
                await self.write(f"getnamefiles:*")

            elif command == "namefiles":
                split2 = __split[1].split(",")
                fileId = int(split2[1])
                folder = self.folders[self.folders_index]

                self.folders_progress = 0.5 + (fileId + 1) / len(folder.children) * 0.5
                self.folders_message = f"Received file {fileId + 1}/{len(folder.children)}"

                folder.children[fileId] = LogFile(split2[2])

                if fileId + 1 < len(folder.children):
                    await self.write(f"getnamefiles:*")
                elif self.folders_index + 1 < len(self.folders):
                    self.folders_index = self.folders_index + 1
                    folder = self.folders[self.folders_index]
                    await self.write(f"gnfiles:{folder.name},*")
                else:
                    self.folders_pending = False
                    self.folders_changed = True

            elif command == "getslog":
                split2 = __split[1].split(",")
                self.download_size = int(split2[0])

                await self.write(f"startlog:*")

            elif command == "getflog":
                self.download_written = self.download_written + self.download_file_stream.write(__split[1].replace('~', '\n'))
                await self.write(f"getflog:ok,*")

                self.folders_progress = self.download_written / self.download_size
                self.folders_message = f"{human_readable_size(self.download_written)}/{human_readable_size(self.download_size)}"

            elif command.startswith("endlog"):
                print("closed")
                self.download_file_stream.flush()
                self.download_file_stream.close()


        except Exception as e:
            print(e)

        # self.updated.emit(self)

    #
    #
    #

    def on_disconnect(self, client):
        self.logger.info("Disconnected!")

    async def on_data_rx(self, _: int, data: bytearray):
        command = data.decode()
        result = command.find('\n')

        queue = []

        print(f'rxxx: {command}')

        while result != -1:
            self.read_buffer += command[0:result]
            queue.append(self.read_buffer)
            self.read_buffer = ''

            command = command[result:-1]
            result = command.find('\n')

        self.read_buffer += command

        tasks = asyncio.gather(*[self.process_message(msg) for msg in queue])
        await tasks
