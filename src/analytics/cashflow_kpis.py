"""
Cash flow KPIs and capital allocation patterns.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any

def compute_free_cash_flow(cfo: float, cfi: float) -> float:
    """Free Cash Flow = CFO + CFI (CFI is negative for CapEx)."""
    return (cfo or 0) + (cfi or 0)

def compute_cfo_quality(cfo: float, pat: float) -> Tuple[Optional[float], str]:
    """
    CFO Quality = CFO / PAT.
    Returns (ratio, label) where label is 'High Quality', 'Moderate', 'Accrual Risk', or None.
    """
    if pat is None or pat == 0:
        return None, None
    ratio = cfo / pat if cfo is not None else None
    if ratio is None:
        return None, None
    if ratio > 1.0:
        return ratio, 'High Quality'
    elif ratio >= 0.5:
        return ratio, 'Moderate'
    else:
        return ratio, 'Accrual Risk'

def compute_capex_intensity(capex: float, sales: float) -> Tuple[Optional[float], str]:
    """
    CapEx Intensity = abs(capex) / sales * 100.
    Returns (pct, label) where label is 'Asset Light', 'Moderate', 'Capital Intensive'.
    """
    if sales is None or sales == 0:
        return None, None
    capex_abs = abs(capex or 0)
    intensity = (capex_abs / sales) * 100
    if intensity < 3:
        return intensity, 'Asset Light'
    elif intensity <= 8:
        return intensity, 'Moderate'
    else:
        return intensity, 'Capital Intensive'

def compute_fcf_conversion(fcf: float, operating_profit: float) -> Optional[float]:
    """FCF Conversion = FCF / operating_profit * 100."""
    if operating_profit is None or operating_profit == 0:
        return None
    return (fcf / operating_profit) * 100 if fcf is not None else None

def classify_capital_allocation(cfo: float, cfi: float, cff: float) -> str:
    """
    Classify capital allocation pattern based on signs of CFO, CFI, CFF.
    Converts None/NaN to 0.
    """
    # Convert None or NaN to 0
    cfo = 0 if (cfo is None or pd.isna(cfo)) else cfo
    cfi = 0 if (cfi is None or pd.isna(cfi)) else cfi
    cff = 0 if (cff is None or pd.isna(cff)) else cff

    sign_cfo = 1 if cfo > 0 else (-1 if cfo < 0 else 0)
    sign_cfi = 1 if cfi > 0 else (-1 if cfi < 0 else 0)
    sign_cff = 1 if cff > 0 else (-1 if cff < 0 else 0)

    # Pattern: (+,-,-) = Reinvestor
    if sign_cfo > 0 and sign_cfi < 0 and sign_cff < 0:
        return 'Reinvestor'
    # (+,-,+) = Mixed (investing and borrowing)
    if sign_cfo > 0 and sign_cfi < 0 and sign_cff > 0:
        return 'Mixed'
    # (+,+,-) = Liquidating Assets (selling investments, repaying debt)
    if sign_cfo > 0 and sign_cfi > 0 and sign_cff < 0:
        return 'Liquidating Assets'
    # (-,+,+) = Distress Signal (operations negative, selling assets, raising funds)
    if sign_cfo < 0 and sign_cfi > 0 and sign_cff > 0:
        return 'Distress Signal'
    # (-,-,+) = Growth Funded by Debt (operations negative, investing, borrowing)
    if sign_cfo < 0 and sign_cfi < 0 and sign_cff > 0:
        return 'Growth Funded by Debt'
    # (+,+,+) = Cash Accumulator (positive all)
    if sign_cfo > 0 and sign_cfi > 0 and sign_cff > 0:
        return 'Cash Accumulator'
    # (-,-,-) = Pre-Revenue (all negative)
    if sign_cfo < 0 and sign_cfi < 0 and sign_cff < 0:
        return 'Pre-Revenue'
    # Default: mixed
    return 'Mixed'