"""GNSS module for reading and parsing NMEA 0183 data from a serial port."""

from sensing.gnss.reader import GNSSReader
from sensing.gnss.types import GNSSData

__all__ = ["GNSSData", "GNSSReader"]
