#!/usr/bin/env python3
"""Stages encrypted Cloudflare secrets on the Raspberry Pi so GKE Primary (acr-eu) can import them with zero copy/paste.

Usage on the Raspberry Pi:
    1. Put your Cloudflare Worker secrets in ~/acr-standby/cloudflare.env (chmod 600), e.g.:
           ADMIN_KEY=...
           STEAM_API_KEY=...
           DISCORD_WEBHOOK_URL=...
           DISCORD_CUPS_WEBHOOK_URL=...
           DISCORD_BOT_TOKEN=...
           TWITCH_CLIENT_SECRET=...
           ANTHROPIC_API_KEY=...
           AZURE_SPEECH_KEY=...
           REPORTS_KEY=...
    2. Stage encrypted bundle:
           python3 tools/stage_secrets_on_pi.py ~/acr-standby/cloudflare.env

Security model (standard library only, Python 3.9+):
- Reads the 256-bit key in ~/acr-standby/standby.key (already paired privately with acr-eu; never leaves Pi/acr-eu).
- Derives distinct encryption and MAC subkeys via PBKDF2-HMAC-SHA256 (100,000 iterations + random 16-byte salt).
- Encrypts the key/value JSON payload and appends an Encrypt-then-MAC HMAC-SHA256 authentication tag.
- Writes ~/acr-standby/data/traces/traces/888888000000001.json.gz, which standby_receiver.py only serves to callers
  presenting a valid HMAC-SHA256 request signature with standby.key.
"""
import argparse
import gzip
import hashlib
import hmac
import json
import os
import re
import sys

SECRET_TRACE_ID = '888888000000001'
ALLOWED_KEYS = {
    'ADMIN_KEY',
    'STEAM_API_KEY',
    'DISCORD_WEBHOOK_URL',
    'DISCORD_CUPS_WEBHOOK_URL',
    'DISCORD_BOT_TOKEN',
    'DISCORD_PUBLIC_KEY',
    'TWITCH_CLIENT_SECRET',
    'ANTHROPIC_API_KEY',
    'AZURE_SPEECH_KEY',
    'REPORTS_KEY',
}


