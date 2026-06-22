"""
Normalisation utilities for Nifty 100 ETL pipeline.
Handles year standardisation, ticker normalisation, and data cleansing.
"""

import re
import pandas as pd
from typing import Optional, Tuple, List


def normalize_year(year_value: any) -> str:
    """
    Standardise year labels to YYYY-MM format.
    
    Handles:
    - Mar-23 → 2023-03
    - Mar 23 → 2023-03
    - March-2023 → 2023-03
    - 2023 → 2023-03
    - FY23 → 2023-03
    - Dec-22 → 2022-12
    - Jun-23 → 2023-06
    
    Returns:
        str: Standardised year in YYYY-MM format, or 'PARSE_ERROR' if unparseable
    """
    if pd.isna(year_value):
        return 'PARSE_ERROR'
    
    year_str = str(year_value).strip()
    
    # Already in YYYY-MM format
    if re.match(r'^\d{4}-\d{2}$', year_str):
        return year_str
    
    # Mar-23, Mar 23, March-2023
    month_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }
    
    # Pattern: Month-YY or Month YY
    match = re.match(r'^([A-Za-z]{3,9})\s*[-]?\s*(\d{2,4})$', year_str)
    if match:
        month_name = match.group(1).lower()[:3]
        year_num = match.group(2)
        
        if month_name in month_map:
            # 2-digit year: 23 → 2023
            if len(year_num) == 2:
                year_full = f"20{year_num}" if int(year_num) < 50 else f"19{year_num}"
            else:
                year_full = year_num
            return f"{year_full}-{month_map[month_name]}"
    
    # Pattern: FY23, FY2023
    match = re.match(r'^FY(\d{2,4})$', year_str, re.IGNORECASE)
    if match:
        year_num = match.group(1)
        if len(year_num) == 2:
            year_full = f"20{year_num}" if int(year_num) < 50 else f"19{year_num}"
        else:
            year_full = year_num
        return f"{year_full}-03"  # March year-end
    
    # Pattern: YYYY only (assume March year-end)
    if re.match(r'^\d{4}$', year_str):
        return f"{year_str}-03"
    
    # Pattern: YYYY-MM already checked above
    return 'PARSE_ERROR'


def normalize_ticker(ticker: any) -> str:
    """
    Normalise NSE ticker symbols to uppercase without whitespace.
    
    Args:
        ticker: Raw ticker string or NaN
        
    Returns:
        str: Normalised ticker, or 'MISSING' if empty
    """
    if pd.isna(ticker):
        return 'MISSING'
    
    ticker_str = str(ticker).strip()
    if not ticker_str:
        return 'MISSING'
    
    # Preserve hyphens and ampersands (valid NSE ticker characters)
    # e.g., BAJAJ-AUTO, M&M
    return ticker_str.upper()


def normalize_company_id(company_id: any) -> str:
    """
    Alias for normalize_ticker - standardises company_id across all tables.
    """
    return normalize_ticker(company_id)


def load_excel_with_header(path: str, header_row: int = 1) -> pd.DataFrame:
    """
    Load Excel file with specified header row.
    
    Core datasets use header=1 (Row 0 is metadata, Row 1 is actual headers).
    Supplementary datasets use header=0.
    
    Args:
        path: Path to Excel file
        header_row: Row index to use as column headers (0-based)
        
    Returns:
        pd.DataFrame: Loaded DataFrame with cleaned headers
    """
    df = pd.read_excel(path, header=header_row)
    
    # Clean column names: strip whitespace, lowercase, replace spaces with underscores
    df.columns = df.columns.str.strip()
    df.columns = df.columns.str.lower()
    df.columns = df.columns.str.replace(' ', '_')
    df.columns = df.columns.str.replace('[^a-z0-9_]', '', regex=True)
    
    return df


def validate_company_id(df: pd.DataFrame, column: str = 'company_id') -> Tuple[bool, List[str]]:
    """
    Validate that company_id column contains valid ticker symbols.
    
    Returns:
        Tuple[bool, List[str]]: (is_valid, list_of_issues)
    """
    issues = []
    
    if column not in df.columns:
        issues.append(f"Column '{column}' not found")
        return False, issues
    
    for idx, value in df[column].items():
        if pd.isna(value) or str(value).strip() == '':
            issues.append(f"Row {idx}: Empty company_id")
            continue
        
        normalized = normalize_ticker(value)
        if normalized == 'MISSING':
            issues.append(f"Row {idx}: Invalid company_id '{value}'")
    
    return len(issues) == 0, issues


def extract_cagr_from_text(text: str, metric_type: str = 'sales') -> Optional[float]:
    """
    Extract CAGR percentage from analysis.xlsx text fields.
    
    Example: "10 Years: 21%" → returns 21.0
    
    Args:
        text: Raw text from analysis.xlsx
        metric_type: 'sales', 'profit', 'stock_price', 'roe'
        
    Returns:
        Optional[float]: CAGR percentage, or None if not found
    """
    if not text or not isinstance(text, str):
        return None
    
    # Pattern: "10 Years: 21%" or "5 Years: 6%"
    pattern = r'(\d+)\s*Years?\s*[:]?\s*([\d.]+)%'
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return float(match.group(2))
    
    # Alternative: "10yrs 21%"
    pattern_alt = r'(\d+)yrs?\s*([\d.]+)%'
    match = re.search(pattern_alt, text, re.IGNORECASE)
    
    if match:
        return float(match.group(2))
    
    return None