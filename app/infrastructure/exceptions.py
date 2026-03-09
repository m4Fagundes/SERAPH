"""Domain-specific exceptions for the infrastructure layer."""


class ProjectIOError(IOError):
    """Raised when a project file cannot be read or written.

    Wraps lower-level OSError / json.JSONDecodeError so that callers can
    catch a single, application-level exception type rather than having to
    handle every possible I/O or serialisation error individually.
    """
