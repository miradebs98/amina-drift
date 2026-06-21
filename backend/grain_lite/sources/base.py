"""
grain_lite Source Adapter Base

Abstract base class for document sources. Each source (10-K, earnings transcript, etc.)
implements this interface to provide documents for exposure scoring.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from enum import Enum


class SourceType(Enum):
    """Types of document sources."""
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    EIGHT_K = "8-K"
    EARNINGS_TRANSCRIPT = "earnings_transcript"
    DEF_14A = "DEF-14A"
    MACRO = "macro"


@dataclass
class Document:
    """A document from any source."""
    source_type: SourceType
    ticker: str
    content: str
    
    # Metadata
    filing_date: Optional[date] = None
    fiscal_period: Optional[str] = None  # e.g., "Q3 2024", "FY 2023"
    section: Optional[str] = None  # e.g., "Risk Factors", "MD&A", "CEO Remarks"
    
    # Transcript-specific
    speaker: Optional[str] = None  # e.g., "Tim Cook", "CFO"
    is_qa: bool = False  # Is this from Q&A section?
    
    # Scoring metadata
    source_weight: float = 1.0  # Base weight for this source
    recency_weight: float = 1.0  # Recency adjustment
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def effective_weight(self) -> float:
        """Combined weight for scoring."""
        return self.source_weight * self.recency_weight
    
    @property
    def age_days(self) -> int:
        """Days since document was filed/released."""
        if self.filing_date:
            return (date.today() - self.filing_date).days
        return 365  # Default to 1 year if unknown


@dataclass
class SourceResult:
    """Result from fetching documents from a source."""
    source_type: SourceType
    ticker: str
    documents: List[Document]
    success: bool
    error_message: Optional[str] = None
    fetch_time: float = 0.0  # Seconds to fetch


class DocumentSource(ABC):
    """
    Abstract base class for document sources.
    
    Each source (EDGAR, transcripts, etc.) implements this interface
    to provide a consistent way to fetch and process documents.
    """
    
    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """The type of source this adapter handles."""
        pass
    
    @property
    @abstractmethod
    def base_weight(self) -> float:
        """Base weight for documents from this source (0.0 to 1.0)."""
        pass
    
    @property
    def name(self) -> str:
        """Human-readable name for this source."""
        return self.source_type.value
    
    @abstractmethod
    def fetch(self, ticker: str, **kwargs) -> SourceResult:
        """
        Fetch documents for a ticker from this source.
        
        Args:
            ticker: Company ticker symbol
            **kwargs: Source-specific options
            
        Returns:
            SourceResult with documents and status
        """
        pass
    
    @abstractmethod
    def is_available(self, ticker: str) -> bool:
        """
        Check if this source has data available for a ticker.
        
        Args:
            ticker: Company ticker symbol
            
        Returns:
            True if data is available
        """
        pass
    
    def calculate_recency_weight(self, filing_date: date) -> float:
        """
        Calculate weight adjustment based on document age.
        
        More recent documents get higher weight.
        """
        if filing_date is None:
            return 0.5  # Unknown date = lower weight
        
        age_days = (date.today() - filing_date).days
        
        if age_days < 30:  # Last month
            return 1.2
        elif age_days < 90:  # Last quarter
            return 1.0
        elif age_days < 180:  # Last 6 months
            return 0.9
        elif age_days < 365:  # Last year
            return 0.7
        else:
            return 0.5  # Older than a year


# Source weight configuration
SOURCE_WEIGHTS = {
    SourceType.TEN_K: 0.35,
    SourceType.TEN_Q: 0.15,
    SourceType.EIGHT_K: 0.10,
    SourceType.EARNINGS_TRANSCRIPT: 0.30,
    SourceType.DEF_14A: 0.05,
    SourceType.MACRO: 0.05,
}


def get_source_weight(source_type: SourceType) -> float:
    """Get the configured weight for a source type."""
    return SOURCE_WEIGHTS.get(source_type, 0.1)
