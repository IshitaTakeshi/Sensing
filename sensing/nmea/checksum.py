"""NMEA checksum validation.

NMEA 0183 sentences use a simple XOR checksum for data integrity verification.
The checksum is calculated over all characters between '$' and '*' (exclusive),
then represented as a two-digit uppercase hexadecimal number after the '*'.

Example sentence structure:
    $GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F
    ^                         checksum content                        ^^
    start                                                          checksum (0x7F = 127)
"""


def _extract_checksum_parts(sentence: str) -> tuple[str, str] | None:
    """Extract the payload content and provided checksum from an NMEA sentence.

    NMEA sentences follow the format: $<content>*<checksum>
    This function separates these components for validation.

    Args:
        sentence: Raw NMEA sentence string (e.g., "$GNGGA,...*7F")

    Returns:
        A tuple of (content, checksum_hex) if the sentence has valid structure,
        or None if:
        - Missing '$' start delimiter
        - Missing '*' checksum delimiter
        - Checksum is not exactly 2 characters (truncated sentence)

    Example:
        >>> _extract_checksum_parts("$GNGGA,123519*7F")
        ('GNGGA,123519', '7F')
    """
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
    """Calculate the XOR checksum of a content string.

    The NMEA checksum algorithm XORs the ASCII value of each character
    in the content. This is a simple error-detection mechanism that can
    detect single-bit errors and some multi-bit errors.

    Args:
        content: The string between '$' and '*' (exclusive)

    Returns:
        Integer checksum value (0-255)

    Example:
        For content "GNGGA", the calculation is:
        ord('G') ^ ord('N') ^ ord('G') ^ ord('G') ^ ord('A')
        = 71 ^ 78 ^ 71 ^ 71 ^ 65 = ...
    """
    result = 0
    for character in content:
        result ^= ord(character)
    return result


def validate_checksum(sentence: str) -> bool:
    """Validate the checksum of an NMEA sentence.

    Performs end-to-end validation by:
    1. Extracting the content between '$' and '*'
    2. Computing the XOR of all content bytes
    3. Comparing against the provided 2-digit hex checksum

    Args:
        sentence: Complete NMEA sentence including '$', '*', and checksum.
                  May include trailing whitespace/newlines (will be stripped).

    Returns:
        True if the checksum is valid, False if:
        - Sentence is malformed (missing delimiters)
        - Checksum is truncated or non-hexadecimal
        - Calculated checksum doesn't match provided checksum

    Example:
        >>> validate_checksum("$GNGGA,123519.00,...*7F")
        True
        >>> validate_checksum("$GNGGA,123519.00,...*FF")  # wrong checksum
        False
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
