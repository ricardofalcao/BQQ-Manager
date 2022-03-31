"""
UART Service
-------------

An example showing how to write a simple program using the Nordic Semiconductor
(nRF) UART service.

"""

import asyncio
import logging
import sys

import qasync
from PySide2.QtWidgets import QApplication

from gui import MainWidget

logging.basicConfig(level=logging.INFO)

#
#
#


def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    widget = MainWidget()
    widget.show()

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
