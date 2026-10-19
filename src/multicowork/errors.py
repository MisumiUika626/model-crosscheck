"""Errors raised at the model response boundary."""


class FormatError(ValueError):
    """A model response is not one valid protocol object."""
