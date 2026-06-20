"""
GRAIN EDGAR Integration

Wrapper around existing EDGAR extractor for fetching SEC filings.
"""

import os
import sys
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import date

from backend.grain_lite.utils import retry, RateLimitError, logger

# Configure EDGAR data directory
from backend.grain_lite.config import get_config
EDGAR_DIR = get_config().edgar_dir  # Uses GRAIN/data/raw_filings

# Cache for SEC company tickers JSON (2MB file, same for all tickers)
_tickers_cache = None
_tickers_cache_time = 0


def get_sec_headers() -> Dict[str, str]:
    """Get SEC API headers from environment."""
    # Environment already loaded by grain.config
    user_agent = os.getenv("SEC_USER_AGENT", "GRAIN User (grain@example.com)")
    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate"
    }


def _get_sec_tickers_data() -> Dict:
    """Get SEC company tickers JSON, cached for 1 hour."""
    import time
    global _tickers_cache, _tickers_cache_time

    if _tickers_cache and (time.time() - _tickers_cache_time) < 3600:
        return _tickers_cache

    headers = get_sec_headers()
    tickers_url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(tickers_url, headers=headers, timeout=30)
    if response.status_code == 429:
        retry_after = float(response.headers.get("Retry-After", 10))
        raise RateLimitError("SEC EDGAR rate limited for ticker lookup", retry_after=retry_after)
    response.raise_for_status()

    _tickers_cache = response.json()
    _tickers_cache_time = time.time()
    return _tickers_cache


def has_sec_filings(ticker: str) -> bool:
    """Fast check whether a ticker exists in SEC EDGAR.

    Uses the cached SEC company_tickers.json (no extra API call).
    Returns False for non-US tickers (e.g. AIR.PA, RHM.DE, SAP.DE)
    that are not registered SEC filers.
    """
    try:
        tickers_data = _get_sec_tickers_data()
        for entry in tickers_data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                return True
        return False
    except Exception:
        # If we can't check, assume it has filings (safe default)
        return True


@retry(max_attempts=3, delay=2.0, backoff=2.0, exceptions=(requests.RequestException, RateLimitError))
def fetch_company_info(ticker: str) -> Dict[str, Any]:
    """
    Fetch basic company information from SEC.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with cik, name, sic, sic_description, etc.
    """
    tickers_data = _get_sec_tickers_data()

    # Find the ticker
    for entry in tickers_data.values():
        if entry.get("ticker", "").upper() == ticker.upper():
            cik = str(entry["cik_str"]).zfill(10)
            return {
                "ticker": ticker.upper(),
                "cik": cik,
                "name": entry.get("title", ""),
            }

    raise ValueError(f"Ticker {ticker} not found")


@retry(max_attempts=3, delay=2.0, backoff=2.0, exceptions=(requests.RequestException, RateLimitError))
def fetch_filing_list(
    ticker: str,
    filing_types: List[str] = ["10-K", "10-Q"],
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch list of filings for a company.

    Args:
        ticker: Stock ticker symbol
        filing_types: Types of filings to fetch (10-K, 10-Q, 8-K)
        limit: Maximum number of filings per type

    Returns:
        List of filing metadata dicts
    """
    headers = get_sec_headers()
    company_info = fetch_company_info(ticker)
    cik = company_info["cik"]

    # Fetch submissions
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    response = requests.get(submissions_url, headers=headers, timeout=30)
    if response.status_code == 429:
        retry_after = float(response.headers.get("Retry-After", 10))
        raise RateLimitError(f"SEC EDGAR rate limited for {ticker} filing list", retry_after=retry_after)
    response.raise_for_status()
    data = response.json()

    filings = []
    target_count = limit * len(filing_types)

    def _extract_filings(submission_block):
        """Extract matching filings from a submissions block."""
        forms = submission_block.get("form", [])
        accessions = submission_block.get("accessionNumber", [])
        f_dates = submission_block.get("filingDate", [])
        primary_docs = submission_block.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form in filing_types and len(filings) < target_count:
                filings.append({
                    "ticker": ticker.upper(),
                    "cik": cik,
                    "form": form,
                    "accession": accessions[i],
                    "filing_date": f_dates[i],
                    "primary_document": primary_docs[i],
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accessions[i].replace('-', '')}/{primary_docs[i]}"
                })

    # Search "recent" first
    _extract_filings(data.get("filings", {}).get("recent", {}))

    # If we didn't find enough, paginate through older filing index files
    if len(filings) < target_count:
        overflow_files = data.get("filings", {}).get("files", [])
        for of in overflow_files:
            if len(filings) >= target_count:
                break
            try:
                of_url = f"https://data.sec.gov/submissions/{of['name']}"
                of_resp = requests.get(of_url, headers=headers, timeout=30)
                if of_resp.status_code == 429:
                    retry_after = float(of_resp.headers.get("Retry-After", 10))
                    raise RateLimitError(f"SEC EDGAR rate limited for {ticker} overflow", retry_after=retry_after)
                of_resp.raise_for_status()
                _extract_filings(of_resp.json())
            except RateLimitError:
                raise
            except Exception:
                continue

    return filings


@retry(max_attempts=3, delay=2.0, backoff=2.0, exceptions=(requests.RequestException, RateLimitError))
def fetch_filing_content(filing_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download and parse a filing's HTML content given its metadata.

    This is the fast path: takes pre-fetched filing metadata (from fetch_filing_list)
    and only makes a single HTTP request to download the document. Use this instead of
    fetch_filing() when you already have the filing metadata.

    Args:
        filing_meta: Dict from fetch_filing_list() with keys: url, form, filing_date, etc.

    Returns:
        Same dict with added raw_text and char_count fields
    """
    from bs4 import BeautifulSoup
    import re

    headers = get_sec_headers()

    url = filing_meta["url"]
    response = requests.get(url, headers=headers, timeout=60)
    if response.status_code == 429:
        retry_after = float(response.headers.get("Retry-After", 10))
        raise RateLimitError(
            f"SEC EDGAR rate limited fetching {filing_meta.get('ticker', '?')} {filing_meta.get('form', '?')}",
            retry_after=retry_after,
        )
    response.raise_for_status()

    # Parse HTML and extract text
    soup = BeautifulSoup(response.content, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "head", "meta", "link"]):
        element.decompose()

    # Remove iXBRL hidden elements that contain metadata garbage
    for element in soup.find_all(style=lambda x: x and 'display:none' in x.replace(' ', '').lower()):
        element.decompose()
    for element in soup.find_all(style=lambda x: x and 'visibility:hidden' in x.replace(' ', '').lower()):
        element.decompose()

    # Remove all ix: namespace elements (iXBRL inline tags)
    for tag_name in ['ix:header', 'ix:hidden', 'ix:resources', 'ix:references', 'ix:continuation', 'ix:footnote']:
        for element in soup.find_all(tag_name):
            element.decompose()

    text = soup.get_text(separator="\n")

    # Clean up whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Filter out XBRL metadata patterns from extracted text
    xbrl_patterns = [
        r'^[0-9]{10}\s+us-gaap:[A-Za-z]+.*$',
        r'^us-gaap:[A-Za-z]+.*$',
        r'^dei:[A-Za-z]+.*$',
        r'^[0-9]{10}\s+[0-9]{4}-[0-9]{2}-[0-9]{2}\s*$',
        r'^srt:[A-Za-z]+.*$',
        r'^[a-z]{2,10}:[A-Za-z]+.*$',
        r'^[a-z]{2,5}:[A-Z][A-Za-z]+Member\s*.*$',
    ]

    filtered_lines = []
    for line in lines:
        is_xbrl = False
        for pattern in xbrl_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                is_xbrl = True
                break
        if not is_xbrl:
            filtered_lines.append(line)

    clean_text = "\n".join(filtered_lines)

    # Return a copy with content added (don't mutate the input)
    result = dict(filing_meta)
    result["raw_text"] = clean_text
    result["char_count"] = len(clean_text)
    return result


