"""
Database Models for NGX Data System
Includes: Companies, Prices, Financials, Inflation, Performance Tracking
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Float, Date,
    DateTime, Boolean, Text, ForeignKey, Numeric, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class Company(Base):
    """NGX Listed Company"""
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sector = Column(String(100), nullable=False, index=True)
    
    # Key attributes
    listing_date = Column(Date, nullable=True)
    has_fx_revenue = Column(Boolean, default=False)
    is_inflation_beater = Column(Boolean, default=False)
    market_cap_category = Column(String(50))  # Large, Mid, Small
    
    # Market (future-proofing for NYSE/NASDAQ)
    market = Column(String(10), default="NGX")
    currency = Column(String(3), default="NGN")

    # Metadata
    website = Column(String(200))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    prices = relationship("StockPrice", back_populates="company", cascade="all, delete-orphan")
    financials = relationship("Financial", back_populates="company", cascade="all, delete-orphan")
    performance = relationship("InflationPerformance", back_populates="company", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Company(ticker='{self.ticker}', name='{self.name}')>"


class StockPrice(Base):
    """Daily Stock Prices"""
    __tablename__ = 'stock_prices'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    
    # OHLCV data
    open = Column(Numeric(12, 2))
    high = Column(Numeric(12, 2))
    low = Column(Numeric(12, 2))
    close = Column(Numeric(12, 2), nullable=False)
    volume = Column(Integer)
    
    # Derived metrics
    change = Column(Numeric(12, 2))
    change_percent = Column(Numeric(8, 4))
    
    # Metadata
    source = Column(String(50))  # NGX, manual, API
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="prices")
    
    # Indexes
    __table_args__ = (
        Index('idx_company_date', 'company_id', 'date', unique=True),
    )
    
    def __repr__(self):
        return f"<StockPrice(ticker='{self.company.ticker}', date='{self.date}', close={self.close})>"


class Financial(Base):
    """Company Financials (Quarterly/Annual)"""
    __tablename__ = 'financials'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    
    # Period
    period_end = Column(Date, nullable=False)
    period_type = Column(String(10), nullable=False)  # Q1, Q2, Q3, Q4, FY
    fiscal_year = Column(Integer, nullable=False, index=True)
    
    # Income Statement (in Naira millions)
    revenue = Column(Numeric(18, 2))
    cost_of_revenue = Column(Numeric(18, 2))
    gross_profit = Column(Numeric(18, 2))
    operating_expenses = Column(Numeric(18, 2))
    operating_income = Column(Numeric(18, 2))
    net_income = Column(Numeric(18, 2))
    ebitda = Column(Numeric(18, 2))
    
    # Balance Sheet (in Naira millions)
    total_assets = Column(Numeric(18, 2))
    current_assets = Column(Numeric(18, 2))
    total_liabilities = Column(Numeric(18, 2))
    current_liabilities = Column(Numeric(18, 2))
    total_equity = Column(Numeric(18, 2))
    total_debt = Column(Numeric(18, 2))
    cash = Column(Numeric(18, 2))
    
    # Cash Flow (in Naira millions)
    operating_cash_flow = Column(Numeric(18, 2))
    investing_cash_flow = Column(Numeric(18, 2))
    financing_cash_flow = Column(Numeric(18, 2))
    free_cash_flow = Column(Numeric(18, 2))
    
    # Per Share Metrics
    eps = Column(Numeric(12, 4))  # Earnings per share
    book_value_per_share = Column(Numeric(12, 4))
    dividend_per_share = Column(Numeric(12, 4))
    
    # Ratios
    roe = Column(Numeric(8, 4))  # Return on Equity %
    roa = Column(Numeric(8, 4))  # Return on Assets %
    debt_to_equity = Column(Numeric(8, 4))
    current_ratio = Column(Numeric(8, 4))
    gross_margin = Column(Numeric(8, 4))
    net_margin = Column(Numeric(8, 4))
    
    # FX exposure
    fx_revenue_percentage = Column(Numeric(8, 2))  # % of revenue in FX
    fx_denominated_debt = Column(Numeric(18, 2))  # FX debt amount
    
    # Metadata
    source = Column(String(100))  # SEC filing, company report, etc
    currency = Column(String(3), default='NGN')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="financials")
    
    # Indexes
    __table_args__ = (
        Index('idx_company_fiscal', 'company_id', 'fiscal_year', 'period_type', unique=True),
    )
    
    def __repr__(self):
        return f"<Financial(ticker='{self.company.ticker}', period='{self.fiscal_year}-{self.period_type}')>"


class InflationData(Base):
    """Nigerian Inflation Rates (CPI)"""
    __tablename__ = 'inflation_data'
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    
    # Inflation rates
    headline_cpi = Column(Numeric(8, 4), nullable=False)  # Overall CPI
    food_inflation = Column(Numeric(8, 4))
    core_inflation = Column(Numeric(8, 4))
    
    # Month-over-month
    mom_change = Column(Numeric(8, 4))
    
    # Year-over-year
    yoy_change = Column(Numeric(8, 4))
    
    # Source
    source = Column(String(100), default='NBS Nigeria')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<InflationData(date='{self.date}', cpi={self.headline_cpi}%)>"


class MacroIndicator(Base):
    """Nigerian Macro Economic Indicators"""
    __tablename__ = 'macro_indicators'
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    
    # Central Bank
    mpr = Column(Numeric(8, 4))  # Monetary Policy Rate
    crar = Column(Numeric(8, 4))  # Cash Reserve Ratio
    liquidity_ratio = Column(Numeric(8, 4))
    
    # Foreign Exchange
    usd_ngn_official = Column(Numeric(12, 4))
    usd_ngn_parallel = Column(Numeric(12, 4))
    
    # Interest Rates
    treasury_bill_91d = Column(Numeric(8, 4))
    treasury_bill_182d = Column(Numeric(8, 4))
    treasury_bill_364d = Column(Numeric(8, 4))
    
    # Commodities
    brent_crude_usd = Column(Numeric(12, 4))
    
    # Source
    source = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<MacroIndicator(date='{self.date}', mpr={self.mpr}%)>"


class InflationPerformance(Base):
    """
    Pre-calculated inflation-beating performance metrics
    Updated periodically by calculators
    """
    __tablename__ = 'inflation_performance'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    calculation_date = Column(Date, nullable=False, index=True)
    
    # Returns (annualized %)
    return_1yr = Column(Numeric(12, 4))
    return_3yr = Column(Numeric(12, 4))
    return_5yr = Column(Numeric(12, 4))
    return_10yr = Column(Numeric(12, 4))
    
    # Inflation over same periods (annualized %)
    inflation_1yr = Column(Numeric(12, 4))
    inflation_3yr = Column(Numeric(12, 4))
    inflation_5yr = Column(Numeric(12, 4))
    inflation_10yr = Column(Numeric(12, 4))
    
    # Excess returns (stock return - inflation)
    excess_return_1yr = Column(Numeric(12, 4))
    excess_return_3yr = Column(Numeric(12, 4))
    excess_return_5yr = Column(Numeric(12, 4))
    excess_return_10yr = Column(Numeric(12, 4))
    
    # Dividends included
    dividend_yield_1yr = Column(Numeric(8, 4))
    total_return_1yr = Column(Numeric(12, 4))  # Price + dividends
    total_return_3yr = Column(Numeric(12, 4))
    total_return_5yr = Column(Numeric(12, 4))
    
    # Flags
    beats_inflation_1yr = Column(Boolean)
    beats_inflation_3yr = Column(Boolean)
    beats_inflation_5yr = Column(Boolean)
    beats_inflation_all = Column(Boolean)  # Beats in all 3 periods
    
    # Volatility (annualized standard deviation)
    volatility_1yr = Column(Numeric(12, 4))
    volatility_3yr = Column(Numeric(12, 4))
    
    # Sharpe-like ratio (excess return / volatility)
    risk_adjusted_return_1yr = Column(Numeric(12, 4))
    risk_adjusted_return_3yr = Column(Numeric(12, 4))
    
    # Ranking
    percentile_rank = Column(Integer)  # 1-100, relative to all stocks
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="performance")
    
    # Indexes
    __table_args__ = (
        Index('idx_company_calc_date', 'company_id', 'calculation_date', unique=True),
        Index('idx_inflation_beaters', 'beats_inflation_all', 'excess_return_3yr'),
    )
    
    def __repr__(self):
        return f"<InflationPerformance(ticker='{self.company.ticker}', 3yr={self.excess_return_3yr}%)>"


class DataQuality(Base):
    """Track data quality and completeness"""
    __tablename__ = 'data_quality'
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    
    # Coverage metrics
    companies_tracked = Column(Integer)
    prices_available = Column(Integer)
    financials_current = Column(Integer)
    
    # Quality scores (0-100)
    price_data_quality = Column(Integer)
    financial_data_quality = Column(Integer)
    overall_quality_score = Column(Integer)
    
    # Alerts
    missing_data_alerts = Column(Text)
    stale_data_alerts = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class ConversationHistory(Base):
    """Per-user conversation history for Claude context window"""
    __tablename__ = 'conversation_history'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    command = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_conv_user_time', 'telegram_id', 'created_at'),
    )


class Watchlist(Base):
    """User price alert subscriptions"""
    __tablename__ = 'watchlist'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    ticker = Column(String(20), nullable=False)
    alert_price_above = Column(Numeric(12, 2), nullable=True)
    alert_price_below = Column(Numeric(12, 2), nullable=True)
    is_active = Column(Boolean, default=True)
    triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('telegram_id', 'ticker', name='uq_user_ticker_watch'),
    )


class UserFeedback(Base):
    """Analysis quality ratings from users"""
    __tablename__ = 'user_feedback'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    command = Column(String(50), nullable=False)
    ticker = Column(String(20), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SyncLog(Base):
    """Data sync execution records"""
    __tablename__ = 'sync_log'

    id = Column(Integer, primary_key=True)
    sync_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    records_affected = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# Database initialization functions
def create_database_engine(database_url: str):
    """Create database engine"""
    if not database_url:
        raise ValueError("DATABASE_URL is not set. Add it to Railway environment variables.")
    if database_url.startswith("sqlite"):
        return create_engine(database_url, echo=False, connect_args={"check_same_thread": False})
    # pg8000 doesn't support pool_pre_ping the same way; use basic args for it
    is_pg8000 = "pg8000" in database_url
    return create_engine(
        database_url,
        echo=False,
        pool_size=3,
        max_overflow=5,
        pool_timeout=30,
        pool_pre_ping=not is_pg8000,
    )


def init_database(engine):
    """Initialize all tables (market data + bot user tables)"""
    # Import bot models so they register with Base before create_all
    from database import bot_db as _  # noqa: F401
    Base.metadata.create_all(engine)
    print("✅ Database tables created successfully")


def get_session(engine):
    """Get database session"""
    Session = sessionmaker(bind=engine)
    return Session()


# Helper function to seed initial companies
def seed_companies(session):
    """Seed database with top 20 NGX companies"""
    companies_data = [
        # Banking
        ("GTCO", "Guaranty Trust Holding Co.", "Banking", date(1996, 9, 20), True, "Large"),
        ("ZENITHBANK", "Zenith Bank", "Banking", date(2004, 10, 21), True, "Large"),
        ("ACCESSCORP", "Access Holdings", "Banking", date(1998, 2, 3), True, "Large"),
        ("UBA", "United Bank for Africa", "Banking", date(1970, 8, 10), True, "Large"),
        ("FBNH", "FBN Holdings", "Banking", date(2012, 11, 26), False, "Large"),
        ("STANBIC", "Stanbic IBTC Holdings", "Banking", date(2012, 11, 20), True, "Mid"),
        ("FIDELITYBNK", "Fidelity Bank", "Banking", date(2005, 5, 24), False, "Mid"),
        
        # Cement
        ("DANGCEM", "Dangote Cement", "Cement", date(2010, 10, 26), True, "Large"),
        ("BUACEMENT", "BUA Cement", "Cement", date(2020, 1, 17), True, "Large"),
        ("WAPCO", "Lafarge Africa", "Cement", date(1979, 1, 1), False, "Mid"),
        
        # Telecoms
        ("MTNN", "MTN Nigeria", "Telecoms", date(2019, 5, 16), True, "Large"),
        ("AIRTELAFRI", "Airtel Africa", "Telecoms", date(2019, 6, 28), True, "Large"),
        
        # Oil & Gas
        ("SEPLAT", "Seplat Energy", "Oil & Gas", date(2014, 4, 16), True, "Large"),
        ("TOTAL", "TotalEnergies Marketing", "Oil & Gas", date(1978, 1, 1), True, "Mid"),
        ("CONOIL", "Conoil", "Oil & Gas", date(1992, 11, 5), False, "Small"),
        
        # FMCG
        ("NESTLE", "Nestlé Nigeria", "FMCG", date(1979, 4, 20), False, "Large"),
        ("UNILEVER", "Unilever Nigeria", "FMCG", date(1973, 1, 1), False, "Mid"),
        ("FLOURMILL", "Flour Mills of Nigeria", "FMCG", date(1978, 1, 1), False, "Mid"),
        ("NASCON", "NASCON Allied Industries", "FMCG", date(1991, 6, 24), False, "Small"),
        
        # Agriculture
        ("PRESCO", "Presco", "Agriculture", date(2002, 8, 1), True, "Mid"),
        ("OKOMUOIL", "Okomu Oil Palm", "Agriculture", date(1991, 2, 15), True, "Mid"),
    ]
    
    for ticker, name, sector, listing_date, has_fx, market_cap in companies_data:
        # Check if already exists
        existing = session.query(Company).filter_by(ticker=ticker).first()
        if not existing:
            company = Company(
                ticker=ticker,
                name=name,
                sector=sector,
                listing_date=listing_date,
                has_fx_revenue=has_fx,
                market_cap_category=market_cap,
                is_active=True
            )
            session.add(company)
    
    session.commit()
    print(f"✅ Seeded {len(companies_data)} companies")


if __name__ == "__main__":
    # Test database creation
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://ngx_user:ngx_password@localhost:5432/ngx_data"
    )
    
    print("Creating database tables...")
    engine = create_database_engine(DATABASE_URL)
    init_database(engine)
    
    print("\nSeeding initial data...")
    session = get_session(engine)
    seed_companies(session)
    session.close()
    
    print("\n✅ Database setup complete!")
