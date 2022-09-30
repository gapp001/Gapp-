from datetime import datetime
from decimal import Decimal
from typing import List
from enum import Enum
from pydantic import BaseModel


class StellarPaymentTransactionSchema(BaseModel):
    id: str
    paging_token: str
    successful: bool
    hash: str
    ledger: int
    created_at: datetime
    source_account: str
    source_account_sequence: str
    fee_account: str
    fee_charged: str
    max_fee: str
    operation_count: int
    envelope_xdr: str
    result_xdr: str
    result_meta_xdr: str
    fee_meta_xdr: str
    memo_type: str
    signatures: List[str]
    valid_after: datetime | None
    valid_before: datetime | None


class DjangoAuthCredentials(BaseModel):
    access_token: str
    refresh_token: str


class GAUserSchema(BaseModel):
    public_id: str
    email: str | None
    last_name: str | None
    first_name: str | None
    phone_number: str | None
    country: str
    stellar_public_key: str | None


class GASubjectDetailsSchema(BaseModel):
    bank_account_number: str | None
    bank_account_name: str | None
    bank_name: str | None


class GASubjectSchema(BaseModel):
    id: int
    user: GAUserSchema | None
    details: GASubjectDetailsSchema | None


class GATransactionDetailingSchema(BaseModel):
    trigger: str | None
    request_id: int | None


class GATransactionSchema(BaseModel):
    id: int
    debit_subject: GASubjectSchema | None
    credit_subject: GASubjectSchema | None
    type_transaction: int
    transaction_status: int
    stellar_status: int
    stellar_transaction_hash: str | None
    is_internal_transfer: bool
    amount_currency: str
    amount: Decimal
    national_currency_amount: Decimal
    created_at: datetime
    detailing: GATransactionDetailingSchema | None
    hash_str: str | None
    kind: int
    related_user: GAUserSchema
    wallet: int | None


class TransactionResultSchema(BaseModel):
    transaction_id: int
    public_key: str
    secret_key: str | None
    stellar_transaction_hash: str | None
    stellar_transaction_status: int | None
    stellar_transaction_detail: str | None


class GAStellarAccountSchema(BaseModel):
    pk: int
    user_id: int
    public_key: str
    status: str
    created_at: str


class StellarAccountStatus(Enum):
    not_created = 'not_created'
    keypair_generated = 'keypair_generated'
    need_trustline = 'need_trustline'
    fulfilled = 'fulfilled'

class GAStellarAccountBoundedSchema(BaseModel):
    pk: int
    status: str

