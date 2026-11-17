

class UnsupportedFileType(ValueError):
    pass


class InvalidFileContent(ValueError):
    pass


class NotFound(LookupError):
    pass


class FilenameConflict(ValueError):
    pass


class RetryNotAllowed(ValueError):
    pass


class StorageUnavailable(RuntimeError):
    pass


class QueueUnavailable(RuntimeError):
    pass