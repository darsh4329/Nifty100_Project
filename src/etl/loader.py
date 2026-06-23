"""
Main ETL Loader for Nifty 100 Financial Intelligence Platform.
Loads all 7 core + 5 supplementary datasets into SQLite database.
"""

import os
import sys
import sqlite3
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.etl.normaliser import (
    normalize_year, 
    normalize_ticker, 
    normalize_company_id,
    load_excel_with_header
)
from src.etl.validator import (
    DataQualityValidator, 
    export_validation_results,
    generate_load_audit
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
RAW_DATA_DIR = Path("data/raw")
SUPPORTING_DATA_DIR = Path("data/supporting")
DB_PATH = Path("data/nifty100.db")
OUTPUT_DIR = Path("output")

# Core datasets (header=1)
CORE_DATASETS = {
    'companies': {
        'file': RAW_DATA_DIR / 'companies.xlsx',
        'header': 1,
        'pk': 'id',
        'normalise': {'id': normalize_ticker}
    },
    'profitandloss': {
        'file': RAW_DATA_DIR / 'profitandloss.xlsx',
        'header': 1,
        'pk': ('company_id', 'year'),
        'normalise': {'company_id': normalize_ticker, 'year': normalize_year}
    },
    'balancesheet': {
        'file': RAW_DATA_DIR / 'balancesheet.xlsx',
        'header': 1,
        'pk': ('company_id', 'year'),
        'normalise': {'company_id': normalize_ticker, 'year': normalize_year}
    },
    'cashflow': {
        'file': RAW_DATA_DIR / 'cashflow.xlsx',
        'header': 1,
        'pk': ('company_id', 'year'),
        'normalise': {'company_id': normalize_ticker, 'year': normalize_year}
    },
    'analysis': {
        'file': RAW_DATA_DIR / 'analysis.xlsx',
        'header': 1,
        'pk': 'id',
        'normalise': {'company_id': normalize_ticker}
    },
    'documents': {
        'file': RAW_DATA_DIR / 'documents.xlsx',
        'header': 1,
        'pk': ('company_id', 'year'),
        'normalise': {'company_id': normalize_ticker}
    },
    'prosandcons': {
        'file': RAW_DATA_DIR / 'prosandcons.xlsx',
        'header': 1,
        'pk': 'id',
        'normalise': {'company_id': normalize_ticker}
    }
}

# Supplementary datasets (header=0)
SUPPLEMENTARY_DATASETS = {
    'sectors': {
        'file': SUPPORTING_DATA_DIR / 'sectors.xlsx',
        'header': 0,
        'pk': 'company_id',
        'normalise': {'company_id': normalize_ticker}
    },
    'stock_prices': {
        'file': SUPPORTING_DATA_DIR / 'stock_prices.xlsx',
        'header': 0,
        'pk': ('company_id', 'date'),
        'normalise': {'company_id': normalize_ticker}
    },
    'market_cap': {
        'file': SUPPORTING_DATA_DIR / 'market_cap.xlsx',
        'header': 0,
        'pk': ('company_id', 'year'),
        'normalise': {'company_id': normalize_ticker}
    },
    'financial_ratios': {
        'file': SUPPORTING_DATA_DIR / 'financial_ratios.xlsx',
        'header': 0,
        'pk': ('company_id', 'year'),
        'normalise': {'company_id': normalize_ticker, 'year': normalize_year}
    },
    'peer_groups': {
        'file': SUPPORTING_DATA_DIR / 'peer_groups.xlsx',
        'header': 0,
        'pk': ('company_id', 'peer_group_name'),
        'normalise': {'company_id': normalize_ticker}
    }
}

# All datasets combined
ALL_DATASETS = {**CORE_DATASETS, **SUPPLEMENTARY_DATASETS}

# Table creation order (FK dependencies)
TABLE_ORDER = [
    'companies',
    'profitandloss', 'balancesheet', 'cashflow',
    'analysis', 'documents', 'prosandcons',
    'sectors', 'stock_prices', 'market_cap',
    'financial_ratios', 'peer_groups',
    'peer_percentiles', 'capital_allocation', 'screener_results'
]


class Nifty100Loader:
    """Main ETL loader class."""
    
    def __init__(self, db_path: str = "data/nifty100.db", output_dir: str = "output"):
        self.db_path = Path(db_path)
        self.output_dir = Path(output_dir)
        self.conn = None
        self.cursor = None
        self.load_stats = {}
        self.validation_results = []
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def connect(self):
        """Establish database connection."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        logger.info(f"Connected to database: {self.db_path}")
        
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
            
    def create_schema(self, schema_path: str = "db/schema.sql"):
        """Create all tables using schema.sql."""
        schema_file = Path(schema_path)
        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_path}")
            return False
            
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
            
        # Split by semicolon and execute each statement
        statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
        
        for stmt in statements:
            try:
                self.cursor.execute(stmt)
            except sqlite3.OperationalError as e:
                logger.warning(f"Schema statement error (may be normal): {e}")
                
        self.conn.commit()
        logger.info("Database schema created/verified")
        return True
        
    def load_dataset(self, table_name: str, dataset_config: Dict[str, Any]) -> Dict[str, Any]:
        """Load a single dataset into the database."""
        start_time = time.time()
        stats = {
            'table': table_name,
            'rows_in': 0,
            'rows_loaded': 0,
            'rows_out': 0,
            'runtime_sec': 0,
            'status': 'UNKNOWN'
        }
        
        file_path = dataset_config.get('file')
        if not file_path or not Path(file_path).exists():
            logger.error(f"File not found: {file_path}")
            stats['status'] = 'FILE_NOT_FOUND'
            return stats
            
        try:
            # Load Excel
            header = dataset_config.get('header', 1)
            df = load_excel_with_header(str(file_path), header_row=header)
            stats['rows_in'] = len(df)
            
            # Normalise columns
            normalise_map = dataset_config.get('normalise', {})
            for col, func in normalise_map.items():
                if col in df.columns:
                    df[col] = df[col].apply(func)
                    
            # Clean column names to match schema
            df.columns = df.columns.str.lower().str.replace(' ', '_')
            
            # Remove duplicates
            pk = dataset_config.get('pk')
            if pk:
                if isinstance(pk, tuple):
                    pk_cols = list(pk)
                else:
                    pk_cols = [pk]
                    
                # Check for duplicates
                dup_mask = df.duplicated(subset=pk_cols, keep='last')
                if dup_mask.any():
                    logger.warning(f"Found {dup_mask.sum()} duplicate rows in {table_name}, keeping last")
                    df = df[~dup_mask]
                    
            stats['rows_loaded'] = len(df)
            
            # Load into SQLite
            if len(df) > 0:
                df.to_sql(table_name, self.conn, if_exists='replace', index=False)
                stats['rows_out'] = len(df)
                stats['status'] = 'SUCCESS'
                logger.info(f"Loaded {len(df)} rows into {table_name}")
            else:
                stats['status'] = 'EMPTY'
                logger.warning(f"No data to load for {table_name}")
                
        except Exception as e:
            logger.error(f"Error loading {table_name}: {e}")
            stats['status'] = f'ERROR: {str(e)}'
            
        stats['runtime_sec'] = time.time() - start_time
        return stats
        
    def run_full_load(self) -> Dict[str, Any]:
        """Run full ETL load for all 12 datasets."""
        logger.info("=" * 60)
        logger.info("Starting Nifty 100 Full Data Load")
        logger.info("=" * 60)
        
        # Create schema first
        self.create_schema()
        
        # Load in correct order (companies first for FK)
        load_order = ['companies'] + [t for t in ALL_DATASETS.keys() if t != 'companies']
        
        for table_name in load_order:
            if table_name not in ALL_DATASETS:
                logger.warning(f"Skipping unknown table: {table_name}")
                continue
                
            logger.info(f"Loading {table_name}...")
            stats = self.load_dataset(table_name, ALL_DATASETS[table_name])
            self.load_stats[table_name] = stats
            
            # Verify row count
            try:
                count = self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                logger.info(f"  → {count} rows in {table_name}")
            except sqlite3.OperationalError:
                pass
                
        self.conn.commit()
        logger.info("=" * 60)
        logger.info("Full data load completed")
        logger.info("=" * 60)
        
        return self.load_stats
        
    def run_validation(self, df_companies=None, df_pl=None, df_bs=None, df_cf=None, df_docs=None):
        """Run data quality validation."""
        logger.info("Running data quality validation...")
        
        validator = DataQualityValidator(str(self.db_path))
        validator.connect()
        
        # Load dataframes if not provided
        if df_companies is None:
            df_companies = pd.read_sql("SELECT * FROM companies", self.conn)
        if df_pl is None:
            df_pl = pd.read_sql("SELECT * FROM profitandloss", self.conn)
        if df_bs is None:
            df_bs = pd.read_sql("SELECT * FROM balancesheet", self.conn)
        if df_cf is None:
            df_cf = pd.read_sql("SELECT * FROM cashflow", self.conn)
        if df_docs is None:
            df_docs = pd.read_sql("SELECT * FROM documents", self.conn)
            
        results = validator.run_all_rules(
            df_companies=df_companies,
            df_pl=df_pl,
            df_bs=df_bs,
            df_cf=df_cf,
            df_docs=df_docs
        )
        
        validator.close()
        
        # Export results
        export_validation_results(results, str(self.output_dir / "validation_failures.csv"))
        
        # Check for CRITICAL failures
        critical_failures = [r for r in results if r['severity'] == 'CRITICAL' and r['status'] == 'FAIL']
        if critical_failures:
            logger.error(f"Found {len(critical_failures)} CRITICAL validation failures")
            for r in critical_failures:
                logger.error(f"  {r['rule_id']}: {r['details']}")
        else:
            logger.info("✓ All CRITICAL validation rules passed")
            
        self.validation_results = results
        return results
        
    def export_audit(self):
        """Export load audit to CSV."""
        generate_load_audit(self.load_stats, str(self.output_dir / "load_audit.csv"))
        logger.info(f"Load audit exported to {self.output_dir / 'load_audit.csv'}")
        
    def verify_fk(self) -> bool:
        """Verify foreign key integrity."""
        result = self.cursor.execute("PRAGMA foreign_key_check").fetchall()
        if result:
            logger.warning(f"FK violations found: {len(result)}")
            for row in result:
                logger.warning(f"  {row}")
            return False
        else:
            logger.info("✓ Foreign key check passed (0 violations)")
            return True


def main():
    """Main entry point."""
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize loader
    loader = Nifty100Loader(str(DB_PATH), str(OUTPUT_DIR))
    
    try:
        loader.connect()
        
        # Run full load
        load_stats = loader.run_full_load()
        
        # Verify FK
        fk_ok = loader.verify_fk()
        
        # Run validation
        validation_results = loader.run_validation()
        
        # Export audit
        loader.export_audit()
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("LOAD SUMMARY")
        logger.info("=" * 60)
        for table, stats in load_stats.items():
            logger.info(f"  {table:20s} {stats.get('rows_out', 0):>8,d} rows  [{stats.get('status', 'UNKNOWN')}]")
            
        # Critical failures check
        critical = [r for r in validation_results if r['severity'] == 'CRITICAL' and r['status'] == 'FAIL']
        if critical:
            logger.error(f"\n⚠️  {len(critical)} CRITICAL validation failures detected!")
            logger.error("Please review output/validation_failures.csv")
        else:
            logger.info("\n✓ All CRITICAL validation rules passed - database is ready!")
            
        logger.info(f"\nDatabase: {DB_PATH}")
        logger.info(f"Validation report: {OUTPUT_DIR / 'validation_failures.csv'}")
        logger.info(f"Load audit: {OUTPUT_DIR / 'load_audit.csv'}")
        
    except Exception as e:
        logger.error(f"Fatal error during load: {e}")
        raise
    finally:
        loader.close()


if __name__ == "__main__":
    main()