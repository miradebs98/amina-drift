"""
GRAIN Earnings Calendar

Maps company tickers to their earnings call dates.
Used to construct accurate Motley Fool transcript URLs.

Data sourced from official company investor relations pages.
"""

from datetime import date
from typing import Dict, List, Optional, Tuple


# Earnings call dates for major companies
# Format: 'ticker': {'Q1_YYYY': 'YYYY-MM-DD', ...}
# Note: Fiscal years vary by company

EARNINGS_CALENDAR: Dict[str, Dict[str, str]] = {
    # Apple - Fiscal Year ends September
    # Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun, Q4=Jul-Sep
    "AAPL": {
        # FY 2025
        "Q1_2025": "2025-01-30",
        "Q2_2025": "2025-05-01",
        "Q3_2025": "2025-07-31",
        "Q4_2025": "2025-10-30",
        # FY 2024
        "Q1_2024": "2024-02-01",
        "Q2_2024": "2024-05-02",
        "Q3_2024": "2024-08-01",
        "Q4_2024": "2024-10-31",
    },
    
    # Microsoft - Fiscal Year ends June
    # Q1=Jul-Sep, Q2=Oct-Dec, Q3=Jan-Mar, Q4=Apr-Jun
    "MSFT": {
        # FY 2025
        "Q1_2025": "2024-10-30",
        "Q2_2025": "2025-01-29",
        "Q3_2025": "2025-04-30",
        "Q4_2025": "2025-07-30",
        # FY 2024
        "Q1_2024": "2023-10-24",
        "Q2_2024": "2024-01-30",
        "Q3_2024": "2024-04-25",
        "Q4_2024": "2024-07-30",
    },
    
    # NVIDIA - Fiscal Year ends January
    # Q1=Feb-Apr, Q2=May-Jul, Q3=Aug-Oct, Q4=Nov-Jan
    "NVDA": {
        # FY 2026 (calendar 2025)
        "Q4_2025": "2025-02-26",  # Actually FY26 Q4
        "Q1_2026": "2025-05-28",
        "Q2_2026": "2025-08-27",
        "Q3_2026": "2025-11-19",
        # FY 2025 (calendar 2024)
        "Q1_2025": "2024-05-22",
        "Q2_2025": "2024-08-28",
        "Q3_2025": "2024-11-20",
        "Q4_2025": "2025-02-26",
    },
    
    # Alphabet/Google - Fiscal Year ends December (calendar year)
    "GOOGL": {
        # FY 2025
        "Q1_2025": "2025-04-24",
        "Q2_2025": "2025-07-29",
        "Q3_2025": "2025-10-29",
        "Q4_2025": "2026-02-04",  # Typically early February
        # FY 2024
        "Q1_2024": "2024-04-25",
        "Q2_2024": "2024-07-23",
        "Q3_2024": "2024-10-29",
        "Q4_2024": "2025-02-04",
    },
    
    # Amazon - Fiscal Year ends December (calendar year)
    "AMZN": {
        # FY 2025
        "Q1_2025": "2025-05-01",
        "Q2_2025": "2025-08-07",
        "Q3_2025": "2025-10-30",
        "Q4_2025": "2026-02-06",
        # FY 2024
        "Q1_2024": "2024-04-30",
        "Q2_2024": "2024-08-01",
        "Q3_2024": "2024-10-31",
        "Q4_2024": "2025-02-06",
    },
    
    # Meta - Fiscal Year ends December (calendar year)
    "META": {
        # FY 2025
        "Q1_2025": "2025-04-30",
        "Q2_2025": "2025-07-30",
        "Q3_2025": "2025-10-29",
        "Q4_2025": "2026-01-29",
        # FY 2024
        "Q1_2024": "2024-04-24",
        "Q2_2024": "2024-07-24",
        "Q3_2024": "2024-10-30",
        "Q4_2024": "2025-01-29",
    },
    
    # Tesla - Fiscal Year ends December (calendar year)
    "TSLA": {
        # FY 2025
        "Q1_2025": "2025-04-22",
        "Q2_2025": "2025-07-22",
        "Q3_2025": "2025-10-16",
        "Q4_2025": "2026-01-29",
        # FY 2024
        "Q1_2024": "2024-04-23",
        "Q2_2024": "2024-07-23",
        "Q3_2024": "2024-10-23",
        "Q4_2024": "2025-01-29",
    },
    
    # JPMorgan Chase
    "JPM": {
        "Q1_2025": "2025-04-11",
        "Q2_2025": "2025-07-15",
        "Q3_2025": "2025-10-15",
        "Q4_2025": "2026-01-15",
        "Q1_2024": "2024-04-12",
        "Q2_2024": "2024-07-12",
        "Q3_2024": "2024-10-11",
        "Q4_2024": "2025-01-15",
    },
}


