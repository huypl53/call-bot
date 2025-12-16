"""
Delegation Tool
Allows the root agent to hand off work to a specialized realtime agent.
"""

from typing import Any, Dict, Optional

from cti.agents.realtime_agent_orchestrator import RealtimeAgentOrchestrator
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


class DelegateToAgentTool(BaseTool):
    """Tool để handoff sang các realtime agent chuyên trách"""

    def __init__(self, orchestrator: RealtimeAgentOrchestrator):
        self._orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "delegate_to_agent"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": (
                "Chuyển tác vụ sang realtime agent chuyên trách. "
                "Các agent khả dụng: availability_agent, booking_agent, data_agent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": ["availability_agent", "booking_agent", "data_agent"],
                        "description": "Tên agent cần handoff",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Ngữ cảnh/tác vụ cần xử lý (ví dụ: thời gian, dịch vụ, nhân viên ưu tiên)",
                    },
                },
                "required": ["agent"],
            },
        }

    async def execute(
        self,
        session_manager: SessionManager,
        agent: str,
        payload: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return await self._orchestrator.run_agent(agent, payload, session_manager)
