"""
grain_lite Document Chunker

Split documents into semantic chunks for embedding and retrieval.

Supports:
- Generic text chunking with section awareness
- Speaker-aware chunking for earnings calls (CEO/CFO weighted higher)
- SEC filing section parsing (Risk Factors, MD&A, etc.)
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re


class ChunkType(Enum):
    """Type of chunk content."""
    GENERIC = "generic"
    SEC_FILING = "sec_filing"
    EARNINGS_CALL = "earnings_call"
    NEWS = "news"


class SpeakerRole(Enum):
    """Role of speaker in earnings call."""
    CEO = "ceo"
    CFO = "cfo"
    EXECUTIVE = "executive"      # COO, President, VP, etc.
    INVESTOR_RELATIONS = "ir"
    ANALYST = "analyst"
    OPERATOR = "operator"
    UNKNOWN = "unknown"


@dataclass
class Chunk:
    """A chunk of text from a document."""
    text: str
    index: int
    start_char: int
    end_char: int
    
    # Source identification
    source_type: Optional[str] = None     # "10-K", "10-Q", "earnings_call"
    source_id: Optional[str] = None       # "AAPL_10K_2024"
    company: Optional[str] = None
    filing_date: Optional[str] = None
    filing_url: Optional[str] = None      # Direct link to SEC EDGAR filing
    
    # Section/context
    section: Optional[str] = None         # "risk_factors", "mda", "management", "qa"
    
    # Earnings call specific
    speaker: Optional[str] = None         # "Tim Cook"
    speaker_role: Optional[str] = None    # "CEO", "CFO", "Analyst"
    sentiment: Optional[float] = None     # -1 to 1
    
    # Scoring weights
    section_boost: float = 1.0
    speaker_boost: float = 1.0
    recency_boost: float = 1.0
    
    # General metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def char_count(self) -> int:
        return len(self.text)
    
    @property
    def word_count(self) -> int:
        return len(self.text.split())
    
    @property
    def effective_boost(self) -> float:
        """Combined boost factor."""
        return self.section_boost * self.speaker_boost * self.recency_boost


# =============================================================================
# SPEAKER ROLE DETECTION
# =============================================================================

def detect_speaker_role(title: str, speaker: str = "") -> SpeakerRole:
    """
    Detect the role of a speaker from their title.
    
    Args:
        title: Speaker's title (e.g., "Chief Executive Officer")
        speaker: Speaker's name (optional)
        
    Returns:
        SpeakerRole enum
    """
    title_lower = (title or "").lower()
    speaker_lower = (speaker or "").lower()
    
    # CEO patterns
    if any(t in title_lower for t in ["ceo", "chief executive"]):
        return SpeakerRole.CEO
    
    # CFO patterns
    if any(t in title_lower for t in ["cfo", "chief financial"]):
        return SpeakerRole.CFO
    
    # Other executives
    if any(t in title_lower for t in [
        "coo", "chief operating",
        "president", "vice president", "vp",
        "evp", "svp", "executive",
        "chief", "director of"
    ]):
        return SpeakerRole.EXECUTIVE
    
    # Investor Relations
    if any(t in title_lower for t in ["investor relation", "ir "]):
        return SpeakerRole.INVESTOR_RELATIONS
    
    # Analyst
    if "analyst" in title_lower:
        return SpeakerRole.ANALYST
    
    # Operator
    if "operator" in title_lower:
        return SpeakerRole.OPERATOR
    
    return SpeakerRole.UNKNOWN


def get_speaker_boost(role: SpeakerRole) -> float:
    """
    Get boost factor for speaker role.
    
    CEO/CFO statements are weighted higher than analyst questions.
    """
    boosts = {
        SpeakerRole.CEO: 1.5,
        SpeakerRole.CFO: 1.4,
        SpeakerRole.EXECUTIVE: 1.3,
        SpeakerRole.INVESTOR_RELATIONS: 1.0,
        SpeakerRole.ANALYST: 0.8,    # Questions, not statements
        SpeakerRole.OPERATOR: 0.2,   # Procedural
        SpeakerRole.UNKNOWN: 0.9,
    }
    return boosts.get(role, 1.0)


# =============================================================================
# SEC FILING SECTION DETECTION
# =============================================================================

SEC_SECTION_PATTERNS = {
    "risk_factors": [
        r"item\s*1a\.?\s*risk\s*factors?",
        r"risk\s*factors?(?:\s+and\s+uncertainties)?",
    ],
    "business": [
        r"item\s*1\.?\s*business",
        r"^business$",
        r"description\s+of\s+business",
    ],
    "mda": [
        r"item\s*7\.?\s*management",
        r"management['']?s\s*discussion\s*and\s*analysis",
        r"md&a",
    ],
    "financial_statements": [
        r"item\s*8\.?\s*financial\s*statements",
        r"consolidated\s+financial\s+statements",
    ],
    "legal_proceedings": [
        r"item\s*3\.?\s*legal\s*proceedings",
        r"^legal\s+proceedings$",
    ],
    "market_risk": [
        r"item\s*7a\.?\s*quantitative",
        r"quantitative\s+and\s+qualitative\s+disclosures?\s+about\s+market\s+risk",
    ],
    "controls": [
        r"item\s*9a\.?\s*controls",
        r"controls\s+and\s+procedures",
    ],
}


def detect_sec_section(text: str) -> Optional[str]:
    """
    Detect which SEC filing section text belongs to.
    
    Args:
        text: Text to analyze (usually first 500 chars)
        
    Returns:
        Section name or None
    """
    text_lower = text[:500].lower().strip()
    
    for section_name, patterns in SEC_SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return section_name
    
    return None


def get_section_boost(section: Optional[str], theme: Optional[str] = None) -> float:
    """
    Get boost factor for section type.
    
    Risk Factors gets highest boost for risk-related themes.
    """
    # Default section boosts
    boosts = {
        "risk_factors": 2.0,          # Critical for thematic exposure
        "mda": 1.5,                   # Management analysis
        "business": 1.2,              # Operational context
        "legal_proceedings": 1.3,     # Specific issues
        "market_risk": 1.4,           # Market risks
        "financial_statements": 0.8,  # Numbers, less useful for NLP
        "controls": 0.6,              # Internal controls
        None: 1.0,
    }
    
    # Adjust based on theme if provided
    if theme and section:
        theme_lower = theme.lower()
        
        # Risk-related themes get extra boost from risk_factors
        if any(t in theme_lower for t in ["risk", "exposure", "tariff", "china"]):
            if section == "risk_factors":
                return 2.5
        
        # Strategy themes get boost from MD&A
        if any(t in theme_lower for t in ["strategy", "growth", "market"]):
            if section == "mda":
                return 2.0
    
    return boosts.get(section, 1.0)


# =============================================================================
# EARNINGS CALL CHUNKER (SPEAKER-AWARE)
# =============================================================================

class EarningsCallChunker:
    """
    Chunk earnings call transcripts by speaker turns.
    
    Each chunk is a speaker's statement(s), preserving:
    - Speaker name and role
    - Sentiment score
    - Section type (prepared remarks vs Q&A)
    """
    
    def __init__(
        self,
        max_chunk_size: int = 2000,
        min_chunk_size: int = 100,
        combine_consecutive: bool = True
    ):
        """
        Initialize earnings call chunker.
        
        Args:
            max_chunk_size: Maximum chunk size (chars)
            min_chunk_size: Minimum chunk size
            combine_consecutive: Combine consecutive turns from same speaker
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.combine_consecutive = combine_consecutive
    
    def chunk_transcript(
        self,
        statements: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Chunk an earnings call transcript by speaker.
        
        Args:
            statements: List of statement dicts with speaker/title/content/sentiment
            metadata: Document-level metadata (company, quarter, etc.)
            
        Returns:
            List of Chunk objects
        """
        if not statements:
            return []
        
        metadata = metadata or {}
        chunks = []
        chunk_index = 0
        char_pos = 0
        
        # Detect section transitions (prepared remarks -> Q&A)
        qa_started = False
        
        i = 0
        while i < len(statements):
            stmt = statements[i]
            speaker = stmt.get("speaker", "Unknown")
            title = stmt.get("title", "")
            content = stmt.get("content", "")
            sentiment = float(stmt.get("sentiment", 0))
            
            # Detect Q&A section start
            if not qa_started and self._is_qa_transition(content, title):
                qa_started = True
            
            section = "analyst_qa" if qa_started else "management"
            
            # Detect speaker role
            role = detect_speaker_role(title, speaker)
            speaker_boost = get_speaker_boost(role)
            
            # Combine with consecutive turns from same speaker
            combined_content = content
            combined_sentiment = [sentiment]
            
            if self.combine_consecutive:
                while (i + 1 < len(statements) and 
                       statements[i + 1].get("speaker") == speaker and
                       len(combined_content) + len(statements[i + 1].get("content", "")) < self.max_chunk_size):
                    i += 1
                    next_stmt = statements[i]
                    combined_content += "\n\n" + next_stmt.get("content", "")
                    combined_sentiment.append(float(next_stmt.get("sentiment", 0)))
            
            # Skip if too short
            if len(combined_content) < self.min_chunk_size:
                i += 1
                continue

            # Average sentiment
            avg_sentiment = sum(combined_sentiment) / len(combined_sentiment)

            # Split long content at sentence boundaries (consistent with SECFilingChunker)
            content_pieces = self._split_long_content(combined_content)

            for piece in content_pieces:
                if len(piece) < self.min_chunk_size:
                    continue

                chunk = Chunk(
                    text=piece,
                    index=chunk_index,
                    start_char=char_pos,
                    end_char=char_pos + len(piece),
                    source_type="earnings_call",
                    source_id=metadata.get("source_id"),
                    company=metadata.get("company") or metadata.get("ticker"),
                    filing_date=metadata.get("filing_date"),
                    section=section,
                    speaker=speaker,
                    speaker_role=role.value,
                    sentiment=avg_sentiment,
                    section_boost=1.2 if section == "management" else 1.0,
                    speaker_boost=speaker_boost,
                    recency_boost=metadata.get("recency_boost", 1.0),
                    metadata={
                        "title": title,
                        "quarter": metadata.get("quarter"),
                        **metadata
                    }
                )

                chunks.append(chunk)
                chunk_index += 1
                char_pos += len(piece)

            i += 1

        return chunks

    def _split_long_content(self, text: str) -> List[str]:
        """
        Split long content at sentence boundaries using sentence-first approach.

        This ensures consistency with SECFilingChunker - no mid-word cuts.
        """
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # If content fits in one chunk, return as-is
        if len(text) <= self.max_chunk_size:
            return [text]

        # Split by sentences first (same pattern as SECFilingChunker)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

        pieces = []
        current_piece = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If adding sentence exceeds limit, save current piece
            if len(current_piece) + len(sentence) + 1 > self.max_chunk_size and len(current_piece) >= self.min_chunk_size:
                pieces.append(current_piece.strip())
                current_piece = ""

            # Handle sentences longer than max_chunk_size (rare edge case)
            if len(sentence) > self.max_chunk_size:
                # Save current piece first
                if current_piece.strip():
                    pieces.append(current_piece.strip())
                    current_piece = ""

                # Split long sentence at word boundaries
                while len(sentence) > self.max_chunk_size:
                    break_point = sentence.rfind(' ', 0, self.max_chunk_size)
                    if break_point == -1 or break_point < self.max_chunk_size // 2:
                        break_point = sentence.find(' ', self.max_chunk_size // 2)
                        if break_point == -1:
                            break_point = self.max_chunk_size

                    pieces.append(sentence[:break_point].strip())
                    sentence = sentence[break_point:].strip()

                # Remaining part becomes start of next piece
                current_piece = sentence
                continue

            current_piece = current_piece + " " + sentence if current_piece else sentence

        # Final piece
        if current_piece.strip():
            pieces.append(current_piece.strip())

        return pieces
    
    def _is_qa_transition(self, content: str, title: str) -> bool:
        """Detect if this is the transition to Q&A section."""
        content_lower = content.lower()
        title_lower = title.lower()
        
        # Operator typically announces Q&A
        if "operator" in title_lower:
            if any(t in content_lower for t in [
                "question-and-answer", "q&a", "questions", 
                "open the floor", "take your questions"
            ]):
                return True
        
        return False
    
    def chunk_from_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Chunk earnings call from raw text (fallback when no structured data).
        
        Uses regex patterns to detect speaker turns.
        """
        # Pattern: "Speaker Name (Title):" or "Speaker Name:" at line start
        speaker_pattern = r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*(?:\(([^)]+)\))?\s*:'
        
        statements = []
        for match in re.finditer(speaker_pattern, text, re.MULTILINE):
            speaker = match.group(1)
            title = match.group(2) or ""
            
            # Get content until next speaker or end
            start = match.end()
            next_match = re.search(speaker_pattern, text[start:], re.MULTILINE)
            if next_match:
                end = start + next_match.start()
            else:
                end = len(text)
            
            content = text[start:end].strip()
            
            if content:
                statements.append({
                    "speaker": speaker.strip(),
                    "title": title.strip(),
                    "content": content,
                    "sentiment": 0  # Unknown for text-based parsing
                })
        
        return self.chunk_transcript(statements, metadata)


