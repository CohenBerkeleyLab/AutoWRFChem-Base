

class PrepInputError(Exception):
    """
    Superclass for any input preparation errors
    """
    pass


class MetFilesMissingError(PrepInputError):
    """
    Error if met files needed not found
    """
    pass


class RealExeFailedError(PrepInputError):
    """
    Error if a call to real.exe failed during one of the component preparation functions
    """
    pass
