# data_ingestion/ingest.py
import logging
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.services.vector_db_client import (
    VectorDBClient,
)  # Using the same client as worker

# If storing metadata/chunks in PostgreSQL:
# from app.db.session import SessionLocal
# from app.models.chunk_metadata import ChunkMetadata # A new model if storing chunks in PG

from datasets import load_dataset, Dataset
from sentence_transformers import SentenceTransformer  # For chunking by tokens
from typing import List, Dict, Any, Iterator, Optional

# Setup logging for the script
setup_logging()
logger = logging.getLogger(__name__)
logger.setLevel(settings.LOG_LEVEL)  # Ensure script log level matches settings

# --- Text Splitting Logic ---
# Using a simple text splitter based on sentence-transformers tokenizer
# For more advanced splitting, consider LangChain's RecursiveCharacterTextSplitter


class SimpleTokenTextSplitter:
    def __init__(
        self,
        model_name: str = settings.EMBEDDING_MODEL_NAME,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
    ):
        self.tokenizer = SentenceTransformer(
            model_name
        ).tokenizer  # Access underlying tokenizer
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.info(
            f"SimpleTokenTextSplitter initialized with model '{model_name}', chunk_size={chunk_size}, overlap={chunk_overlap}"
        )

    def split_text(
        self, text: str, document_id: str, source_url: Optional[str]
    ) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []

        tokens = self.tokenizer.encode(text)
        chunks = []
        current_pos = 0
        chunk_index = 0

        while current_pos < len(tokens):
            end_pos = min(current_pos + self.chunk_size, len(tokens))
            chunk_tokens = tokens[current_pos:end_pos]

            # Decode tokens back to text for the current chunk
            # Ensure skip_special_tokens=True if the tokenizer adds them and they are not desired in the chunk text
            chunk_text = self.tokenizer.decode(
                chunk_tokens,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            ).strip()

            if chunk_text:  # Only add non-empty chunks
                chunk_id = f"{document_id}_chunk_{chunk_index}"
                chunks.append(
                    {
                        "id": chunk_id,  # This will be the ID in ChromaDB
                        "text": chunk_text,
                        "metadata": {
                            "document_id": document_id,  # Original document ID (e.g., article title)
                            "chunk_index": chunk_index,
                            "source_url": source_url
                            or f"wikipedia_article_{document_id.replace(' ', '_')}",
                            "original_text_length_tokens": len(
                                tokens
                            ),  # Length of the original document in tokens
                            "chunk_length_tokens": len(chunk_tokens),
                        },
                    }
                )
                chunk_index += 1

            if end_pos == len(tokens):  # Reached the end of the text
                break

            # Move current_pos forward by chunk_size minus overlap
            current_pos += self.chunk_size - self.chunk_overlap
            if (
                current_pos >= end_pos
            ):  # Ensure progress if overlap is large or chunk_size is small
                current_pos = end_pos

        if not chunks:
            logger.warning(
                f"No chunks created for document_id: {document_id}. Original text length: {len(text)} chars, {len(tokens)} tokens."
            )
        else:
            logger.debug(f"Split document {document_id} into {len(chunks)} chunks.")
        return chunks


