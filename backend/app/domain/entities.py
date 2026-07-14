from enum import StrEnum


class CollectionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"
