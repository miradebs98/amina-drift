"""
grain_lite Embedder

Generate embeddings for document chunks using OpenAI or local models.
"""

from typing import List, Optional, Union
import numpy as np

from backend.grain_lite.config import get_config
from backend.grain_lite.chunker import Chunk


class Embedder:
    """
    Text embedding generator for grain_lite.
    
    Uses OpenAI embeddings by default, with support for local models.
    """
    
    def __init__(self, model: Optional[str] = None):
        """
        Initialize embedder.
        
        Args:
            model: Embedding model name (default from config)
        """
        self.config = get_config()
        self.model = model or self.config.llm.embedding_model
        self._client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize OpenAI client."""
        if self.config.llm.has_openai:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.config.llm.openai_api_key, timeout=60.0)
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        else:
            raise ValueError("OpenAI API key required for embeddings")
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        # Truncate if too long (8191 tokens max for ada-002)
        if len(text) > 30000:
            text = text[:30000]
        
        response = self._client.embeddings.create(
            input=text,
            model=self.model
        )
        
        return response.data[0].embedding
    
    def embed_texts(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embedding vectors
        """
        import logging
        import time
        _logger = logging.getLogger(__name__)

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # Truncate long texts
            batch = [t[:30000] if len(t) > 30000 else t for t in batch]

            # Filter out empty/whitespace-only texts, track their indices
            valid_indices = []
            valid_batch = []
            for j, t in enumerate(batch):
                if t.strip():
                    valid_indices.append(j)
                    valid_batch.append(t)

            if not valid_batch:
                # All texts in this batch are empty — use zero vectors
                dim = 512  # text-embedding-3-small default dimension
                all_embeddings.extend([[0.0] * dim] * len(batch))
                continue

            # Try API call with one retry
            last_error = None
            for attempt in range(2):
                try:
                    response = self._client.embeddings.create(
                        input=valid_batch,
                        model=self.model
                    )
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    if attempt == 0:
                        _logger.warning(f"Embedding batch {i // batch_size} failed (attempt 1), retrying in 2s: {e}")
                        time.sleep(2)

            if last_error is not None:
                _logger.error(f"Embedding batch {i // batch_size} failed after retry: {last_error}")
                raise last_error

            # Sort by index to maintain order
            sorted_embeddings = sorted(response.data, key=lambda x: x.index)
            valid_embeddings = [e.embedding for e in sorted_embeddings]

            # Reconstruct full batch with zero vectors for empty texts
            dim = len(valid_embeddings[0]) if valid_embeddings else 512
            batch_embeddings = [[0.0] * dim for _ in range(len(batch))]
            for vi, original_idx in enumerate(valid_indices):
                batch_embeddings[original_idx] = valid_embeddings[vi]

            all_embeddings.extend(batch_embeddings)

        return all_embeddings
    
    def embed_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Generate embeddings for chunks and attach them.
        
        Args:
            chunks: List of Chunk objects
            
        Returns:
            Chunks with 'embedding' added to metadata
        """
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embed_texts(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.metadata['embedding'] = embedding
        
        return chunks


# Convenience functions
_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    """Get or create global embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def embed_text(text: str) -> List[float]:
    """Embed a single text."""
    return get_embedder().embed_text(text)


def embed_chunks(chunks: List[Chunk]) -> List[Chunk]:
    """Embed multiple chunks."""
    return get_embedder().embed_chunks(chunks)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(vec1)
    b = np.array(vec2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


if __name__ == "__main__":
    print("Testing grain_lite Embedder...")
    
    try:
        embedder = Embedder()
        
        # Test single embedding
        embedding = embedder.embed_text("Apple is exposed to China risk")
        print(f"✓ Generated embedding: {len(embedding)} dimensions")
        
        # Test similarity
        e1 = embedder.embed_text("China tariff risk exposure")
        e2 = embedder.embed_text("Greater China revenue concentration")
        e3 = embedder.embed_text("Sunny weather in California")
        
        sim_related = cosine_similarity(e1, e2)
        sim_unrelated = cosine_similarity(e1, e3)
        
        print(f"✓ Similarity (related): {sim_related:.3f}")
        print(f"✓ Similarity (unrelated): {sim_unrelated:.3f}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        print("  (This is expected if OPENAI_API_KEY is not set)")
