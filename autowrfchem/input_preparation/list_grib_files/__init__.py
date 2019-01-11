from .. import PrepInputError


class MixedTarredUntarredFilesError(PrepInputError):
    """
    Error to use if cannot tell whether met files need untarred or not
    """
    pass