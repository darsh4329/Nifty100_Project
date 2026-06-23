-- ============================================================
-- Nifty 100 Financial Intelligence Platform
-- Exploratory Queries - Sprint 1
-- ============================================================

-- Q1: Company count
SELECT COUNT(*) AS total_companies FROM companies;

-- Q2: Year coverage by company
SELECT 
    c.id,
    c.company_name,
    COUNT(DISTINCT p.year) AS pl_years,
    COUNT(DISTINCT b.year) AS bs_years,
    COUNT(DISTINCT cf.year) AS cf_years
FROM companies c
LEFT JOIN profitandloss p ON c.id = p.company_id
LEFT JOIN balancesheet b ON c.id = b.company_id
LEFT JOIN cashflow cf ON c.id = cf.company_id
GROUP BY c.id
ORDER BY pl_years DESC;

-- Q3: Companies with <5 years of P&L data
SELECT 
    c.id,
    c.company_name,
    COUNT(p.year) AS years
FROM companies c
LEFT JOIN profitandloss p ON c.id = p.company_id
GROUP BY c.id
HAVING years < 5
ORDER BY years;

-- Q4: Sector distribution
SELECT 
    broad_sector,
    COUNT(*) AS company_count,
    ROUND(AVG(index_weight_pct), 2) AS avg_index_weight
FROM sectors
GROUP BY broad_sector
ORDER BY company_count DESC;

-- Q5: Balance sheet quality check
SELECT 
    company_id,
    year,
    total_assets,
    total_liabilities,
    ROUND(ABS(total_assets - total_liabilities) / NULLIF(total_assets, 0) * 100, 2) AS diff_pct
FROM balancesheet
WHERE total_assets > 0
  AND ABS(total_assets - total_liabilities) / total_assets > 0.01
ORDER BY diff_pct DESC
LIMIT 20;

-- Q6: Cash flow sum check
SELECT 
    company_id,
    year,
    operating_activity,
    investing_activity,
    financing_activity,
    operating_activity + investing_activity + financing_activity AS computed_net,
    net_cash_flow,
    ROUND(ABS(net_cash_flow - (operating_activity + investing_activity + financing_activity)), 2) AS diff
FROM cashflow
WHERE ABS(net_cash_flow - (operating_activity + investing_activity + financing_activity)) > 10
ORDER BY diff DESC
LIMIT 20;

-- Q7: Most profitable companies (latest year)
WITH latest AS (
    SELECT 
        company_id,
        MAX(year) AS latest_year
    FROM profitandloss
    GROUP BY company_id
)
SELECT 
    p.company_id,
    c.company_name,
    p.year,
    p.sales,
    p.net_profit,
    ROUND(p.net_profit / p.sales * 100, 2) AS npm
FROM profitandloss p
JOIN latest l ON p.company_id = l.company_id AND p.year = l.latest_year
JOIN companies c ON p.company_id = c.id
WHERE p.sales > 0
ORDER BY npm DESC
LIMIT 20;

-- Q8: Debt-free companies (latest year)
WITH latest AS (
    SELECT 
        company_id,
        MAX(year) AS latest_year
    FROM balancesheet
    GROUP BY company_id
)
SELECT 
    b.company_id,
    c.company_name,
    b.year,
    b.borrowings,
    b.equity_capital + b.reserves AS total_equity,
    ROUND(b.borrowings / NULLIF(b.equity_capital + b.reserves, 0), 2) AS debt_to_equity
FROM balancesheet b
JOIN latest l ON b.company_id = l.company_id AND b.year = l.latest_year
JOIN companies c ON b.company_id = c.id
WHERE b.borrowings = 0
ORDER BY c.company_name;

-- Q9: Document coverage
SELECT 
    c.id,
    c.company_name,
    COUNT(d.year) AS doc_count,
    COUNT(DISTINCT d.year) AS distinct_years,
    MIN(d.year) AS earliest,
    MAX(d.year) AS latest
FROM companies c
LEFT JOIN documents d ON c.id = d.company_id
GROUP BY c.id
ORDER BY doc_count DESC;

-- Q10: P&L - Balance Sheet - Cash Flow coverage overlap
SELECT 
    c.id,
    c.company_name,
    COUNT(DISTINCT p.year) AS pl_years,
    COUNT(DISTINCT b.year) AS bs_years,
    COUNT(DISTINCT cf.year) AS cf_years,
    COUNT(DISTINCT p.year || b.year || cf.year) AS overlap
FROM companies c
LEFT JOIN profitandloss p ON c.id = p.company_id
LEFT JOIN balancesheet b ON c.id = b.company_id AND b.year = p.year
LEFT JOIN cashflow cf ON c.id = cf.company_id AND cf.year = p.year
GROUP BY c.id
HAVING pl_years > 0
ORDER BY overlap;