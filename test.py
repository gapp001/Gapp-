import requests
from stellar_sdk.asset import Asset
from stellar_sdk.keypair import Keypair
from stellar_sdk.network import Network
from stellar_sdk.server import Server
from stellar_sdk.transaction_builder import TransactionBuilder

ROOT_ISSUER_SECRET_KEY = 'SAYQOCAD6GLQPSGVWUSEZHXUSBWTMONV6GMIPFIYHVW6IEGCYFQF4OWX'  # root issuer account
ISSUER_SECRET_KEY = 'SCVGEUZ4RSJL5BPTP6CZFYQJTDECUX767HNWWIENZKZFSCCVLHHJ3VHO'
RECEIVER_SECRET_KEY = 'SAZPM5WTIYAS4VJQFUI2QXDMQRUN7KDL73EAZ3BHKOIPIQV2QPM555LO'

TESTNET = 'https://horizon-testnet.stellar.org'

ASSET_CODE = 'gaNGN'
ASSET_ISSUER_PUBLIC_KEY = 'GA5SGFB5CP4SIHSP4QUVCCPBYNSTULVVA7VO3G2YAZ72H6TGIQTSJAM5'

DEFAULT_TIMEOUT = 31536000  # One year in seconds


# @dataclass
# class TransactionEnvelopeDTO:
#     type: str # "ENVELOPE_TYPE_TX"
#     source_account: str # "GD4TTQKE3DCGFZ7LEYUFPUEYXLIEUNGPI3JXI7GENPLF2WGF762MGX3L"
#     fee: int # "100"
#     seq_num: int # "440075234050099"
#     time_bounds_present: bool # "true"
#     time_bounds_min_time: str # "0 (1970-01-01 00:00:00.000000+00:00 (UTC))"
#     time_bounds_max_time: str # "1648218561 (2022-03-25 14:29:21.000000+00:00 (UTC))"
#     memo_type: str # "MEMO_NONE"
#     operations_len: int # "1"
#     operation_source_account_present: bool # "false"
#     operation_body_type: str # "CHANGE_TRUST"

#     operation_body_change_trust_op_line_type: str # "ASSET_TYPE_CREDIT_ALPHANUM12"
#     operation_body_change_trust_op_line: str # "gaNGN:GA5SGFB5CP4SIHSP4QUVCCPBYNSTULVVA7VO3G2YAZ72H6TGIQTSJAM5"
#     operation_body_change_trust_op_limit: str # "9223372036854775807 (922337203685.4775807)"

#     operation_body_payment_op_destination: str # "ASSET_TYPE_CREDIT_ALPHANUM12"
#     operation_body_payment_op_asset: str # "gaNGN:GA5SGFB5CP4SIHSP4QUVCCPBYNSTULVVA7VO3G2YAZ72H6TGIQTSJAM5"
#     operation_body_payment_op_amount: str # "9223372036854775807 (922337203685.4775807)"

#     ext_v: int # "0"
#     signatures_len: int # "1"
#     signature_hint: str # "c5ffb4c3"
#     signature_signature: str # "8a17907101968f0a32a8556ad9e1db87a18b09f8d20cb0fa15e5d0b9494f3a6c27e721f1bc9a1b4439724ff954da80b28ec39936bf459c967633d2ee2e47a408"

#     def __init__(self, **kwargs):
#         self.type = kwargs.get('type')
#         self.source_account = kwargs.get('tx_sourceAccount')
#         self.fee = kwargs.get('tx_fee')
#         self.seq_num = kwargs.get('tx_seqNum')
#         self.time_bounds_present = kwargs.get('tx_timeBounds__present')
#         self.time_bounds_min_time = kwargs.get('tx_timeBounds_minTime')
#         self.time_bounds_max_time = kwargs.get('tx_timeBounds_maxTime')
#         self.memo_type = kwargs.get('tx_memo_type')
#         self.operations_len = kwargs.get('tx_operations_len')
#         self.operation_source_account_present = kwargs.get('tx_operations[0]_sourceAccount__present')
#         self.operation_body_type = kwargs.get('tx_operations[0]_body_type')

#         self.operation_body_change_trust_op_line_type = kwargs.get('tx_operations[0]_body_changeTrustOp_line_type')
#         self.operation_body_change_trust_op_line = kwargs.get('tx_operations[0]_body_changeTrustOp_line')
#         self.operation_body_change_trust_op_limit = kwargs.get('tx_operations[0]_body_changeTrustOp_limit')

#         self.operation_body_payment_op_destination = kwargs.get('tx_operations[0]_body_paymentOp_destination')
#         self.operation_body_payment_op_asset = kwargs.get('tx_operations[0]_body_paymentOp_asset')
#         self.operation_body_payment_op_amount = kwargs.get('tx_operations[0]_body_paymentOp_amount')

#         self.ext_v = kwargs.get('tx_ext_v')
#         self.signatures_len = kwargs.get('signatures_len')
#         self.signature_hint = kwargs.get('signatures[0]_hint')
#         self.signature_signature = kwargs.get('signatures[0]_signature')

#     @staticmethod
#     def get_transaction_envelope_data(transaction_envelope: TransactionEnvelope) -> dict:
#         transaction_envelope = to_txrep(transaction_envelope=transaction_envelope)
#         transaction_envelope_dict = {}
#         for line in transaction_envelope.split('\n'):
#             key, value = line.split(': ')
#             transaction_envelope_dict[key.replace('.', '_')] = value
#         # transaction_envelope_dict = dict(
#         #     map(lambda item: item.split(': '), transaction_envelope.split('\n')))
#         # transaction_envelope_dict = {key.strip().replace('.', '_'): value.strip() for (
#         #     key, value) in transaction_envelope_dict.items()}
#         return transaction_envelope_dict


