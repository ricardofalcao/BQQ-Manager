"""
UART Service
-------------

An example showing how to write a simple program using the Nordic Semiconductor
(nRF) UART service.

"""

import asyncio
import functools
import os
import sys

import qasync
from PySide2.QtCore import QSize
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QApplication


#
#
#

from ble import Scanner
from gui import MainWidget


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


async def main():
    def close_future(future, loop):
        loop.call_later(10, future.cancel)
        future.cancel()

    loop = asyncio.get_event_loop()
    future = asyncio.Future()

    app = QApplication.instance()
    if hasattr(app, "aboutToQuit"):
        getattr(app, "aboutToQuit").connect(
            functools.partial(close_future, future, loop)
        )

    ble_scanner = Scanner()

    widget = MainWidget(ble_scanner)
    widget.setWindowTitle("BBQ Manager")

    icon = QIcon()
    for size in [16, 24, 32, 48, 64, 96, 128, 256, 512]:
        icon.addFile(resource_path(f'icons/{size}.png'), QSize(size, size))

    widget.setWindowIcon(icon)

    widget.resize(1000, 600)
    widget.show()

    #

    asyncio.run_coroutine_threadsafe(ble_scanner.scan_ble_devices(), loop)

    await future

    print("Stopping current scan")
    await ble_scanner.stop_ble_scan()
    print("Disconnecting devices")
    await ble_scanner.disconnect_devices()

    print("Goodbye")
    sys.exit(0)

if __name__ == "__main__":
    try:
        qasync.run(main())
    except asyncio.exceptions.CancelledError:
        sys.exit(0)
