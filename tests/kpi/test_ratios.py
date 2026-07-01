import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.analytics.ratios import *
from src.analytics.cagr import compute_cagr
from src.analytics.cashflow_kpis import *

class TestProfitability:
    def test_npm_normal(self):
        assert compute_npm(100, 200) == 50.0

    def test_npm_zero_sales(self):
        assert compute_npm(100, 0) is None

    def test_npm_none_sales(self):
        assert compute_npm(100, None) is None

    def test_npm_negative_profit(self):
        assert compute_npm(-50, 200) == -25.0

    def test_opm_normal(self):
        assert compute_opm(50, 200) == 25.0

    def test_opm_zero_sales(self):
        assert compute_opm(50, 0) is None

    def test_roe_normal(self):
        assert compute_roe(20, 100) == 20.0

    def test_roe_negative_equity(self):
        assert compute_roe(20, -50) is None

    def test_roe_zero_equity(self):
        assert compute_roe(20, 0) is None

    def test_roce_normal(self):
        assert compute_roce(30, 100, 50) == 20.0  # 30/150*100

    def test_roce_zero_capital(self):
        assert compute_roce(30, 0, 0) is None

    def test_roa_normal(self):
        assert compute_roa(20, 400) == 5.0

    def test_roa_zero_assets(self):
        assert compute_roa(20, 0) is None

class TestLeverage:
    def test_de_positive(self):
        assert compute_debt_to_equity(50, 100) == 0.5

    def test_de_zero_borrowings(self):
        assert compute_debt_to_equity(0, 100) == 0.0

    def test_de_negative_equity(self):
        assert compute_debt_to_equity(50, -100) == 0.0

    def test_icr_normal(self):
        val, label, warn = compute_interest_coverage(100, 20, 10)
        assert val == 12.0
        assert label is None
        assert warn is False

    def test_icr_debt_free(self):
        val, label, warn = compute_interest_coverage(100, 20, 0)
        assert val is None
        assert label == 'Debt Free'
        assert warn is False

    def test_icr_no_earnings(self):
        val, label, warn = compute_interest_coverage(0, 0, 10)
        assert val == 0.0
        assert label == 'No Earnings'
        assert warn is True

    def test_high_leverage_flag(self):
        assert high_leverage_flag(6, 'Consumer') is True
        assert high_leverage_flag(6, 'Financials') is False

class TestCAGR:
    def test_cagr_normal(self):
        val, flag = compute_cagr(100, 121, 2)
        assert round(val, 2) == 10.0
        assert flag is None

    def test_cagr_turnaround(self):
        val, flag = compute_cagr(-100, 200, 2)
        assert val is None
        assert flag == 'TURNAROUND'

    def test_cagr_decline_to_loss(self):
        val, flag = compute_cagr(100, -50, 2)
        assert val is None
        assert flag == 'DECLINE_TO_LOSS'

    def test_cagr_both_negative(self):
        val, flag = compute_cagr(-100, -50, 2)
        assert val is None
        assert flag == 'BOTH_NEGATIVE'

    def test_cagr_zero_base(self):
        val, flag = compute_cagr(0, 100, 2)
        assert val is None
        assert flag == 'ZERO_BASE'

    def test_cagr_insufficient(self):
        val, flag = compute_cagr(100, 121, 0)
        assert val is None
        assert flag == 'INSUFFICIENT'

class TestCashFlow:
    def test_fcf(self):
        assert compute_free_cash_flow(100, -30) == 70

    def test_cfo_quality_high(self):
        ratio, label = compute_cfo_quality(150, 100)
        assert ratio == 1.5
        assert label == 'High Quality'

    def test_cfo_quality_moderate(self):
        ratio, label = compute_cfo_quality(75, 100)
        assert ratio == 0.75
        assert label == 'Moderate'

    def test_cfo_quality_accrual(self):
        ratio, label = compute_cfo_quality(40, 100)
        assert ratio == 0.4
        assert label == 'Accrual Risk'

    def test_capex_intensity_light(self):
        pct, label = compute_capex_intensity(10, 1000)
        assert pct == 1.0
        assert label == 'Asset Light'

    def test_capex_intensity_moderate(self):
        pct, label = compute_capex_intensity(50, 1000)
        assert pct == 5.0
        assert label == 'Moderate'

    def test_capex_intensity_heavy(self):
        pct, label = compute_capex_intensity(100, 1000)
        assert pct == 10.0
        assert label == 'Capital Intensive'

    def test_fcf_conversion(self):
        assert compute_fcf_conversion(70, 100) == 70.0

    def test_fcf_conversion_zero_op(self):
        assert compute_fcf_conversion(70, 0) is None

    def test_capital_allocation_patterns(self):
        assert classify_capital_allocation(100, -30, -20) == 'Reinvestor'
        assert classify_capital_allocation(100, -30, 20) == 'Mixed'
        assert classify_capital_allocation(-100, 50, 30) == 'Distress Signal'
        assert classify_capital_allocation(100, 50, -30) == 'Liquidating Assets'