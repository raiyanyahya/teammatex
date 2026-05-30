"""Task queue retry policy: exponential backoff for failed jobs."""

def retry_with_backoff(job, max_attempts: int = 3) -> None:
    """Re-run a failed job with exponentially increasing delay."""
    ...
