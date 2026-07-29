"""Constants for Chore Race."""

from typing import Final

DOMAIN: Final = "chore_race"
PLATFORMS: Final = ["sensor"]
STORAGE_KEY: Final = f"{DOMAIN}.data"
STORAGE_VERSION: Final = 1
CONFIG_ENTRY_UNIQUE_ID: Final = DOMAIN

DEFAULT_NORMAL_COMPLETION_POINTS: Final = 1
DEFAULT_FAIR_PLAY_BONUS: Final = 1

EVENT_TASK_CREATED: Final = f"{DOMAIN}_task_created"
EVENT_TASK_COMPLETED: Final = f"{DOMAIN}_task_completed"
EVENT_TASK_REOPENED: Final = f"{DOMAIN}_task_reopened"
EVENT_DATA_UPDATED: Final = f"{DOMAIN}_data_updated"

SERVICE_CREATE_PARTICIPANT: Final = "create_participant"
SERVICE_UPDATE_PARTICIPANT: Final = "update_participant"
SERVICE_CREATE_CHORE_TYPE: Final = "create_chore_type"
SERVICE_UPDATE_CHORE_TYPE: Final = "update_chore_type"
SERVICE_CREATE_TASK: Final = "create_task"
SERVICE_CREATE_RECURRENCE_RULE: Final = "create_recurrence_rule"
SERVICE_UPDATE_RECURRENCE_RULE: Final = "update_recurrence_rule"
SERVICE_DELETE_RECURRENCE_RULE: Final = "delete_recurrence_rule"
SERVICE_START_RACE: Final = "start_race"
SERVICE_STOP_RACE: Final = "stop_race"
SERVICE_COMPLETE_TASK: Final = "complete_task"
SERVICE_UNDO_COMPLETION: Final = "undo_completion"
SERVICE_DELETE_TASK: Final = "delete_task"
