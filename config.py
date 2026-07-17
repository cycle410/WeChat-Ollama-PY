import json
import os
import hashlib
import base64
import socket
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from pathlib import Path

# 配置目录（项目本地 .config）
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / ".config"
CONFIG_FILE = DATA_DIR / "config.json"
TOKEN_FILE = DATA_DIR / "token.json"

def ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except:
        pass

def load_config():
    ensure_dir()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(config):
    ensure_dir()
    safe = {k: v for k, v in config.items() if k != 'apiKey'}
    if 'apiKey' in config:
        safe['_encKey'] = _encrypt(config['apiKey'])
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(safe, f, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except:
        pass

def load_config_with_key():
    cfg = load_config()
    if '_encKey' in cfg:
        cfg['apiKey'] = _decrypt(cfg['_encKey'])
        del cfg['_encKey']
    return cfg

def load_token():
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_token(token):
    ensure_dir()
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token, f, indent=2)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except:
        pass

# 跨平台机器 ID（使用主机名 + 用户目录 + 用户名）
def _get_machine_id():
    hostname = socket.gethostname()
    homedir = os.path.expanduser('~')
    try:
        username = os.getlogin()
    except:
        username = os.environ.get('USERNAME', 'unknown')
    return hashlib.sha256((hostname + homedir + username).encode()).digest()[:32]

_MACHINE_ID = _get_machine_id()

def _encrypt(plaintext):
    from cryptography.hazmat.primitives import padding
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(_MACHINE_ID), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode()) + padder.finalize()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(iv + encrypted).decode()

def _decrypt(encoded):
    from cryptography.hazmat.primitives import padding
    raw = base64.b64decode(encoded)
    iv, ciphertext = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(_MACHINE_ID), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return plaintext.decode()

def mask_key(key):
    if not key or len(key) < 8:
        return '***'
    return key[:6] + '...' + key[-3:]