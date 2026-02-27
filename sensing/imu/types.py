"""IMU data types for sensor readings."""

from dataclasses import dataclass


@dataclass
class IMUData:
    """A single IMU sample with accelerometer and gyroscope readings.

    Attributes:
        timestamp: CLOCK_REALTIME seconds captured at the DRDY interrupt edge.

        accel_x: Acceleration along X-axis in m/s².
        accel_y: Acceleration along Y-axis in m/s².
        accel_z: Acceleration along Z-axis in m/s².

        gyro_x: Angular rate around X-axis in rad/s.
        gyro_y: Angular rate around Y-axis in rad/s.
        gyro_z: Angular rate around Z-axis in rad/s.

    Example:
        >>> with IMUReader() as imu:
        ...     sample = imu.read()
        >>> sample.accel_z  # roughly 9.8 m/s² when flat
        9.79...
        >>> sample.gyro_x   # near 0 rad/s when stationary
        0.001...
    """

    timestamp: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
