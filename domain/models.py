from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class SignalType(Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True)
class SignalInfo:
    signal_id: str
    signal_type: SignalType
    description: str
    from_box: str
    via_boxes: Tuple[str, ...]
    to_box: str
    program_address: str
    logic_group: str = ""

    def __post_init__(self):
        if not self.signal_id:
            raise ValueError("信号IDは必須です")
        if not self.description:
            raise ValueError("説明は必須です")


@dataclass
class BoxConnection:
    from_box_name: str
    from_box_no: str
    kabel_no: str
    to_box_no: str
    to_box_name: str
