"""
UART Service
-------------

An example showing how to write a simple program using the Nordic Semiconductor
(nRF) UART service.

"""

import asyncio
import sys
import threading

from PySide2.QtCore import QSize
from PySide2.QtGui import QIcon
from bleak import BleakScanner

from PySide2.QtWidgets import QApplication

import ble
import gui

#
#
#


#
#
#

if __name__ == "__main__":
    app = QApplication(sys.argv)

    loop = asyncio.get_event_loop()
    ble_scanner = ble.BLEScanner(loop)

    widget = gui.BLEWidget(ble_scanner)
    widget.setWindowTitle("BBQ Manager")

    icon = QIcon()
    for size in [16, 24, 32, 48, 64, 96, 128, 256, 512]:
        icon.addFile(f'icons/{size}.png', QSize(size, size))

    widget.setWindowIcon(icon)

    widget.resize(1000, 600)
    widget.show()

    ble_scanner.scan_started.connect(lambda: widget.update_scan_button(True))
    ble_scanner.scan_finished.connect(lambda: widget.update_scan_button(False))

    ble_scanner.disconnect_started.connect(lambda: widget.update_disconnect_all_button(True))
    ble_scanner.disconnect_finished.connect(lambda: widget.update_disconnect_all_button(False))

    ble_scanner.device_connected.connect(widget.add_device)
    ble_scanner.device_disconnecting.connect(lambda: widget.update_disconnect_button(True))
    ble_scanner.device_disconnected.connect(widget.remove_device)

    asyncio.run_coroutine_threadsafe(ble_scanner.scan_ble_devices(), ble_scanner.loop)

    ble_scanner.start()

    app.exec_()

    print("Stopping current scan")
    asyncio.run_coroutine_threadsafe(ble_scanner.stop_ble_scan(), ble_scanner.loop).result()
    print("Disconnecting devices")
    asyncio.run_coroutine_threadsafe(ble_scanner.disconnect_devices(), ble_scanner.loop).result()

    ble_scanner.stop()

    print("Goodbye")
    sys.exit(0)

