from dataclasses import dataclass, fields
from enum import Enum


@dataclass
class TransactionType:
    INCOMING_TRANSACTION: int = 1
    OUTGOING_TRANSACTION: int = 2

    def __init__(self):
        self.CHOICES = [(field.default, field.name) for field in fields(TransactionType)]

    def get_choice_label_by_value(self, value: int) -> str:
        for choice in self.CHOICES:
            if value in choice:
                return choice[1]
            continue


@dataclass
class TransactionKind:
    GENESIS: int = 1
    POS_MERCHANT: int = 2
    OUTGOING_DONATE: int = 3
    INCOMING_DONATE: int = 4
    WITHDRAWAL: int = 5
    OUTGOING_VOTING_DONATE: int = 6

    def __init__(self):
        self.CHOICES = [(field.default, field.name) for field in fields(TransactionKind)]

    def get_choice_label_by_value(self, value: int) -> str:
        for choice in self.CHOICES:
            if value in choice:
                return choice[1]
            continue


@dataclass
class TransactionStatus:
    REJECTED: int = 1
    IN_PROCESSING: int = 2
    COMPLETED: int = 3

    def __init__(self):
        self.CHOICES = [(field.default, field.name) for field in fields(TransactionStatus)]

    def get_choice_label_by_value(self, value: int) -> str:
        for choice in self.CHOICES:
            if value in choice:
                return choice[1]
            continue

@dataclass
class StellarTransactionStatus:
    CONFIRMED: int = 1
    UNCONFIRMED: int = 2

    def __init__(self):
        self.CHOICES = [(field.default, field.name) for field in fields(StellarTransactionStatus)]

    def get_choice_label_by_value(self, value: int) -> str:
        for choice in self.CHOICES:
            if value in choice:
                return choice[1]
            continue

class StellarAccountStatus(Enum):
    not_created = 'not_created'
    keypair_generated = 'keypair_generated'
    need_trustline = 'need_trustline'
    fulfilled = 'fulfilled'