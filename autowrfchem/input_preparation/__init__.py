

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
