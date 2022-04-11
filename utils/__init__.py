from dataclasses import dataclass
from typing import List


@dataclass
class Alarm:
    hour: int = 0
    minute: int = 0
    duration: int = 0
    enabled: bool = False

@dataclass
class LogFile:
    name: str

@dataclass
class LogFolder:
    name: str
    children: List[LogFile]

def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']:
        if size < 1024.0 or unit == 'PiB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

