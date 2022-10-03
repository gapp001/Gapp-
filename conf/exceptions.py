class BaseException(Exception):
    message: str = ''

    def __init__(self, message: str | None = None, *args: object) -> None:
        self.message = message or self.message
        super().__init__(self.message)




class NoIssuerAccountFound(BaseException):
    """Raised when Issuer Account is not found"""
    message: str = 'Issuer account not found. Please, create an Issuer Account, fund this account and try again'
