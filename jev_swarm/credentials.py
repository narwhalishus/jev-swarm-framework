"""Resolve only the explicitly named Bedrock credential, without logging it."""
import os
import platform
import subprocess

def bedrock_token(supplied: str | None = None, keychain_service: str = 'bedrock-token-acct-a') -> str:
    token = supplied or os.environ.get('AWS_BEARER_TOKEN_BEDROCK', '')
    if token:
        return token.strip()
    if platform.system() != 'Darwin':
        raise ValueError('macOS Keychain is not available in this runtime. Run on your Mac to use '+
                         keychain_service+', or set AWS_BEARER_TOKEN_BEDROCK here.')
    if not keychain_service or keychain_service.startswith('-'):
        raise ValueError('Provide an exact Keychain service name')
    try:
        result = subprocess.run(['/usr/bin/security','find-generic-password','-s',keychain_service,'-w'],
                                capture_output=True,text=True,timeout=20,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise ValueError('Could not read the specified Keychain item. Unlock Keychain or set AWS_BEARER_TOKEN_BEDROCK.') from None
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError('Keychain item '+keychain_service+' was not found or access was denied. No other items were searched.')
    return result.stdout.strip()
