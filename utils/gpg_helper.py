
import binascii
from typing import List, Optional
from gnupg import GPG, GenKey, ImportResult, Crypt, TrustResult
from base64 import b64encode, b64decode
from conf.exceptions import Base64DecodeError
from conf.settings import settings


gpg = GPG()
gpg.encoding = 'utf-8'


class GPGHelper:
    """Class helper for gnupg library"""
    TRUST_ULTIMATE: str = 'TRUST_ULTIMATE'
    ENCRYPTION_OK_STATUS: str = 'encryption ok'

    @staticmethod
    def encrypt_data(data: str, fingerprints: list[str], passphrase: str | None = None) -> Crypt:
        """Method for encrypting data by public_keys in `fingerprints`"""
        return gpg.encrypt(data, recipients=fingerprints, passphrase=passphrase, sign=False)

    @staticmethod
    def decrypt_data(data: str, passphrase: str | None = None):
        """Method for decrypting data"""
        return gpg.decrypt(data, passphrase=passphrase)

    @staticmethod
    def generate_key() -> GenKey:
        """Method for generating GPG keypair"""
        input_data = gpg.gen_key_input(
            key_type='RSA', key_length=2048, no_protection=True)
        return gpg.gen_key(input_data)

    @staticmethod
    def export_key(keyids: str | List[str], is_private_key: bool = False, passphrase: str = None, can_encode_to_base64=True) -> bytes:
        """Method for exporting key to byte string"""
        _key = gpg.export_keys(
            keyids=keyids, secret=is_private_key, passphrase=passphrase).encode()
        return __class__.b64encode_data(_key) if can_encode_to_base64 else _key

    @staticmethod
    def import_key(key_data: bytes | str, passphrase: str | None = None, is_base64_encoded_key: bool = False) -> ImportResult:
        """Method for importGPGing key from byte string"""
        if isinstance(key_data, str):
            key_data = key_data.encode()

        if is_base64_encoded_key:
            try:
                key_data: bytes = __class__.b64decode_data(key_data)
            except binascii.Error:
                raise Base64DecodeError
        return gpg.import_keys(key_data=key_data, passphrase=passphrase)

    @staticmethod
    def entrust_key(fingerprints: list[str]) -> TrustResult:
        """Methon for adding key to trusted with option `TRUST_ULTIMATE`"""
        return gpg.trust_keys(fingerprints=fingerprints,
                                             trustlevel=__class__.TRUST_ULTIMATE)

    @staticmethod
    def b64encode_data(value: bytes) -> bytes:
        """Method for encoding value to base64"""
        return b64encode(value)

    @staticmethod
    def b64decode_data(value: bytes) -> bytes:
        """Method for decoding value from base64"""
        return b64decode(value)

    class _RootKeyGPGHelper:
        """Class helper for operations with Root GPG keys"""
        GPG_ROOT_B64_PRIV_KEY: str = settings.GPG_ROOT_B64_PRIV_KEY

        @staticmethod
        def generate_root_key(passphrase: str | None = None) -> GenKey:
            """Method for generating Root GPG keypair"""
            input_data = gpg.gen_key_input(
                key_type='RSA', key_length=2048, passphrase=passphrase or settings.GPG_ROOT_KEY_PASSPHRASE)
            return gpg.gen_key(input_data)

        @classmethod
        def generate_root_keypair(cls, key_name_prefix: str = '', passphrase: str | None = None):
            """Method for generating root keypair and exporting them to filesystem"""
            root_key = cls.generate_root_key(passphrase=passphrase)
            exported_public_key: bytes = GPGHelper.export_key(
                keyids=root_key.fingerprint,
                can_encode_to_base64=False,
            )
            exported_private_key: bytes = GPGHelper.export_key(
                keyids=root_key.fingerprint,
                is_private_key=True,
                passphrase=passphrase or settings.GPG_ROOT_KEY_PASSPHRASE,
                can_encode_to_base64=False,
            )

            def _save_key(filename: str, data: bytes):
                with open(filename, 'wb') as file:
                    file.write(data)

            _save_key(
                f'{key_name_prefix + "_" if key_name_prefix else ""}public.pem', data=exported_public_key)
            _save_key(
                f'{key_name_prefix + "_" if key_name_prefix else ""}private.key', data=exported_private_key)

        @staticmethod
        def import_root_key_from_filesystem(path: str | None = None, is_private_key: bool = False, passphrase: str | None = None) -> ImportResult:
            """Method for importing root key from filesystem"""
            with open(path, 'rb') as file:
                return GPGHelper.import_key(
                    key_data=file.read(),
                    passphrase=(
                        passphrase or settings.GPG_ROOT_KEY_PASSPHRASE) if is_private_key else None
                )

        @staticmethod
        def import_key_from_env(is_private_key: bool = False) -> ImportResult:
            """
                Method for importing Root key from .env file
                If `is_private_key` is False, returns public_key, else returns private_key
            """
            key: ImportResult = GPGHelper.import_key(
                key_data=settings.GPG_ROOT_B64_PRIV_KEY if is_private_key else settings.GPG_ROOT_B64_PUB_KEY,
                passphrase=settings.GPG_ROOT_KEY_PASSPHRASE if is_private_key else None,
                is_base64_encoded_key=True,
            )
            GPGHelper.entrust_key(fingerprints=key.fingerprints)
            return key

        @staticmethod
        def decrypt_message(message: bytes, is_base64_encoded: bool = True) -> Crypt:
            if is_base64_encoded:
                message: bool = GPGHelper.b64decode_data(value=message)
            __class__.import_key_from_env(is_private_key=True)
            print(f'{settings.GPG_ROOT_KEY_PASSPHRASE=}')
            result: Crypt = GPGHelper.decrypt_data(
                data=message.decode(), passphrase=settings.GPG_ROOT_KEY_PASSPHRASE)
            # print(f'{result.__dict__=}')
            if not result.ok:
                raise DecryptionError(result.status)
            return result

    root_key_helper = _RootKeyGPGHelper()


class DecryptionError(Exception):
    ...


"""
b'-----BEGIN PGP MESSAGE-----\r\n\r\nhQEMA6GwKohFMdasAQgAik1868oOVVcqhH9Jmn8n91BL06j1liexwiJcP1RJZVD0\r\nLdCah7GsgihgHNhb353iK1PTpKPf2sBjDe70/RIjfuaiE04DCSEEgANNsjq4gNLm\r\nbWnz3ELerPuOwQaQvQgX40YPS98WK3VrTN/QvcdLVNEr3fnXt7vbU8WkTe6hQyZq\r\n2SgViVvNnxTbPANLP14+0Bw594jaRjwidtmmpu3cLNTUOjsN+oxtfhToziEwtkyB\r\n56Y38pQSySVhY5pUa2jyHxpbDhwc0kl9H0SFWhmTu4pr6qNfr8vfUjEW9rIVFJEt\r\nylio+o+KtN/IT22NzTaF9T6/aVoocTEuiJjKhbOTIdR9AQkCECpQubTiEC1dpv6A\r\nUHte8Ah6sr4FBuWN3r/+ZLeNGCpSzjjGn09IvzP8fsf7TvQ/RSUNxwQyMYwziAhd\r\nasywzKqT7re872UFPOmailXtWDqLnbP7xSCWXnsnsFvHPXS8IgFruSJ8p8SZoMBN\r\nxdgOf72FA9kLv6AYktg=\r\n=2DQY\r\n-----END PGP MESSAGE-----\r\n'
"""
