"""
NGX Data System Setup & Population
Run this script to set up database and populate with initial data
"""
import sys
sys.path.append('.')

import os
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
from loguru import logger
from decimal import Decimal

# Import our modules
from database.models import (
    create_database_engine, init_database, get_session, seed_companies,
    Company, StockPrice, InflationData, MacroIndicator
)
from scrapers.price_scraper import NGXPriceScraper
from scrapers.financial_scraper import FinancialScraper
from calculators.inflation_calculator import InflationCalculator

# Configure logging
logger.add("logs/setup_{time}.log", rotation="1 day", retention="7 days")


class NGXDataSetup:
    """
    Master class for setting up and populating NGX data system
    """
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_database_engine(database_url)
        self.session = get_session(self.engine)
        
        self.price_scraper = NGXPriceScraper()
        self.financial_scraper = FinancialScraper()
        self.calculator = InflationCalculator(database_url)
    
    def setup_database(self):
        """Create all database tables"""
        logger.info("Setting up database...")
        init_database(self.engine)
        logger.info("✅ Database tables created")
    
    def seed_initial_data(self):
        """Seed initial companies and basic data"""
        logger.info("Seeding initial data...")
        seed_companies(self.session)
        logger.info("✅ Initial data seeded")
    
    def populate_inflation_data(self, years_back: int = 10):
        """
        Populate inflation data
        For MVP, uses representative values
        In production, scrape from NBS Nigeria
        """
        logger.info(f"Populating inflation data ({years_back} years)...")
        
        # Nigerian inflation data (representative values for development)
        # In production, scrape from https://www.nigerianstat.gov.ng/
        
        end_date = date.today()
        start_date = end_date - timedelta(days=years_back * 365)
        
        current_date = start_date
        inflation_records = []
        
        # Generate monthly inflation data
        # Uses realistic Nigerian inflation trajectory
        while current_date <= end_date:
            year = current_date.year
            
            # Model Nigerian inflation trend (simplified)
            if year <= 2015:
                base_inflation = 8.0
            elif year <= 2020:
                base_inflation = 12.0
            elif year <= 2023:
                base_inflation = 18.0
            else:
                base_inflation = 22.0
            
            # Add seasonal variation
            month_factor = 1.0 + (current_date.month % 12) * 0.02
            headline_cpi = base_inflation * month_factor
            
            # Check if record exists
            existing = self.session.query(InflationData).filter_by(
                date=current_date
            ).first()
            
            if not existing:
                inflation_record = InflationData(
                    date=current_date,
                    headline_cpi=Decimal(str(round(headline_cpi, 2))),
                    food_inflation=Decimal(str(round(headline_cpi * 1.2, 2))),
                    core_inflation=Decimal(str(round(headline_cpi * 0.9, 2))),
                    source='Development Data (Replace with NBS)'
                )
                inflation_records.append(inflation_record)
            
            # Move to next month
            if current_date.month == 12:
                current_date = date(current_date.year + 1, 1, 1)
            else:
                current_date = date(current_date.year, current_date.month + 1, 1)
        
        if inflation_records:
            self.session.bulk_save_objects(inflation_records)
            self.session.commit()
            logger.info(f"✅ Populated {len(inflation_records)} inflation records")
        else:
            logger.info("Inflation data already exists")
    
    def populate_macro_data(self, years_back: int = 5):
        """
        Populate macro economic indicators
        """
        logger.info(f"Populating macro data ({years_back} years)...")
        
        end_date = date.today()
        start_date = end_date - timedelta(days=years_back * 365)
        
        current_date = start_date
        macro_records = []
        
        while current_date <= end_date:
            year = current_date.year
            
            # Model Nigerian macro trends (simplified)
            # MPR
            if year <= 2020:
                mpr = 13.5
            elif year <= 2022:
                mpr = 11.5
            else:
                mpr = 18.75
            
            # USD/NGN (official)
            if year <= 2015:
                usd_ngn = 200.0
            elif year <= 2020:
                usd_ngn = 360.0
            elif year <= 2023:
                usd_ngn = 750.0
            else:
                usd_ngn = 1550.0
            
            # Brent crude
            brent = 75.0 + (current_date.month % 12) * 2.0
            
            existing = self.session.query(MacroIndicator).filter_by(
                date=current_date
            ).first()
            
            if not existing:
                macro_record = MacroIndicator(
                    date=current_date,
                    mpr=Decimal(str(mpr)),
                    usd_ngn_official=Decimal(str(usd_ngn)),
                    usd_ngn_parallel=Decimal(str(usd_ngn * 1.05)),
                    treasury_bill_91d=Decimal(str(mpr - 2.0)),
                    treasury_bill_364d=Decimal(str(mpr - 1.0)),
                    brent_crude_usd=Decimal(str(brent)),
                    source='Development Data'
                )
                macro_records.append(macro_record)
            
            # Move to next month
            if current_date.month == 12:
                current_date = date(current_date.year + 1, 1, 1)
            else:
                current_date = date(current_date.year, current_date.month + 1, 1)
        
        if macro_records:
            self.session.bulk_save_objects(macro_records)
            self.session.commit()
            logger.info(f"✅ Populated {len(macro_records)} macro records")
        else:
            logger.info("Macro data already exists")
    
    def populate_stock_prices(self, years_back: int = 10):
        """
        Populate historical stock prices
        Uses fallback mock data for development
        """
        logger.info(f"Populating stock prices ({years_back} years)...")
        
        # Get all companies
        companies = self.session.query(Company).filter_by(is_active=True).all()
        
        for company in companies:
            logger.info(f"Populating prices for {company.ticker}")
            
            # Check if we already have recent data
            latest_price = self.session.query(StockPrice).filter_by(
                company_id=company.id
            ).order_by(StockPrice.date.desc()).first()
            
            if latest_price and latest_price.date >= date.today() - timedelta(days=7):
                logger.info(f"  {company.ticker} already has recent prices")
                continue
            
            # Generate historical prices (for development)
            # In production, this would scrape actual data
            self._generate_historical_prices(company, years_back)
        
        logger.info("✅ Stock prices populated")
    
    def _generate_historical_prices(self, company: Company, years_back: int):
        """
        Generate synthetic historical prices for development
        Models realistic price movements with growth trends
        """
        # Base prices for different stocks
        base_prices = {
            "GTCO": 30.0, "ZENITHBANK": 25.0, "ACCESSCORP": 12.0,
            "UBA": 15.0, "FBNH": 10.0, "STANBIC": 35.0, "FIDELITYBNK": 7.0,
            "DANGCEM": 200.0, "BUACEMENT": 60.0, "WAPCO": 20.0,
            "MTNN": 150.0, "AIRTELAFRI": 1000.0,
            "SEPLAT": 2000.0, "TOTAL": 300.0, "CONOIL": 40.0,
            "NESTLE": 600.0, "UNILEVER": 12.0, "FLOURMILL": 25.0, "NASCON": 18.0,
            "PRESCO": 150.0, "OKOMUOIL": 100.0,
        }
        
        # Growth rates (annual %)
        growth_rates = {
            "GTCO": 15.0, "ZENITHBANK": 18.0, "ACCESSCORP": 12.0,
            "DANGCEM": 20.0, "BUACEMENT": 25.0,
            "MTNN": 10.0, "AIRTELAFRI": 22.0,
            "SEPLAT": 15.0, "PRESCO": 18.0, "OKOMUOIL": 16.0,
        }
        
        ticker = company.ticker
        start_price = base_prices.get(ticker, 10.0)
        annual_growth = growth_rates.get(ticker, 8.0) / 100
        
        end_date = date.today()
        start_date = end_date - timedelta(days=years_back * 365)
        
        current_date = start_date
        current_price = start_price
        
        import random
        random.seed(hash(ticker))  # Consistent random for same ticker
        
        price_records = []
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            # Daily change: trend + noise
            daily_growth = (1 + annual_growth) ** (1/252) - 1
            daily_noise = random.gauss(0, 0.02)  # 2% volatility
            daily_change = daily_growth + daily_noise
            
            new_price = current_price * (1 + daily_change)
            
            # Ensure price stays positive
            new_price = max(new_price, start_price * 0.3)
            
            price_record = StockPrice(
                company_id=company.id,
                date=current_date,
                close=Decimal(str(round(new_price, 2))),
                open=Decimal(str(round(current_price, 2))),
                high=Decimal(str(round(max(current_price, new_price) * 1.01, 2))),
                low=Decimal(str(round(min(current_price, new_price) * 0.99, 2))),
                volume=random.randint(100000, 10000000),
                change=Decimal(str(round(new_price - current_price, 2))),
                change_percent=Decimal(str(round(daily_change * 100, 2))),
                source='Generated (Development)'
            )
            
            price_records.append(price_record)
            current_price = new_price
            current_date += timedelta(days=1)
        
        # Bulk insert
        self.session.bulk_save_objects(price_records)
        self.session.commit()
        
        logger.info(f"  Generated {len(price_records)} price records for {ticker}")
    
    def calculate_inflation_performance(self):
        """
        Calculate inflation performance for all stocks
        """
        logger.info("Calculating inflation performance metrics...")
        
        companies = self.session.query(Company).filter_by(is_active=True).all()
        tickers = [c.ticker for c in companies]
        
        results = self.calculator.batch_calculate_performance(tickers)
        
        successful = sum(1 for v in results.values() if v)
        logger.info(f"✅ Performance calculated: {successful}/{len(tickers)} stocks")
    
    def run_full_setup(self):
        """
        Run complete setup process
        """
        logger.info("=" * 60)
        logger.info("NGX Data System - Full Setup")
        logger.info("=" * 60)
        
        try:
            # Step 1: Database
            self.setup_database()
            
            # Step 2: Initial data
            self.seed_initial_data()
            
            # Step 3: Inflation data
            self.populate_inflation_data(years_back=10)
            
            # Step 4: Macro data
            self.populate_macro_data(years_back=5)
            
            # Step 5: Stock prices
            self.populate_stock_prices(years_back=10)
            
            # Step 6: Calculate performance
            self.calculate_inflation_performance()
            
            logger.info("=" * 60)
            logger.info("✅ Setup Complete!")
            logger.info("=" * 60)
            
            # Print summary
            self.print_summary()
            
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            raise
    
    def print_summary(self):
        """Print database summary"""
        companies_count = self.session.query(Company).count()
        prices_count = self.session.query(StockPrice).count()
        inflation_count = self.session.query(InflationData).count()
        
        print("\n" + "=" * 60)
        print("DATABASE SUMMARY")
        print("=" * 60)
        print(f"Companies:      {companies_count:,}")
        print(f"Price Records:  {prices_count:,}")
        print(f"Inflation Data: {inflation_count:,} months")
        print("=" * 60)
        
        # Show inflation beaters
        beaters = self.calculator.get_inflation_beaters()
        
        if beaters:
            print("\nTOP INFLATION-BEATING STOCKS:")
            print("-" * 60)
            for i, stock in enumerate(beaters[:10], 1):
                print(f"{i:2}. {stock['ticker']:12} | "
                      f"3yr excess: {stock['excess_return_3yr']:+6.2f}% | "
                      f"{stock['name']}")
            print("=" * 60)
    
    def close(self):
        """Cleanup"""
        self.session.close()
        self.calculator.close()


def main():
    """Main entry point"""
    load_dotenv()
    
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://ngx_user:ngx_password@localhost:5432/ngx_data"
    )
    
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║           NGX DATA SYSTEM SETUP & POPULATION              ║
║                                                            ║
║  This will:                                                ║
║  1. Create database tables                                 ║
║  2. Seed 20+ NGX companies                                 ║
║  3. Populate 10 years of inflation data                    ║
║  4. Populate 10 years of stock prices                      ║
║  5. Calculate inflation performance metrics                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    response = input("Continue with setup? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Setup cancelled")
        return
    
    setup = NGXDataSetup(DATABASE_URL)
    
    try:
        setup.run_full_setup()
    finally:
        setup.close()


if __name__ == "__main__":
    main()
