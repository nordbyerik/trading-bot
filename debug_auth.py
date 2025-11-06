#!/usr/bin/env python3
"""
Debug script to test signature generation
"""

import base64
import os
import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend


def test_signature_generation():
    """Test the signature generation process."""

    print("=" * 60)
    print("Signature Generation Debug")
    print("=" * 60)

    # Get credentials from environment
    api_key_id = os.environ.get('KALSHI_API_KEY_ID')
    private_key_b64 = os.environ.get('KALSHI_PRIV_KEY')

    if not api_key_id or not private_key_b64:
        print("Error: Missing environment variables")
        return

    print(f"\nAPI Key ID: {api_key_id[:10]}...{api_key_id[-10:]}")
    print(f"Private key (base64 length): {len(private_key_b64)}")

    # Decode the private key
    try:
        private_key_pem = base64.b64decode(private_key_b64).decode('utf-8')
        print(f"\nDecoded PEM length: {len(private_key_pem)}")
        print(f"PEM header: {private_key_pem[:30]}")

        # Load as private key
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
        print("✓ Private key loaded successfully")

    except Exception as e:
        print(f"✗ Failed to load private key: {e}")
        return

    # Test signature with balance endpoint
    timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
    method = "GET"
    path = "/trade-api/v2/portfolio/balance"

    print(f"\nTest parameters:")
    print(f"  Timestamp: {timestamp}")
    print(f"  Method: {method}")
    print(f"  Path: {path}")

    # Create message to sign
    message = f"{timestamp}{method}{path}".encode('utf-8')
    print(f"\nMessage to sign: {message.decode('utf-8')}")
    print(f"Message bytes: {message}")
    print(f"Message length: {len(message)}")

    # Sign the message
    try:
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        print(f"\n✓ Signature generated")
        print(f"Signature bytes length: {len(signature)}")

        # Base64 encode
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        print(f"Signature (base64): {signature_b64[:50]}...")
        print(f"Signature (base64) length: {len(signature_b64)}")

        print("\nHeaders that would be sent:")
        print(f"  KALSHI-ACCESS-KEY: {api_key_id}")
        print(f"  KALSHI-ACCESS-SIGNATURE: {signature_b64[:50]}...")
        print(f"  KALSHI-ACCESS-TIMESTAMP: {timestamp}")

    except Exception as e:
        print(f"✗ Failed to sign: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_signature_generation()
