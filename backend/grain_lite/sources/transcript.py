"""
GRAIN Earnings Transcript Source Adapter

Fetches earnings call transcripts.
Primary source: Alpha Vantage API (structured, with sentiment)
Fallback: Motley Fool web scraping
"""

import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from backend.grain_lite.utils import retry, RateLimitError, IngestionTracker, logger
from backend.grain_lite.sources.base import (
    DocumentSource,
    Document,
    SourceResult,
    SourceType,
    get_source_weight
)


# Company ticker mappings
COMPANY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft", 
    "GOOGL": "Alphabet",
    "GOOG": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "JPM": "JPMorgan Chase",
    "BAC": "Bank of America",
    "WFC": "Wells Fargo",
    "JNJ": "Johnson & Johnson",
    "PG": "Procter & Gamble",
    "UNH": "UnitedHealth",
    "V": "Visa",
    "HD": "Home Depot",
    "MA": "Mastercard",
    "DIS": "Walt Disney",
    "NFLX": "Netflix",
    "INTC": "Intel",
    "AMD": "AMD",
    "CRM": "Salesforce",
    "ORCL": "Oracle",
    "IBM": "IBM",
    "COST": "Costco",
    "WMT": "Walmart",
    "KO": "Coca-Cola",
    "PEP": "PepsiCo",
}


@dataclass
class TranscriptSection:
    """A section of an earnings transcript."""
    speaker: str
    title: str
    content: str
    sentiment: float  # -1.0 to 1.0
    section_type: str  # "management", "analyst", "operator"
    

