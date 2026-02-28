"""JSON formatting utilities for sensor data."""

import json

from sensing.gnss import GNSSData
from sensing.imu import IMUData

__all__ = ["format_gnss_message", "format_imu_message"]


def format_gnss_message(data: GNSSData) -> str:
    """Serialize GNSS data into a JSON string for WebSocket transmission."""
    vtg = data.vtg
    vtg_valid = vtg.valid if vtg is not None else None
    speed = vtg.speed_meters_per_second if vtg is not None else None
    track = vtg.track_true_degrees if vtg is not None else None

    return json.dumps({
        "type": "gnss",
        "lat": data.gga.latitude_degrees,
        "lon": data.gga.longitude_degrees,
        "alt": data.gga.altitude_meters,
        "fix_quality": data.gga.fix_quality,
        "num_satellites": data.gga.num_satellites,
        "hdop": data.gga.horizontal_dilution_of_precision,
        "utc_time": data.gga.utc_time,
        "speed_ms": speed,
        "track_degrees": track,
        "vtg_valid": vtg_valid,
    })


def format_imu_message(data: IMUData) -> str:
    """Serialize IMU data into a JSON string for WebSocket transmission."""
    return json.dumps({
        "type": "imu",
        "timestamp_ns": data.timestamp_ns,
        "accel_x": data.accel_x,
        "accel_y": data.accel_y,
        "accel_z": data.accel_z,
        "gyro_z": data.gyro_z,
    })