def fetch_filing(
    ticker: str,
    filing_type: str = "10-K",
    filing_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch a specific filing's text content by looking it up in the filing list.

    Note: For bulk ingestion, prefer fetch_filing_content() with pre-fetched metadata
    to avoid redundant API calls (this function re-fetches the filing list each time).

    Args:
        ticker: Stock ticker symbol
        filing_type: Type of filing (10-K, 10-Q)
        filing_date: Optional specific date (YYYY-MM-DD), otherwise latest

    Returns:
        Dict with filing metadata and raw_text
    """
    # Use limit=20 to cover multi-year ranges (fixes 10-Q date mismatch bug)
    filings = fetch_filing_list(ticker, [filing_type], limit=20)

    if not filings:
        raise ValueError(f"No {filing_type} filings found for {ticker}")

    # Select filing
    if filing_date:
        filing = next((f for f in filings if f["filing_date"] == filing_date), None)
        if not filing:
            raise ValueError(f"No {filing_type} filing found for {ticker} on {filing_date}")
    else:
        filing = filings[0]  # Latest

    return fetch_filing_content(filing)


def fetch_company_filings(
    ticker: str,
    filing_types: List[str] = ["10-K"],
    limit: int = 1
) -> List[Dict[str, Any]]:
    """
    Fetch multiple filings with their content.
    
    Args:
        ticker: Stock ticker symbol
        filing_types: Types of filings to fetch
        limit: Number of filings per type
        
    Returns:
        List of filing dicts with raw_text
    """
    from tqdm import tqdm
    import time
    
    filing_list = fetch_filing_list(ticker, filing_types, limit)
    
    results = []
    for filing_meta in tqdm(filing_list, desc=f"Fetching {ticker} filings"):
        try:
            filing = fetch_filing(
                ticker, 
                filing_meta["form"], 
                filing_meta["filing_date"]
            )
            results.append(filing)
            time.sleep(1.0)  # SEC EDGAR rate limit: max 10 req/s
        except Exception as e:
            logger.warning(f"Failed to fetch {filing_meta['form']} from {filing_meta['filing_date']}: {e}")
    
    return results


if __name__ == "__main__":
    # Test EDGAR integration
    print("Testing GRAIN EDGAR integration...")
    
    try:
        # Test company info
        info = fetch_company_info("AAPL")
        print(f"✓ Company info: {info['name']} (CIK: {info['cik']})")
        
        # Test filing list
        filings = fetch_filing_list("AAPL", ["10-K"], limit=3)
        print(f"✓ Found {len(filings)} 10-K filings")
        
        # Test fetching content (optional - takes longer)
        # filing = fetch_filing("AAPL", "10-K")
        # print(f"✓ Fetched filing: {filing['char_count']} characters")
        
    except Exception as e:
        print(f"✗ Error: {e}")
