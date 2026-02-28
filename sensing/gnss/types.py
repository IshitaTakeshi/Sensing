"""GNSS data types for combined parsed sentences."""

from dataclasses import dataclass, field

from sensing.nmea.types import GGAData, VTGData


@dataclass
class GNSSData:
    """A combined GNSS sample pairing a GGA fix with the most recent VTG velocity.

    ``GNSSReader`` emits one ``GNSSData`` per GGA sentence received. The
    accompanying ``vtg`` field holds the last ``VTGData`` seen before that GGA;
    it is ``None`` until the first VTG sentence has been received.

    Attributes:
        gga: Parsed GGA sentence with position, altitude, and fix quality.
            Always present; ``gga.valid`` is ``False`` when there is no fix.

        vtg: Parsed VTG sentence with speed and track, or ``None`` if no VTG
            sentence has been received yet. ``vtg.valid`` may also be
            ``False`` when the receiver reports no valid velocity.

    Example:
        >>> with GNSSReader() as gnss:
        ...     data = gnss.read()
        >>> data.gga.latitude_degrees  # decimal degrees, or None if no fix
        48.1173
        >>> data.gga.fix_quality
        4  # RTK Fixed
        >>> data.vtg.speed_meters_per_second if data.vtg else None
        2.833...
    """

    gga: GGAData
    vtg: VTGData | None = field(default=None)
