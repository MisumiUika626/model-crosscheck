"""Errors raised at the model response boundary."""


class FormatError(ValueError):
    """A model response is not one valid protocol object."""


class RunConflictError(FileExistsError):
    """A run evidence path already exists and cannot be overwritten."""


class RunNotFoundError(FileNotFoundError):
    """The requested run directory does not exist."""
