# app/ros/__init__.py
from .cli_client import call_service_cli
from .srv_builders import (
    make_seq_no,
    infer_channel_from_target_name,
    yaml_cup,
    yaml_coffee,
    yaml_ice,
    yaml_powder,
)
