"""NMEA checksum validation."""


def _extract_checksum_parts(sentence: str) -> tuple[str, str] | None:
    """Extract content and provided checksum from NMEA sentence."""
    if not sentence.startswith("$") or "*" not in sentence:
        return None

    start = sentence.index("$") + 1
    end = sentence.index("*")
    content = sentence[start:end]
    provided = sentence[end + 1 : end + 3]

    if len(provided) != 2:
        return None

    return content, provided


def _calculate_xor_checksum(content: str) -> int:
    """Calculate XOR checksum of content string."""
    result = 0
    for character in content:
        result ^= ord(character)
    return result


def validate_checksum(sentence: str) -> bool:
    """Validate NMEA sentence checksum.

    The checksum is the XOR of all bytes between '$' and '*' (exclusive).
    """
    sentence = sentence.strip()

    parts = _extract_checksum_parts(sentence)
    if parts is None:
        return False

    content, provided = parts

    try:
        calculated = _calculate_xor_checksum(content)
        return calculated == int(provided, 16)
    except ValueError:
        return False
