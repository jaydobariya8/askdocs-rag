from __future__ import annotations

import chromadb
from fastembed import TextEmbedding
from groq import Groq
from backend.config import settings

NO_INFO_MSG = "I don't have enough information in the uploaded documents to answer this question."

SYSTEM_PROMPT_TEMPLATE = """You are a helpful document assistant. Answer the user's question ONLY using the provided context from uploaded documents.

Rules:
- Only use information from the provided context
- If the context doesn't contain enough information to answer, say "I don't have enough information in the uploaded documents to answer this question."
- Be concise and accurate
- Cite which document the information comes from when possible

Context:
{context}"""


class RAGEngine:
    def __init__(self):
        self._chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._embed_model = TextEmbedding(model_name=settings.embedding_model)
        self._groq = Groq(api_key=settings.groq_api_key)
        self._collection = self._chroma.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._embed_model.embed(texts)]

    def add_document(self, doc_id: str, filename: str, chunks: list[str]) -> dict:
        embeddings = self._embed(chunks)
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"doc_id": doc_id, "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ]
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        return {"doc_id": doc_id, "filename": filename, "num_chunks": len(chunks)}

    def query(self, question: str) -> dict:
        question_embedding = self._embed([question])

        total = self._collection.count()
        if total == 0:
            return {
                "answer": NO_INFO_MSG,
                "sources": [],
                "chunks_used": 0,
            }

        n_results = min(settings.top_k, total)
        results = self._collection.query(
            query_embeddings=question_embedding,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        distances = results["distances"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]

        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # RELEVANCE_THRESHOLD acts as max acceptable distance
        best_distance = min(distances) if distances else 2.0
        if best_distance > settings.relevance_threshold:
            return {
                "answer": NO_INFO_MSG,
                "sources": [],
                "chunks_used": 0,
            }

        # Build context with source attribution
        context_parts = []
        sources = []
        for doc, meta, dist in zip(docs, metas, distances):
            if dist <= settings.relevance_threshold:
                fname = meta["filename"]
                context_parts.append(f"[Source: {fname}]\n{doc}")
                if fname not in sources:
                    sources.append(fname)

        context = "\n\n---\n\n".join(context_parts)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)

        response = self._groq.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        answer = response.choices[0].message.content

        return {
            "answer": answer,
            "sources": sources,
            "chunks_used": len(context_parts),
        }

    def list_documents(self) -> list[dict]:
        total = self._collection.count()
        if total == 0:
            return []

        # Fetch all metadata in batches
        results = self._collection.get(include=["metadatas"])
        metas = results["metadatas"]

        doc_map: dict[str, dict] = {}
        for meta in metas:
            doc_id = meta["doc_id"]
            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta["filename"],
                    "num_chunks": 0,
                }
            doc_map[doc_id]["num_chunks"] += 1

        return list(doc_map.values())

    def delete_document(self, doc_id: str) -> bool:
        results = self._collection.get(
            where={"doc_id": doc_id},
            include=["metadatas"],
        )
        ids_to_delete = results["ids"]
        if not ids_to_delete:
            return False
        self._collection.delete(ids=ids_to_delete)
        return True
