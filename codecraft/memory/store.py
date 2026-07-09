from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from codecraft.config import settings

logger = logging.getLogger(__name__)


class AgentMemory:
    def __init__(self, memory_dir: Optional[str] = None):
        memory_dir = memory_dir or str(Path(settings.data_dir) / "memory")
        Path(memory_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=memory_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collections: dict[str, Any] = {}
        logger.info(f"AgentMemory initialized at {memory_dir}")

    def _get_collection(self, name: str) -> Any:
        if name not in self._collections:
            safe_name = name.replace("/", "_").replace(" ", "_").replace(".", "_")
            self._collections[name] = self._client.get_or_create_collection(
                name=safe_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    def remember(
        self,
        agent: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        memory_type: str = "knowledge",
    ) -> str:
        mem_id = str(uuid.uuid4())
        collection = self._get_collection(agent)
        meta = metadata or {}
        meta["agent"] = agent
        meta["type"] = memory_type
        meta["timestamp"] = datetime.now(timezone.utc).isoformat()

        collection.add(
            ids=[mem_id],
            documents=[content[:8000]],
            metadatas=[meta],
        )
        return mem_id

    def recall(
        self,
        agent: str,
        query: str,
        n_results: int = 5,
        memory_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        try:
            collection = self._get_collection(agent)
            where = {"type": memory_type} if memory_type else None

            results = collection.query(
                query_texts=[query],
                n_results=min(n_results, collection.count()),
                where=where,
            )

            memories: list[dict[str, Any]] = []
            if results.get("ids") and results["ids"][0]:
                for i, mem_id in enumerate(results["ids"][0]):
                    memories.append({
                        "id": mem_id,
                        "content": results["documents"][0][i] if results.get("documents") else "",
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "score": results["distances"][0][i] if results.get("distances") else 0.0,
                    })
            return memories
        except Exception as e:
            logger.warning(f"Memory recall failed for {agent}: {e}")
            return []

    def forget(self, agent: str, memory_id: str) -> bool:
        try:
            collection = self._get_collection(agent)
            collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            logger.warning(f"Memory forget failed: {e}")
            return False

    def get_context_window(self, agent: str, query: str, max_tokens: int = 4000) -> str:
        memories = self.recall(agent, query, n_results=8)
        if not memories:
            return ""

        lines = ["## Relevant Past Knowledge\n"]
        for i, mem in enumerate(memories, 1):
            content = mem["content"]
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{i}. {content}")

        result = "\n".join(lines)
        if len(result) > max_tokens * 4:
            result = result[: max_tokens * 4]
        return result

    def remember_conversation(
        self,
        agent: str,
        role: str,
        content: str,
        project: str = "",
    ) -> str:
        return self.remember(
            agent=agent,
            content=f"[{role}]: {content}",
            metadata={"project": project, "role": role},
            memory_type="conversation",
        )

    def remember_artifact(
        self,
        agent: str,
        filename: str,
        content: str,
        project: str = "",
    ) -> str:
        return self.remember(
            agent=agent,
            content=f"[FILE: {filename}]\n{content}",
            metadata={"project": project, "filename": filename},
            memory_type="artifact",
        )

    def remember_decision(
        self,
        agent: str,
        decision: str,
        rationale: str = "",
        project: str = "",
    ) -> str:
        return self.remember(
            agent=agent,
            content=f"DECISION: {decision}\nRATIONALE: {rationale}",
            metadata={"project": project, "decision": decision[:100]},
            memory_type="decision",
        )

    def remember_error(
        self,
        agent: str,
        error: str,
        context: str = "",
        project: str = "",
    ) -> str:
        return self.remember(
            agent=agent,
            content=f"ERROR: {error}\nCONTEXT: {context}",
            metadata={"project": project, "error_type": error[:100]},
            memory_type="error",
        )

    def get_project_memories(self, project: str, n_results: int = 50) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for agent_name in self._list_collections():
            memories = self.recall(agent_name, project, n_results=n_results)
            for m in memories:
                if m.get("metadata", {}).get("project") == project:
                    results.append(m)
        return results[:n_results]

    def clear_agent_memory(self, agent: str) -> None:
        try:
            self._client.delete_collection(name=agent.replace("/", "_"))
            self._collections.pop(agent, None)
            logger.info(f"Cleared memory for agent: {agent}")
        except Exception as e:
            logger.warning(f"Failed to clear memory for {agent}: {e}")

    def clear_project_memory(self, project: str) -> int:
        deleted = 0
        for agent_name in self._list_collections():
            try:
                collection = self._get_collection(agent_name)
                results = collection.get(where={"project": project})
                if results.get("ids"):
                    collection.delete(ids=results["ids"])
                    deleted += len(results["ids"])
            except Exception:
                pass
        return deleted

    def _list_collections(self) -> list[str]:
        try:
            return [c.name for c in self._client.list_collections()]
        except Exception:
            return list(self._collections.keys())

    def get_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        total = 0
        for name in self._list_collections():
            try:
                collection = self._get_collection(name)
                count = collection.count()
                stats[name] = count
                total += count
            except Exception:
                stats[name] = 0
        stats["total"] = total
        return stats


_agent_memory: Optional[AgentMemory] = None


def get_memory() -> AgentMemory:
    global _agent_memory
    if _agent_memory is None:
        _agent_memory = AgentMemory()
    return _agent_memory
