from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from codecraft.agents.base import BaseAgent, AgentContext
from codecraft.llm.base import LLMMessage
from codecraft.llm.models import resolve_model_for_agent

logger = logging.getLogger(__name__)


class ThinkTank:
    """Enables multiple agents to collaborate on a single task through structured debate."""

    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds
        self._handlers: list[Callable[[str, dict[str, Any]], None]] = []

    def on_event(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._handlers.append(handler)

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        for handler in self._handlers:
            try:
                handler(event, data)
            except Exception:
                pass

    async def collaborate(
        self,
        agents: list[BaseAgent],
        task: str,
        context: AgentContext,
    ) -> dict[str, Any]:
        """
        Run a collaborative think-tank session:
        1. All agents produce an initial response independently
        2. Agents review each other's responses
        3. Agents refine their responses based on peer feedback
        4. Final convergence to a unified solution
        """
        results: dict[str, list[dict[str, Any]]] = {a.name: [] for a in agents}
        transcript: list[dict[str, Any]] = []

        self._emit("thinktank_start", {
            "task": task[:200],
            "agents": [a.name for a in agents],
            "max_rounds": self.max_rounds,
        })

        # Round 1: Independent thinking
        self._emit("thinktank_round", {"round": 1, "phase": "independent"})
        round_responses: dict[str, str] = {}

        for agent in agents:
            self._emit("agent_start", {"agent": agent.name, "task": task[:200]})
            try:
                response = await agent.run(task)
                round_responses[agent.name] = response
                results[agent.name].append({"round": 1, "role": "proposal", "content": response})
                transcript.append({"agent": agent.name, "round": 1, "content": response[:1000]})
                self._emit("agent_complete", {"agent": agent.name, "output_length": len(response)})
            except Exception as e:
                self._emit("agent_error", {"agent": agent.name, "error": str(e)})
                round_responses[agent.name] = f"[ERROR: {e}]"

        # Rounds 2..N: Review and refine
        for round_num in range(2, self.max_rounds + 1):
            self._emit("thinktank_round", {"round": round_num, "phase": "review"})

            previous_summary = self._build_round_summary(round_responses, transcript)
            review_task = (
                f"## Think Tank Round {round_num}\n"
                f"### Original Task\n{task}\n\n"
                f"### Peer Responses (Round {round_num - 1})\n{previous_summary}\n\n"
                f"### Your Role\n"
                f"Critique the other agents' approaches. Identify strengths and weaknesses. "
                f"Then produce your REFINED solution incorporating the best ideas from all agents. "
                f"If you now agree with another agent's approach, say so explicitly and explain why. "
                f"Be concise but thorough. Converge toward the best solution."
            )

            for agent in agents:
                self._emit("agent_start", {"agent": agent.name, "round": round_num})
                try:
                    response = await agent.run(review_task)
                    round_responses[agent.name] = response
                    results[agent.name].append({"round": round_num, "role": "refinement", "content": response})
                    transcript.append({"agent": agent.name, "round": round_num, "content": response[:1000]})
                    self._emit("agent_complete", {"agent": agent.name, "round": round_num})
                except Exception as e:
                    self._emit("agent_error", {"agent": agent.name, "round": round_num, "error": str(e)})

            if self._has_converged(round_responses):
                self._emit("thinktank_converged", {"round": round_num})
                break

        # Final: Synthesize
        self._emit("thinktank_round", {"phase": "synthesis"})
        final_solution = await self._synthesize(
            agents[0],
            task,
            round_responses,
            transcript,
        )

        self._emit("thinktank_complete", {
            "agents": len(agents),
            "rounds_completed": self.max_rounds,
            "solution_length": len(final_solution),
        })

        return {
            "final_solution": final_solution,
            "transcript": transcript,
            "individual_results": results,
            "converged": self._has_converged(round_responses),
        }

    def _build_round_summary(self, responses: dict[str, str], transcript: list) -> str:
        parts = []
        for agent_name, response in responses.items():
            short = response[:800] if len(response) > 800 else response
            parts.append(f"### {agent_name}\n{short}\n")
        return "\n".join(parts)

    def _has_converged(self, responses: dict[str, str]) -> bool:
        agree_indicators = [
            "i agree", "agreed", "concur", "i second", "same approach",
            "adopt", "combining", "merge", "similar", "i like the",
            "best approach is the same", "no further changes",
        ]
        agreement_count = 0
        for response in responses.values():
            lower = response.lower()
            if any(ind in lower for ind in agree_indicators):
                agreement_count += 1
        return agreement_count >= len(responses) * 0.6

    async def _synthesize(
        self,
        lead_agent: BaseAgent,
        task: str,
        final_responses: dict[str, str],
        transcript: list,
    ) -> str:
        summary = "\n\n".join(
            f"### {name}\n{resp[:1000]}" for name, resp in final_responses.items()
        )

        synthesis_prompt = (
            f"## Think Tank Synthesis\n"
            f"### Original Task\n{task}\n\n"
            f"### All Agent Final Responses\n{summary}\n\n"
            f"### Your Role\n"
            f"You are the synthesizer. Produce a SINGLE unified final answer that:\n"
            f"1. Incorporates the best ideas from ALL agents\n"
            f"2. Resolves any remaining disagreements\n"
            f"3. Is clear, actionable, and complete\n"
            f"4. Notes where there was disagreement and how it was resolved\n\n"
            f"## Final Unified Solution"
        )

        try:
            result = await lead_agent.run(synthesis_prompt)
            return result
        except Exception:
            agents_list = list(final_responses.keys())
            if agents_list:
                return final_responses[agents_list[0]]
            return "[Synthesis failed]"


class DebateSession:
    """Two or more agents debate a topic with structured turns."""

    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns

    async def debate(
        self,
        agents: list[BaseAgent],
        topic: str,
        moderator: Optional[BaseAgent] = None,
    ) -> dict[str, Any]:
        transcript: list[dict[str, Any]] = []
        positions: dict[str, dict[str, str]] = {}

        for turn in range(1, self.max_turns + 1):
            for agent in agents:
                other_agents = [a for a in agents if a.name != agent.name]
                other_positions = "\n".join(
                    f"{a.name} (turn {turn - 1}): {positions.get(a.name, {}).get(f'turn_{turn-1}', 'No position yet')[:500]}"
                    for a in other_agents
                )

                debate_prompt = (
                    f"## Debate: {topic}\n"
                    f"### Turn {turn}/{self.max_turns}\n\n"
                    f"### Other Agents' Most Recent Positions\n{other_positions}\n\n"
                    f"### Your Role\n"
                    f"1. If turn 1: State your position clearly\n"
                    f"2. If turn >1: Address counter-arguments, refine your position, "
                    f"acknowledge valid points from others.\n"
                    f"3. Be concise. Focus on strongest arguments."
                )

                try:
                    response = await agent.run(debate_prompt)
                    positions.setdefault(agent.name, {})[f"turn_{turn}"] = response
                    transcript.append({
                        "agent": agent.name,
                        "turn": turn,
                        "content": response[:1000],
                    })
                except Exception as e:
                    transcript.append({
                        "agent": agent.name,
                        "turn": turn,
                        "error": str(e),
                    })

        return {
            "topic": topic,
            "transcript": transcript,
            "final_positions": positions,
        }
