"""User authentication: password login and JWT token verification."""


def login(email: str, password: str) -> str:
    """Verify the user's password and return a signed session JWT."""
    ...


def verify_token(token: str) -> dict | None:
    """Decode and validate a session JWT; return its payload or None."""
    ...
