"""Which `NOTIFICATIONS_MODE` values actually send. Imported by the sender and by the doctor
consent rules, so both read one definition (and neither imports the other)."""

SENDING_MODES = frozenset({"allowlist", "live"})
