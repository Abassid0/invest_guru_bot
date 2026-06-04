"""
Inflation Performance Calculator
Calculates stock returns vs Nigerian inflation over 1yr, 3yr, 5yr, 10yr periods
Identifies inflation-beating stocks
"""
import sys
sys.path.append('..')

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import pandas as pd
import numpy as np
from loguru import logger
from database.models import (
    Company, StockPrice, InflationData, InflationPerformance,
    get_session, create_database_engine
)
from sqlalchemy import func, and_


class InflationCalculator:
    """
    Calculates inflation-adjusted returns for NGX stocks
    """
    
    def __init__(self, database_url: str):
        self.engine = create_database_engine(database_url)
        self.session = get_session(self.engine)
    
    def calculate_stock_returns(
        self, 
        ticker: str, 
        start_date: date, 
        end_date: date,
        include_dividends: bool = True
    ) -> Optional[Decimal]:
        """
        Calculate annualized return for a stock over a period
        
        Returns:
            Annualized return as percentage (e.g., 25.5 for 25.5%)
        """
        # Get company
        company = self.session.query(Company).filter_by(ticker=ticker).first()
        if not company:
            logger.warning(f"Company {ticker} not found")
            return None
        
        # Get price at start
        start_price_record = self.session.query(StockPrice).filter(
            and_(
                StockPrice.company_id == company.id,
                StockPrice.date <= start_date
            )
        ).order_by(StockPrice.date.desc()).first()
        
        # Get price at end
        end_price_record = self.session.query(StockPrice).filter(
            and_(
                StockPrice.company_id == company.id,
                StockPrice.date <= end_date
            )
        ).order_by(StockPrice.date.desc()).first()
        
        if not start_price_record or not end_price_record:
            logger.warning(f"Insufficient price data for {ticker}")
            return None
        
        start_price = float(start_price_record.close)
        end_price = float(end_price_record.close)
        
        # Calculate capital appreciation
        capital_return = ((end_price - start_price) / start_price) * 100
        
        # Add dividend yield if requested
        total_return = capital_return
        if include_dividends:
            dividend_yield = self._calculate_dividend_yield(
                company.id, start_date, end_date
            )
            total_return += dividend_yield
        
        # Annualize the return
        years = (end_date - start_price_record.date).days / 365.25
        if years > 0:
            annualized_return = ((1 + total_return/100) ** (1/years) - 1) * 100
        else:
            annualized_return = total_return
        
        return Decimal(str(round(annualized_return, 4)))
    
    def calculate_inflation_rate(
        self, 
        start_date: date, 
        end_date: date
    ) -> Optional[Decimal]:
        """
        Calculate annualized inflation rate over a period
        Uses Nigerian CPI data
        
        Returns:
            Annualized inflation rate as percentage
        """
        # Get CPI at start
        start_cpi = self.session.query(InflationData).filter(
            InflationData.date <= start_date
        ).order_by(InflationData.date.desc()).first()
        
        # Get CPI at end
        end_cpi = self.session.query(InflationData).filter(
            InflationData.date <= end_date
        ).order_by(InflationData.date.desc()).first()
        
        if not start_cpi or not end_cpi:
            logger.warning(f"Insufficient inflation data for period")
            # Use fallback average
            return self._get_fallback_inflation(start_date, end_date)
        
        # Calculate cumulative inflation
        cumulative_inflation = float(end_cpi.headline_cpi) - float(start_cpi.headline_cpi)
        
        # Annualize
        years = (end_date - start_cpi.date).days / 365.25
        if years > 0:
            annualized_inflation = cumulative_inflation / years
        else:
            annualized_inflation = cumulative_inflation
        
        return Decimal(str(round(annualized_inflation, 4)))
    
    def calculate_excess_return(
        self,
        ticker: str,
        years_back: int,
        calculation_date: Optional[date] = None
    ) -> Dict:
        """
        Calculate excess return (stock return - inflation) over specified period
        
        Args:
            ticker: Stock ticker
            years_back: Number of years (1, 3, 5, or 10)
            calculation_date: Reference date (defaults to today)
        
        Returns:
            Dict with stock_return, inflation, excess_return, beats_inflation
        """
        if calculation_date is None:
            calculation_date = date.today()
        
        # Calculate start date
        start_date = calculation_date - timedelta(days=years_back * 365)
        
        # Get stock return
        stock_return = self.calculate_stock_returns(
            ticker, start_date, calculation_date, include_dividends=True
        )
        
        # Get inflation
        inflation_rate = self.calculate_inflation_rate(start_date, calculation_date)
        
        if stock_return is None or inflation_rate is None:
            return {
                'period': f'{years_back}yr',
                'stock_return': None,
                'inflation': None,
                'excess_return': None,
                'beats_inflation': False
            }
        
        # Calculate excess return
        excess_return = stock_return - inflation_rate
        
        return {
            'period': f'{years_back}yr',
            'stock_return': float(stock_return),
            'inflation': float(inflation_rate),
            'excess_return': float(excess_return),
            'beats_inflation': excess_return > 0
        }
    
    def calculate_all_periods(
        self,
        ticker: str,
        calculation_date: Optional[date] = None
    ) -> Dict:
        """
        Calculate inflation performance across all periods (1yr, 3yr, 5yr, 10yr)
        """
        if calculation_date is None:
            calculation_date = date.today()
        
        results = {}
        
        for years in [1, 3, 5, 10]:
            key = f'{years}yr'
            results[key] = self.calculate_excess_return(
                ticker, years, calculation_date
            )
        
        # Determine if beats inflation in all measurable periods
        beats_all = all(
            results[key]['beats_inflation'] 
            for key in ['1yr', '3yr', '5yr'] 
            if results[key]['excess_return'] is not None
        )
        
        results['beats_inflation_all'] = beats_all
        
        return results
    
    def calculate_volatility(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> Optional[Decimal]:
        """
        Calculate annualized volatility (standard deviation of returns)
        """
        company = self.session.query(Company).filter_by(ticker=ticker).first()
        if not company:
            return None
        
        # Get all prices in period
        prices = self.session.query(StockPrice).filter(
            and_(
                StockPrice.company_id == company.id,
                StockPrice.date >= start_date,
                StockPrice.date <= end_date
            )
        ).order_by(StockPrice.date).all()
        
        if len(prices) < 30:  # Need minimum data points
            return None
        
        # Calculate daily returns
        price_values = [float(p.close) for p in prices]
        daily_returns = []
        
        for i in range(1, len(price_values)):
            daily_return = (price_values[i] - price_values[i-1]) / price_values[i-1]
            daily_returns.append(daily_return)
        
        # Calculate standard deviation
        std_dev = np.std(daily_returns)
        
        # Annualize (assumes ~252 trading days)
        annualized_vol = std_dev * np.sqrt(252) * 100
        
        return Decimal(str(round(annualized_vol, 4)))
    
    def calculate_risk_adjusted_return(
        self,
        ticker: str,
        years_back: int,
        calculation_date: Optional[date] = None
    ) -> Optional[Decimal]:
        """
        Calculate risk-adjusted return (excess return / volatility)
        Similar to Sharpe ratio concept
        """
        if calculation_date is None:
            calculation_date = date.today()
        
        start_date = calculation_date - timedelta(days=years_back * 365)
        
        # Get excess return
        excess = self.calculate_excess_return(ticker, years_back, calculation_date)
        if excess['excess_return'] is None:
            return None
        
        # Get volatility
        volatility = self.calculate_volatility(ticker, start_date, calculation_date)
        if volatility is None or volatility == 0:
            return None
        
        # Calculate risk-adjusted return
        risk_adj_return = Decimal(str(excess['excess_return'])) / volatility
        
        return Decimal(str(round(risk_adj_return, 4)))
    
    def save_performance_metrics(
        self,
        ticker: str,
        calculation_date: Optional[date] = None
    ) -> bool:
        """
        Calculate and save all performance metrics to database
        """
        if calculation_date is None:
            calculation_date = date.today()
        
        try:
            # Get company
            company = self.session.query(Company).filter_by(ticker=ticker).first()
            if not company:
                logger.warning(f"Company {ticker} not found")
                return False
            
            # Calculate all period returns
            all_results = self.calculate_all_periods(ticker, calculation_date)
            
            # Calculate volatility for 1yr and 3yr
            vol_1yr = self.calculate_volatility(
                ticker,
                calculation_date - timedelta(days=365),
                calculation_date
            )
            
            vol_3yr = self.calculate_volatility(
                ticker,
                calculation_date - timedelta(days=3*365),
                calculation_date
            )
            
            # Calculate risk-adjusted returns
            risk_adj_1yr = self.calculate_risk_adjusted_return(ticker, 1, calculation_date)
            risk_adj_3yr = self.calculate_risk_adjusted_return(ticker, 3, calculation_date)
            
            # Check if record exists
            existing = self.session.query(InflationPerformance).filter(
                and_(
                    InflationPerformance.company_id == company.id,
                    InflationPerformance.calculation_date == calculation_date
                )
            ).first()
            
            # Prepare data
            performance_data = {
                'company_id': company.id,
                'calculation_date': calculation_date,
                
                # Returns
                'return_1yr': all_results['1yr']['stock_return'],
                'return_3yr': all_results['3yr']['stock_return'],
                'return_5yr': all_results['5yr']['stock_return'],
                'return_10yr': all_results['10yr']['stock_return'],
                
                # Inflation
                'inflation_1yr': all_results['1yr']['inflation'],
                'inflation_3yr': all_results['3yr']['inflation'],
                'inflation_5yr': all_results['5yr']['inflation'],
                'inflation_10yr': all_results['10yr']['inflation'],
                
                # Excess returns
                'excess_return_1yr': all_results['1yr']['excess_return'],
                'excess_return_3yr': all_results['3yr']['excess_return'],
                'excess_return_5yr': all_results['5yr']['excess_return'],
                'excess_return_10yr': all_results['10yr']['excess_return'],
                
                # Flags
                'beats_inflation_1yr': all_results['1yr']['beats_inflation'],
                'beats_inflation_3yr': all_results['3yr']['beats_inflation'],
                'beats_inflation_5yr': all_results['5yr']['beats_inflation'],
                'beats_inflation_all': all_results['beats_inflation_all'],
                
                # Volatility
                'volatility_1yr': vol_1yr,
                'volatility_3yr': vol_3yr,
                
                # Risk-adjusted
                'risk_adjusted_return_1yr': risk_adj_1yr,
                'risk_adjusted_return_3yr': risk_adj_3yr,
            }
            
            if existing:
                # Update existing
                for key, value in performance_data.items():
                    setattr(existing, key, value)
                logger.info(f"Updated performance metrics for {ticker}")
            else:
                # Create new
                performance = InflationPerformance(**performance_data)
                self.session.add(performance)
                logger.info(f"Created performance metrics for {ticker}")
            
            self.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error saving performance metrics for {ticker}: {e}")
            self.session.rollback()
            return False
    
    def batch_calculate_performance(
        self,
        tickers: Optional[List[str]] = None,
        calculation_date: Optional[date] = None
    ) -> Dict[str, bool]:
        """
        Calculate performance for multiple stocks
        """
        if tickers is None:
            # Get all active companies
            companies = self.session.query(Company).filter_by(is_active=True).all()
            tickers = [c.ticker for c in companies]
        
        results = {}
        
        for ticker in tickers:
            logger.info(f"Calculating performance for {ticker}")
            success = self.save_performance_metrics(ticker, calculation_date)
            results[ticker] = success
        
        successful = sum(1 for v in results.values() if v)
        logger.info(f"Completed: {successful}/{len(tickers)} successful")
        
        return results
    
    def get_inflation_beaters(
        self,
        min_excess_return_3yr: float = 0.0,
        min_periods_beating: int = 3
    ) -> List[Dict]:
        """
        Get list of stocks that beat inflation
        
        Args:
            min_excess_return_3yr: Minimum 3yr excess return required
            min_periods_beating: Minimum number of periods where stock beats inflation
        
        Returns:
            List of dicts with ticker, company name, and performance metrics
        """
        # Query latest performance data
        latest_date_subquery = self.session.query(
            func.max(InflationPerformance.calculation_date)
        ).scalar_subquery()
        
        query = self.session.query(
            Company, InflationPerformance
        ).join(
            InflationPerformance
        ).filter(
            and_(
                InflationPerformance.calculation_date == latest_date_subquery,
                InflationPerformance.beats_inflation_all == True,
                InflationPerformance.excess_return_3yr >= min_excess_return_3yr
            )
        ).order_by(
            InflationPerformance.excess_return_3yr.desc()
        )
        
        results = []
        for company, performance in query.all():
            results.append({
                'ticker': company.ticker,
                'name': company.name,
                'sector': company.sector,
                'has_fx_revenue': company.has_fx_revenue,
                'excess_return_1yr': float(performance.excess_return_1yr or 0),
                'excess_return_3yr': float(performance.excess_return_3yr or 0),
                'excess_return_5yr': float(performance.excess_return_5yr or 0),
                'beats_all_periods': performance.beats_inflation_all,
                'risk_adjusted_return_3yr': float(performance.risk_adjusted_return_3yr or 0),
            })
        
        return results
    
    def _calculate_dividend_yield(
        self, 
        company_id: int, 
        start_date: date, 
        end_date: date
    ) -> float:
        """
        Calculate total dividend yield over period
        Note: Requires dividend data in Financial table
        """
        # This would query dividend_per_share from Financial table
        # For now, return 0 (needs dividend data)
        return 0.0
    
    def _get_fallback_inflation(self, start_date: date, end_date: date) -> Decimal:
        """
        Fallback: Use average Nigerian inflation when exact data unavailable
        """
        # Nigerian inflation has averaged 15-20% in recent years
        # Use conservative 18% annual average
        years = (end_date - start_date).days / 365.25
        cumulative = 18.0 * years
        return Decimal(str(round(cumulative / years, 4)))
    
    def close(self):
        """Close database session"""
        self.session.close()


# Test
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://ngx_user:ngx_password@localhost:5432/ngx_data"
    )
    
    calculator = InflationCalculator(DATABASE_URL)
    
    print("=" * 60)
    print("Inflation Calculator Test")
    print("=" * 60)
    
    # Note: This test requires price and inflation data in database
    # For full test, run after data population
    
    print("\n✅ Calculator initialized")
    print("💡 Run after populating price & inflation data")
    
    calculator.close()
