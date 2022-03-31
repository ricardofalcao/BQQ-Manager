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


def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    ble_scanner = Scanner()
    loop.create_task(ble_scanner.scan_ble_devices())

    widget = MainWidget(ble_scanner)
    widget.setWindowTitle("BBQ Manager")

    icon = QIcon()
    for size in [16, 24, 32, 48, 64, 96, 128, 256, 512]:
        icon.addFile(resource_path(f'icons/{size}.png'), QSize(size, size))

    widget.setWindowIcon(icon)

    widget.resize(1000, 600)
    widget.show()

    with loop:
        loop.run_forever()

    print("Goodbye")
    sys.exit(0)


if __name__ == "__main__":
    main()
