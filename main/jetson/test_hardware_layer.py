"""Hardware-free tests for the robot layer:  python3 -m pytest jetson/ sensors/"""
import math
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sensors"))

import motor_board as mb                       # noqa: E402
from base_driver import mecanum_ik, scale_to_limit   # noqa: E402
from detector import decode_yolov8, parse_hailo_nms  # noqa: E402
from teleop import command                     # noqa: E402


def test_crc8_maxim_check_value():
    assert mb.crc8(b"123456789") == 0xA1      # CRC-8/MAXIM catalogue check value


def test_motor_frame_layout():
    f = mb.frame(mb.FUNC_MOTOR, mb.motor_payload({1: 0.5, 4: -1.25}))
    assert f[:2] == b"\xAA\x55" and f[2] == 3 and f[3] == len(f) - 5
    assert f[4:6] == bytes([0x01, 2])
    assert struct.unpack("<Bf", f[6:11]) == (0, 0.5)
    assert struct.unpack("<Bf", f[11:16]) == (3, -1.25)
    assert f[-1] == mb.crc8(f[2:-1])


def test_parser_survives_noise_and_split_reads():
    batt = mb.frame(mb.FUNC_SYS, bytes([0x04]) + struct.pack("<H", 11800))
    imu = mb.frame(mb.FUNC_IMU, struct.pack("<6f", 0, 0, 9.8, 0, 0, 0.1))
    bad = bytearray(batt); bad[-1] ^= 0xFF
    stream = b"\x00\xAA\x13" + bytes(bad) + batt + imu
    p, out = mb.FrameParser(), []
    for i in range(0, len(stream), 3):          # arrives in 3-byte chunks
        out += list(p.feed(stream[i:i + 3]))
    assert [f for f, _ in out] == [mb.FUNC_SYS, mb.FUNC_IMU]
    assert struct.unpack("<H", out[0][1][1:])[0] == 11800


def test_mecanum_kinematics():
    r = 0.05
    fwd = mecanum_ik(0.2, 0, 0, r=r)
    assert all(math.isclose(w, 0.2 / (2 * math.pi * r)) for w in fwd)
    fl, fr, rl, rr = mecanum_ik(0, 0.2, 0, r=r)          # strafe left
    assert fl < 0 < fr and rl > 0 > rr
    fl, fr, rl, rr = mecanum_ik(0, 0, 1.0, r=r)          # rotate CCW
    assert fl < 0 and rl < 0 and fr > 0 and rr > 0


def test_speed_limit_keeps_direction():
    w = scale_to_limit([3.0, -1.5, 1.0, 0.0], 1.5)
    assert max(abs(v) for v in w) == 1.5 and w[1] == -0.75


def test_teleop_deadman():
    assert command("w", 0.1, 0.25, 0.3, 1.0) == (0.3, 0, 0)
    assert command("w", 0.5, 0.25, 0.3, 1.0) == (0, 0, 0)      # key released
    assert command("z", 0.0, 0.25, 0.3, 1.0) == (0, 0, 0)      # unknown key stops


def test_yolov8_decode_and_nms():
    out = np.zeros((1, 84, 3), np.float32)
    out[0, :4, 0] = [320, 320, 100, 200]; out[0, 4, 0] = 0.9   # person
    out[0, :4, 1] = [322, 318, 100, 200]; out[0, 4, 1] = 0.6   # overlapping duplicate
    out[0, :4, 2] = [100, 100, 50, 50];   out[0, 5, 2] = 0.95  # bicycle — ignored
    dets = decode_yolov8(out, conf=0.4, iou=0.5)
    assert len(dets) == 1 and dets[0][0] == np.float32(0.9)
    assert dets[0][1] == (270.0, 220.0, 370.0, 420.0)


def test_hailo_nms_flat_buffer():
    flat = [1, 0.1, 0.2, 0.5, 0.6, 0.88] + [0] * 79                  # 1 person, 0 of the rest
    for raw in (flat, np.array(flat, np.float32)):
        (score, box), = parse_hailo_nms(raw, 80)
        assert math.isclose(score, 0.88, rel_tol=1e-6) and math.isclose(box[2], 0.5, rel_tol=1e-6)
    per_class = [np.array([[0.1, 0.2, 0.5, 0.6, 0.7]])] + [np.zeros((0, 5))] * 79
    assert parse_hailo_nms(per_class, 80)[0][0] == np.float32(0.7)


def test_bridge_frames():
    # avoid importing rclpy: exercise the pure frame maths by hand
    origin = (0.5, 0.5)
    to_grid = lambda x, y: (x + origin[0], y + origin[1])
    to_odom = lambda gx, gy: (gx - origin[0], gy - origin[1])
    cell = 0.5
    gx, gy = (3 + 0.5) * cell, (2 + 0.5) * cell      # centre of cell (3,2)
    ox, oy = to_odom(gx, gy)
    assert (ox, oy) == (1.25, 0.75)
    assert tuple(int(v // cell) for v in to_grid(ox, oy)) == (3, 2)