class EarningsTranscriptSource(DocumentSource):
    """
    Document source for earnings call transcripts.
    
    Primary source: Alpha Vantage API (structured JSON with sentiment)
    Fallback: Motley Fool web scraping
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the transcript source.
        
        Args:
            cache_dir: Directory to cache/store transcripts
        """
        # Set cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            from backend.grain_lite.config import get_config
            project_root = get_config().base_dir
            self.cache_dir = project_root / "data" / "raw_filings" / "Earnings_Transcripts"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Check for Alpha Vantage API
        self._load_env()
        self._alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self._has_alpha_vantage = bool(self._alpha_vantage_key)

        # Motley Fool fallback is DISABLED - Alpha Vantage is the only source
        # Keeping the code for reference but never using it
        self._has_playwright = False  # Disabled - always use Alpha Vantage

        if self._has_alpha_vantage:
            logger.info("Alpha Vantage API available for earnings transcripts")
        else:
            logger.warning("ALPHA_VANTAGE_API_KEY not set - transcripts unavailable")
    
    def _load_env(self):
        """Load environment variables (already loaded by grain.config)."""
        # Environment variables already loaded by grain.config module
        pass
    
    @property
    def source_type(self) -> SourceType:
        return SourceType.EARNINGS_TRANSCRIPT
    
    @property
    def base_weight(self) -> float:
        return get_source_weight(SourceType.EARNINGS_TRANSCRIPT)
    
    def fetch(self, ticker: str, **kwargs) -> SourceResult:
        """
        Fetch earnings transcripts for a ticker.
        
        Args:
            ticker: Company ticker symbol
            num_quarters: Number of quarters to fetch (default: 4)
            use_cache: Whether to check cache first (default: True)
            fetch_new: Whether to fetch new transcripts from API (default: True)
            
        Returns:
            SourceResult with parsed transcript documents
        """
        start_time = time.time()
        ticker = ticker.upper()
        num_quarters = kwargs.get('num_quarters', 4)
        use_cache = kwargs.get('use_cache', True)
        fetch_new = kwargs.get('fetch_new', True)
        min_year = kwargs.get('min_year')
        max_year = kwargs.get('max_year')
        
        documents = []
        ingestion_warnings = []

        # First, load from cache
        if use_cache:
            cached_transcripts = self._load_from_cache(ticker)
            documents.extend(cached_transcripts)
            if cached_transcripts:
                logger.info(f"Loaded {len(cached_transcripts)} cached transcripts for {ticker}")
        
        # Fetch new transcripts if needed
        if fetch_new and len(documents) < num_quarters:
            if self._has_alpha_vantage:
                # Primary: Alpha Vantage API (with year filtering for efficiency)
                try:
                    new_docs, tracker = self._fetch_from_alpha_vantage(ticker, num_quarters, min_year, max_year)
                    cached_periods = {d.fiscal_period for d in documents}
                    for doc in new_docs:
                        if doc.fiscal_period not in cached_periods:
                            documents.append(doc)
                    # Capture tracker warnings for the SourceResult
                    if not tracker.is_complete:
                        ingestion_warnings = tracker.warnings
                except Exception as e:
                    logger.warning(f"Alpha Vantage error for {ticker}: {e}")
            
            elif self._has_playwright:
                # Fallback: Motley Fool scraping
                try:
                    new_docs = self._fetch_from_motley_fool(ticker, num_quarters - len(documents))
                    cached_periods = {d.fiscal_period for d in documents}
                    for doc in new_docs:
                        if doc.fiscal_period not in cached_periods:
                            documents.append(doc)
                except Exception as e:
                    logger.warning(f"Web fetch error for {ticker}: {e}")
        
        # Sort by date (most recent first)
        documents.sort(key=lambda d: d.filing_date or date.min, reverse=True)
        
        # Limit to requested number
        documents = documents[:num_quarters]
        
        # Build error message from warnings
        error_msg = None
        if not documents:
            error_msg = "No transcripts found"
        elif ingestion_warnings:
            error_msg = "; ".join(ingestion_warnings)

        return SourceResult(
            source_type=self.source_type,
            ticker=ticker,
            documents=documents,
            success=len(documents) > 0,
            error_message=error_msg,
            fetch_time=time.time() - start_time
        )
    
    @retry(max_attempts=3, delay=3.0, backoff=2.0, exceptions=(requests.RequestException, RateLimitError))
    def _fetch_single_quarter(self, ticker: str, quarter: str) -> Optional[Dict]:
        """Fetch a single quarter's transcript with retry."""
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "EARNINGS_CALL_TRANSCRIPT",
                "symbol": ticker,
                "quarter": quarter,
                "apikey": self._alpha_vantage_key
            },
            timeout=30
        )
        data = response.json()

        if "Note" in data:
            raise RateLimitError(
                f"Alpha Vantage rate limit for {ticker} {quarter}: {data['Note']}",
                retry_after=3.0  # Premium tier (75 calls/min) recovers fast
            )
        if "Error Message" in data:
            return None  # Genuine "no data" — not retryable

        transcript_data = data.get("transcript", [])
        return data if transcript_data else None

    def _fetch_earnings_calendar(self, ticker: str) -> Dict[str, str]:
        """Fetch actual earnings call dates from Alpha Vantage.

        Uses OVERVIEW API to determine fiscal year structure, then EARNINGS API
        to get exact reportedDate for each quarter.

        Returns:
            Dict mapping quarter string ("2024Q3") to reported date ("2024-12-03").
        """
        _MONTH_NAMES = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        # Step 1: Get fiscal year end month from OVERVIEW API
        fy_end_month = 12  # Default to calendar year
        try:
            resp = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "OVERVIEW", "symbol": ticker,
                    "apikey": self._alpha_vantage_key,
                },
                timeout=30,
            )
            overview = resp.json()
            fy_str = overview.get("FiscalYearEnd", "").strip().lower()
            if fy_str in _MONTH_NAMES:
                fy_end_month = _MONTH_NAMES[fy_str]
            logger.debug(f"{ticker} fiscal year ends in month {fy_end_month}")
        except Exception as e:
            logger.warning(f"Failed to fetch OVERVIEW for {ticker}, assuming calendar year: {e}")

        time.sleep(0.5)

        # Step 2: Get quarterly earnings data
        try:
            resp = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "EARNINGS", "symbol": ticker,
                    "apikey": self._alpha_vantage_key,
                },
                timeout=30,
            )
            data = resp.json()
            if "Note" in data or "Information" in data:
                logger.warning(f"Rate limited fetching earnings for {ticker}")
                return {}
            entries = data.get("quarterlyEarnings", [])
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {ticker}: {e}")
            return {}

        # Step 3: Compute quarter-end months from fiscal year end
        # Q1 starts the month after FY end, each quarter spans 3 months
        q1_end = ((fy_end_month + 3 - 1) % 12) + 1
        q2_end = ((fy_end_month + 6 - 1) % 12) + 1
        q3_end = ((fy_end_month + 9 - 1) % 12) + 1
        q4_end = fy_end_month

        month_to_quarter = {q1_end: 1, q2_end: 2, q3_end: 3, q4_end: 4}

        # Step 4: Map each entry to "YYYYQn" -> reportedDate
        calendar = {}
        for entry in entries:
            fiscal_end = entry.get("fiscalDateEnding", "")
            reported = entry.get("reportedDate", "")
            if not fiscal_end or not reported:
                continue
            try:
                end_date = datetime.strptime(fiscal_end, "%Y-%m-%d").date()
            except ValueError:
                continue

            quarter_num = month_to_quarter.get(end_date.month)
            if quarter_num is None:
                continue

            # Determine fiscal year label
            if quarter_num == 4:
                fiscal_year = end_date.year
            elif end_date.month > fy_end_month:
                fiscal_year = end_date.year + 1
            else:
                fiscal_year = end_date.year

            key = f"{fiscal_year}Q{quarter_num}"
            calendar[key] = reported

        logger.info(f"Loaded earnings calendar for {ticker}: {len(calendar)} quarters (FY ends month {fy_end_month})")
        return calendar

    def _resolve_filing_date(self, quarter: str, earnings_calendar: Dict[str, str]) -> Optional[date]:
        """Resolve the actual filing date for a fiscal quarter.

        Looks up the exact reportedDate from the earnings calendar.
        Returns None if not found — better no date than a wrong one.
        """
        reported = earnings_calendar.get(quarter)
        if reported:
            try:
                return datetime.strptime(reported, "%Y-%m-%d").date()
            except ValueError:
                pass

        logger.warning(f"No earnings calendar match for {quarter}, filing_date will be None")
        return None

    def _fetch_from_alpha_vantage(self, ticker: str, num_quarters: int, min_year: int = None, max_year: int = None) -> Tuple[List[Document], IngestionTracker]:
        """
        Fetch transcripts from Alpha Vantage API (optimized to respect year range).

        Args:
            ticker: Company ticker
            num_quarters: Maximum number of quarters to fetch
            min_year: Minimum year (filters quarters before API calls)
            max_year: Maximum year (filters quarters before API calls)

        Returns:
            Tuple of (documents, tracker) for completeness tracking
        """
        documents = []

        today = date.today()
        current_year = today.year

        # Set year bounds
        if max_year is None:
            max_year = current_year
        if min_year is None:
            min_year = max_year - 2  # Default to 3 years

        # Fetch actual earnings calendar FIRST — this gives us correct fiscal quarter
        # labels (e.g. "2026Q4" for NVDA's Jan-ending FY) with their reportedDate.
        # Using these instead of calendar-year quarters fixes transcript fetch for
        # companies with non-December fiscal year ends.
        earnings_calendar = self._fetch_earnings_calendar(ticker)
        time.sleep(0.5)  # Respect rate limit before transcript calls

        if earnings_calendar:
            # Use fiscal quarters from earnings calendar, filtered by reportedDate year range
            quarters = []
            for quarter_key, reported_date_str in earnings_calendar.items():
                try:
                    reported_date = datetime.strptime(reported_date_str, "%Y-%m-%d").date()
                    if reported_date > today:
                        continue  # Skip future earnings
                    if min_year <= reported_date.year <= max_year:
                        quarters.append((reported_date, quarter_key))
                except ValueError:
                    continue
            # Sort by reportedDate descending (most recent first), take fiscal quarter keys
            quarters.sort(key=lambda x: x[0], reverse=True)
            quarters = [q[1] for q in quarters[:num_quarters]]
        else:
            # Fallback: generate calendar-year quarters if earnings calendar unavailable
            quarters = []
            for year in range(max_year, min_year - 1, -1):
                for q in range(4, 0, -1):
                    quarter_end_month = q * 3
                    quarter_date = date(year, quarter_end_month, 1)
                    if quarter_date <= today:
                        quarters.append(f"{year}Q{q}")
            quarters = quarters[:num_quarters]

        tracker = IngestionTracker(
            source_type="earnings_call",
            requested=list(quarters),
        )

        logger.info(f"Fetching {len(quarters)} quarters from Alpha Vantage (years {min_year}-{max_year}): {quarters}")

        management_titles = ["CEO", "CFO", "COO", "President", "Vice President",
                           "Chief", "Director", "EVP", "SVP"]

        def _fetch_and_parse(quarter):
            """Fetch and parse a single quarter's transcript. Returns (quarter, doc_or_None, error_or_None)."""
            try:
                data = self._fetch_single_quarter(ticker, quarter)

                if data is None:
                    return quarter, None, "No transcript available"

                transcript_data = data.get("transcript", [])

                # Parse statements
                sections = []
                full_text_parts = []

                for item in transcript_data:
                    speaker = item.get("speaker", "Unknown")
                    title = item.get("title", "")
                    content = item.get("content", "")
                    sentiment = float(item.get("sentiment", 0))

                    is_management = any(t in title for t in management_titles)
                    section_type = "management" if is_management else "analyst" if "Analyst" in title else "operator"

                    section = TranscriptSection(
                        speaker=speaker,
                        title=title,
                        content=content,
                        sentiment=sentiment,
                        section_type=section_type
                    )
                    sections.append(section)
                    full_text_parts.append(f"{speaker} ({title}): {content}")

                full_text = "\n\n".join(full_text_parts)

                # Parse quarter for fiscal period
                fiscal_quarter = int(quarter[-1])
                fiscal_year = int(quarter[:4])
                fiscal_period = f"Q{fiscal_quarter} {fiscal_year}"

                # Resolve actual filing date from earnings calendar (falls back to estimate)
                filing_date = self._resolve_filing_date(quarter, earnings_calendar)

                doc = Document(
                    source_type=SourceType.EARNINGS_TRANSCRIPT,
                    ticker=ticker,
                    content=full_text,
                    filing_date=filing_date,
                    fiscal_period=fiscal_period,
                    section="Full Transcript",
                    source_weight=self.base_weight,
                    recency_weight=self.calculate_recency_weight(filing_date),
                    metadata={
                        'source': 'alpha_vantage',
                        'quarter': quarter,
                        'statement_count': len(sections),
                        'sections': [s.__dict__ for s in sections[:5]]
                    }
                )

                # Cache it
                self._cache_transcript(doc)
                logger.info(f"{ticker} {fiscal_period}: {len(sections)} statements, {len(full_text):,} chars")

                return quarter, doc, None

            except RateLimitError as e:
                logger.warning(f"Rate limit exhausted for {ticker} {quarter} after retries: {e}")
                return quarter, None, "Rate limited (retries exhausted)"
            except Exception as e:
                logger.warning(f"Failed to fetch {ticker} {quarter}: {e}")
                return quarter, None, str(e)

        # Fetch quarters sequentially with small delay to avoid Alpha Vantage
        # silent throttling (returns empty transcript instead of rate limit error)
        for q in quarters:
            quarter, doc, error = _fetch_and_parse(q)
            if doc:
                documents.append(doc)
                tracker.succeeded.append(quarter)
            elif error:
                tracker.failed[quarter] = error
            time.sleep(0.5)

        return documents, tracker

    def _fetch_from_motley_fool(self, ticker: str, num_quarters: int) -> List[Document]:
        """Fetch transcripts from Motley Fool using Playwright (fallback)."""
        from playwright.sync_api import sync_playwright
        
        try:
            from backend.grain_lite.sources.earnings_calendar import get_transcript_urls
            urls_to_try = get_transcript_urls(ticker, num_quarters + 2)
        except ImportError:
            urls_to_try = []
        
        documents = []
        company_name = COMPANY_NAMES.get(ticker, ticker)
        
        logger.info(f"Fetching from Motley Fool (fallback) for {ticker}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            if urls_to_try:
                for quarter_label, earnings_date, url in urls_to_try:
                    if len(documents) >= num_quarters:
                        break
                    
                    try:
                        response = page.goto(url, wait_until='domcontentloaded', timeout=20000)
                        
                        if response and response.status == 200:
                            time.sleep(3)
                            
                            text = page.evaluate('document.body.innerText')
                            
                            if len(text) > 5000 and ('Prepared Remarks' in text or 'earnings' in text.lower()):
                                start = text.find('Prepared Remarks')
                                if start == -1:
                                    start = 0
                                end = text.find('Duration:')
                                if end == -1:
                                    end = len(text)
                                
                                transcript = text[start:end].strip()
                                
                                if len(transcript) > 3000:
                                    year, month, day = earnings_date.split('-')
                                    filing_date = date(int(year), int(month), int(day))
                                    fiscal_period = quarter_label.replace('_', ' ')
                                    
                                    doc = Document(
                                        source_type=SourceType.EARNINGS_TRANSCRIPT,
                                        ticker=ticker,
                                        content=transcript,
                                        filing_date=filing_date,
                                        fiscal_period=fiscal_period,
                                        section="Full Transcript",
                                        source_weight=self.base_weight,
                                        recency_weight=self.calculate_recency_weight(filing_date),
                                        metadata={'source': 'motley_fool', 'url': url}
                                    )
                                    documents.append(doc)
                                    self._cache_transcript(doc)
                                    print(f"    ✓ {fiscal_period} ({len(transcript):,} chars)")
                                    
                    except Exception:
                        continue
            
            browser.close()
        
        return documents
    
    def is_available(self, ticker: str) -> bool:
        """Check if we have or can get transcripts for this ticker."""
        cached = self._load_from_cache(ticker.upper())
        if cached:
            return True
        # Only Alpha Vantage is supported (Motley Fool fallback disabled)
        return self._has_alpha_vantage
    
    def _load_from_cache(self, ticker: str) -> List[Document]:
        """Load transcripts from local cache."""
        documents = []
        company_name = COMPANY_NAMES.get(ticker, ticker)
        
        patterns = [
            f"{company_name} {ticker}",
            f"{ticker}",
            f"{company_name}_{ticker}",
        ]
        
        for pattern in patterns:
            company_dir = self.cache_dir / pattern
            if company_dir.exists():
                for transcript_dir in company_dir.iterdir():
                    if transcript_dir.is_dir() and "Transcript" in transcript_dir.name:
                        for txt_file in transcript_dir.glob("*.txt"):
                            doc = self._parse_transcript_file(txt_file, ticker)
                            if doc:
                                documents.append(doc)
        
        return documents
    
    def _parse_transcript_file(self, filepath: Path, ticker: str) -> Optional[Document]:
        """Parse a transcript text file into a Document."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
            filing_date = None
            if date_match:
                filing_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
            
            quarter_match = re.search(r'Q([1-4])\s+(?:fiscal\s+)?(\d{4})', content[:500], re.IGNORECASE)
            fiscal_period = None
            if quarter_match:
                fiscal_period = f"Q{quarter_match.group(1)} {quarter_match.group(2)}"
            
            return Document(
                source_type=SourceType.EARNINGS_TRANSCRIPT,
                ticker=ticker,
                content=content,
                filing_date=filing_date,
                fiscal_period=fiscal_period,
                section="Full Transcript",
                source_weight=self.base_weight,
                recency_weight=self.calculate_recency_weight(filing_date),
                metadata={'source': 'cache', 'filepath': str(filepath)}
            )
            
        except Exception as e:
            logger.warning(f"Error parsing transcript {filepath}: {e}")
            return None
    
    def _cache_transcript(self, doc: Document) -> None:
        """Cache a transcript document to local storage."""
        try:
            company_name = COMPANY_NAMES.get(doc.ticker, doc.ticker)
            company_dir = self.cache_dir / f"{company_name} {doc.ticker}"
            company_dir.mkdir(parents=True, exist_ok=True)
            
            date_str = doc.filing_date.strftime("%Y-%m-%d") if doc.filing_date else "unknown"
            
            transcript_dir = company_dir / f"Earnings_Transcripts_{date_str}"
            transcript_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"{company_name}_{doc.ticker}_Earnings_Transcript_{date_str}.txt"
            filepath = transcript_dir / filename
            
            header = f"{company_name} Inc. ({doc.ticker})\n{doc.fiscal_period} Earnings Conference Call\n{date_str}\n\n"
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(header + doc.content)
            
            logger.debug(f"Cached: {filepath.name}")
                
        except Exception as e:
            logger.warning(f"Error caching transcript: {e}")


def get_transcript_source(cache_dir: Optional[str] = None) -> EarningsTranscriptSource:
    """Get a configured earnings transcript source."""
    return EarningsTranscriptSource(cache_dir=cache_dir)


if __name__ == "__main__":
    print("=" * 60)
    print("  GRAIN Earnings Transcript Source Test")
    print("=" * 60)
    
    source = EarningsTranscriptSource()
    print(f"\nCache directory: {source.cache_dir}")
    print(f"Alpha Vantage available: {source._has_alpha_vantage}")
    print(f"Playwright available: {source._has_playwright}")
    print(f"Base weight: {source.base_weight:.0%}")
    
    print("\n" + "-" * 40)
    print("Fetching AAPL transcripts...")
    
    result = source.fetch("AAPL", num_quarters=2)
    
    print(f"\nResults:")
    print(f"  Success: {result.success}")
    print(f"  Documents: {len(result.documents)}")
    print(f"  Fetch time: {result.fetch_time:.2f}s")
    
    for doc in result.documents:
        print(f"\n  📄 {doc.fiscal_period or 'Unknown period'}")
        print(f"     Date: {doc.filing_date}")
        print(f"     Source: {doc.metadata.get('source', 'unknown')}")
        print(f"     Weight: {doc.effective_weight:.2f}")
        print(f"     Content: {len(doc.content):,} chars")
        if 'statement_count' in doc.metadata:
            print(f"     Statements: {doc.metadata['statement_count']}")
