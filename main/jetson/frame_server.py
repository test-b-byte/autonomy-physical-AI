#!/usr/bin/env python3
"""
Camera frame server: the depth camera lives on the Jetson, the person
detector runs on the Pi's Hailo accelerator.  This node forwards JPEG frames
from a ROS CompressedImage topic to the Pi over ZeroMQ.

  wire:  ZMQ PUB on tcp://*:5555, one part per frame:
         8-byte little-endian f64 capture time (unix s) + JPEG bytes
         The Pi subscribes with CONFLATE (always the newest frame).

  python3 jetson/frame_server.py
  python3 jetson/frame_server.py --topic /camera/color/image_raw/compressed --fps 5
"""
from __future__ import annotations

import argparse
import struct
import time


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--topic", default="/camera/left_ir/image_raw/compressed",
                    help="sensor_msgs/CompressedImage (JPEG) topic")
    ap.add_argument("--bind", default="tcp://*:5555")
    ap.add_argument("--fps", type=float, default=8.0, help="max frames/s forwarded")
    args = ap.parse_args()

    import rclpy
    import zmq
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CompressedImage

    sock = zmq.Context.instance().socket(zmq.PUB)
    sock.setsockopt(zmq.SNDHWM, 2)
    sock.setsockopt(zmq.LINGER, 0)
    sock.bind(args.bind)

    rclpy.init()
    node = rclpy.create_node("ghost_frame_server")
    log = node.get_logger()
    state = {"last": 0.0, "sent": 0, "warned": False}
    period = 1.0 / args.fps

    def on_image(msg: CompressedImage) -> None:
        now = time.monotonic()
        if now - state["last"] < period:
            return
        state["last"] = now
        if "jpeg" not in msg.format.lower() and "jpg" not in msg.format.lower() and not state["warned"]:
            state["warned"] = True
            log.warn(f"frame format is {msg.format!r} — the Pi detector expects JPEG")
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if abs(stamp - time.time()) > 3600:          # camera clock, not wall clock
            stamp = time.time()
        try:
            sock.send(struct.pack("<d", stamp) + bytes(msg.data), zmq.NOBLOCK)
            state["sent"] += 1
            if state["sent"] % 100 == 1:
                log.info(f"forwarded {state['sent']} frames from {args.topic}")
        except zmq.Again:
            pass

    node.create_subscription(CompressedImage, args.topic, on_image, qos_profile_sensor_data)
    log.info(f"forwarding {args.topic} → {args.bind} at ≤{args.fps} fps")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
        sock.close()


if __name__ == "__main__":
    main()
