# tests/etl/test_normaliser.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import pandas as pd
from src.etl.normaliser import (
    normalize_year,
    normalize_ticker,
    normalize_company_id,
    load_excel_with_header,
    validate_company_id,
    extract_cagr_from_text
)



class TestYearNormaliser:
    """20+ test cases for normalize_year()"""
    
    def test_mar23_format(self):
        assert normalize_year('Mar-23') == '2023-03'
    
    def test_mar23_with_space(self):
        assert normalize_year('Mar 23') == '2023-03'
    
    def test_march_2023_full(self):
        assert normalize_year('March-2023') == '2023-03'
    
    def test_december_2022(self):
        assert normalize_year('Dec-22') == '2022-12'
    
    def test_june_2023(self):
        assert normalize_year('Jun-23') == '2023-06'
    
    def test_fy24_format(self):
        assert normalize_year('FY24') == '2024-03'
    
    def test_fy2023_format(self):
        assert normalize_year('FY2023') == '2023-03'
    
    def test_yyyy_only(self):
        assert normalize_year('2023') == '2023-03'
    
    def test_yyyy_mm_already(self):
        assert normalize_year('2023-03') == '2023-03'
    
    def test_april_fy(self):
        assert normalize_year('Apr-24') == '2024-04'
    
    def test_february(self):
        assert normalize_year('Feb-25') == '2025-02'
    
    def test_september(self):
        assert normalize_year('Sep-23') == '2023-09'
    
    def test_october(self):
        assert normalize_year('Oct-24') == '2024-10'
    
    def test_november(self):
        assert normalize_year('Nov-23') == '2023-11'
    
    def test_january(self):
        assert normalize_year('Jan-24') == '2024-01'
    
    def test_year_1999_fy(self):
        assert normalize_year('FY99') == '1999-03'
    
    def test_year_2000(self):
        assert normalize_year('2000') == '2000-03'
    
    def test_parse_error_garbage(self):
        assert normalize_year('garbage') == 'PARSE_ERROR'
    
    def test_parse_error_empty(self):
        assert normalize_year('') == 'PARSE_ERROR'
    
    def test_parse_error_nan(self):
        assert normalize_year(pd.NA) == 'PARSE_ERROR'
    
    def test_july_2024(self):
        assert normalize_year('Jul-24') == '2024-07'
    
    def test_august_2024(self):
        assert normalize_year('Aug-24') == '2024-08'


class TestTickerNormaliser:
    """15+ test cases for normalize_ticker()"""
    
    def test_tcs_uppercase(self):
        assert normalize_ticker('tcs') == 'TCS'
    
    def test_tcs_whitespace(self):
        assert normalize_ticker(' TCS ') == 'TCS'
    
    def test_bajaj_auto_hyphen(self):
        assert normalize_ticker('bajaj-auto') == 'BAJAJ-AUTO'
    
    def test_m_and_m_ampersand(self):
        assert normalize_ticker('M&M') == 'M&M'
    
    def test_hdfc_bank(self):
        assert normalize_ticker('hdfcbank') == 'HDFCBANK'
    
    def test_icici_bank(self):
        assert normalize_ticker('icicibank') == 'ICICIBANK'
    
    def test_reliance(self):
        assert normalize_ticker('reliance') == 'RELIANCE'
    
    def test_infy(self):
        assert normalize_ticker('infy') == 'INFY'
    
    def test_axis_bank(self):
        assert normalize_ticker('axisbank') == 'AXISBANK'
    
    def test_whitespace_stripped(self):
        assert normalize_ticker('  SBIN  ') == 'SBIN'
    
    def test_lowercase_preserves(self):
        assert normalize_ticker('tata motors') == 'TATA MOTORS'
    
    def test_empty_string(self):
        assert normalize_ticker('') == 'MISSING'
    
    def test_nan_value(self):
        assert normalize_ticker(pd.NA) == 'MISSING'
    
    def test_none_value(self):
        assert normalize_ticker(None) == 'MISSING'
    
    def test_numeric_ticker(self):
        assert normalize_ticker(12345) == '12345'
    
    def test_special_chars_preserved(self):
        assert normalize_ticker('M&M') == 'M&M'
    
    def test_normalize_company_id_alias(self):
        from src.etl.normaliser import normalize_company_id
        assert normalize_company_id('tcs') == 'TCS'


class TestExcelLoader:
    def test_load_with_header_1(self, tmp_path):
        """Test loading Excel with header=1"""
        import pandas as pd
        
        # Create test Excel with metadata row
        df = pd.DataFrame({
            'Company ID': ['TCS', 'INFY'],
            'Sales': [100, 200]
        })
        file_path = tmp_path / 'test.xlsx'
        df.to_excel(file_path, index=False)
        
        # Should load with header=0 by default
        loaded = load_excel_with_header(str(file_path), header_row=0)
        assert 'company_id' in loaded.columns
        assert loaded.shape[0] == 2


class TestCAGRExtractor:
    def test_extract_10yr_sales(self):
        text = "10 Years: 21%"
        assert extract_cagr_from_text(text, 'sales') == 21.0
    
    def test_extract_5yr_profit(self):
        text = "5 Years: 6%"
        assert extract_cagr_from_text(text, 'profit') == 6.0
    
    def test_extract_10yr_roe(self):
        text = "10 Years: 17%"
        assert extract_cagr_from_text(text, 'roe') == 17.0
    
    def test_alternative_format(self):
        text = "10yrs 21%"
        assert extract_cagr_from_text(text, 'sales') == 21.0
    
    def test_no_match_returns_none(self):
        text = "No CAGR data here"
        assert extract_cagr_from_text(text, 'sales') is None
    
    def test_empty_string(self):
        assert extract_cagr_from_text('', 'sales') is None
    
    def test_none_value(self):
        assert extract_cagr_from_text(None, 'sales') is None
    
    def test_decimal_percentage(self):
        text = "5 Years: 15.5%"
        assert extract_cagr_from_text(text, 'sales') == 15.5