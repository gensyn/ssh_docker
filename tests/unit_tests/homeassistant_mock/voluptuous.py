class _Marker:
    def __init__(self, key, *args, **kwargs):
        self._key = key

    def __hash__(self):
        return hash(self._key)

    def __eq__(self, other):
        return self._key == (other._key if isinstance(other, _Marker) else other)


class Required(_Marker):
    """Mark a schema key as required."""


class Optional(_Marker):
    """Mark a schema key as optional."""


class Schema:
    """Mock voluptuous Schema."""

    def __init__(self, schema=None):
        """Initialize the schema."""

    def __call__(self, data):
        """Validate data - pass through in mock."""
        return data


def All(*args):
    """Mock All validator - returns last argument."""
    return args[-1] if args else {}
