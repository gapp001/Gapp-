from abc import ABC
from dataclasses import dataclass
from decimal import Decimal
import sys

from typing import Any, Dict, List, Literal

@dataclass
class ArgsDTO(ABC):
    """Abstract ArgsDTO class"""

@dataclass
class CreatePaymanetArgsDTO(ArgsDTO):
    public_key: str
    amount: Decimal
    currency: Literal['NGN', 'USD']

    def __post_init__ (self):
        if isinstance(self.amount, str):
            self.amount = Decimal(self.amount)
    

def get_command_name(args: List[str]) -> str:
    """Returns command name from list args"""
    try:
        return args[1]
    except IndexError:
        raise ValueError('Command not provided')

def parse_args_by_command_name(command_name: str, args: List[str]) -> ArgsDTO:
    """Returns ArgsDTO by command name"""
    if command_name == 'send_assets':
        kwargs: Dict[str, str] = dict((arg.split('=', maxsplit=1) for arg in args))

        return CreatePaymanetArgsDTO(**kwargs)
    raise ValueError('Got unexpected command name')

def process_command(command_name: str, args_dto: ArgsDTO):
    """Function for proccessing command"""
    if command_name == 'send_assets':
        args_dto: CreatePaymanetArgsDTO = args_dto 
        from application.services.stellar_payment_operation_service import StellarPaymentOperationService
        return StellarPaymentOperationService.accural_funds_to_stellar_account(
            recipient_public_key=args_dto.public_key,
            amount=args_dto.amount,
            currency=args_dto.currency,
        )

if __name__ == "__main__":
    args: List[str] = sys.argv
    command_name: str = get_command_name(args=args)
    args_dto: ArgsDTO = parse_args_by_command_name(command_name=command_name, args=args[2:])
    try:
        result: Any = process_command(command_name=command_name, args_dto=args_dto)
        print(result)
    except Exception as e:
        print(e.__class__, e.args)

    