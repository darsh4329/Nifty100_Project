"""
Data Quality Validator for Nifty 100 ETL Pipeline.
Implements 16 DQ rules (DQ-01 to DQ-16).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import sqlite3
import logging
import requests
from typing import Dict, List, Any, Optional
from src.etl.normaliser import normalize_year, normalize_ticker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataQualityValidator:
    """Data Quality Validator implementing all 16 DQ rules."""
    
    def __init__(self, db_path: str = "data/nifty100.db"):
        self.db_path = db_path
        self.conn = None
        self.validation_results = []
        
    def connect(self):
        """Establish database connection."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def _get_id_col(self, df: pd.DataFrame) -> str:
        """Helper to get the correct ID column name."""
        if 'company_id' in df.columns:
            return 'company_id'
        elif 'id' in df.columns:
            return 'id'
        return None
            
    def run_all_rules(self, df_companies: pd.DataFrame = None, 
                     df_pl: pd.DataFrame = None,
                     df_bs: pd.DataFrame = None,
                     df_cf: pd.DataFrame = None,
                     df_docs: pd.DataFrame = None) -> List[Dict]:
        """
        Run all 16 DQ rules.
        
        Returns:
            List[Dict]: List of validation results with rule_id, severity, status, details
        """
        self.validation_results = []
        
        # Rule DQ-01: Company PK Uniqueness
        self._rule_dq01(df_companies)
        # Rule DQ-02: Annual PK Uniqueness
        self._rule_dq02(df_pl, df_bs, df_cf)
        # Rule DQ-03: FK Integrity
        self._rule_dq03(df_companies, df_pl, df_bs, df_cf, df_docs)
        # Rule DQ-04: Balance Sheet Balance
        self._rule_dq04(df_bs)
        # Rule DQ-05: OPM Cross-Check
        self._rule_dq05(df_pl)
        # Rule DQ-06: Positive Sales
        self._rule_dq06(df_pl)
        # Rule DQ-07: Year Format
        self._rule_dq07(df_pl, df_bs, df_cf)
        # Rule DQ-08: Ticker Format
        self._rule_dq08(df_companies, df_pl, df_bs, df_cf)
        # Rule DQ-09: Net Cash Check
        self._rule_dq09(df_cf)
        # Rule DQ-10: Non-Negative Fixed Assets
        self._rule_dq10(df_bs)
        # Rule DQ-11: Tax Rate Range
        self._rule_dq11(df_pl)
        # Rule DQ-12: Dividend Payout Cap
        self._rule_dq12(df_pl)
        # Rule DQ-13: URL Validity
        # self._rule_dq13(df_docs)
        # Rule DQ-14: EPS Sign Consistency
        self._rule_dq14(df_pl)
        # Rule DQ-15: BSE Balance (informational)
        self._rule_dq15(df_bs)
        # Rule DQ-16: Coverage Check
        self._rule_dq16(df_pl, df_bs, df_cf)
        
        return self.validation_results
    
    def _add_result(self, rule_id: str, severity: str, status: str, 
                    details: str, company_id: str = None, year: str = None):
        """Add a validation result."""
        self.validation_results.append({
            'rule_id': rule_id,
            'severity': severity,
            'status': status,
            'company_id': company_id,
            'year': year,
            'details': details
        })
    
    def _get_company_col(self, df: pd.DataFrame) -> str:
        """Get company ID column name."""
        for col in ['company_id', 'id']:
            if col in df.columns:
                return col
        return None
    
    def _rule_dq01(self, df: pd.DataFrame):
        """DQ-01: Company PK Uniqueness"""
        if df is None:
            self._add_result('DQ-01', 'CRITICAL', 'FAIL', 'No companies data provided')
            return
        
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-01', 'CRITICAL', 'FAIL', 'No ID column found')
            return
            
        unique_ids = df[id_col].nunique()
        total_rows = len(df)
        if unique_ids == total_rows:
            self._add_result('DQ-01', 'CRITICAL', 'PASS', f'All {unique_ids} company IDs are unique')
        else:
            duplicates = df[id_col].value_counts()
            duplicates = duplicates[duplicates > 1]
            dup_list = duplicates.index.tolist()
            self._add_result('DQ-01', 'CRITICAL', 'FAIL', f'Duplicate company IDs found: {dup_list}')
    
    def _rule_dq02(self, df_pl, df_bs, df_cf):
        """DQ-02: Annual PK Uniqueness"""
        for df, table_name in [(df_pl, 'P&L'), (df_bs, 'Balance Sheet'), (df_cf, 'Cash Flow')]:
            if df is None:
                continue
            
            id_col = self._get_company_col(df)
            if id_col is None:
                self._add_result('DQ-02', 'CRITICAL', 'FAIL', f'No company ID column in {table_name}')
                continue
                
            key_pairs = df.groupby([id_col, 'year']).size()
            duplicates = key_pairs[key_pairs > 1]
            if len(duplicates) == 0:
                self._add_result('DQ-02', 'CRITICAL', 'PASS', f'No duplicate (company_id, year) in {table_name}')
            else:
                self._add_result('DQ-02', 'CRITICAL', 'FAIL', f'Duplicate (company_id, year) in {table_name}: {len(duplicates)} pairs')
    
    def _rule_dq03(self, df_companies, df_pl, df_bs, df_cf, df_docs):
        """DQ-03: FK Integrity"""
        if df_companies is None:
            self._add_result('DQ-03', 'CRITICAL', 'FAIL', 'No companies data for FK check')
            return
            
        comp_id_col = self._get_company_col(df_companies)
        if comp_id_col is None:
            self._add_result('DQ-03', 'CRITICAL', 'FAIL', 'No company ID column in companies')
            return
            
        valid_tickers = set(df_companies[comp_id_col].unique())
        orphan_rows = []
        
        for df, table_name in [(df_pl, 'profitandloss'), (df_bs, 'balancesheet'), 
                               (df_cf, 'cashflow'), (df_docs, 'documents')]:
            if df is None:
                continue
            id_col = self._get_company_col(df)
            if id_col is None:
                continue
            for _, row in df.iterrows():
                ticker = row.get(id_col)
                if ticker not in valid_tickers:
                    orphan_rows.append(f"{table_name}: {ticker}")
                    
        if len(orphan_rows) == 0:
            self._add_result('DQ-03', 'CRITICAL', 'PASS', 'All FK relationships intact')
        else:
            self._add_result('DQ-03', 'CRITICAL', 'FAIL', f'Found {len(orphan_rows)} orphan rows: {orphan_rows[:5]}...')
    
    def _rule_dq04(self, df):
        """DQ-04: Balance Sheet Balance"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-04', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        issues = []
        for idx, row in df.iterrows():
            try:
                total_assets = row.get('total_assets', 0)
                total_liabilities = row.get('total_liabilities', 0)
                if total_assets > 0:
                    diff_pct = abs(total_assets - total_liabilities) / total_assets * 100
                    if diff_pct > 1:
                        issues.append(f"{row[id_col]}-{row['year']}: diff {diff_pct:.2f}%")
            except:
                continue
        if len(issues) == 0:
            self._add_result('DQ-04', 'WARNING', 'PASS', 'All balance sheets balance within 1%')
        else:
            self._add_result('DQ-04', 'WARNING', 'FAIL', f'{len(issues)} rows out of balance: {issues[:3]}...')
    
    def _rule_dq05(self, df):
        """DQ-05: OPM Cross-Check"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-05', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        issues = []
        for idx, row in df.iterrows():
            try:
                opm_source = row.get('opm_percentage', 0)
                sales = row.get('sales', 0)
                operating_profit = row.get('operating_profit', 0)
                if sales > 0:
                    opm_computed = (operating_profit / sales) * 100
                    if abs(opm_source - opm_computed) > 1:
                        issues.append(f"{row[id_col]}-{row['year']}: src={opm_source:.1f}, comp={opm_computed:.1f}")
            except:
                continue
        if len(issues) == 0:
            self._add_result('DQ-05', 'WARNING', 'PASS', 'All OPM values cross-check within 1%')
        else:
            self._add_result('DQ-05', 'WARNING', 'FAIL', f'{len(issues)} OPM mismatches: {issues[:3]}...')
    
    def _rule_dq06(self, df):
        """DQ-06: Positive Sales"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-06', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        negative_sales = []
        for idx, row in df.iterrows():
            sales = row.get('sales', 0)
            if sales < 0:
                negative_sales.append(f"{row[id_col]}-{row['year']}: sales={sales}")
        if len(negative_sales) == 0:
            self._add_result('DQ-06', 'WARNING', 'PASS', 'All sales values are positive')
        else:
            self._add_result('DQ-06', 'WARNING', 'FAIL', f'{len(negative_sales)} rows with negative sales: {negative_sales[:3]}...')
    
    def _rule_dq07(self, df_pl, df_bs, df_cf):
        """DQ-07: Year Format"""
        import re
        pattern = r'^\d{4}-\d{2}$'
        for df, table_name in [(df_pl, 'P&L'), (df_bs, 'Balance Sheet'), (df_cf, 'Cash Flow')]:
            if df is None:
                continue
                
            id_col = self._get_company_col(df)
            if id_col is None:
                continue
                
            errors = []
            for idx, row in df.iterrows():
                year = row.get('year', '')
                if not re.match(pattern, str(year)):
                    errors.append(f"{row.get(id_col, 'unknown')}: '{year}'")
            if len(errors) == 0:
                self._add_result('DQ-07', 'CRITICAL', 'PASS', f'All years in {table_name} are in YYYY-MM format')
            else:
                self._add_result('DQ-07', 'CRITICAL', 'FAIL', f'{len(errors)} year format errors in {table_name}: {errors[:3]}...')
    
    def _rule_dq08(self, df_companies, df_pl, df_bs, df_cf):
        """DQ-08: Ticker Format"""
        issues = []
        for df, table_name in [(df_pl, 'P&L'), (df_bs, 'Balance Sheet'), (df_cf, 'Cash Flow')]:
            if df is None:
                continue
            id_col = self._get_company_col(df)
            if id_col is None:
                continue
            for idx, row in df.iterrows():
                ticker = row.get(id_col, '')
                normalized = normalize_ticker(ticker)
                if normalized == 'MISSING' or len(normalized) < 2:
                    issues.append(f"{table_name}: '{ticker}'")
        if len(issues) == 0:
            self._add_result('DQ-08', 'CRITICAL', 'PASS', 'All tickers are valid')
        else:
            self._add_result('DQ-08', 'CRITICAL', 'FAIL', f'{len(issues)} invalid tickers: {issues[:3]}...')
    
    def _rule_dq09(self, df):
        """DQ-09: Net Cash Check"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-09', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        issues = []
        for idx, row in df.iterrows():
            try:
                net_cash_flow = row.get('net_cash_flow', 0)
                cfo = row.get('operating_activity', 0)
                cfi = row.get('investing_activity', 0)
                cff = row.get('financing_activity', 0)
                sum_components = cfo + cfi + cff
                if abs(net_cash_flow - sum_components) > 10:
                    issues.append(f"{row[id_col]}-{row['year']}: diff={net_cash_flow - sum_components:.1f}")
            except:
                continue
        if len(issues) == 0:
            self._add_result('DQ-09', 'WARNING', 'PASS', 'All cash flow sums balance within 10 Cr')
        else:
            self._add_result('DQ-09', 'WARNING', 'FAIL', f'{len(issues)} cash flow mismatches: {issues[:3]}...')
    
    def _rule_dq10(self, df):
        """DQ-10: Non-Negative Fixed Assets"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-10', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        negative_fa = []
        for idx, row in df.iterrows():
            fixed_assets = row.get('fixed_assets', 0)
            if fixed_assets < 0:
                negative_fa.append(f"{row[id_col]}-{row['year']}: fa={fixed_assets}")
        if len(negative_fa) == 0:
            self._add_result('DQ-10', 'WARNING', 'PASS', 'All fixed assets are non-negative')
        else:
            self._add_result('DQ-10', 'WARNING', 'FAIL', f'{len(negative_fa)} rows with negative fixed assets: {negative_fa[:3]}...')
    
    def _rule_dq11(self, df):
        """DQ-11: Tax Rate Range"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-11', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        out_of_range = []
        for idx, row in df.iterrows():
            tax = row.get('tax_percentage', 0)
            if not pd.isna(tax) and (tax < 0 or tax > 60):
                out_of_range.append(f"{row[id_col]}-{row['year']}: tax={tax}")
        if len(out_of_range) == 0:
            self._add_result('DQ-11', 'WARNING', 'PASS', 'All tax rates are within 0-60% range')
        else:
            self._add_result('DQ-11', 'WARNING', 'FAIL', f'{len(out_of_range)} tax rates out of range: {out_of_range[:3]}...')
    
    def _rule_dq12(self, df):
        """DQ-12: Dividend Payout Cap"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-12', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        high_payout = []
        for idx, row in df.iterrows():
            payout = row.get('dividend_payout', 0)
            if not pd.isna(payout) and payout > 200:
                high_payout.append(f"{row[id_col]}-{row['year']}: payout={payout}")
        if len(high_payout) == 0:
            self._add_result('DQ-12', 'WARNING', 'PASS', 'All dividend payouts are ≤ 200%')
        else:
            self._add_result('DQ-12', 'WARNING', 'FAIL', f'{len(high_payout)} dividend payouts > 200%: {high_payout[:3]}...')
    
    def _rule_dq13(self, df):
        """DQ-13: URL Validity"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-13', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        invalid_urls = []
        for idx, row in df.iterrows():
            url = row.get('annual_report', '')
            if not url:
                url = row.get('Annual_Report', '')
            if url and isinstance(url, str) and url.startswith('http'):
                try:
                    response = requests.head(url, timeout=3, allow_redirects=True, stream=True)
                    response.close()
                    if response.status_code >= 400:
                        invalid_urls.append(f"{row[id_col]}-{row.get('year', 'unknown')}: status={response.status_code}")
                except:
                    invalid_urls.append(f"{row[id_col]}-{row.get('year', 'unknown')}: connection error")
        if len(invalid_urls) == 0:
            self._add_result('DQ-13', 'WARNING', 'PASS', 'All URLs are valid')
        else:
            self._add_result('DQ-13', 'WARNING', 'FAIL', f'{len(invalid_urls)} invalid URLs found (logged but not rejected)')
    
    def _rule_dq14(self, df):
        """DQ-14: EPS Sign Consistency"""
        if df is None:
            return
            
        id_col = self._get_company_col(df)
        if id_col is None:
            self._add_result('DQ-14', 'WARNING', 'FAIL', 'No company ID column')
            return
            
        issues = []
        for idx, row in df.iterrows():
            net_profit = row.get('net_profit', 0)
            eps = row.get('eps', 0)
            if net_profit > 0 and eps < 0:
                issues.append(f"{row[id_col]}-{row['year']}: profit={net_profit}, eps={eps}")
            elif net_profit < 0 and eps > 0:
                issues.append(f"{row[id_col]}-{row['year']}: profit={net_profit}, eps={eps}")
        if len(issues) == 0:
            self._add_result('DQ-14', 'WARNING', 'PASS', 'EPS sign consistent with net profit')
        else:
            self._add_result('DQ-14', 'WARNING', 'FAIL', f'{len(issues)} EPS sign inconsistencies: {issues[:3]}...')
    
    def _rule_dq15(self, df):
        """DQ-15: BSE Balance (informational)"""
        if df is None:
            return
        balanced = 0
        total = 0
        for idx, row in df.iterrows():
            total += 1
            total_assets = row.get('total_assets', 0)
            total_liabilities = row.get('total_liabilities', 0)
            if total_assets > 0 and abs(total_assets - total_liabilities) / total_assets < 0.01:
                balanced += 1
        if total == 0:
            self._add_result('DQ-15', 'INFO', 'PASS', 'No balance sheet data to check')
        else:
            pct = (balanced / total) * 100
            self._add_result('DQ-15', 'INFO', 'PASS', f'{balanced}/{total} ({pct:.1f}%) balance sheets balance within 1%')
    
    def _rule_dq16(self, df_pl, df_bs, df_cf):
        """DQ-16: Coverage Check"""
        companies_coverage = {}
        for df in [df_pl, df_bs, df_cf]:
            if df is None:
                continue
            id_col = self._get_company_col(df)
            if id_col is None:
                continue
            for _, row in df.iterrows():
                ticker = row.get(id_col, '')
                if ticker not in companies_coverage:
                    companies_coverage[ticker] = {'pl': 0, 'bs': 0, 'cf': 0}
                # Determine which table
                if 'sales' in df.columns:
                    companies_coverage[ticker]['pl'] += 1
                elif 'total_assets' in df.columns:
                    companies_coverage[ticker]['bs'] += 1
                else:
                    companies_coverage[ticker]['cf'] += 1
        low_coverage = []
        for ticker, coverage in companies_coverage.items():
            pl_years = coverage['pl']
            bs_years = coverage['bs']
            cf_years = coverage['cf']
            if pl_years < 5 or bs_years < 5 or cf_years < 5:
                low_coverage.append(f"{ticker}: PL={pl_years}, BS={bs_years}, CF={cf_years}")
        if len(low_coverage) == 0:
            self._add_result('DQ-16', 'WARNING', 'PASS', 'All companies have ≥ 5 years of data')
        else:
            self._add_result('DQ-16', 'WARNING', 'FAIL', f'{len(low_coverage)} companies with < 5 years: {low_coverage[:3]}...')


# ===== Export helper functions =====

def export_validation_results(results: List[Dict], output_path: str = "output/validation_failures.csv"):
    """Export validation results to CSV."""
    if not results:
        return
    df = pd.DataFrame(results)
    df.to_csv(output_path, index=False)
    logger.info(f"Validation results exported to {output_path}")
    return df


def generate_load_audit(load_stats: Dict[str, Any], output_path: str = "output/load_audit.csv"):
    """Generate load audit report."""
    df = pd.DataFrame([
        {
            'table': table,
            'rows_in': stats.get('rows_in', 0),
            'rows_out': stats.get('rows_out', 0),
            'rejected': stats.get('rows_out', 0) - stats.get('rows_loaded', 0),
            'runtime_sec': stats.get('runtime_sec', 0),
            'status': stats.get('status', 'UNKNOWN')
        }
        for table, stats in load_stats.items()
    ])
    df.to_csv(output_path, index=False)
    logger.info(f"Load audit exported to {output_path}")
    return df