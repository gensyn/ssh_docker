def generate_entity_id(entity_id_format, name, hass=None, current_ids=None):
    """Generate an entity ID from a format string and name."""
    return entity_id_format.format(name)