def _keystream(enc_key, nonce, length):
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(enc_key, nonce + counter.to_bytes(8, 'big'), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_bundle(standby_key_bytes, secrets_dict):
    if len(standby_key_bytes) != 32:
        raise ValueError('standby_key_bytes must be 32 bytes')
    salt = os.urandom(16)
    nonce = os.urandom(16)
    derived = hashlib.pbkdf2_hmac('sha256', standby_key_bytes, b'acr-secrets-v1|' + salt, 100_000, dklen=64)
    enc_key, mac_key = derived[:32], derived[32:]
    plaintext = json.dumps(secrets_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
    stream = _keystream(enc_key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    mac = hmac.new(mac_key, b'v1|' + salt + b'|' + nonce + b'|' + ciphertext, hashlib.sha256).hexdigest()
    return {
        'v': 1,
        'salt': salt.hex(),
        'nonce': nonce.hex(),
        'ct': ciphertext.hex(),
        'mac': mac,
    }


def decrypt_bundle(standby_key_bytes, envelope):
    if len(standby_key_bytes) != 32:
        raise ValueError('standby_key_bytes must be 32 bytes')
    if not isinstance(envelope, dict) or envelope.get('v') != 1:
        raise ValueError('unsupported secret envelope version')
    salt = bytes.fromhex(envelope['salt'])
    nonce = bytes.fromhex(envelope['nonce'])
    ciphertext = bytes.fromhex(envelope['ct'])
    derived = hashlib.pbkdf2_hmac('sha256', standby_key_bytes, b'acr-secrets-v1|' + salt, 100_000, dklen=64)
    enc_key, mac_key = derived[:32], derived[32:]
    want_mac = hmac.new(mac_key, b'v1|' + salt + b'|' + nonce + b'|' + ciphertext, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want_mac, str(envelope.get('mac') or '')):
        raise ValueError('secret envelope MAC verification failed')
    stream = _keystream(enc_key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream))
    data = json.loads(plaintext.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('decrypted payload is not a dict')
    return data


def parse_env_file(path):
    secrets_map = {}
    with open(path, 'r', encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[len('export '):].strip()
            if '=' not in line:
                raise SystemExit('Invalid line %d in %s (expected KEY=VALUE)' % (lineno, path))
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                v = v[1:-1]
            if not re.match(r'^[A-Z0-9_]+$', k):
                raise SystemExit('Invalid key name %r on line %d' % (k, lineno))
            if k not in ALLOWED_KEYS:
                print('Warning: skipping unrecognized key %s (allowed: %s)' % (k, ', '.join(sorted(ALLOWED_KEYS))))
                continue
            if v:
                secrets_map[k] = v
    return secrets_map


def main():
    ap = argparse.ArgumentParser(description='Encrypt & stage Cloudflare secrets on the Raspberry Pi for acr-eu.')
    ap.add_argument('env_file', nargs='?', help='Path to .env file containing KEY=VALUE secrets')
    ap.add_argument('--standby-dir', default=os.path.expanduser('~/acr-standby'),
                    help='Raspberry Pi standby directory containing standby.key and data/ (default: ~/acr-standby)')
    ap.add_argument('--decrypt-file', help='Decrypt and print JSON from a downloaded .json.gz envelope (used on admin side)')
    ap.add_argument('--cleanup', action='store_true', help='Remove staged encrypted envelope from Pi after import')
    args = ap.parse_args()

    standby_dir = os.path.abspath(os.path.expanduser(args.standby_dir))
    traces_dir = os.path.join(standby_dir, 'data', 'traces', 'traces')
    staged_path = os.path.join(traces_dir, '%s.json.gz' % SECRET_TRACE_ID)

    if args.cleanup:
        if os.path.exists(staged_path):
            os.remove(staged_path)
            print('Removed staged secret bundle %s' % staged_path)
        else:
            print('No staged secret bundle present at %s' % staged_path)
        return

    if args.decrypt_file:
        key_hex = os.environ.get('STANDBY_KEY', '').strip()
        if not key_hex:
            key_path = os.path.join(standby_dir, 'standby.key')
            with open(key_path, 'r', encoding='utf-8') as kf:
                key_hex = kf.read().strip()
        with gzip.open(args.decrypt_file, 'rt', encoding='utf-8') as gf:
            env = json.load(gf)
        out = decrypt_bundle(bytes.fromhex(key_hex), env)
        sys.stdout.write(json.dumps(out))
        return

    if not args.env_file:
        ap.error('Provide path to your secrets .env file (e.g. ~/acr-standby/cloudflare.env)')

    key_path = os.path.join(standby_dir, 'standby.key')
    if not os.path.exists(key_path):
        raise SystemExit('Missing %s — run bash live/install_pi_listener.sh first.' % key_path)
    with open(key_path, 'r', encoding='utf-8') as kf:
        standby_key = bytes.fromhex(kf.read().strip())

    secrets_map = parse_env_file(os.path.expanduser(args.env_file))
    if not secrets_map:
        raise SystemExit('No non-empty allowed keys found in %s' % args.env_file)

    envelope = encrypt_bundle(standby_key, secrets_map)
    os.makedirs(traces_dir, exist_ok=True)
    tmp_path = staged_path + '.tmp.%d' % os.getpid()
    with gzip.open(tmp_path, 'wt', encoding='utf-8') as gf:
        json.dump(envelope, gf, separators=(',', ':'))
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, staged_path)
    print('Staged %d encrypted secret(s) (%s) -> %s' % (
        len(secrets_map), ', '.join(sorted(secrets_map.keys())), staged_path,
    ))
    print('Let the GKE admin know so acr-eu imports them, then run: python3 tools/stage_secrets_on_pi.py --cleanup')


if __name__ == '__main__':
    main()
