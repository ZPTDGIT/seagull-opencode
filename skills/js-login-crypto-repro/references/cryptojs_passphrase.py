# CryptoJS passphrase 模式 (OpenSSL 兼容) Python 模板
# CryptoJS.AES.encrypt(msg, 'passphrase').toString() 的等价实现
import os, base64, hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


def evp_bytes_to_key(password: bytes, salt: bytes, key_len=32, iv_len=16):
    """OpenSSL EVP_BytesToKey (MD5, 1 轮) — CryptoJS 同款"""
    dt, block = b'', b''
    while len(dt) < key_len + iv_len:
        block = hashlib.md5(block + password + salt).digest()
        dt += block
    return dt[:key_len], dt[key_len:key_len + iv_len]


def encrypt_aes(plaintext: str, passphrase: str) -> str:
    salt = os.urandom(8)
    key, iv = evp_bytes_to_key(passphrase.encode('utf-8'), salt)
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plaintext.encode('utf-8'), 16))
    return base64.b64encode(b'Salted__' + salt + ct).decode('ascii')


def decrypt_aes(ciphertext_b64: str, passphrase: str) -> str:
    raw = base64.b64decode(ciphertext_b64)
    assert raw[:8] == b'Salted__', 'not CryptoJS/OpenSSL format'
    salt, ct = raw[8:16], raw[16:]
    key, iv = evp_bytes_to_key(passphrase.encode('utf-8'), salt)
    return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16).decode('utf-8')
