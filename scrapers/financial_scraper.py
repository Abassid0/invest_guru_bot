"""
Financial Statements Scraper
Extracts company financials from NGX filings, company reports, and SEC Nigeria
"""
import requests
from bs4 import BeautifulSoup
import pdfplumber
import re
from datetime import datetime, date
from typing import Dict, List, Optional
from decimal import Decimal
from loguru import logger
import pandas as pd


class FinancialScraper:
    """
    Scrapes financial statements from multiple sources
    Priority: SEC Nigeria filings > Company IR pages > Manual data entry
    """
    
    def __init__(self):
        self.sec_base_url = "https://sec.gov.ng"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def fetch_company_financials(self, ticker: str, fiscal_year: int) -> Optional[Dict]:
        """
        Fetch financial statements for a company
        """
        logger.info(f"Fetching financials for {ticker} FY{fiscal_year}")
        
        # Try multiple sources in order
        financials = None
        
        # 1. Try SEC Nigeria filings
        financials = self._fetch_from_sec_nigeria(ticker, fiscal_year)
        
        # 2. Try company investor relations page
        if not financials:
            financials = self._fetch_from_company_ir(ticker, fiscal_year)
        
        # 3. Try NGX company page
        if not financials:
            financials = self._fetch_from_ngx(ticker, fiscal_year)
        
        # 4. Return placeholder structure if nothing found
        if not financials:
            logger.warning(f"No financials found for {ticker} FY{fiscal_year}")
            financials = self._get_placeholder_financials(ticker, fiscal_year)
        
        return financials
    
    def _fetch_from_sec_nigeria(self, ticker: str, fiscal_year: int) -> Optional[Dict]:
        """
        Fetch from SEC Nigeria public filings
        """
        try:
            # SEC Nigeria has company filings database
            # This is a simplified version - actual implementation would need
            # proper navigation of SEC's filing system
            
            search_url = f"{self.sec_base_url}/filings/company/{ticker}"
            
            # This would need actual SEC API or scraping logic
            logger.info(f"Checking SEC Nigeria for {ticker}")
            
            # Placeholder: In production, parse actual SEC filings
            return None
            
        except Exception as e:
            logger.error(f"Error fetching from SEC Nigeria: {e}")
            return None
    
    def _fetch_from_company_ir(self, ticker: str, fiscal_year: int) -> Optional[Dict]:
        """
        Fetch from company investor relations page
        """
        try:
            # Map tickers to company IR URLs
            company_ir_urls = {
                "GTCO": "https://www.gtcoplc.com/investor-relations",
                "DANGCEM": "https://www.dangotecement.com/investor-relations",
                "ZENITHBANK": "https://www.zenithbank.com/investor-relations",
                "MTNN": "https://www.mtnonline.com/investors",
                # Add more as available
            }
            
            if ticker not in company_ir_urls:
                return None
            
            logger.info(f"Checking company IR for {ticker}")
            
            # This would need actual scraping/PDF parsing
            # For now, return None
            return None
            
        except Exception as e:
            logger.error(f"Error fetching from company IR: {e}")
            return None
    
    def _fetch_from_ngx(self, ticker: str, fiscal_year: int) -> Optional[Dict]:
        """
        Fetch from NGX company profile page
        """
        try:
            url = f"https://ngxgroup.com/issuers/{ticker.lower()}"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'lxml')
            
            # NGX provides some basic financial metrics
            # This would need proper parsing of their structure
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching from NGX: {e}")
            return None
    
    def _get_placeholder_financials(self, ticker: str, fiscal_year: int) -> Dict:
        """
        Generate placeholder financial structure
        In production, this should be replaced with actual data or manual entry
        """
        return {
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'period_type': 'FY',
            'period_end': date(fiscal_year, 12, 31),
            
            # Income Statement (in millions of Naira)
            'revenue': None,
            'gross_profit': None,
            'operating_income': None,
            'net_income': None,
            'ebitda': None,
            
            # Balance Sheet
            'total_assets': None,
            'total_liabilities': None,
            'total_equity': None,
            'total_debt': None,
            'cash': None,
            
            # Cash Flow
            'operating_cash_flow': None,
            'free_cash_flow': None,
            
            # Per Share
            'eps': None,
            'book_value_per_share': None,
            'dividend_per_share': None,
            
            # Ratios
            'roe': None,
            'roa': None,
            'debt_to_equity': None,
            
            # FX exposure
            'fx_revenue_percentage': None,
            'fx_denominated_debt': None,
            
            'source': 'Placeholder - Manual Entry Required',
            'currency': 'NGN'
        }
    
    def parse_financial_pdf(self, pdf_path: str) -> Dict:
        """
        Parse financial data from PDF annual report
        This is a helper for manual processing
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages[:50]:  # First 50 pages usually have financials
                    text += page.extract_text() or ""
            
            # Extract key financial figures using regex
            financials = {}
            
            # Revenue patterns
            revenue_patterns = [
                r'Revenue.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:million|billion)?',
                r'Turnover.*?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
            ]
            
            # Extract revenue
            for pattern in revenue_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    financials['revenue'] = self._parse_amount(match.group(1))
                    break
            
            logger.info(f"Extracted financials from PDF: {len(financials)} fields")
            return financials
            
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
            return {}
    
    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse financial amount string to Decimal (in millions)"""
        try:
            # Remove commas and convert
            cleaned = amount_str.replace(',', '')
            return Decimal(cleaned)
        except:
            return None
    
    def get_manual_entry_template(self, ticker: str, fiscal_year: int) -> Dict:
        """
        Return a template for manual financial data entry
        """
        template = {
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'period_type': 'FY',  # Q1, Q2, Q3, Q4, or FY
            'period_end': None,  # date object
            
            # Income Statement (₦ millions)
            'revenue': None,
            'cost_of_revenue': None,
            'gross_profit': None,
            'operating_expenses': None,
            'operating_income': None,
            'net_income': None,
            'ebitda': None,
            
            # Balance Sheet (₦ millions)
            'total_assets': None,
            'current_assets': None,
            'total_liabilities': None,
            'current_liabilities': None,
            'total_equity': None,
            'total_debt': None,
            'cash': None,
            
            # Cash Flow (₦ millions)
            'operating_cash_flow': None,
            'investing_cash_flow': None,
            'financing_cash_flow': None,
            'free_cash_flow': None,
            
            # Per Share Metrics
            'eps': None,
            'book_value_per_share': None,
            'dividend_per_share': None,
            
            # Calculated Ratios
            'roe': None,  # %
            'roa': None,  # %
            'debt_to_equity': None,
            'current_ratio': None,
            'gross_margin': None,  # %
            'net_margin': None,  # %
            
            # FX Exposure
            'fx_revenue_percentage': None,  # % of revenue in FX
            'fx_denominated_debt': None,  # Amount in ₦ millions
            
            # Metadata
            'source': 'Manual Entry',
            'currency': 'NGN',
        }
        
        return template
    
    def load_manual_financials(self, csv_path: str) -> List[Dict]:
        """
        Load manually entered financial data from CSV
        """
        try:
            df = pd.read_csv(csv_path)
            
            financials = []
            for _, row in df.iterrows():
                financial_data = row.to_dict()
                
                # Convert date fields
                if 'period_end' in financial_data:
                    financial_data['period_end'] = pd.to_datetime(
                        financial_data['period_end']
                    ).date()
                
                financials.append(financial_data)
            
            logger.info(f"Loaded {len(financials)} financial records from CSV")
            return financials
            
        except Exception as e:
            logger.error(f"Error loading manual financials: {e}")
            return []


# Test
if __name__ == "__main__":
    from loguru import logger
    
    logger.add("logs/financial_scraper_test.log", rotation="1 day")
    
    scraper = FinancialScraper()
    
    print("=" * 60)
    print("Financial Scraper Test")
    print("=" * 60)
    
    # Test: Get manual entry template
    print("\nManual Entry Template for GTCO FY2023:")
    template = scraper.get_manual_entry_template("GTCO", 2023)
    
    print(json.dumps(template, indent=2, default=str))
    
    print("\n✅ Financial scraper test complete")
    print("\n💡 Tip: For production, fill templates manually or connect to data provider")
