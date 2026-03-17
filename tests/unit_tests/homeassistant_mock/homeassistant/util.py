def slugify(value):
    """Convert a string to a slug."""
    return value.lower().replace(" ", "_").replace("-", "_")