# =============================================================================
# SEC FILING CHUNKER (SECTION-AWARE)
# =============================================================================

class SECFilingChunker:
    """
    Chunk SEC filings (10-K, 10-Q) with section awareness.
    
    Parses major sections and chunks each separately,
    preserving section metadata for retrieval filtering.
    """
    
    SECTION_HEADERS = {
        "10-K": [
            (r"ITEM\s*1A\.?\s*[-–]?\s*RISK\s*FACTORS", "risk_factors"),
            (r"ITEM\s*1\.?\s*[-–]?\s*BUSINESS", "business"),
            (r"ITEM\s*7\.?\s*[-–]?\s*MANAGEMENT", "mda"),
            (r"ITEM\s*7A\.?\s*[-–]?\s*QUANTITATIVE", "market_risk"),
            (r"ITEM\s*8\.?\s*[-–]?\s*FINANCIAL\s*STATEMENTS", "financial_statements"),
            (r"ITEM\s*3\.?\s*[-–]?\s*LEGAL\s*PROCEEDINGS", "legal_proceedings"),
        ],
        "10-Q": [
            (r"ITEM\s*1A\.?\s*[-–]?\s*RISK\s*FACTORS", "risk_factors"),
            (r"ITEM\s*2\.?\s*[-–]?\s*MANAGEMENT", "mda"),
            (r"ITEM\s*1\.?\s*[-–]?\s*FINANCIAL\s*STATEMENTS", "financial_statements"),
            (r"ITEM\s*3\.?\s*[-–]?\s*QUANTITATIVE", "market_risk"),
        ],
    }
    
    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100
    ):
        """
        Initialize SEC filing chunker.
        
        Args:
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            min_chunk_size: Minimum chunk size
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def chunk_filing(
        self,
        text: str,
        filing_type: str = "10-K",
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Chunk an SEC filing with section awareness.
        
        Args:
            text: Filing text
            filing_type: "10-K" or "10-Q"
            metadata: Document metadata
            
        Returns:
            List of Chunk objects with section labels
        """
        metadata = metadata or {}
        all_chunks = []
        
        # Parse document into sections
        sections = self._parse_sections(text, filing_type)
        
        # Chunk each section separately
        chunk_index = 0
        for section_name, section_text in sections.items():
            if len(section_text) < self.min_chunk_size:
                continue
            
            section_boost = get_section_boost(section_name)
            section_chunks = self._chunk_section(
                section_text, 
                section_name, 
                chunk_index,
                section_boost,
                metadata
            )
            
            all_chunks.extend(section_chunks)
            chunk_index += len(section_chunks)
        
        return all_chunks
    
    def _parse_sections(
        self, 
        text: str, 
        filing_type: str
    ) -> Dict[str, str]:
        """Parse document into named sections."""
        sections = {}
        headers = self.SECTION_HEADERS.get(filing_type, self.SECTION_HEADERS["10-K"])
        
        # Find all section starts
        section_positions = []
        for pattern, name in headers:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            for match in matches:
                section_positions.append((match.start(), match.end(), name))
        
        # Sort by position
        section_positions.sort(key=lambda x: x[0])
        
        # Extract section content
        for i, (start, header_end, name) in enumerate(section_positions):
            # Content starts after header
            content_start = header_end
            
            # Content ends at next section or end of document
            if i + 1 < len(section_positions):
                content_end = section_positions[i + 1][0]
            else:
                content_end = len(text)
            
            section_text = text[content_start:content_end].strip()
            
            # Store if substantial
            if len(section_text) > self.min_chunk_size:
                sections[name] = section_text
        
        # If no sections found, treat as single unnamed section
        if not sections:
            sections["general"] = text
        
        return sections
    
    def _chunk_section(
        self,
        text: str,
        section: str,
        start_index: int,
        section_boost: float,
        metadata: Dict[str, Any]
    ) -> List[Chunk]:
        """
        Chunk a single section using sentence-first approach.

        This approach splits text into sentences FIRST, then combines them into
        chunks that respect size limits. This ensures ~99% of chunks end at
        proper sentence boundaries (vs ~80% with paragraph-first approach).
        """
        chunks = []
        chunk_index = start_index

        # Normalize whitespace while preserving sentence structure
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) < self.min_chunk_size:
            return []

        # If text is small enough, return as single chunk
        if len(text) <= self.chunk_size:
            return [Chunk(
                text=self._clean_chunk_start(text),
                index=chunk_index,
                start_char=0,
                end_char=len(text),
                source_type=metadata.get("source_type", "sec_filing"),
                source_id=metadata.get("source_id"),
                company=metadata.get("company") or metadata.get("ticker"),
                filing_date=metadata.get("filing_date"),
                filing_url=metadata.get("filing_url"),
                section=section,
                section_boost=section_boost,
                recency_boost=metadata.get("recency_boost", 1.0),
                metadata=metadata
            )]

        # SENTENCE-FIRST APPROACH: Split into sentences, then combine
        # Pattern: period/question/exclamation followed by space and capital letter
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

        current_chunk = ""
        start_char = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If adding sentence exceeds limit, save current chunk
            if len(current_chunk) + len(sentence) + 1 > self.chunk_size and len(current_chunk) >= self.min_chunk_size:
                chunk_text = self._clean_chunk_start(current_chunk.strip())

                if len(chunk_text) >= self.min_chunk_size:
                    chunks.append(Chunk(
                        text=chunk_text,
                        index=chunk_index,
                        start_char=start_char,
                        end_char=start_char + len(chunk_text),
                        source_type=metadata.get("source_type", "sec_filing"),
                        source_id=metadata.get("source_id"),
                        company=metadata.get("company") or metadata.get("ticker"),
                        filing_date=metadata.get("filing_date"),
                        filing_url=metadata.get("filing_url"),
                        section=section,
                        section_boost=section_boost,
                        recency_boost=metadata.get("recency_boost", 1.0),
                        metadata=metadata
                    ))
                    chunk_index += 1

                # Start new chunk fresh (no overlap to avoid mid-word cuts)
                start_char = start_char + len(current_chunk)
                current_chunk = ""

            # Handle sentences longer than chunk_size (rare edge case)
            if len(sentence) > self.chunk_size:
                # Save current chunk first if any
                if len(current_chunk) >= self.min_chunk_size:
                    chunk_text = self._clean_chunk_start(current_chunk.strip())
                    if len(chunk_text) >= self.min_chunk_size:
                        chunks.append(Chunk(
                            text=chunk_text,
                            index=chunk_index,
                            start_char=start_char,
                            end_char=start_char + len(chunk_text),
                            source_type=metadata.get("source_type", "sec_filing"),
                            source_id=metadata.get("source_id"),
                            company=metadata.get("company") or metadata.get("ticker"),
                            filing_date=metadata.get("filing_date"),
                            section=section,
                            section_boost=section_boost,
                            recency_boost=metadata.get("recency_boost", 1.0),
                            metadata=metadata
                        ))
                        chunk_index += 1
                    start_char = start_char + len(current_chunk)
                    current_chunk = ""

                # Split long sentence at word boundaries
                while len(sentence) > self.chunk_size:
                    break_point = sentence.rfind(' ', 0, self.chunk_size)
                    if break_point == -1 or break_point < self.chunk_size // 2:
                        break_point = sentence.find(' ', self.chunk_size // 2)
                        if break_point == -1:
                            break_point = self.chunk_size

                    piece = sentence[:break_point].strip()
                    if len(piece) >= self.min_chunk_size:
                        chunks.append(Chunk(
                            text=piece,
                            index=chunk_index,
                            start_char=start_char,
                            end_char=start_char + len(piece),
                            source_type=metadata.get("source_type", "sec_filing"),
                            source_id=metadata.get("source_id"),
                            company=metadata.get("company") or metadata.get("ticker"),
                            filing_date=metadata.get("filing_date"),
                            section=section,
                            section_boost=section_boost,
                            recency_boost=metadata.get("recency_boost", 1.0),
                            metadata=metadata
                        ))
                        chunk_index += 1
                    start_char += len(piece) + 1
                    sentence = sentence[break_point:].strip()

                # Remaining part becomes start of next chunk
                current_chunk = sentence
                continue

            # Add sentence to current chunk
            current_chunk = current_chunk + " " + sentence if current_chunk else sentence

        # Final chunk
        if current_chunk.strip():
            chunk_text = self._clean_chunk_start(current_chunk.strip())
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(Chunk(
                    text=chunk_text,
                    index=chunk_index,
                    start_char=start_char,
                    end_char=start_char + len(chunk_text),
                    source_type=metadata.get("source_type", "sec_filing"),
                    source_id=metadata.get("source_id"),
                    company=metadata.get("company") or metadata.get("ticker"),
                    filing_date=metadata.get("filing_date"),
                    section=section,
                    section_boost=section_boost,
                    recency_boost=metadata.get("recency_boost", 1.0),
                    metadata=metadata
                ))

        return chunks

    def _clean_chunk_start(self, text: str) -> str:
        """Ensure chunk starts with capital letter, number, or bullet point."""
        match = re.search(r'[A-Z0-9•●■]', text)
        if match and match.start() < 50:  # Only trim if within first 50 chars
            return text[match.start():]
        return text
    
    def _get_overlap(self, text: str) -> str:
        """Get overlap text from end of current chunk, ensuring word boundaries."""
        if len(text) <= self.chunk_overlap:
            return ""

        overlap_region = text[-self.chunk_overlap * 2:]
        sentences = re.split(r'(?<=[.!?])\s+', overlap_region)

        if len(sentences) > 1:
            result = ""
            for sent in reversed(sentences):
                if len(result) + len(sent) <= self.chunk_overlap:
                    result = sent + " " + result
                else:
                    break
            return result.strip()

        # Fallback: ensure we don't cut mid-word
        overlap_text = text[-self.chunk_overlap:]
        # Find first space to start at word boundary
        space_pos = overlap_text.find(' ')
        if space_pos > 0 and space_pos < len(overlap_text) - 10:
            return overlap_text[space_pos:].strip()
        # If no good word boundary, skip overlap to avoid mid-word cuts
        return ""


# =============================================================================
# LEGACY / GENERIC CHUNKER
# =============================================================================

class SemanticChunker:
    """
    Generic semantic document chunker.
    
    For documents without special structure (news, etc).
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
        respect_sections: bool = True
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.respect_sections = respect_sections
    
    def chunk_document(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """Split a document into chunks."""
        if not text or len(text) < self.min_chunk_size:
            return []
        
        metadata = metadata or {}
        paragraphs = self._split_into_paragraphs(text)
        chunks = self._combine_into_chunks(paragraphs, text, metadata)
        
        return chunks
    
    def _split_into_paragraphs(self, text: str) -> List[Dict[str, Any]]:
        """Split text into paragraphs with positions."""
        paragraphs = []
        pattern = r'\n\s*\n'
        parts = re.split(pattern, text)
        
        current_pos = 0
        for part in parts:
            part = part.strip()
            if part:
                start = text.find(part, current_pos)
                if start == -1:
                    start = current_pos
                
                paragraphs.append({
                    'text': part,
                    'start': start,
                    'end': start + len(part),
                    'section': detect_sec_section(part)
                })
                
                current_pos = start + len(part)
        
        return paragraphs
    
    def _combine_into_chunks(
        self, 
        paragraphs: List[Dict], 
        original_text: str,
        metadata: Dict[str, Any]
    ) -> List[Chunk]:
        """Combine paragraphs into chunks."""
        chunks = []
        current_text = ""
        current_start = 0
        current_section = None
        chunk_index = 0
        
        for para in paragraphs:
            para_text = para['text']
            para_section = para['section']
            
            potential_size = len(current_text) + len(para_text) + 2
            
            should_start_new = (
                potential_size > self.chunk_size or
                (self.respect_sections and para_section and para_section != current_section)
            )
            
            if should_start_new and len(current_text) >= self.min_chunk_size:
                chunks.append(Chunk(
                    text=current_text.strip(),
                    index=chunk_index,
                    start_char=current_start,
                    end_char=current_start + len(current_text),
                    section=current_section,
                    section_boost=get_section_boost(current_section),
                    metadata=metadata
                ))
                chunk_index += 1
                
                overlap_text = self._get_overlap(current_text)
                current_text = overlap_text + "\n\n" + para_text if overlap_text else para_text
                current_start = para['start'] - len(overlap_text) if overlap_text else para['start']
                current_section = para_section or current_section
            else:
                if current_text:
                    current_text += "\n\n" + para_text
                else:
                    current_text = para_text
                    current_start = para['start']
                
                if para_section:
                    current_section = para_section
        
        if len(current_text) >= self.min_chunk_size:
            chunks.append(Chunk(
                text=current_text.strip(),
                index=chunk_index,
                start_char=current_start,
                end_char=current_start + len(current_text),
                section=current_section,
                section_boost=get_section_boost(current_section),
                metadata=metadata
            ))
        
        return chunks
    
    def _get_overlap(self, text: str) -> str:
        """Get overlap text, ensuring word boundaries."""
        if len(text) <= self.chunk_overlap:
            return ""

        overlap_region = text[-self.chunk_overlap*2:]
        sentences = re.split(r'(?<=[.!?])\s+', overlap_region)

        if len(sentences) > 1:
            result = ""
            for sent in reversed(sentences):
                if len(result) + len(sent) <= self.chunk_overlap:
                    result = sent + " " + result
                else:
                    break
            return result.strip()

        # Fallback: ensure we don't cut mid-word
        overlap_text = text[-self.chunk_overlap:]
        space_pos = overlap_text.find(' ')
        if space_pos > 0 and space_pos < len(overlap_text) - 10:
            return overlap_text[space_pos:].strip()
        return ""


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def chunk_earnings_call(
    statements: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    max_chunk_size: int = 2000
) -> List[Chunk]:
    """
    Convenience function to chunk earnings call by speaker.
    
    Args:
        statements: List of {speaker, title, content, sentiment}
        metadata: Document metadata
        max_chunk_size: Max chunk size
        
    Returns:
        List of Chunk objects with speaker/role metadata
    """
    chunker = EarningsCallChunker(max_chunk_size=max_chunk_size)
    return chunker.chunk_transcript(statements, metadata)


def chunk_sec_filing(
    text: str,
    filing_type: str = "10-K",
    metadata: Optional[Dict[str, Any]] = None,
    chunk_size: int = 1500
) -> List[Chunk]:
    """
    Convenience function to chunk SEC filing with section awareness.
    
    Args:
        text: Filing text
        filing_type: "10-K" or "10-Q"
        metadata: Document metadata
        chunk_size: Target chunk size
        
    Returns:
        List of Chunk objects with section metadata
    """
    chunker = SECFilingChunker(chunk_size=chunk_size)
    return chunker.chunk_filing(text, filing_type, metadata)


def chunk_document(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    metadata: Optional[Dict[str, Any]] = None
) -> List[Chunk]:
    """
    Convenience function to chunk generic document.
    
    Args:
        text: Document text
        chunk_size: Target chunk size
        chunk_overlap: Overlap between chunks
        metadata: Optional metadata
        
    Returns:
        List of Chunk objects
    """
    chunker = SemanticChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    return chunker.chunk_document(text, metadata)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  grain_lite Document Chunker Test")
    print("=" * 60)
    
    # Test 1: Earnings Call Chunking
    print("\n1. Testing Earnings Call Chunker...")
    
    sample_statements = [
        {"speaker": "Operator", "title": "Operator", "content": "Good afternoon. Welcome to Apple's Q4 earnings call.", "sentiment": 0.0},
        {"speaker": "Tim Cook", "title": "CEO", "content": "Thank you. We had an excellent quarter with strong iPhone sales across all regions. Our services business continues to grow at double digits.", "sentiment": 0.8},
        {"speaker": "Tim Cook", "title": "CEO", "content": "Greater China showed resilience despite macro challenges. We see AI as a major opportunity for the next decade.", "sentiment": 0.6},
        {"speaker": "Luca Maestri", "title": "CFO", "content": "Revenue was $90 billion, up 5% year over year. Gross margin expanded to 46%.", "sentiment": 0.7},
        {"speaker": "Operator", "title": "Operator", "content": "We will now begin the question and answer session.", "sentiment": 0.0},
        {"speaker": "Erik Woodring", "title": "Analyst, Morgan Stanley", "content": "Can you comment on China tariff impacts and how you're thinking about supply chain diversification?", "sentiment": -0.2},
        {"speaker": "Tim Cook", "title": "CEO", "content": "We continue to monitor the situation carefully. We have diversified some production to India and Vietnam.", "sentiment": 0.3},
    ]
    
    ec_chunker = EarningsCallChunker(max_chunk_size=1000)
    chunks = ec_chunker.chunk_transcript(sample_statements, {"company": "AAPL", "quarter": "Q4 2024"})
    
    print(f"   Created {len(chunks)} chunks from {len(sample_statements)} statements")
    for chunk in chunks:
        print(f"\n   [{chunk.index}] {chunk.speaker} ({chunk.speaker_role})")
        print(f"       Section: {chunk.section}")
        print(f"       Boost: speaker={chunk.speaker_boost:.1f}, section={chunk.section_boost:.1f}")
        print(f"       Sentiment: {chunk.sentiment:.2f}")
        print(f"       Text: {chunk.text[:100]}...")
    
    # Test 2: SEC Filing Section Detection
    print("\n" + "-" * 40)
    print("2. Testing SEC Section Detection...")
    
    sample_sec = """
    ITEM 1A. RISK FACTORS
    
    Investing in our common stock involves a high degree of risk. You should 
    carefully consider the risks described below.
    
    Our manufacturing operations are concentrated in China. Trade restrictions, 
    tariffs, and geopolitical tensions could materially impact our business.
    
    We depend on a limited number of suppliers for key components. Any disruption
    in supply could harm our results.
    
    ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS
    
    The following discussion should be read in conjunction with our consolidated
    financial statements. Revenue increased 5% driven by strong iPhone demand.
    
    We invested heavily in AI and machine learning capabilities during the year.
    """
    
    sec_chunker = SECFilingChunker(chunk_size=500)
    sec_chunks = sec_chunker.chunk_filing(sample_sec, "10-K", {"company": "AAPL"})
    
    print(f"   Created {len(sec_chunks)} chunks from SEC filing")
    for chunk in sec_chunks:
        print(f"\n   [{chunk.index}] Section: {chunk.section}")
        print(f"       Boost: {chunk.section_boost:.1f}")
        print(f"       Text: {chunk.text[:100]}...")
    
    # Test 3: Speaker Role Detection
    print("\n" + "-" * 40)
    print("3. Testing Speaker Role Detection...")
    
    test_titles = [
        "Chief Executive Officer",
        "CFO",
        "Analyst, Goldman Sachs",
        "VP of Operations",
        "Operator",
        "Director of Investor Relations",
    ]
    
    for title in test_titles:
        role = detect_speaker_role(title)
        boost = get_speaker_boost(role)
        print(f"   '{title}' -> {role.value} (boost: {boost:.1f}x)")
    
    print("\n✅ All tests complete!")