def generate_keypair() -> Keypair:
    '''Generate random keypairs and funding them with friendbot.'''
    return Keypair.random()


def get_keypair_from_secret(secret_key: str) -> Keypair:
    '''Get or generate random keypairs.'''
    keypair = Keypair.from_secret(secret=secret_key)
    print(f'Public key: {keypair.public_key}')
    print(f'Secret key: {keypair.secret}\n')
    return keypair


def create_root_account() -> Keypair:
    keypair = generate_keypair()
    url = 'https://friendbot.stellar.org'
    _response = requests.get(url, params={'addr': keypair.public_key})
    return keypair


def create_account_operation(issuing_keypair: Keypair) -> Keypair:
    '''Create and fund a new account with the specified starting balance.'''
    server = Server(horizon_url=TESTNET)

    # Fetch the current sequence number for the source account from Horizon.
    issuer = server.load_account(issuing_keypair.public_key)
    receiving_keypair = generate_keypair()
    base_fee = server.fetch_base_fee()

    # Build transaction around create account operation.
    transaction = (
        TransactionBuilder(
            source_account=issuer,
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=base_fee,
        )
        .append_create_account_op(
            destination=receiving_keypair.public_key,
            starting_balance='12.25'
        )
        .set_timeout(DEFAULT_TIMEOUT)
        .add_text_memo(memo_text='')
        .build()
    )

    url = 'http://127.0.0.1:8000/stellar/submit_transaction/'
    transaction_xdr = transaction.to_xdr()
    secret_key = issuing_keypair.secret
    data = {'transaction_xdr': transaction_xdr, 'secret_key': secret_key}

    response = requests.post(url=url, json=data)

    print(f'Public key: {receiving_keypair.public_key}')
    print(f'Secret key: {receiving_keypair.secret}')

    return receiving_keypair


def change_trust_operation(receiving_keypair: Keypair, asset: Asset):
    '''Create a trustline between receiving account and issuing account for asset.'''
    server = Server(horizon_url=TESTNET)

    # Fetch the current sequence number for the source account from Horizon.
    receiver = server.load_account(receiving_keypair.public_key)
    base_fee = server.fetch_base_fee()

    # Build transaction around trustline operation (creating asset).
    transaction = (
        TransactionBuilder(
            source_account=receiver,
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=base_fee,
        )
        .append_change_trust_op(asset=asset)
        .set_timeout(DEFAULT_TIMEOUT)
        .build()
    )

    url = 'http://127.0.0.1:8000/stellar/submit_transaction/'
    transaction_xdr = transaction.to_xdr()
    secret_key = receiving_keypair.secret
    data = {'transaction_xdr': transaction_xdr, 'secret_key': secret_key}
    response = requests.post(url=url, json=data)

    # transaction_hash = response.get('id')
    # tx = server.transactions().transaction(transaction_hash=transaction_hash).call()

    return response


def payment_operation(issuing_keypair: Keypair, receiving_keypair: Keypair, asset: Asset, amount: str):
    '''Send asset from issuing accout to receiving account.'''
    server = Server(horizon_url=TESTNET)

    # Fetch the current sequence number for the source account from Horizon.
    issuer = server.load_account(issuing_keypair.public_key)
    base_fee = server.fetch_base_fee()

    # Build transaction around payment operation (sending asset to distributor).
    transaction = (
        TransactionBuilder(
            source_account=issuer,
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=base_fee,
        )
        .append_payment_op(
            destination=receiving_keypair.public_key,
            asset=asset,
            amount=amount
        )
        .set_timeout(DEFAULT_TIMEOUT)
        .build()
    )

    url = 'http://127.0.0.1:8000/stellar/submit_transaction/'
    transaction_xdr = transaction.to_xdr()
    secret_key = issuing_keypair.secret
    data = {'transaction_xdr': transaction_xdr, 'secret_key': secret_key}

    response = requests.post(url=url, json=data)

    return response


def app():
    print('\nIssuer Keypair')
    if not ISSUER_SECRET_KEY:
        issuer = create_root_account()
    else:
        issuer = get_keypair_from_secret(secret_key=ISSUER_SECRET_KEY)

    print('Receiver Keypair')
    if not RECEIVER_SECRET_KEY:
        receiver = create_account_operation(issuing_keypair=issuer)
    else:
        receiver = get_keypair_from_secret(secret_key=RECEIVER_SECRET_KEY)

    print('Creating asset...')
    asset = Asset(code=ASSET_CODE, issuer=ASSET_ISSUER_PUBLIC_KEY)
    transaction = change_trust_operation(
        receiving_keypair=receiver,
        asset=asset
    )
    print(transaction)

    print('\nSending asset...')
    amount = '150'
    transaction = payment_operation(
        issuing_keypair=issuer,
        receiving_keypair=receiver,
        asset=asset,
        amount=amount
    )
    print(transaction)

    # print('\nSending native asset...')
    # amount = '10'
    # asset = Asset.native()
    # transaction = payment_operation(
    #     issuing_keypair=issuer,
    #     receiving_keypair=receiver,
    #     asset=asset,
    #     amount=amount
    # )
    # print(transaction)


if __name__ == '__main__':
    app()
