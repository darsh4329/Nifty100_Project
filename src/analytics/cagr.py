"""
Compound Annual Growth Rate (CAGR) engine with edge case handling.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from typing import Optional, Tuple, List

def compute_cagr(start: float, end: float, n: int) -> Tuple[Optional[float], Optional[str]]:
    """
    Compute CAGR and flag edge cases.

    Returns:
        (cagr_value, flag)
        flags: None (normal), 'TURNAROUND', 'DECLINE_TO_LOSS', 'BOTH_NEGATIVE', 'ZERO_BASE', 'INSUFFICIENT'
    """
    if n <= 0:
        return None, 'INSUFFICIENT'

    # Handle None or missing values
    if start is None or end is None:
        return None, None

    if start == 0:
        return None, 'ZERO_BASE'

    if start < 0 and end < 0:
        return None, 'BOTH_NEGATIVE'

    if start < 0 and end > 0:
        return None, 'TURNAROUND'

    if start > 0 and end < 0:
        return None, 'DECLINE_TO_LOSS'

    # Normal case: both positive
    if start > 0 and end > 0:
        ratio = end / start
        cagr = (ratio ** (1.0 / n) - 1) * 100
        return cagr, None

    # Should not reach here
    return None, None

def compute_revenue_cagr(series: List[float], years: List[int], window: int) -> Tuple[Optional[float], Optional[str]]:
    """
    Compute CAGR over a rolling window.
    series: list of values in chronological order (oldest first)
    years: list of year labels
    window: 3, 5, or 10 years
    """
    if len(series) < window + 1:
        return None, 'INSUFFICIENT'

    # Use the most recent available window: end value at current year, start at window years ago
    start_value = series[-window - 1]
    end_value = series[-1]
    return compute_cagr(start_value, end_value, window)
