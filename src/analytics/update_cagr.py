import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.analytics.cagr import compute_cagr
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path("data/nifty100.db")

def update_cagr():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Get all companies
    companies = cursor.execute("SELECT id FROM companies").fetchall()
    for (company_id,) in companies:
        # Get P&L series
        rows = cursor.execute("""
            SELECT year, sales, net_profit, eps
            FROM profitandloss
            WHERE company_id = ?
            ORDER BY year
        """, (company_id,)).fetchall()
        if len(rows) < 3:
            continue
        years = [r[0] for r in rows]
        sales_vals = [r[1] for r in rows]
        pat_vals = [r[2] for r in rows]
        eps_vals = [r[3] for r in rows]

        # For each window
        for window in [3, 5, 10]:
            if len(sales_vals) >= window + 1:
                cagr_sales, flag_sales = compute_cagr(sales_vals[-window-1], sales_vals[-1], window)
                cagr_pat, flag_pat = compute_cagr(pat_vals[-window-1], pat_vals[-1], window)
                cagr_eps, flag_eps = compute_cagr(eps_vals[-window-1], eps_vals[-1], window)

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
    conn.close()
    logger.info("CAGR update complete")

if __name__ == "__main__":
    update_cagr()