"""Custom exception types for OAuth workflows."""


class OAuthFlowError(Exception):
    """Base class for OAuth-related failures."""


class AuthorizationDeclined(OAuthFlowError):
    """Raised when the user declines an authorization request."""


class CallbackTimeoutError(OAuthFlowError):
    """Raised when the delegated authorization callback is not received in time."""


class TokenRefreshError(OAuthFlowError):
    """Raised when refreshing an access token fails irrecoverably."""


class MissingUserIdentityError(OAuthFlowError):
    """Raised when an OAuth flow is attempted without a known user identity."""
