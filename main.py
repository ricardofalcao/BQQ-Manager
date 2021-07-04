"""
UART Service
-------------

An example showing how to write a simple program using the Nordic Semiconductor
(nRF) UART service.

"""

import asyncio
import sys
import threading

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
    widget.resize(800, 600)
    widget.show()

    ble_scanner.scan_started.connect(lambda: widget.update_scan_button(True))
    ble_scanner.scan_finished.connect(lambda: widget.update_scan_button(False))
    ble_scanner.device_connected.connect(widget.add_device)
    ble_scanner.device_disconnected.connect(widget.remove_device)

    asyncio.run_coroutine_threadsafe(ble_scanner.scan_ble_devices(), loop)

    ble_scanner.start()

    app.exec_()

    print("Finishing")

    asyncio.run_coroutine_threadsafe(ble_scanner.stop_ble_scan(), loop)
    asyncio.run_coroutine_threadsafe(ble_scanner.disconnect_devices(), loop)
    loop.call_soon_threadsafe(loop.stop)
