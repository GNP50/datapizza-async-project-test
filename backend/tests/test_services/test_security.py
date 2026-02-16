"""Security service tests"""
import pytest
from datetime import datetime, timedelta

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    create_verification_token,
    verify_verification_token
)


@pytest.mark.asyncio
class TestPasswordHashing:
    """Test password hashing functions"""

    def test_password_hash_creates_hash(self):
        """Test that password hashing creates a hash"""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 0

    def test_password_hash_different_each_time(self):
        """Test that same password creates different hashes (salt)"""
        password = "mysecretpassword"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Test verifying correct password"""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password"""
        password = "mysecretpassword"
        wrong_password = "wrongpassword"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_empty(self):
        """Test verifying empty password"""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert verify_password("", hashed) is False


@pytest.mark.asyncio
class TestTokenGeneration:
    """Test JWT token generation"""

    def test_create_access_token(self):
        """Test creating access token"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """Test creating refresh token"""
        data = {"sub": "user123"}
        token = create_refresh_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_token_contains_data(self):
        """Test that access token contains the provided data"""
        user_id = "user123"
        data = {"sub": user_id}
        token = create_access_token(data)

        decoded = decode_token(token)
        assert decoded["sub"] == user_id
        assert decoded["type"] == "access"

    def test_refresh_token_contains_data(self):
        """Test that refresh token contains the provided data"""
        user_id = "user123"
        data = {"sub": user_id}
        token = create_refresh_token(data)

        decoded = decode_token(token)
        assert decoded["sub"] == user_id
        assert decoded["type"] == "refresh"

    def test_token_has_expiration(self):
        """Test that tokens have expiration time"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        decoded = decode_token(token)
        assert "exp" in decoded
        assert decoded["exp"] > datetime.utcnow().timestamp()


@pytest.mark.asyncio
class TestTokenDecoding:
    """Test JWT token decoding"""

    def test_decode_valid_token(self):
        """Test decoding a valid token"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["sub"] == "user123"

    def test_decode_invalid_token(self):
        """Test decoding an invalid token raises exception"""
        invalid_token = "invalid.token.here"

        with pytest.raises(Exception):
            decode_token(invalid_token)

    def test_decode_expired_token(self):
        """Test decoding an expired token raises exception"""
        from jose import jwt
        from app.core.config import get_settings

        settings = get_settings()
        data = {
            "sub": "user123",
            "exp": datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
        }

        token = jwt.encode(data, settings.jwt_secret, algorithm="HS256")

        with pytest.raises(Exception):
            decode_token(token)

    def test_decode_tampered_token(self):
        """Test decoding a tampered token raises exception"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        # Tamper with the token
        tampered_token = token[:-5] + "XXXXX"

        with pytest.raises(Exception):
            decode_token(tampered_token)


@pytest.mark.asyncio
class TestVerificationTokens:
    """Test email verification tokens"""

    def test_create_verification_token(self):
        """Test creating verification token"""
        email = "test@example.com"
        token = create_verification_token(email)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_verification_token_valid(self):
        """Test verifying a valid verification token"""
        email = "test@example.com"
        token = create_verification_token(email)

        verified_email = verify_verification_token(token)
        assert verified_email == email

    def test_verify_verification_token_invalid(self):
        """Test verifying an invalid verification token"""
        invalid_token = "invalid.token.here"

        verified_email = verify_verification_token(invalid_token)
        assert verified_email is None

    def test_verification_token_different_emails(self):
        """Test verification tokens for different emails"""
        email1 = "user1@example.com"
        email2 = "user2@example.com"

        token1 = create_verification_token(email1)
        token2 = create_verification_token(email2)

        assert verify_verification_token(token1) == email1
        assert verify_verification_token(token2) == email2
        assert token1 != token2


@pytest.mark.asyncio
class TestTokenExpiration:
    """Test token expiration handling"""

    def test_access_token_expiration_time(self):
        """Test access token has correct expiration time"""
        from app.core.config import get_settings

        settings = get_settings()
        data = {"sub": "user123"}
        token = create_access_token(data)

        decoded = decode_token(token)
        exp_time = datetime.fromtimestamp(decoded["exp"])
        current_time = datetime.utcnow()

        # Should expire in approximately the configured time
        time_diff = (exp_time - current_time).total_seconds()
        expected_seconds = settings.access_token_expire_minutes * 60

        # Allow 5 seconds tolerance
        assert abs(time_diff - expected_seconds) < 5

    def test_refresh_token_expiration_time(self):
        """Test refresh token has correct expiration time"""
        from app.core.config import get_settings

        settings = get_settings()
        data = {"sub": "user123"}
        token = create_refresh_token(data)

        decoded = decode_token(token)
        exp_time = datetime.fromtimestamp(decoded["exp"])
        current_time = datetime.utcnow()

        # Should expire in approximately the configured time
        time_diff = (exp_time - current_time).total_seconds()
        expected_seconds = settings.refresh_token_expire_days * 24 * 60 * 60

        # Allow 5 seconds tolerance
        assert abs(time_diff - expected_seconds) < 5


@pytest.mark.asyncio
class TestTokenSecurity:
    """Test token security features"""

    def test_tokens_are_unique(self):
        """Test that tokens created at different times are unique"""
        import time
        data = {"sub": "user123"}

        token1 = create_access_token(data)

        # Wait enough time to ensure different expiration timestamp
        time.sleep(1)

        token2 = create_access_token(data)

        # Tokens should be different due to different expiration times
        assert token1 != token2

    def test_access_and_refresh_tokens_different(self):
        """Test that access and refresh tokens are different"""
        data = {"sub": "user123"}

        access_token = create_access_token(data)
        refresh_token = create_refresh_token(data)

        assert access_token != refresh_token

        decoded_access = decode_token(access_token)
        decoded_refresh = decode_token(refresh_token)

        assert decoded_access["type"] == "access"
        assert decoded_refresh["type"] == "refresh"
