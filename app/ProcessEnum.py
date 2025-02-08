from enum import Enum

class ProcessEnum(Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    BREAK = "break"
    COMPLETED = "completed"
    ERROR = "error"