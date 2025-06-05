# app/services/vector_db_client.py
import chromadb
from chromadb.utils import embedding_functions
from app.core.config import settings
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class VectorDBClient:
    def __init__(
        self, host: str, port: int, collection_name: str, embedding_model_name: str
    ):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        self._client = None
        self._collection = None
        self._ef = None  # Embedding function

        try:
            # Using HttpClient for connecting to a remote ChromaDB server
            self._client = chromadb.HttpClient(host=self.host, port=self.port)
            logger.info(f"ChromaDB HTTP client initialized for {self.host}:{self.port}")

            # Ping the server to check connectivity
            self._client.heartbeat()  # Raises exception if server is not reachable
            logger.info("Successfully connected to ChromaDB server.")

            # Initialize the embedding function
            # This will download the model if not already cached by sentence-transformers
            # Ensure the worker has internet access or the model is pre-cached in the Docker image
            self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model_name,
                # device="cuda" if torch.cuda.is_available() else "cpu" # Set device if needed
            )
            logger.info(
                f"SentenceTransformer embedding function initialized with model: {self.embedding_model_name}"
            )

            # Get or create the collection
            # Note: The embedding function should ideally be part of the collection metadata
            # if the collection is created with a specific embedding function.
            # If the collection exists, ChromaDB usually expects queries with vectors,
            # or it uses the EF associated with the collection.
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self._ef,  # Pass EF here for consistency
            )
            logger.info(
                f"ChromaDB collection '{self.collection_name}' retrieved/created successfully."
            )

        except Exception as e:
            logger.error(
                f"Failed to initialize VectorDBClient or connect to ChromaDB: {e}",
                exc_info=True,
            )
            self._client = None
            self._collection = None
            # Depending on the application's needs, you might re-raise or handle this gracefully.

    def is_healthy(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.heartbeat()
            return True
        except Exception:
            return False

    def add_documents(
        self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]
    ):
        if not self._collection:
            logger.error(
                "ChromaDB collection is not initialized. Cannot add documents."
            )
            raise ConnectionError("ChromaDB collection not initialized.")
        try:
            # ChromaDB's add method can take embeddings directly or generate them if an EF is associated
            # If EF is associated with collection, it might use that.
            # Or, you can pass embeddings explicitly:
            # embeddings = self._ef(documents) # Generate embeddings
            # self._collection.add(embeddings=embeddings, metadatas=metadatas, ids=ids)

            # If EF is associated with the collection at creation, it should handle embedding internally for documents.
            self._collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(
                f"Added {len(documents)} documents to collection '{self.collection_name}'."
            )
        except Exception as e:
            logger.error(f"Error adding documents to ChromaDB: {e}", exc_info=True)
            raise

    def query_documents(
        self, query_text: str, top_k: int = 5
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        if not self._collection:
            logger.error(
                "ChromaDB collection is not initialized. Cannot query documents."
            )
            raise ConnectionError("ChromaDB collection not initialized.")
        try:
            # Querying with text, ChromaDB will use the associated embedding function
            results = self._collection.query(
                query_texts=[query_text],
                n_results=top_k,
                include=[
                    "metadatas",
                    "documents",
                    "distances",
                ],  # 'distances' are similarity scores (lower is better for L2, higher for cosine)
            )

            # Process results: ChromaDB returns lists for each included field
            # results structure: QueryResult(ids=[[]], embeddings=None, documents=[[]], metadatas=[[]], distances=[[]])
            # We are querying for one text, so we expect lists of lists with one inner list.

            processed_results = []
            if results and results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    doc_id = results["ids"][0][i]
                    distance = (
                        results["distances"][0][i]
                        if results["distances"] and results["distances"][0]
                        else None
                    )
                    metadata = (
                        results["metadatas"][0][i]
                        if results["metadatas"] and results["metadatas"][0]
                        else {}
                    )
                    document_text = (
                        results["documents"][0][i]
                        if results["documents"] and results["documents"][0]
                        else ""
                    )

                    # Assuming distance is L2, convert to a pseudo-similarity (higher is better) if needed, or use as is.
                    # For cosine similarity (if used by EF), distance might already be similarity.
                    # Here, we'll just use the distance as the score.
                    score = (
                        1.0 - distance if distance is not None else 0.0
                    )  # Example for L2, needs adjustment for cosine

                    # Ensure metadata has 'text' if not included in 'documents' from Chroma
                    if "text" not in metadata and document_text:
                        metadata["text"] = document_text

                    processed_results.append(
                        (doc_id, score, metadata)  # (chunk_id, score, metadata_dict)
                    )

            logger.info(
                f"Query '{query_text[:30]}...' returned {len(processed_results)} results from '{self.collection_name}'."
            )
            return processed_results
        except Exception as e:
            logger.error(f"Error querying documents from ChromaDB: {e}", exc_info=True)
            raise

    def get_collection_count(self) -> Optional[int]:
        if not self._collection:
            logger.warning("ChromaDB collection is not initialized. Cannot get count.")
            return None
        try:
            return self._collection.count()
        except Exception as e:
            logger.error(f"Error getting collection count: {e}", exc_info=True)
            return None


# Global instance (optional, can be managed by a dependency injection system or context)
_vector_db_client_instance: Optional[VectorDBClient] = None


def get_vector_db_client() -> VectorDBClient:
    global _vector_db_client_instance
    if _vector_db_client_instance is None:
        logger.info("Initializing global VectorDBClient instance.")
        _vector_db_client_instance = VectorDBClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            collection_name=settings.CHROMA_COLLECTION_NAME,
            embedding_model_name=settings.EMBEDDING_MODEL_NAME,
        )
        if not _vector_db_client_instance.is_healthy():
            logger.error(
                "Failed to initialize a healthy global VectorDBClient instance."
            )
            # raise ConnectionError("Failed to connect to VectorDB on initialization")
            # Or allow it to be None and handle in calling code
            _vector_db_client_instance = None  # Set back to None if unhealthy
            raise ConnectionError(
                "Failed to establish a healthy connection with VectorDB."
            )

    if _vector_db_client_instance and not _vector_db_client_instance.is_healthy():
        logger.warning(
            "Global VectorDBClient instance is unhealthy. Attempting to re-initialize."
        )
        # Potentially add retry logic or re-initialization here
        # For now, we'll just log and subsequent calls might fail if it remains unhealthy.
        # Re-initialization could be:
        # _vector_db_client_instance = VectorDBClient(...)
        # if not _vector_db_client_instance.is_healthy(): ...
        raise ConnectionError("VectorDB client is currently unhealthy.")

    if (
        _vector_db_client_instance is None
    ):  # Check again after potential re-init attempt
        raise ConnectionError(
            "VectorDB client could not be initialized or is unhealthy."
        )

    return _vector_db_client_instance
