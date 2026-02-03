"""NMEA data types for parsed sentences.

This module defines dataclasses for structured NMEA sentence data.

Design Decisions:
    1. Optional fields (float | None): NMEA fields may be empty, indicated by
       consecutive commas. Using None distinguishes "no data received" from
       "measured zero" - critical for stationary detection and data quality.

    2. Separate valid flag: The valid field indicates navigation validity,
       NOT parse validity. A successfully parsed sentence may still be
       navigationally invalid (e.g., no GPS fix). This allows consumers to:
       - Distinguish parse errors (None return) from invalid fixes (valid=False)
       - Process invalid data for debugging/logging while filtering for navigation

    3. fix_quality as int (not Optional): The value 0 already means "invalid"
       in the NMEA spec, so there's no semantic difference between "empty" and "0".
"""

from dataclasses import dataclass


@dataclass
class GGAData:
    """Parsed GGA (Global Positioning System Fix Data) sentence.

    GGA provides the primary position fix information from GNSS receivers,
    including coordinates, altitude, and fix quality metrics.

    Attributes:
        utc_time: UTC timestamp in HHMMSS.ss format (e.g., "123519.00").
            None if field was empty.

        latitude_degrees: Latitude in decimal degrees, positive=North.
            Range: -90.0 to +90.0. None if no fix or field empty.
            Converted from NMEA's DDMM.MMMM format.

        longitude_degrees: Longitude in decimal degrees, positive=East.
            Range: -180.0 to +180.0. None if no fix or field empty.
            Converted from NMEA's DDDMM.MMMM format.

        fix_quality: GPS fix quality indicator (always present, defaults to 0):
            0 = Invalid (no fix)
            1 = GPS fix (SPS - Standard Positioning Service)
            2 = DGPS fix (Differential GPS)
            4 = RTK Fixed (centimeter-level accuracy)
            5 = RTK Float (decimeter-level accuracy, converging)
            6 = Dead reckoning mode

        num_satellites: Number of satellites used in the fix solution.
            More satellites generally means better accuracy.
            None if field was empty.

        horizontal_dilution_of_precision: HDOP value indicating position
            accuracy. Lower is better (< 1 = ideal, 1-2 = excellent,
            2-5 = good, > 10 = poor). None if field was empty.

        altitude_meters: Altitude above mean sea level (MSL) in meters.
            None if no fix or field empty.

        geoid_height_meters: Height of geoid (MSL) above WGS84 ellipsoid.
            Used to convert between ellipsoidal and orthometric heights:
            ellipsoid_height = altitude_meters + geoid_height_meters.
            None if field was empty.

        valid: Navigation validity flag. True only if fix_quality > 0.
            A False value means the receiver has no fix; coordinates
            should not be used for navigation.

    Example:
        >>> gga = parse_gga("$GNGGA,123519.00,4807.038,N,01131.000,E,4,12,0.5,545.4,M,47.0,M,,*7D")
        >>> gga.fix_quality
        4  # RTK Fixed
        >>> gga.latitude_degrees
        48.1173
        >>> gga.valid
        True
    """

    utc_time: str | None
    latitude_degrees: float | None
    longitude_degrees: float | None
    fix_quality: int
    num_satellites: int | None
    horizontal_dilution_of_precision: float | None
    altitude_meters: float | None
    geoid_height_meters: float | None
    valid: bool


@dataclass
class VTGData:
    """Parsed VTG (Track Made Good and Ground Speed) sentence.

    VTG provides velocity information - ground speed and heading (track).
    Essential for navigation and sensor fusion applications.

    Attributes:
        track_true_degrees: Heading/track relative to true north in degrees.
            Range: 0.0 to 360.0 (0 = North, 90 = East, 180 = South, 270 = West).
            None when stationary (GNSS cannot determine heading without movement).

        speed_knots: Ground speed in nautical miles per hour (knots).
            1 knot = 1.852 km/h = 0.514 m/s.
            None if field was empty.

        speed_kilometers_per_hour: Ground speed in km/h.
            None if field was empty.

        speed_meters_per_second: Ground speed in m/s (SI units).
            Computed from km/h for sensor fusion compatibility.
            None if km/h field was empty.

        mode: FAA mode indicator (NMEA 2.3+):
            'A' = Autonomous (standard GPS positioning)
            'D' = Differential (DGPS or RTK - higher accuracy)
            'E' = Estimated (dead reckoning - no satellite fix)
            'N' = Not valid (no fix)
            None if field was missing (older receivers).

        valid: Navigation validity flag. True only if mode is present
            and not 'N'. A False value means velocity data should not
            be used for navigation.

    Note:
        When the vehicle is stationary, track_true_degrees is typically None
        because GNSS receivers cannot determine heading without movement.
        Speed values may be 0.0 (measured zero) or None (no data).

    Example:
        >>> vtg = parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,D*3E")
        >>> vtg.track_true_degrees
        54.7
        >>> vtg.speed_meters_per_second
        2.833...
        >>> vtg.mode
        'D'  # Differential mode
        >>> vtg.valid
        True
    """

    track_true_degrees: float | None
    speed_knots: float | None
    speed_kilometers_per_hour: float | None
    speed_meters_per_second: float | None
    mode: str | None
    valid: bool
