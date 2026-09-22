"""HTTP header names shared by the gateway and the services."""

# Set by Traefik ForwardAuth after the auth service verified the token.
X_USER_ID = "X-User-Id"
X_USER_ROLE = "X-User-Role"
X_SELLER_ID = "X-Seller-Id"

# Tracing and safe retries.
X_REQUEST_ID = "X-Request-Id"
X_CORRELATION_ID = "X-Correlation-Id"
IDEMPOTENCY_KEY = "Idempotency-Key"

#: Headers a client must never be able to set from the outside.
UNTRUSTED_FROM_CLIENT = (X_USER_ID, X_USER_ROLE, X_SELLER_ID)
