import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add bin directory to path to allow importing cca-watchlist
# This is a common pattern for testing scripts that are not installed as packages
bin_path = Path(__file__).parent.parent / "bin"
sys.path.insert(0, str(bin_path))

# The import must happen after the path is modified
# We use a try-finally block to ensure the path is restored
try:
    # We are importing the script as a module.
    # To do this, we need to refer to it by its filename without the .py extension
    import cca_watchlist as watchlist
finally:
    # Remove the path modification to avoid side effects
    sys.path.pop(0)


def test_slugify():
    """Tests the slugify static method."""
    assert watchlist.Watchlist.slugify("Test Name") == "test-name"
    assert watchlist.Watchlist.slugify("Jméno s diakritikou") == "jmeno-s-diakritikou"
    assert watchlist.Watchlist.slugify("  leading & trailing spaces  ") == "leading-trailing-spaces"
    assert watchlist.Watchlist.slugify("Special---Chars!!") == "special-chars"
    assert watchlist.Watchlist.slugify("server1 OOM kills") == "server1-oom-kills"


def test_parse_check_after():
    """Tests the parse_check_after static method."""
    assert watchlist.Watchlist.parse_check_after("2025-10-16 morning") == "2025-10-16T06:00:00"
    assert watchlist.Watchlist.parse_check_after("2025-10-16 afternoon") == "2025-10-16T12:00:00"
    assert watchlist.Watchlist.parse_check_after("2025-10-16") == "2025-10-16T06:00:00"
    assert watchlist.Watchlist.parse_check_after("invalid date") is None
    assert watchlist.Watchlist.parse_check_after(None) is None
    assert watchlist.Watchlist.parse_check_after("") is None


def test_parse_monitor_until():
    """Tests the parse_monitor_until static method."""
    today = datetime.now(timezone.utc).date()

    # Test "1 week"
    one_week_from_today = today + timedelta(days=7)
    expected_ts = f"{one_week_from_today}T00:00:00"
    assert watchlist.Watchlist.parse_monitor_until("1 week") == expected_ts

    # Test "3 days"
    three_days_from_today = today + timedelta(days=3)
    expected_ts_3d = f"{three_days_from_today}T00:00:00"
    assert watchlist.Watchlist.parse_monitor_until("3 days") == expected_ts_3d

    # Test "10 day" (singular)
    ten_days_from_today = today + timedelta(days=10)
    expected_ts_10d = f"{ten_days_from_today}T00:00:00"
    assert watchlist.Watchlist.parse_monitor_until("10 day") == expected_ts_10d

    # Test invalid formats
    assert watchlist.Watchlist.parse_monitor_until("invalid duration") is None
    assert watchlist.Watchlist.parse_monitor_until(None) is None
    assert watchlist.Watchlist.parse_monitor_until("") is None

# To run these tests, you would typically use pytest:
# 1. Make sure you have pytest installed: pip install pytest
# 2. Run pytest from the root of the project: pytest
#
# Note: The import system for the script under test is a bit of a hack.
# In a more mature project, you'd want to structure your code as a proper
# Python package to make imports and testing cleaner.
