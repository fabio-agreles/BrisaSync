"""Camada de credenciais, OAuth 2.0 Google Desktop e ponte cifrada do BrisaSync."""

from .oauth_google import (
    GoogleOAuthDesktopClient,
    OAuthAccessDeniedError,
    OAuthClientConfig,
    OAuthConfigurationError,
    OAuthError,
    OAuthProtocolError,
    OAuthRevokedOrExpiredError,
    OAuthTimeoutOrCancelledError,
    PKCEChallenge,
    REQUIRED_GOOGLE_SCOPES,
    default_oauth_client_config_path,
    generate_pkce_pair,
    generate_state,
)
from .rclone_bridge import (
    REMOTE_NAME,
    RcloneEncryptedBridge,
    default_encrypted_rclone_config_path,
)
from .store import (
    CredentialCapabilities,
    CredentialStore,
    OAuthCredentials,
    VaultLockedError,
    VaultUnavailableError,
    redact_secrets,
)

__all__ = [
    "CredentialCapabilities",
    "CredentialStore",
    "GoogleOAuthDesktopClient",
    "OAuthAccessDeniedError",
    "OAuthClientConfig",
    "OAuthConfigurationError",
    "OAuthCredentials",
    "OAuthError",
    "OAuthProtocolError",
    "OAuthRevokedOrExpiredError",
    "OAuthTimeoutOrCancelledError",
    "PKCEChallenge",
    "REMOTE_NAME",
    "REQUIRED_GOOGLE_SCOPES",
    "RcloneEncryptedBridge",
    "VaultLockedError",
    "VaultUnavailableError",
    "default_encrypted_rclone_config_path",
    "default_oauth_client_config_path",
    "generate_pkce_pair",
    "generate_state",
    "redact_secrets",
]
