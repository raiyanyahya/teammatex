"""User CRUD: create, fetch, update, and deactivate user records."""

def create_user(email: str, name: str) -> dict:
    """Insert a new user row and return it."""
    ...

def deactivate_user(user_id: str) -> None:
    """Soft-delete a user by marking them inactive."""
    ...
