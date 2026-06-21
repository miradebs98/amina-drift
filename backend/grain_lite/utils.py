"""
grain_lite Utilities

Common utilities for error handling, logging, and retry logic.
"""

import time
import logging
import functools
from typing import Callable, Any, Optional, Type, Tuple, List, Dict
from datetime import datetime, timezone
from dataclasses import dataclass, field


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger("grain")


class GrainError(Exception):
    """Base exception for grain_lite errors."""
    pass


class ConfigurationError(GrainError):
    """Configuration-related errors."""
    pass


class DataIngestionError(GrainError):
    """Error during data ingestion from EDGAR/FRED."""
    pass


class LLMError(GrainError):
    """Error communicating with LLM API."""
    pass


class VectorStoreError(GrainError):
    """Error with vector store operations."""
    pass


class ThemeNotFoundError(GrainError):
    """Theme not found in library."""
    pass


class PortfolioError(GrainError):
    """Portfolio-related errors."""
    pass


class RateLimitError(DataIngestionError):
    """Rate limit hit on external API (HTTP 429 or API-specific indicator)."""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class IngestionTracker:
    """Tracks what was requested vs. what was successfully fetched."""
    source_type: str  # e.g., "earnings_call", "10-K"
    requested: List[str] = field(default_factory=list)
    succeeded: List[str] = field(default_factory=list)
    failed: Dict[str, str] = field(default_factory=dict)  # item -> reason

    @property
    def is_complete(self) -> bool:
        return len(self.failed) == 0

    @property
    def warnings(self) -> List[str]:
        return [f"{self.source_type} {item}: {reason}" for item, reason in self.failed.items()]


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator for retrying a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback called on each retry
        
    Example:
        @retry(max_attempts=3, delay=1.0, exceptions=(LLMError,))
        def call_llm(prompt):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt)

                    # Respect Retry-After from RateLimitError
                    if isinstance(e, RateLimitError) and e.retry_after:
                        current_delay = max(current_delay, e.retry_after)

                    time.sleep(current_delay)
                    current_delay *= backoff
            
            raise last_exception
        return wrapper
    return decorator


def validate_ticker(ticker: str) -> str:
    """
    Validate and normalize a stock ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Normalized ticker (uppercase, stripped)
        
    Raises:
        ValueError: If ticker is invalid
    """
    if not ticker:
        raise ValueError("Ticker cannot be empty")
    
    ticker = ticker.strip().upper()
    
    if not ticker.isalpha() or len(ticker) > 5:
        # Allow tickers like BRK.A, BRK.B
        if "." not in ticker and "-" not in ticker:
            if not all(c.isalnum() for c in ticker):
                raise ValueError(f"Invalid ticker format: {ticker}")
    
    return ticker


def validate_weight(weight: float) -> float:
    """
    Validate a portfolio weight.
    
    Args:
        weight: Portfolio weight (0.0 to 1.0)
        
    Returns:
        Validated weight
        
    Raises:
        ValueError: If weight is invalid
    """
    if not isinstance(weight, (int, float)):
        raise ValueError(f"Weight must be a number, got {type(weight)}")
    
    if weight < 0:
        raise ValueError(f"Weight cannot be negative: {weight}")
    
    if weight > 1.0:
        logger.warning(f"Weight {weight} > 1.0, normalizing may be needed")
    
    return float(weight)


def validate_score(score: float) -> float:
    """
    Validate and clamp an exposure score.
    
    Args:
        score: Exposure score (0-100)
        
    Returns:
        Clamped score
    """
    if not isinstance(score, (int, float)):
        return 0.0
    
    return max(0.0, min(100.0, float(score)))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division that returns default on divide-by-zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to max length with suffix."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60
    return f"{hours:.1f}h"


def now_utc() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def now_iso() -> str:
    """Get current UTC time as ISO string."""
    return now_utc().isoformat()


class Timer:
    """Simple context manager for timing operations."""
    
    def __init__(self, name: str = "Operation", log: bool = True):
        self.name = name
        self.log = log
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args):
        self.end_time = time.time()
        if self.log:
            logger.info(f"{self.name} completed in {self.elapsed:.2f}s")
    
    @property
    def elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time


if __name__ == "__main__":
    # Test utilities
    print("Testing grain_lite Utilities...")
    
    # Test retry decorator
    @retry(max_attempts=3, delay=0.1)
    def flaky_function(fail_times: list):
        if fail_times:
            fail_times.pop()
            raise ValueError("Simulated failure")
        return "Success"
    
    result = flaky_function([1, 1])  # Will fail twice then succeed
    print(f"✓ Retry decorator: {result}")
    
    # Test validators
    assert validate_ticker("aapl") == "AAPL"
    print("✓ validate_ticker")
    
    assert validate_weight(0.5) == 0.5
    print("✓ validate_weight")
    
    assert validate_score(150) == 100.0
    print("✓ validate_score")
    
    # Test timer
    with Timer("Test operation", log=False) as t:
        time.sleep(0.1)
    assert t.elapsed >= 0.1
    print("✓ Timer")
    
    print("\n✅ All utility tests passed!")