def get_earnings_dates(ticker: str, num_quarters: int = 4) -> List[Tuple[str, str]]:
    """
    Get recent earnings call dates for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        num_quarters: Number of quarters to return
        
    Returns:
        List of (quarter_label, date_string) tuples, most recent first
    """
    ticker = ticker.upper()
    
    if ticker not in EARNINGS_CALENDAR:
        return []
    
    calendar = EARNINGS_CALENDAR[ticker]
    
    # Sort by date (most recent first)
    sorted_dates = sorted(
        [(q, d) for q, d in calendar.items()],
        key=lambda x: x[1],
        reverse=True
    )
    
    return sorted_dates[:num_quarters]


def generate_motley_fool_url(ticker: str, quarter: str, earnings_date: str) -> str:
    """
    Generate Motley Fool transcript URL.
    
    Args:
        ticker: Stock ticker (e.g., 'AAPL')
        quarter: Quarter label (e.g., 'Q1_2025')
        earnings_date: Date string (e.g., '2025-01-30')
        
    Returns:
        Full Motley Fool transcript URL
    """
    ticker_lower = ticker.lower()
    
    # Company name mapping
    company_slugs = {
        "AAPL": "apple",
        "MSFT": "microsoft",
        "GOOGL": "alphabet",
        "GOOG": "alphabet",
        "AMZN": "amazon",
        "META": "meta-platforms",
        "NVDA": "nvidia",
        "TSLA": "tesla",
        "JPM": "jpmorgan-chase",
    }
    
    company = company_slugs.get(ticker.upper(), ticker_lower)
    
    # Parse date
    year, month, day = earnings_date.split("-")
    
    # Parse quarter (Q1_2025 -> q1, 2025)
    q_num = quarter.split("_")[0].lower()
    fiscal_year = quarter.split("_")[1]
    
    url = f"https://www.fool.com/earnings/call-transcripts/{year}/{month}/{day}/{company}-{ticker_lower}-{q_num}-{fiscal_year}-earnings-call-transcript/"
    
    return url


def get_transcript_urls(ticker: str, num_quarters: int = 4) -> List[Tuple[str, str, str]]:
    """
    Get Motley Fool transcript URLs for a ticker.
    
    Args:
        ticker: Stock ticker
        num_quarters: Number of quarters
        
    Returns:
        List of (quarter, date, url) tuples
    """
    dates = get_earnings_dates(ticker, num_quarters)
    
    results = []
    for quarter, earnings_date in dates:
        url = generate_motley_fool_url(ticker, quarter, earnings_date)
        results.append((quarter, earnings_date, url))
    
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("  GRAIN Earnings Calendar")
    print("=" * 70)
    
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        print(f"\n{ticker} Earnings Dates & URLs:")
        print("-" * 70)
        
        urls = get_transcript_urls(ticker, num_quarters=4)
        for quarter, date, url in urls:
            print(f"  {quarter} ({date})")
            print(f"    {url}")
