"""Constants for the Mediola Shutters integration."""

DOMAIN = "mediola_shutters"

# Device type identifiers in Mediola
DEVICE_TYPE_WR = "WR"  # WIR shutters
DEVICE_TYPE_ER = "ER"  # Elero shutters
DEVICE_TYPE_RT = "RT"  # Somfy RTS shutters

# Manufacturer names
MANUFACTURER_WIR = "WIR"
MANUFACTURER_ELERO = "Elero"
MANUFACTURER_SOMFY = "Somfy"
MANUFACTURER_UNKNOWN = "Unknown"

# Configuration keys
CONF_SCAN_INTERVAL = "scan_interval"

# Default scan interval in seconds
DEFAULT_SCAN_INTERVAL = 15

# Elero state codes
ELERO_STATE_OPEN = "2001"  # Fully open - was "1001"
ELERO_STATE_CLOSED = "2002"  # Fully closed - was "1002"
ELERO_STATE_INTERMEDIATE = "200D"  # Somewhere in between - was "100D"
ELERO_STATE_MOVING_UP = "200A"  # Moving upwards - was "100A"
ELERO_STATE_MOVING_DOWN = "200B"  # Moving downwards - was "100B"

# Elero commands
ELERO_CMD_UP = "01"  # Open/Up
ELERO_CMD_DOWN = "00"  # Close/Down
ELERO_CMD_STOP = "02"  # Stop

# Somfy RT commands (prefix before the device id)
RT_CMD_UP = "20"    # Open/Up
RT_CMD_DOWN = "40"  # Close/Down
RT_CMD_STOP = "10"  # Stop
