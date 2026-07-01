"""
Populate financial_ratios table with all computed KPIs.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sqlite3
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from src.analytics.ratios import (
    compute_npm, compute_opm, compute_roe, compute_roce, compute_roa,
    compute_debt_to_equity, compute_interest_coverage,
    compute_net_debt, compute_asset_turnover, high_leverage_flag
)
from src.analytics.cagr import compute_cagr, compute_revenue_cagr
from src.analytics.cashflow_kpis import (
    compute_free_cash_flow, compute_cfo_quality,
    compute_capex_intensity, compute_fcf_conversion,
    classify_capital_allocation
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path("data/nifty100.db")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

def get_sector_map(conn) -> Dict[str, str]:
    """Return dict of company_id -> broad_sector."""
    df = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
    return dict(zip(df['company_id'], df['broad_sector']))

def get_face_value_map(conn) -> Dict[str, float]:
    """Return dict of company_id -> face_value."""
    df = pd.read_sql("SELECT id, face_value FROM companies", conn)
    return dict(zip(df['id'], df['face_value']))

def populate_financial_ratios():
    """Main function to compute and store all KPIs."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get sector mapping and face values
    sector_map = get_sector_map(conn)
    face_value_map = get_face_value_map(conn)

    # Fetch all companies
    companies_df = pd.read_sql("SELECT id, company_name FROM companies", conn)
    company_ids = companies_df['id'].tolist()

    # Prepare lists for capital allocation output
    capital_alloc_records = []
    edge_case_log = []

    total_updated = 0

    for company_id in company_ids:
        # Fetch P&L data
        pl_df = pd.read_sql(
            "SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year",
            conn, params=(company_id,)
        )
        if pl_df.empty:
            continue

        # Fetch balance sheet data
        bs_df = pd.read_sql(
            "SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year",
            conn, params=(company_id,)
        )
        # Merge on year
        df = pd.merge(pl_df, bs_df, on=['company_id', 'year'], how='inner', suffixes=('', '_bs'))

        # Fetch cash flow data
        cf_df = pd.read_sql(
            "SELECT * FROM cashflow WHERE company_id = ? ORDER BY year",
            conn, params=(company_id,)
        )
        if not cf_df.empty:
            df = pd.merge(df, cf_df, on=['company_id', 'year'], how='inner', suffixes=('', '_cf'))

        if df.empty:
            continue

        # Get sector for this company
        broad_sector = sector_map.get(company_id, 'Unknown')

        # Process each year
        for idx, row in df.iterrows():
            year = row['year']
            sales = row.get('sales')
            net_profit = row.get('net_profit')
            op_profit = row.get('operating_profit')
            opm_source = row.get('opm_percentage')
            equity = (row.get('equity_capital') or 0) + (row.get('reserves') or 0)
            borrowings = row.get('borrowings') or 0
            total_assets = row.get('total_assets')
            other_income = row.get('other_income') or 0
            interest = row.get('interest') or 0
            depreciation = row.get('depreciation') or 0
            investments = row.get('investments') or 0
            eps = row.get('eps')
            dividend_payout = row.get('dividend_payout')
            cfo = row.get('operating_activity')
            cfi = row.get('investing_activity')
            cff = row.get('financing_activity')
            tax_pct = row.get('tax_percentage')

            # --- Profitability ---
            npm = compute_npm(net_profit, sales)
            opm = compute_opm(op_profit, sales)
            # Cross-check OPM
            if opm is not None and opm_source is not None:
                if abs(opm - opm_source) > 1:
                    edge_case_log.append(f"{company_id}-{year}: OPM mismatch: computed={opm:.1f}, source={opm_source:.1f}")

            roe = compute_roe(net_profit, equity)
            # EBIT = op_profit - depreciation (using op_profit as EBITDA proxy)
            ebit = (op_profit or 0) - depreciation
            roce = compute_roce(ebit, equity, borrowings)
            # Cross-check ROCE with source if available? Not in our schema.

            roa = compute_roa(net_profit, total_assets)

            # --- Leverage ---
            de = compute_debt_to_equity(borrowings, equity)
            high_lev = high_leverage_flag(de, broad_sector)

            icr, icr_label, icr_warn = compute_interest_coverage(op_profit, other_income, interest)

            net_debt = compute_net_debt(borrowings, investments)

            # --- Efficiency ---
            asset_turnover = compute_asset_turnover(sales, total_assets)

            # --- Cash Flow ---
            fcf = compute_free_cash_flow(cfo, cfi)
            cfo_quality, cfo_label = compute_cfo_quality(cfo, net_profit)
            capex = abs(cfi) if cfi is not None else 0
            capex_intensity, capex_label = compute_capex_intensity(capex, sales)
            fcf_conv = compute_fcf_conversion(fcf, op_profit)

            # --- Capital Allocation ---
            alloc_pattern = classify_capital_allocation(cfo, cfi, cff)
            capital_alloc_records.append({
                'company_id': company_id,
                'year': year,
                'cfo_sign': 'Positive' if cfo and cfo > 0 else ('Negative' if cfo and cfo < 0 else 'Zero'),
                'cfi_sign': 'Positive' if cfi and cfi > 0 else ('Negative' if cfi and cfi < 0 else 'Zero'),
                'cff_sign': 'Positive' if cff and cff > 0 else ('Negative' if cff and cff < 0 else 'Zero'),
                'pattern_label': alloc_pattern
            })

            # --- Book Value per Share ---
            face_value = face_value_map.get(company_id, 1)  # default 1
            shares_outstanding = (row.get('equity_capital') or 0) / face_value if face_value > 0 else 0
            bvps = (equity / shares_outstanding) if shares_outstanding > 0 else None

            # --- CAGR ---
            # We'll compute CAGR for revenue, PAT, EPS using history for this company
            # We need to compute over all years for this company, so we'll do it outside the loop
            # But for simplicity, we'll compute CAGR based on the entire series for each company
            # We'll compute per company and then join back.

            # Instead of computing CAGR inside loop, we'll compute company-wise after gathering all years.

            # Store in a dict to update later
            # We'll compute CAGR at the end per company, but we need to insert row by row.

            # For now, we'll compute CAGR values using the company's full series.
            # We'll handle this after the loop.

        # End of year loop

    # After processing all companies, we need to compute CAGR for each company separately.
    # We'll fetch all data again and compute CAGR per company.

    # We'll compute CAGR per company by selecting all years from financial_ratios or from source tables.
    # We'll run a separate SQL update after populating base KPIs.

    logger.info("Populating base KPIs...")

    # We'll now insert/update the financial_ratios table with base KPIs (without CAGR).
    # Then we'll compute CAGR and update.

    # To keep it simple, we'll implement a two-pass: first insert base KPIs, then compute CAGR.

    # We'll use the existing dataframe df that we merged per company.

    # However, we need to iterate per company and per year to insert.

    # Since we already looped through all companies and years, we can build a list of records.

    records = []
    for company_id in company_ids:
        pl_df = pd.read_sql("SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
        if pl_df.empty:
            continue
        bs_df = pd.read_sql("SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
        df = pd.merge(pl_df, bs_df, on=['company_id', 'year'], how='inner', suffixes=('', '_bs'))
        cf_df = pd.read_sql("SELECT * FROM cashflow WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
        if not cf_df.empty:
            df = pd.merge(df, cf_df, on=['company_id', 'year'], how='inner', suffixes=('', '_cf'))
        if df.empty:
            continue

        broad_sector = sector_map.get(company_id, 'Unknown')
        face_value = face_value_map.get(company_id, 1)

        for _, row in df.iterrows():
            year = row['year']
            sales = row.get('sales')
            net_profit = row.get('net_profit')
            op_profit = row.get('operating_profit')
            opm_source = row.get('opm_percentage')
            equity = (row.get('equity_capital') or 0) + (row.get('reserves') or 0)
            borrowings = row.get('borrowings') or 0
            total_assets = row.get('total_assets')
            other_income = row.get('other_income') or 0
            interest = row.get('interest') or 0
            depreciation = row.get('depreciation') or 0
            investments = row.get('investments') or 0
            eps = row.get('eps')
            dividend_payout = row.get('dividend_payout')
            cfo = row.get('operating_activity')
            cfi = row.get('investing_activity')
            cff = row.get('financing_activity')

            npm = compute_npm(net_profit, sales)
            opm = compute_opm(op_profit, sales)
            roe = compute_roe(net_profit, equity)
            ebit = (op_profit or 0) - depreciation
            roce = compute_roce(ebit, equity, borrowings)
            roa = compute_roa(net_profit, total_assets)
            de = compute_debt_to_equity(borrowings, equity)
            high_lev = high_leverage_flag(de, broad_sector)
            icr, icr_label, icr_warn = compute_interest_coverage(op_profit, other_income, interest)
            net_debt = compute_net_debt(borrowings, investments)
            asset_turnover = compute_asset_turnover(sales, total_assets)
            fcf = compute_free_cash_flow(cfo, cfi)
            cfo_quality, cfo_label = compute_cfo_quality(cfo, net_profit)
            capex = abs(cfi) if cfi is not None else 0
            capex_intensity, capex_label = compute_capex_intensity(capex, sales)
            fcf_conv = compute_fcf_conversion(fcf, op_profit)

            shares_outstanding = (row.get('equity_capital') or 0) / face_value if face_value > 0 else 0
            bvps = (equity / shares_outstanding) if shares_outstanding > 0 else None

            record = {
                'company_id': company_id,
                'year': year,
                'net_profit_margin_pct': npm,
                'operating_profit_margin_pct': opm,
                'return_on_equity_pct': roe,
                'return_on_capital_pct': roce,
                'debt_to_equity': de,
                'interest_coverage': icr,
                'asset_turnover': asset_turnover,
                'free_cash_flow': fcf,
                'capex': capex,
                'earnings_per_share': eps,
                'book_value_per_share': bvps,
                'dividend_payout_ratio_pct': dividend_payout,
                'total_debt': borrowings,
                'cash_from_operations': cfo,
                'high_leverage_flag': 1 if high_lev else 0,
                'icr_label': icr_label,
                'icr_warning_flag': 1 if icr_warn else 0,
                'cfo_quality_label': cfo_label,
                'capex_intensity_label': capex_label,
                'capital_allocation_pattern': alloc_pattern,
            }
            records.append(record)

    # Insert into financial_ratios table (replace existing)
    if records:
        df_ratios = pd.DataFrame(records)
        # Drop existing rows to avoid duplicates
        cursor.execute("DELETE FROM financial_ratios")
        df_ratios.to_sql('financial_ratios', conn, if_exists='append', index=False)
        total_updated = len(df_ratios)
        logger.info(f"Inserted {total_updated} rows into financial_ratios")

    # Now compute CAGR per company using the existing data in financial_ratios
    logger.info("Computing CAGR and updating financial_ratios...")

    # For each company, get time series of sales, net_profit, eps from profitandloss table
    for company_id in company_ids:
        pl_series = pd.read_sql(
            "SELECT year, sales, net_profit, eps FROM profitandloss WHERE company_id = ? ORDER BY year",
            conn, params=(company_id,)
        )
        if len(pl_series) < 3:
            continue
        years = pl_series['year'].tolist()
        sales_vals = pl_series['sales'].tolist()
        pat_vals = pl_series['net_profit'].tolist()
        eps_vals = pl_series['eps'].tolist()

        # Compute CAGR for each window
        for window in [3, 5, 10]:
            if len(sales_vals) >= window + 1:
                # Use last window years
                cagr_sales, flag_sales = compute_cagr(sales_vals[-window-1], sales_vals[-1], window)
                cagr_pat, flag_pat = compute_cagr(pat_vals[-window-1], pat_vals[-1], window)
                cagr_eps, flag_eps = compute_cagr(eps_vals[-window-1], eps_vals[-1], window)

                # Update the most recent year's row for this company with CAGR values
                latest_year = years[-1]
                col_sales = f'revenue_cagr_{window}yr'
                col_pat = f'pat_cagr_{window}yr'
                col_eps = f'eps_cagr_{window}yr'
                flag_sales_col = f'revenue_cagr_{window}yr_flag'
                flag_pat_col = f'pat_cagr_{window}yr_flag'
                flag_eps_col = f'eps_cagr_{window}yr_flag'

                update_sql = f"""
                    UPDATE financial_ratios
                    SET {col_sales} = ?,
                        {flag_sales_col} = ?,
                        {col_pat} = ?,
                        {flag_pat_col} = ?,
                        {col_eps} = ?,
                        {flag_eps_col} = ?
                    WHERE company_id = ? AND year = ?
                """
                cursor.execute(update_sql, (cagr_sales, flag_sales, cagr_pat, flag_pat, cagr_eps, flag_eps, company_id, latest_year))

    conn.commit()

    # Export capital allocation to CSV
    if capital_alloc_records:
        df_cap = pd.DataFrame(capital_alloc_records)
        df_cap.to_csv(OUTPUT_DIR / 'capital_allocation.csv', index=False)
        logger.info(f"Exported capital allocation to {OUTPUT_DIR / 'capital_allocation.csv'}")

    # Export edge case log
    if edge_case_log:
        with open(OUTPUT_DIR / 'ratio_edge_cases.log', 'w') as f:
            for entry in edge_case_log:
                f.write(entry + '\n')
        logger.info(f"Exported edge case log to {OUTPUT_DIR / 'ratio_edge_cases.log'}")

    # Verify row count
    count = cursor.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    logger.info(f"Total rows in financial_ratios: {count}")

    # Spot-check ROE and Revenue CAGR for 3 companies
    sample_companies = ['TCS', 'RELIANCE', 'HDFCBANK']
    for ticker in sample_companies:
        row = cursor.execute(
            "SELECT year, return_on_equity_pct, revenue_cagr_5yr FROM financial_ratios WHERE company_id = ? ORDER BY year DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        if row:
            logger.info(f"{ticker} latest ROE: {row[1]}, Revenue CAGR 5yr: {row[2]}")

    conn.close()

if __name__ == "__main__":
    populate_financial_ratios()