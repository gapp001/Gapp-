class AppBaseException(Exception):
    message: str = ''

    def __init__(self, message: str | None = None, *args: object) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class NoIssuerAccountFound(AppBaseException):
    """Raised when Issuer Account is not found"""
    message: str = 'Issuer account not found. Please, create an Issuer Account, fund this account and try again'

class NoRecipientAccountFound(AppBaseException):
    """Raised when Recipient Account is not found"""
    message: str = 'Recipient account not found. Please, create an Recipient Account, fund this account and try again'


class Base64DecodeError(AppBaseException):
    """Raised when raiser binascii.Error"""
    message: str = 'Incorrect base64 encoded string'
