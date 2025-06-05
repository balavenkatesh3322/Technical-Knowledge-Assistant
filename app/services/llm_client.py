# app/services/llm_client.py
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch
from app.core.config import settings
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, model_name_or_path: str, hf_token: Optional[str] = None):
        self.model_name_or_path = model_name_or_path
        self.tokenizer = None
        self.model = None
        self.pipeline = None  # Using pipeline for easier generation

        # Determine device
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"LLMClient will use device: {self.device}")

        try:
            logger.info(f"Loading tokenizer for {self.model_name_or_path}...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name_or_path, token=hf_token
            )
            logger.info("Tokenizer loaded successfully.")

            logger.info(f"Loading model {self.model_name_or_path}...")
            # For Mistral or similar models, you might need to specify torch_dtype for memory optimization
            # e.g., torch_dtype=torch.bfloat16 if using Ampere+ GPUs
            # For GGUF/GPTQ, loading is different (e.g. via llama-cpp-python, auto-gptq)
            # This basic loader is for full precision models from HF Hub.
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name_or_path,
                token=hf_token,
                torch_dtype=(
                    torch.float16 if self.device == "cuda" else torch.float32
                ),  # Use float16 on GPU if supported
                device_map="auto",  # Automatically distribute model across GPUs if available, or load to self.device
            )
            logger.info(
                f"Model {self.model_name_or_path} loaded successfully to device_map='auto'."
            )

            # Using Hugging Face pipeline for text generation
            self.pipeline = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                device=(
                    0 if self.device == "cuda" else -1
                ),  # device=0 for first GPU, -1 for CPU
                # torch_dtype=torch.bfloat16 # if model loaded with bfloat16
            )
            logger.info("Text generation pipeline initialized successfully.")

        except Exception as e:
            logger.error(
                f"Failed to initialize LLMClient with model {self.model_name_or_path}: {e}",
                exc_info=True,
            )
            # Fallback or re-raise. For now, attributes will remain None.
            self.tokenizer = None
            self.model = None
            self.pipeline = None
            raise ConnectionError(f"Could not initialize LLM: {e}")

    def generate_text(
        self,
        prompt: str,
        max_new_tokens: int = 250,
        temperature: float = 0.1,  # Low temperature for factual answers
        top_p: float = 0.9,
        do_sample: bool = True,  # Must be true if temperature or top_p are set for sampling
    ) -> Optional[str]:
        if not self.pipeline:
            logger.error("LLM pipeline is not initialized. Cannot generate text.")
            return None

        if temperature <= 0:  # Some models expect temp > 0 for sampling
            do_sample = False
            temperature = 0.1  # Set a default if disabling sampling due to temp

        try:
            logger.info(
                f"Generating text for prompt (first 100 chars): '{prompt[:100]}...'"
            )
            # Mistral instruct models expect a specific format, often with [INST] and [/INST]
            # This should be handled by the prompt construction logic before calling this client.

            # pipeline output is a list of dictionaries
            outputs = self.pipeline(
                prompt,
                max_new_tokens=max_new_tokens,
                do_sample=do_sample,
                temperature=(
                    temperature if do_sample else None
                ),  # only pass temp if sampling
                top_p=top_p if do_sample else None,  # only pass top_p if sampling
                # num_return_sequences=1, # Default is 1
                eos_token_id=self.tokenizer.eos_token_id,
                pad_token_id=(
                    self.tokenizer.eos_token_id
                    if self.tokenizer.pad_token_id is None
                    else self.tokenizer.pad_token_id
                ),
            )

            if (
                outputs
                and isinstance(outputs, list)
                and outputs[0].get("generated_text")
            ):
                generated_text_full = outputs[0]["generated_text"]
                # The pipeline often returns the prompt + generated text. We need to extract only the new part.
                # A common way is to check if the generated_text_full starts with the prompt.
                if generated_text_full.startswith(prompt):
                    generated_text_answer = generated_text_full[len(prompt) :].strip()
                else:
                    # This case might happen if the model or pipeline settings behave differently.
                    # Or if the prompt itself was part of a chat template applied by the pipeline.
                    # For now, we'll assume it's the full output and needs stripping.
                    # A more robust solution might involve looking for specific instruction tokens.
                    generated_text_answer = (
                        generated_text_full.strip()
                    )  # Fallback, might include prompt

                logger.info(
                    f"LLM generated text (first 100 chars of answer): '{generated_text_answer[:100]}...'"
                )
                return generated_text_answer
            else:
                logger.warning(
                    f"LLM generation returned an unexpected output format: {outputs}"
                )
                return None
        except Exception as e:
            logger.error(f"Error during LLM text generation: {e}", exc_info=True)
            return None


# Global instance
_llm_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client_instance
    if _llm_client_instance is None:
        logger.info("Initializing global LLMClient instance.")
        model_to_load = (
            settings.LLM_MODEL_PATH
            if settings.LLM_MODEL_PATH
            else settings.LLM_MODEL_NAME
        )
        try:
            _llm_client_instance = LLMClient(
                model_name_or_path=model_to_load,
                hf_token=settings.HUGGING_FACE_HUB_TOKEN,
            )
        except (
            ConnectionError
        ) as e:  # Catch the specific error raised by LLMClient constructor
            logger.error(f"Fatal error: LLMClient could not be initialized: {e}")
            _llm_client_instance = None  # Ensure it's None if init failed
            raise  # Re-raise to signal critical failure

    if (
        _llm_client_instance is None
    ):  # Should not be reached if constructor raises on failure
        raise ConnectionError("LLM client could not be initialized and is None.")

    return _llm_client_instance
