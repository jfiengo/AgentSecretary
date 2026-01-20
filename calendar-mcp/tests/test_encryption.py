"""
Tests for encryption utilities.

This module tests the token encryption/decryption functions including:
- Roundtrip encryption and decryption
- Different token lengths and special characters
- Verification that encrypted output differs from input
"""

import pytest

from app.utils.encryption import decrypt_token, encrypt_token, get_fernet


class TestGetFernet:
    """Tests for get_fernet function."""

    def test_get_fernet_returns_fernet_instance(self):
        """
        Verify that get_fernet returns a valid Fernet instance.
        
        Expected behavior:
        - Returns a Fernet object that can encrypt/decrypt
        """
        fernet = get_fernet()
        
        # Should be able to encrypt and decrypt
        test_data = b"test data"
        encrypted = fernet.encrypt(test_data)
        decrypted = fernet.decrypt(encrypted)
        
        assert decrypted == test_data

    def test_get_fernet_consistent_key(self):
        """
        Verify that get_fernet returns consistent encryption key.
        
        Expected behavior:
        - Multiple calls return Fernet instances with the same key
        - Data encrypted by one can be decrypted by another
        """
        fernet1 = get_fernet()
        fernet2 = get_fernet()
        
        test_data = b"consistent key test"
        encrypted = fernet1.encrypt(test_data)
        decrypted = fernet2.decrypt(encrypted)
        
        assert decrypted == test_data


class TestEncryptToken:
    """Tests for encrypt_token function."""

    def test_encrypt_token_basic(self):
        """
        Verify that encrypt_token encrypts a string.
        
        Expected behavior:
        - Returns a non-empty string
        - Encrypted output differs from input
        """
        token = "my-secret-token"
        
        encrypted = encrypt_token(token)
        
        assert encrypted is not None
        assert len(encrypted) > 0
        assert encrypted != token

    def test_encrypt_token_empty_string(self):
        """
        Verify that empty string can be encrypted.
        
        Expected behavior:
        - Returns a non-empty encrypted string
        """
        encrypted = encrypt_token("")
        
        assert encrypted is not None
        assert len(encrypted) > 0

    def test_encrypt_token_long_string(self):
        """
        Verify that long tokens can be encrypted.
        
        Expected behavior:
        - Long tokens are encrypted successfully
        """
        long_token = "a" * 10000
        
        encrypted = encrypt_token(long_token)
        
        assert encrypted is not None
        assert len(encrypted) > 0

    def test_encrypt_token_special_characters(self):
        """
        Verify that tokens with special characters can be encrypted.
        
        Expected behavior:
        - Tokens with unicode, symbols, etc. are encrypted
        """
        special_token = "token-with-special-chars!@#$%^&*()_+-=[]{}|;':\",./<>?~`"
        
        encrypted = encrypt_token(special_token)
        
        assert encrypted is not None
        assert encrypted != special_token

    def test_encrypt_token_unicode(self):
        """
        Verify that unicode tokens can be encrypted.
        
        Expected behavior:
        - Unicode characters are preserved through encryption
        """
        unicode_token = "token-with-unicode-\u00e9\u00e8\u00ea-\u4e2d\u6587"
        
        encrypted = encrypt_token(unicode_token)
        
        assert encrypted is not None
        assert encrypted != unicode_token

    def test_encrypt_token_different_outputs(self):
        """
        Verify that encrypting the same token twice produces different outputs.
        
        Expected behavior:
        - Fernet uses random IV, so outputs should differ
        """
        token = "same-token"
        
        encrypted1 = encrypt_token(token)
        encrypted2 = encrypt_token(token)
        
        # Due to random IV, encrypted outputs should be different
        assert encrypted1 != encrypted2


class TestDecryptToken:
    """Tests for decrypt_token function."""

    def test_decrypt_token_basic(self):
        """
        Verify that decrypt_token decrypts an encrypted string.
        
        Expected behavior:
        - Returns the original plaintext
        """
        original = "my-secret-token"
        encrypted = encrypt_token(original)
        
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == original

    def test_decrypt_token_empty_string(self):
        """
        Verify that empty string roundtrips correctly.
        
        Expected behavior:
        - Empty string is preserved through encrypt/decrypt
        """
        original = ""
        encrypted = encrypt_token(original)
        
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == original

    def test_decrypt_token_long_string(self):
        """
        Verify that long tokens roundtrip correctly.
        
        Expected behavior:
        - Long tokens are preserved through encrypt/decrypt
        """
        original = "a" * 10000
        encrypted = encrypt_token(original)
        
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == original

    def test_decrypt_token_special_characters(self):
        """
        Verify that special characters roundtrip correctly.
        
        Expected behavior:
        - Special characters are preserved through encrypt/decrypt
        """
        original = "token-with-special-chars!@#$%^&*()_+-=[]{}|;':\",./<>?~`"
        encrypted = encrypt_token(original)
        
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == original

    def test_decrypt_token_unicode(self):
        """
        Verify that unicode characters roundtrip correctly.
        
        Expected behavior:
        - Unicode characters are preserved through encrypt/decrypt
        """
        original = "token-with-unicode-\u00e9\u00e8\u00ea-\u4e2d\u6587"
        encrypted = encrypt_token(original)
        
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == original

    def test_decrypt_token_invalid_input_raises(self):
        """
        Verify that invalid encrypted input raises an error.
        
        Expected behavior:
        - InvalidToken exception is raised for invalid input
        """
        from cryptography.fernet import InvalidToken
        
        with pytest.raises(InvalidToken):
            decrypt_token("not-a-valid-encrypted-token")

    def test_decrypt_token_tampered_input_raises(self):
        """
        Verify that tampered encrypted input raises an error.
        
        Expected behavior:
        - InvalidToken exception is raised for tampered input
        """
        from cryptography.fernet import InvalidToken
        
        original = "my-secret-token"
        encrypted = encrypt_token(original)
        
        # Tamper with the encrypted data
        tampered = encrypted[:-5] + "XXXXX"
        
        with pytest.raises(InvalidToken):
            decrypt_token(tampered)


class TestEncryptDecryptRoundtrip:
    """Integration tests for encrypt/decrypt roundtrip."""

    @pytest.mark.parametrize("token", [
        "simple-token",
        "token with spaces",
        "token\nwith\nnewlines",
        "token\twith\ttabs",
        "12345678901234567890",
        "!@#$%^&*()",
        "",
        "a",
        "a" * 1000,
        "mixed-123-!@#-\u00e9\u00e8",
    ])
    def test_roundtrip_various_tokens(self, token: str):
        """
        Verify that various token formats roundtrip correctly.
        
        Expected behavior:
        - All token formats are preserved through encrypt/decrypt
        """
        encrypted = encrypt_token(token)
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == token

    def test_roundtrip_oauth_like_token(self):
        """
        Verify that OAuth-like tokens roundtrip correctly.
        
        Expected behavior:
        - Realistic OAuth tokens are preserved
        """
        # Simulated OAuth access token
        access_token = "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        
        encrypted = encrypt_token(access_token)
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == access_token

    def test_roundtrip_refresh_token(self):
        """
        Verify that refresh tokens roundtrip correctly.
        
        Expected behavior:
        - Realistic refresh tokens are preserved
        """
        # Simulated OAuth refresh token
        refresh_token = "1//0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        
        encrypted = encrypt_token(refresh_token)
        decrypted = decrypt_token(encrypted)
        
        assert decrypted == refresh_token