def preprocess_wikipedia_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Basic preprocessing for a Wikipedia article from the dataset.
    The rahular/simple-wikipedia dataset has 'title', 'text', 'url', 'id'.
    'text' contains the main content, often with section headers like '== Section Title =='.
    """
    title = article.get("title", "Unknown Title")
    text_content = article.get("text", "")
    url = article.get("url", "")

    # Basic cleaning: remove excessive newlines, leading/trailing whitespace
    text_content = "\n".join(
        [line.strip() for line in text_content.splitlines() if line.strip()]
    )
    text_content = text_content.strip()

    # You might want to remove section headers or handle them specifically
    # For now, we'll keep them as part of the text.

    return {
        "document_id": title.replace(" ", "_").lower(),  # Create a usable ID from title
        "title": title,
        "text": text_content,
        "url": url,
    }


def load_and_chunk_data(
    dataset_name: str,
    text_splitter: SimpleTokenTextSplitter,
    limit: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    """
    Loads data from Hugging Face datasets, preprocesses, and splits it into chunks.
    Yields one chunk at a time to manage memory.
    """
    logger.info(f"Loading dataset: {dataset_name}")
    try:
        # Load a small portion for testing if limit is set
        split_str = f"train[:{limit}]" if limit else "train"
        dataset: Dataset = load_dataset(
            dataset_name, split=split_str, trust_remote_code=True
        )  # Added trust_remote_code
        logger.info(
            f"Dataset '{dataset_name}' loaded with {len(dataset)} articles (after limit)."
        )
    except Exception as e:
        logger.error(f"Failed to load dataset {dataset_name}: {e}", exc_info=True)
        return  # Stop iteration

    processed_articles = 0
    total_chunks_yielded = 0
    for article in dataset:
        processed_article = preprocess_wikipedia_article(article)
        if not processed_article["text"]:
            logger.warning(
                f"Skipping article '{processed_article['title']}' due to empty text content."
            )
            continue

        chunks = text_splitter.split_text(
            text=processed_article["text"],
            document_id=processed_article["document_id"],
            source_url=processed_article["url"],
        )

        for chunk_data in chunks:
            yield chunk_data  # chunk_data is {'id': str, 'text': str, 'metadata': dict}
            total_chunks_yielded += 1

        processed_articles += 1
        if processed_articles % 100 == 0:  # Log progress every 100 articles
            logger.info(
                f"Processed {processed_articles} articles, yielded {total_chunks_yielded} chunks so far..."
            )

    logger.info(
        f"Finished processing all {processed_articles} articles. Total chunks yielded: {total_chunks_yielded}."
    )


def run_ingestion(batch_size: int = 100, article_limit: Optional[int] = None):
    logger.info("Starting data ingestion process...")

    vector_db_client = None
    try:
        vector_db_client = VectorDBClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            collection_name=settings.CHROMA_COLLECTION_NAME,
            embedding_model_name=settings.EMBEDDING_MODEL_NAME,  # EF used by client
        )
        if not vector_db_client.is_healthy():
            logger.error("VectorDB client is not healthy. Aborting ingestion.")
            return

        current_count = vector_db_client.get_collection_count()
        logger.info(
            f"Current number of items in collection '{settings.CHROMA_COLLECTION_NAME}': {current_count}"
        )
        # Add logic here if you want to skip ingestion if already populated, or clear collection.
        # For this example, we'll just add new data. Duplicates might occur if IDs are not unique across runs.

    except ConnectionError as e:
        logger.error(
            f"Failed to connect to VectorDB: {e}. Aborting ingestion.", exc_info=True
        )
        return
    except Exception as e:  # Catch other init errors
        logger.error(
            f"Failed to initialize VectorDBClient: {e}. Aborting ingestion.",
            exc_info=True,
        )
        return

    text_splitter = SimpleTokenTextSplitter(
        model_name=settings.EMBEDDING_MODEL_NAME,  # Use the same model for token counting
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )

    chunk_iterator = load_and_chunk_data(
        dataset_name=settings.DATASET_NAME,
        text_splitter=text_splitter,
        limit=article_limit,  # For testing, process a limited number of articles
    )

    batch_documents: List[str] = []
    batch_metadatas: List[Dict[str, Any]] = []
    batch_ids: List[str] = []
    total_chunks_ingested = 0

    for chunk_data in chunk_iterator:
        batch_documents.append(chunk_data["text"])
        batch_metadatas.append(chunk_data["metadata"])
        batch_ids.append(chunk_data["id"])

        if len(batch_documents) >= batch_size:
            try:
                vector_db_client.add_documents(
                    documents=batch_documents, metadatas=batch_metadatas, ids=batch_ids
                )
                total_chunks_ingested += len(batch_documents)
                logger.info(
                    f"Ingested batch of {len(batch_documents)} chunks. Total ingested: {total_chunks_ingested}"
                )
            except Exception as e:
                logger.error(f"Failed to ingest batch: {e}", exc_info=True)
                # Decide on error handling: skip batch, retry, or abort.
            finally:
                batch_documents, batch_metadatas, batch_ids = [], [], []  # Clear batch

    # Ingest any remaining chunks in the last batch
    if batch_documents:
        try:
            vector_db_client.add_documents(
                documents=batch_documents, metadatas=batch_metadatas, ids=batch_ids
            )
            total_chunks_ingested += len(batch_documents)
            logger.info(
                f"Ingested final batch of {len(batch_documents)} chunks. Total ingested: {total_chunks_ingested}"
            )
        except Exception as e:
            logger.error(f"Failed to ingest final batch: {e}", exc_info=True)
        finally:
            batch_documents, batch_metadatas, batch_ids = [], [], []

    final_count = vector_db_client.get_collection_count()
    logger.info(
        f"Data ingestion process completed. Total chunks ingested in this run: {total_chunks_ingested}."
    )
    logger.info(
        f"New total number of items in collection '{settings.CHROMA_COLLECTION_NAME}': {final_count}"
    )


if __name__ == "__main__":
    # Example: Run ingestion with a limit of 10 articles for quick testing
    # In production, you'd run without article_limit or with a much larger one.
    # The ingestion can be run using:
    # docker-compose run --rm ingestion (if CMD in Dockerfile.ingestion is this script)
    # or
    # docker-compose run --rm ingestion python data_ingestion/ingest.py

    # For local testing without Docker:
    # Ensure .env is loaded (done by config.py) and dependencies are installed.
    # Make sure ChromaDB server is running if connecting to it.

    logger.info("Manual ingestion script execution started.")
    # Set a small limit for articles to process during manual run for testing
    # Set to None to process all articles from the dataset split.
    test_article_limit = (
        10  # Process first 10 articles from the dataset for a quick test
    )
    # test_article_limit = None # Process all

    run_ingestion(batch_size=50, article_limit=test_article_limit)
    logger.info("Manual ingestion script execution finished.")
