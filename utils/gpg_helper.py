
import binascii
from typing import List, Optional
from gnupg import GPG, GenKey, ImportResult, Crypt
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
    def encrypt_data(data: str, fingerprints: list[str]) -> Crypt:
        """Method for encrypting data by public_keys in `fingerprints`"""
        return gpg.encrypt(data, recipients=fingerprints, passphrase=None, sign=False)

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
    def entrust_key(fingerprints: list[str]):
        """Methon for adding key to trusted with option `TRUST_ULTIMATE`"""
        gpg.trust_keys(fingerprints=fingerprints,
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
        ROOT_KEY_PASSPHRASE: str = settings.GPG_ROOT_KEY_PASSPHRASE
        GPG_ROOT_B64_PUB_KEY: str = settings.GPG_ROOT_B64_PUB_KEY
        GPG_ROOT_B64_PRIV_KEY: str = settings.GPG_ROOT_B64_PRIV_KEY

        @staticmethod
        def generate_root_key() -> GenKey:
            """Method for generating Root GPG keypair"""
            input_data = gpg.gen_key_input(
                key_type='RSA', key_length=2048, passphrase=__class__.ROOT_KEY_PASSPHRASE)
            return gpg.gen_key(input_data)

        @classmethod
        def generate_root_keypair(cls):
            """Method for generating root keypair and exporting them to filesystem"""
            root_key = cls.generate_root_key()
            exported_public_key: bytes = GPGHelper.export_key(
                keyids=root_key.fingerprint,
                can_encode_to_base64=False,
            )
            exported_private_key: bytes = GPGHelper.export_key(
                keyids=root_key.fingerprint,
                is_private_key=True,
                passphrase=__class__.ROOT_KEY_PASSPHRASE,
                can_encode_to_base64=False,
            )

            def _save_key(filename: str, data: bytes):
                with open(filename, 'wb') as file:
                    file.write(data)

            _save_key('public.pem', data=exported_public_key)
            _save_key('private.key', data=exported_private_key)

        @staticmethod
        def import_root_key_from_filesystem(path: str | None = None, is_private_key: bool = False) -> ImportResult:
            """Method for importing root key from filesystem"""
            with open(path, 'rb') as file:
                return GPGHelper.import_key(
                    key_data=file.read(),
                    passphrase=__class__.ROOT_KEY_PASSPHRASE if is_private_key else None
                )

        @staticmethod
        def import_key_from_env(is_private_key: bool = False) -> ImportResult:
            """
                Method for importing Root key from .env file
                If `is_private_key` is False, returns public_key, else returns private_key
            """
            return GPGHelper.import_key(
                key_data=__class__.GPG_ROOT_B64_PRIV_KEY if is_private_key else __class__.GPG_ROOT_B64_PRIV_KEY,
                passphrase=__class__.ROOT_KEY_PASSPHRASE if is_private_key else None,
                is_base64_encoded_key=True,
            )
        
        @staticmethod
        def decrypt_message(message: bytes, is_base64_encoded: bool = True) -> Crypt:
            if is_base64_encoded:
                message: bool = GPGHelper.b64decode_data(value=message)
            result: Crypt = GPGHelper.decrypt_data(message.decode(), passphrase=__class__.ROOT_KEY_PASSPHRASE)
            if not result.ok:
                raise DecryptionError(result.status)
            return result
            
    root_key_helper = _RootKeyGPGHelper()


class DecryptionError(Exception):...