# app/worker/logic/retrieval.py
from app.services.vector_db_client import VectorDBClient  # , get_vector_db_client

# Keyword search component would be defined here or imported
# For simplicity, we'll mock keyword search or omit it if focusing on vector search first.
from typing import List, Dict, Any, Tuple
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self, vector_db_client: VectorDBClient, top_k: int = 5):
        self.vector_db_client = vector_db_client
        self.top_k = top_k
        # self.keyword_search_client = ... # Initialize your keyword search client here

    def _semantic_search(
        self, question: str
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Performs semantic search using the vector database."""
        try:
            # query_documents returns list of (chunk_id, score, metadata)
            results = self.vector_db_client.query_documents(
                query_text=question, top_k=self.top_k
            )
            logger.info(
                f"Semantic search for '{question[:30]}...' returned {len(results)} passages."
            )
            return results
        except Exception as e:
            logger.error(f"Error during semantic search: {e}", exc_info=True)
            return []

    def _keyword_search(self, question: str) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Performs keyword search.
        This is a placeholder. A real implementation would query Elasticsearch, Whoosh,
        or a PostgreSQL FTS index.
        Returns: List of (chunk_id, score, metadata_dict)
        """
        logger.warning(
            "Keyword search is currently mocked/not implemented. Returning empty results."
        )
        # Example structure if implemented:
        # results = self.keyword_search_client.search(question, top_k=self.top_k)
        # return results
        return []

    def _combine_and_rerank(
        self,
        semantic_results: List[Tuple[str, float, Dict[str, Any]]],
        keyword_results: List[Tuple[str, float, Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """
        Combines and re-ranks results from semantic and keyword searches.
        A simple strategy: prioritize semantic results, then add unique keyword results.
        A more advanced strategy would use RRF (Reciprocal Rank Fusion) or similar.

        Returns: List of passage dictionaries, each containing 'text', 'source_id', 'chunk_id', 'score', 'url'.
        """
        combined_passages: Dict[str, Dict[str, Any]] = (
            {}
        )  # Use chunk_id as key to ensure uniqueness

        # Add semantic results
        for chunk_id, score, metadata in semantic_results:
            if chunk_id not in combined_passages:
                # Ensure 'text' is in metadata, if not, it might be an issue with vector_db_client.query_documents
                passage_text = metadata.get(
                    "text", f"Text for chunk {chunk_id} not found in metadata."
                )
                if passage_text == f"Text for chunk {chunk_id} not found in metadata.":
                    logger.warning(
                        f"Missing text for chunk {chunk_id} from semantic search metadata."
                    )

                combined_passages[chunk_id] = {
                    "chunk_id": chunk_id,
                    "text": passage_text,
                    "score": score,  # Semantic score
                    "source_id": metadata.get("document_id", "Unknown Source"),
                    "url": metadata.get("source_url", None),
                    "retrieval_method": "semantic",
                }

        # Add keyword results, giving less weight or only adding if not already present
        for chunk_id, score, metadata in keyword_results:
            if (
                chunk_id not in combined_passages
            ):  # Only add if not found by semantic search
                passage_text = metadata.get(
                    "text", f"Text for chunk {chunk_id} not found in metadata."
                )
                if passage_text == f"Text for chunk {chunk_id} not found in metadata.":
                    logger.warning(
                        f"Missing text for chunk {chunk_id} from keyword search metadata."
                    )

                combined_passages[chunk_id] = {
                    "chunk_id": chunk_id,
                    "text": passage_text,
                    "score": score,  # Keyword score
                    "source_id": metadata.get("document_id", "Unknown Source"),
                    "url": metadata.get("source_url", None),
                    "retrieval_method": "keyword",
                }
            # else: you could update the score if found by both, e.g., boost score

        # Convert to list and sort by score (descending, assuming higher is better)
        # This simple sort might not be ideal for RRF.
        sorted_passages = sorted(
            list(combined_passages.values()), key=lambda p: p["score"], reverse=True
        )

        logger.info(f"Combined and re-ranked {len(sorted_passages)} unique passages.")
        return sorted_passages[: self.top_k]

    def retrieve_passages(self, question: str) -> List[Dict[str, Any]]:
        """
        Main method to perform hybrid search and return top-k relevant passages.
        Each passage is a dict with 'text', 'source_id', 'chunk_id', 'score', 'url'.
        """
        logger.info(f"Retrieving passages for question: '{question[:50]}...'")

        semantic_results = self._semantic_search(question)
        # keyword_results = self._keyword_search(question) # Enable when implemented

        # For now, if keyword search is not implemented, just use semantic results
        # final_passages = self._combine_and_rerank(semantic_results, keyword_results)

        # Simplified: just use semantic results directly if keyword search is mocked
        final_passages_data = []
        for chunk_id, score, metadata in semantic_results:
            passage_text = metadata.get(
                "text", f"Text for chunk {chunk_id} not found in metadata."
            )
            if passage_text == f"Text for chunk {chunk_id} not found in metadata.":
                logger.warning(
                    f"Missing text for chunk {chunk_id} from semantic search metadata during final processing."
                )

            final_passages_data.append(
                {
                    "chunk_id": chunk_id,
                    "text": passage_text,
                    "score": score,
                    "source_id": metadata.get(
                        "document_id", "Unknown Source"
                    ),  # from ingestion metadata
                    "url": metadata.get("source_url", None),  # from ingestion metadata
                    "retrieval_method": "semantic",
                }
            )

        # Ensure we only return top_k results even after any combination logic
        final_passages_data = sorted(
            final_passages_data, key=lambda p: p["score"], reverse=True
        )[: self.top_k]

        if not final_passages_data:
            logger.warning(f"No passages found for question: '{question[:50]}...'")

        return final_passages_data


# To get an instance (can be managed by Celery task context or a global factory)
# def get_retriever() -> HybridRetriever:
#     vector_db_client = get_vector_db_client() # This will initialize if not already
#     return HybridRetriever(vector_db_client=vector_db_client, top_k=settings.RETRIEVAL_TOP_K)
