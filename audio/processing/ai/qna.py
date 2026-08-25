from __future__ import annotations

import asyncio
from typing import Any

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from meetly.llm import LLMClient, SYSTEM_PROMPT
from .utils import QNA_PROMPT


class MeetingQnA:

    def __init__(
        self,
        transcript: str,
        llm: LLMClient,
        *,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        retrieval_k: int = 5,
    ) -> None:
        if not isinstance(transcript, str):
            raise TypeError(
                "transcript must be a string."
            )

        transcript = transcript.strip()

        if not transcript:
            raise ValueError(
                "Cannot initialize Q&A with an empty transcript."
            )

        if not isinstance(llm, LLMClient):
            raise TypeError(
                "llm must be an instance of LLMClient."
            )

        if chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than zero."
            )

        if chunk_overlap < 0:
            raise ValueError(
                "chunk_overlap cannot be negative."
            )

        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than chunk_size."
            )

        if retrieval_k <= 0:
            raise ValueError(
                "retrieval_k must be greater than zero."
            )

        self._llm = llm
        self._retrieval_k = retrieval_k

        self._vector_store = self._build_vector_store(
            transcript=transcript,
            embedding_model=embedding_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        self._retriever = self._vector_store.as_retriever(
            search_kwargs={
                "k": retrieval_k,
            }
        )

    async def answer(
        self,
        question: str,
    ) -> str:
        if not isinstance(question, str):
            raise TypeError(
                "question must be a string."
            )

        question = question.strip()

        if not question:
            raise ValueError(
                "Cannot answer an empty question."
            )

        documents = await asyncio.to_thread(
            self._retriever.invoke,
            question,
        )

        if not documents:
            return "Not mentioned."

        context = self._build_context(
            documents
        )

        if not context:
            return "Not mentioned."

        user_prompt = QNA_PROMPT.format(
            context=context,
            question=question,
        )

        answer = await self._llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        answer = answer.strip()

        return answer or "Not mentioned."

    @staticmethod
    def _build_vector_store(
        *,
        transcript: str,
        embedding_model: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> FAISS:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[
                "\n\n",
                "\n",
                ". ",
                " ",
                "",
            ],
        )

        documents = splitter.create_documents(
            [transcript]
        )

        if not documents:
            raise ValueError(
                "Transcript could not be converted into documents."
            )

        embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model,
        )

        return FAISS.from_documents(
            documents,
            embeddings,
        )

    @staticmethod
    def _build_context(
        documents: list[Any],
    ) -> str:
        context_parts: list[str] = []

        for document in documents:
            content = getattr(
                document,
                "page_content",
                None,
            )

            if not isinstance(content, str):
                continue

            content = content.strip()

            if content:
                context_parts.append(content)

        return "\n\n".join(
            context_parts
        )


__all__ = [
    "MeetingQnA",
]