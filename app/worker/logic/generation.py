# app/worker/logic/generation.py
from app.services.llm_client import LLMClient  # , get_llm_client
from typing import List, Dict, Any, Optional
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class AnswerGenerator:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def _construct_prompt(
        self, question: str, context_passages: List[Dict[str, Any]]
    ) -> str:
        """
        Constructs a detailed prompt for the LLM, including context and instructions.
        Mistral Instruct models expect a specific format:
        <s>[INST] Instruction [/INST] Model answer</s>[INST] Follow-up instruction [/INST]
        """
        if not context_passages:
            logger.warning(
                "No context passages provided for prompt construction. Answer quality may be affected."
            )
            # Fallback prompt if no context
            prompt_template = (
                "<s>[INST] You are a helpful AI assistant. "
                "Please answer the following technical question to the best of your ability. "
                "Since no specific context documents were found, rely on your general knowledge. "
                "Question: {question}\n"
                "[/INST] Assistant Answer: "
            )
            return prompt_template.format(question=question)

        context_str = "\n\n".join(
            [
                f"[Context Passage - Source: {p.get('source_id', 'N/A')}, Chunk ID: {p.get('chunk_id', 'N/A')}]\n{p['text']}"
                for p in context_passages
            ]
        )

        # Mistral Instruct Prompt Template
        # Reference: https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.1#instruction-format
        # For multi-turn, the pattern is <s>[INST] UserTurn1 [/INST] ModelTurn1</s>[INST] UserTurn2 [/INST]
        # For single turn RAG:
        prompt = (
            "<s>[INST] You are a specialized AI assistant for Ramboll engineers. "
            "Your task is to answer the technical question below based *only* on the provided context passages. "
            "Do not use any external knowledge. "
            "If the context passages do not contain enough information to answer the question, clearly state that. "
            "When you use information from a passage, try to cite the Source and Chunk ID like this: [Source: <source_id>, Chunk: <chunk_id>]. "
            "Be concise and factual.\n\n"
            "--- CONTEXT PASSAGES START ---\n"
            "{context_str}\n"
            "--- CONTEXT PASSAGES END ---\n\n"
            "QUESTION: {question}\n"
            "[/INST] Assistant Answer based on the provided context: "
        )

        # A simpler prompt if the above is too complex or model struggles with it:
        # prompt = (
        #     "<s>[INST] Answer the following question based solely on the provided context passages. "
        #     "Cite sources if possible using [Source: ID]. If the answer is not in the context, say so.\n\n"
        #     "Context:\n{context_str}\n\n"
        #     "Question: {question} [/INST]"
        # )

        formatted_prompt = prompt.format(context_str=context_str, question=question)
        logger.debug(
            f"Constructed LLM prompt (first 300 chars): {formatted_prompt[:300]}..."
        )
        return formatted_prompt

    def generate_answer(
        self, question: str, context_passages: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Generates an answer using the LLM based on the question and retrieved context.
        """
        if not self.llm_client:
            logger.error("LLMClient is not available in AnswerGenerator.")
            return "Error: LLM service is not available."

        prompt = self._construct_prompt(question, context_passages)

        try:
            # Parameters for generation can be tuned
            generated_text = self.llm_client.generate_text(
                prompt,
                max_new_tokens=settings.LLM_MODEL_NAME.lower().find("mistral") > -1
                and 500
                or 300,  # Mistral can handle longer
                temperature=0.1,  # Factual
                top_p=0.9,
                do_sample=True,  # Important for temperature/top_p to have effect
            )

            if generated_text:
                logger.info(
                    f"Answer generated successfully for question: '{question[:30]}...'"
                )
                # Further post-processing can be done here (e.g., cleaning up citations, ensuring factual consistency if possible)
                return generated_text
            else:
                logger.warning(
                    f"LLM returned no text for question: '{question[:30]}...'"
                )
                return "The language model did not return a response for this question."
        except Exception as e:
            logger.error(f"Error during answer generation: {e}", exc_info=True)
            return f"An error occurred while generating the answer: {str(e)}"


# To get an instance (can be managed by Celery task context or a global factory)
# def get_answer_generator() -> AnswerGenerator:
#     llm_client = get_llm_client() # This will initialize if not already
#     return AnswerGenerator(llm_client=llm_client)
