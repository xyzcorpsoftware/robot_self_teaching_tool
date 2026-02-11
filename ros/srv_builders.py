# app/ros/srv_builders.py
import time


def make_seq_no(prefix: str = "ui") -> str:
    return f"{prefix}-{time.time():.3f}"


def infer_channel_from_target_name(target_name: str) -> int:
    digits = "".join(ch for ch in target_name if ch.isdigit())
    return int(digits) if digits else 1


def yaml_cup(seq_no: str, cmd: str, channel: int) -> str:
    return f"{{seq_no: '{seq_no}', cmd: '{cmd}', channel: {int(channel)}}}"


def yaml_coffee(seq_no: str, cmd: str, protocol_id: int, device_id: int, delay_time: float) -> str:
    return (
        f"{{seq_no: '{seq_no}', cmd: '{cmd}', "
        f"protocol_id: {int(protocol_id)}, device_id: {int(device_id)}, delay_time: {float(delay_time)}}}"
    )


def yaml_ice(seq_no: str, cmd: str, ice_qty: int, water_qty: int, channel: int) -> str:
    return (
        f"{{seq_no: '{seq_no}', cmd: '{cmd}', "
        f"ice_qty: {int(ice_qty)}, water_qty: {int(water_qty)}, channel: {int(channel)}}}"
    )


def yaml_powder(seq_no: str, cmd: str, part_no: int, menu_id: str, opt_id: str, channel: int, req_value: int) -> str:
    return (
        f"{{seq_no: '{seq_no}', cmd: '{cmd}', part_no: {int(part_no)}, "
        f"menu_id: '{menu_id}', opt_id: '{opt_id}', channel: {int(channel)}, req_value: {int(req_value)}}}"
    )
