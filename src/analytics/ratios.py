"""
Financial ratio computations for Nifty 100.
Handles profitability, leverage, and efficiency metrics.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import sqlite3
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

def compute_npm(net_profit: float, sales: float) -> Optional[float]:
    """Net Profit Margin = net_profit / sales * 100. None if sales=0."""
    if sales is None or sales == 0:
        return None
    return (net_profit / sales) * 100 if net_profit is not None else None

def compute_opm(operating_profit: float, sales: float) -> Optional[float]:
    """Operating Profit Margin = operating_profit / sales * 100."""
    if sales is None or sales == 0:
        return None
    return (operating_profit / sales) * 100 if operating_profit is not None else None

def compute_roe(net_profit: float, equity: float) -> Optional[float]:
    """Return on Equity = net_profit / equity * 100. None if equity <= 0."""
    if equity is None or equity <= 0:
        return None
    return (net_profit / equity) * 100 if net_profit is not None else None

def compute_roce(ebit: float, equity: float, borrowings: float) -> Optional[float]:
    """Return on Capital Employed = EBIT / (equity + borrowings) * 100."""
    capital = (equity or 0) + (borrowings or 0)
    if capital <= 0:
        return None
    return (ebit / capital) * 100 if ebit is not None else None

def compute_roa(net_profit: float, total_assets: float) -> Optional[float]:
    """Return on Assets = net_profit / total_assets * 100."""
    if total_assets is None or total_assets <= 0:
        return None
    return (net_profit / total_assets) * 100 if net_profit is not None else None

def compute_debt_to_equity(borrowings: float, equity: float) -> float:
    """Debt-to-Equity = borrowings / equity. Returns 0 if borrowings=0 or equity<=0."""
    if borrowings is None or borrowings == 0:
        return 0.0
    if equity is None or equity <= 0:
        return 0.0
    return borrowings / equity

def compute_interest_coverage(op_profit: float, other_income: float, interest: float) -> Tuple[Optional[float], str, bool]:
    """
    Interest Coverage Ratio = (op_profit + other_income) / interest.
    Returns: (icr_value, icr_label, warning_flag)
    """
    if interest is None or interest == 0:
        return None, 'Debt Free', False
    ebit = (op_profit or 0) + (other_income or 0)
    if ebit <= 0:
        return 0.0, 'No Earnings', True  # Can't cover interest
    icr = ebit / interest
    warning = icr < 1.5
    return icr, None, warning

def compute_net_debt(borrowings: float, investments: float) -> float:
    """Net Debt = borrowings - investments (investments as liquid proxy)."""
    return (borrowings or 0) - (investments or 0)

def compute_asset_turnover(sales: float, total_assets: float) -> Optional[float]:
    """Asset Turnover = sales / total_assets."""
    if total_assets is None or total_assets <= 0:
        return None
    return (sales / total_assets) if sales is not None else None

def high_leverage_flag(debt_to_equity: float, broad_sector: str) -> bool:
    """Flag if D/E > 5 and company is not in Financials sector."""
    if debt_to_equity > 5 and broad_sector != 'Financials':
        return True
    return False