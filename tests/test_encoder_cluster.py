import time

import pytest

from client import StubProc
from conftest import Device, ZCLCommandEvent
from tests.zcl_consts import (
  ZCL_CLUSTER_ON_OFF,
  ZCL_CMD_ONOFF_TOGGLE,
  ZCL_CLUSTER_LEVEL_CONTROL,
  ZCL_CMD_LEVEL_STEP,
  ZCL_LEVEL_MOVE_UP,
  ZCL_CLUSTER_LIGHTING_COLOR_CONTROL,
  ZCL_CMD_LIGHTING_COLOR_STEP_TEMP
)

@pytest.fixture
def encoder_device() -> Device:
    p = StubProc(device_config="X;Y;EA0uA1uA2u;").start() 
    # EA0uA1uA2u;
    d = Device(p)
    yield d  

def test_encoder_cluster_switch_pressing_causes_on_off_command(encoder_device: Device) -> None:
  
    # Test setup
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A2", 0) # Press
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A2", 1) # Release
    encoder_device.step_time(100)

    # Assertions
    encoder_device.wait_for_cmd_send(
        1, ZCL_CLUSTER_ON_OFF, ZCL_CMD_ONOFF_TOGGLE
    )

def test_encoder_cluster_rotating_clockwise_causes_step_up_command(encoder_device: Device) -> None:
  
    # Test setup
    encoder_device.step_time(100)

    # When Rotating clockwise Pin A changes before Pin B
    result = encoder_device.set_gpio("A0", 0)
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A1", 0) 
    encoder_device.step_time(100)

    # Assertions
    cmd = encoder_device.wait_for_cmd_send(
        1, ZCL_CLUSTER_LEVEL_CONTROL, ZCL_CMD_LEVEL_STEP
    )
    assert cmd.data == b'\x00\x0D\x01\x00' # x00 Move Up, StepSize x0D, Transistion Time \x01\x00 (1 x 1/10th Sec)

def test_encoder_cluster_rotating_anticlockwise_causes_step_down_command(encoder_device: Device) -> None:
  
    # Test setup
    encoder_device.step_time(100)

    # When Rotating anti-clockwise Pin B changes before Pin A
    result = encoder_device.set_gpio("A1", 0)
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A0", 0) 
    encoder_device.step_time(100)

    # Assertions
    cmd = encoder_device.wait_for_cmd_send(
        1, ZCL_CLUSTER_LEVEL_CONTROL, ZCL_CMD_LEVEL_STEP
    )
    assert cmd.data == b'\x01\x0D\x01\x00' # x01 Move Down, StepSize x0D, Transistion Time \x01\x00 (1 x 1/10th Sec)

def test_encoder_cluster_rotating_clockwise_white_pressed_causes_step_up_colour_temp_command(encoder_device: Device) -> None:
  
    # Test setup
    encoder_device.step_time(100)

    # When Rotating clockwise Pin A changes before Pin B
    result = encoder_device.set_gpio("A2", 0) # Press
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A0", 0)
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A1", 0) 
    encoder_device.step_time(100)

    # Assertions
    cmd = encoder_device.wait_for_cmd_send(
        1, ZCL_CLUSTER_LIGHTING_COLOR_CONTROL, ZCL_CMD_LIGHTING_COLOR_STEP_TEMP
    )
    assert cmd.data == b'\x01\x0D\x00\x01\x00\x00\x00\xfe\xff' # 01 Move Up, StepSize 0D00, Transistion Time 0100 (1 x 1/10th Sec), 0000 min, feff max

def test_encoder_cluster_rotating_anticlockwise_white_pressed_causes_step_down_colour_temp_command(encoder_device: Device) -> None:
  
    # Test setup
    encoder_device.step_time(100)

    result = encoder_device.set_gpio("A2", 0) # Press
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A1", 0)
    encoder_device.step_time(100)
    result = encoder_device.set_gpio("A0", 0) 
    encoder_device.step_time(100)

    # Assertions
    cmd = encoder_device.wait_for_cmd_send(
        1, ZCL_CLUSTER_LIGHTING_COLOR_CONTROL, ZCL_CMD_LIGHTING_COLOR_STEP_TEMP
    )
    assert cmd.data == b'\x03\x0D\x00\x01\x00\x00\x00\xfe\xff' # 03 Move Down, StepSize 0D00, Transistion Time 0100 (1 x 1/10th Sec), 0000 min, feff max


def _wait_level_steps(device: Device, count: int, timeout: float = 1.0) -> list:
    deadline = time.monotonic() + timeout
    steps = _level_steps(device)
    while len(steps) < count and time.monotonic() < deadline:
        time.sleep(0.05)
        steps = _level_steps(device)
    time.sleep(0.2)  # let any extra command show up
    return _level_steps(device)


def _level_steps(device: Device) -> list:
    steps = []
    for e in device._events:
        if e.kind != "zcl_cmd_send":
            continue
        cmd = ZCLCommandEvent.from_event(e)
        if cmd.cluster == ZCL_CLUSTER_LEVEL_CONTROL and cmd.cmd == ZCL_CMD_LEVEL_STEP:
            steps.append((cmd.data[0], cmd.data[1]))
    return steps


def test_encoder_fast_second_detent_is_sent_after_rate_limit_window(encoder_device: Device) -> None:
    encoder_device.step_time(200)

    # Two clockwise detents (4 edges) inside one 100 ms rate-limit window
    for pin, val in (("A0", 0), ("A1", 0), ("A0", 1), ("A1", 1)):
        encoder_device.set_gpio(pin, val)
        encoder_device.step_time(10)
    encoder_device.step_time(300)

    steps = _wait_level_steps(encoder_device, 2)
    assert [s[0] for s in steps] == [0x00] * len(steps)  # all "up"
    assert sum(s[1] for s in steps) == 26                # nothing left pending


def test_encoder_pending_steps_do_not_leak_into_next_direction(encoder_device: Device) -> None:
    encoder_device.step_time(200)

    for pin, val in (("A0", 0), ("A1", 0), ("A0", 1), ("A1", 1)):
        encoder_device.set_gpio(pin, val)
        encoder_device.step_time(10)
    encoder_device.step_time(1000)
    before = _wait_level_steps(encoder_device, 2)

    # one anti-clockwise detent: B before A
    for pin, val in (("A1", 0), ("A0", 0)):
        encoder_device.set_gpio(pin, val)
        encoder_device.step_time(10)
    encoder_device.step_time(300)

    after = _wait_level_steps(encoder_device, len(before) + 1)
    assert after[len(before):] == [(0x01, 13)]  # exactly one "down" step of 13
