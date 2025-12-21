"""
Realtime Agent Orchestrator
Spins up text-only realtime agents for delegated tasks without touching the Twilio audio stream.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from openai.resources.realtime.realtime import AsyncRealtimeConnection
from openai.types.realtime import RealtimeServerEvent, session_update_event_param

from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.services.tool_service import ToolService

logger = logging.getLogger(__name__)

AGENT_TOOLSETS: Dict[str, List[str]] = {
    "math_agent": [
        "math_add",
        "math_subtract",
        "math_multiply",
        "math_divide",
    ],
    "availability_agent": [
        "get_available_employees",
        "check_booking_availability",
        "get_booking_calendar",
        "get_employee_bookings",
        "get_service_list",
    ],
    "booking_agent": [
        "create_booking",
        "create_customer",
        "update_customer",
        "get_customer_list",
    ],
    "data_agent": [
        "get_employee_list",
        "get_service_list",
        "get_department_list",
        "get_customer_list",
        "get_booking_calendar",
    ],
}

AGENT_INSTRUCTIONS: Dict[str, str] = {
    "math_agent": (
        "Bạn là Math Agent. Thực hiện các phép tính toán học cơ bản: "
        "- Cộng, trừ, nhân, chia hai số được cung cấp. "
        "- Luôn trả về kết quả rõ ràng và thông tin về phép tính đã thực hiện. "
        "Nếu gặp lỗi (ví dụ: chia cho 0), hãy báo rõ lỗi. "
        "Không cần chào hỏi, chỉ thực hiện tính toán khi được yêu cầu."
    ),
    "availability_agent": (
        "Bạn là Availability Agent. Bám sát call-flow: khi root báo bước 'kiểm tra khả dụng' hoặc cần gợi ý khung giờ khác, hãy dùng tools để: "
        "- Lấy nhân viên rảnh theo khoảng thời gian và dịch vụ; nếu không đủ dữ liệu, nêu rõ cần thêm gì (thời gian, duration, nhân viên ưu tiên). "
        "- Đọc lịch trong ngày (bookings/calendar) và lịch nhân viên để xem khung trống. "
        "- Nếu slot bận, đề xuất 2-3 khung giờ lân cận cùng ngày; nếu hết chỗ cả ngày, ghi rõ 'full day'. "
        "Trả về tóm tắt ngắn gọn cho root (đừng chào hỏi)."
    ),
    "booking_agent": (
        "Bạn là Booking Agent. Khi root đã xác nhận thông tin với khách, hãy: "
        "- Kiểm tra dữ liệu bắt buộc: serviceId, employeeId, startTime, endTime, customer name/furigana/phone/age/gender/category (nếu cần), twilioCallSid (có sẵn từ session). "
        "- Nếu thiếu, liệt kê rõ trường thiếu và dừng lại. Không tự đoán. "
        "- Nếu đủ, tạo booking qua API (POST /bookings) với notes/location preference nếu có. "
        "Trả về JSON tóm tắt: success/error, payload đã gửi, bookingId/response nếu thành công."
    ),
    "data_agent": (
        "Bạn là Data Agent. Thực hiện tra cứu nhanh phục vụ call-flow: "
        "- Dịch vụ (gợi ý theo duration/price nếu được cung cấp), nhân viên, chi nhánh/phòng ban, hoặc danh sách khách hàng khớp số điện thoại/tên. "
        "- Dùng đúng tool được cấp, không suy diễn. "
        "- Trả về tóm tắt ngắn gọn và các key/value chính để root tiếp tục hội thoại."
    ),
}


class RealtimeAgentOrchestrator:
    """Manage delegated realtime agents (text-only)"""

    def __init__(self, tool_service: ToolService, websocket_base_url: str):
        self.tool_service = tool_service
        self.websocket_base_url = websocket_base_url
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY, websocket_base_url=websocket_base_url
        )

    async def run_agent(
        self,
        agent_name: str,
        task_payload: Optional[Dict[str, Any]],
        session_manager: SessionManager,
    ) -> Dict[str, Any]:
        """Run a text-only realtime agent and return its summary."""
        if agent_name not in AGENT_INSTRUCTIONS:
            return {
                "success": False,
                "error": f"Unknown agent '{agent_name}'",
                "summary": "",
                "agent": agent_name,
            }

        instructions = AGENT_INSTRUCTIONS[agent_name]
        tool_names = AGENT_TOOLSETS.get(agent_name, [])
        tool_defs = self.tool_service.get_tool_definitions_by_names(tool_names)

        session_config: session_update_event_param.Session = {
            "type": "realtime",
            "model": settings.MODEL,
            "instructions": instructions,
            "output_modalities": ["text"],
            "tools": tool_defs,
            "tool_choice": "auto",
        }

        summary_chunks: List[str] = []
        tool_results: List[Dict[str, Any]] = []

        try:
            async with self.client.realtime.connect(
                model=settings.MODEL
            ) as connection:
                await connection.session.update(session=session_config)

                user_payload = task_payload or {}
                await connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": json.dumps(user_payload, ensure_ascii=False),
                            }
                        ],
                    }
                )
                await connection.response.create()

                async for event in connection:
                    event_type = getattr(event, "type", "")

                    if event_type == "response.output_text.delta":
                        summary_chunks.append(getattr(event, "delta", ""))
                    elif event_type == "response.function_call_arguments.done":
                        result = await self._handle_tool_call(
                            event, connection, session_manager, tool_names
                        )
                        if result:
                            tool_results.append(result)
                    elif event_type == "response.done":
                        break

                summary = "".join(summary_chunks).strip()
                return {
                    "success": True,
                    "summary": summary,
                    "agent": agent_name,
                    "tools_used": tool_results,
                }
        except Exception as exc:
            logger.error(
                "Delegated agent error (%s): %s", agent_name, exc, exc_info=True
            )
            return {
                "success": False,
                "error": str(exc),
                "summary": "".join(summary_chunks).strip(),
                "agent": agent_name,
                "tools_used": tool_results,
            }

    async def _handle_tool_call(
        self,
        event: RealtimeServerEvent,
        connection: AsyncRealtimeConnection,
        session_manager: SessionManager,
        allowed_tools: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Execute a tool call inside a delegated agent."""
        call_id = getattr(event, "call_id", None)
        function_name = getattr(event, "name", None)
        arguments_str = getattr(event, "arguments", "{}")

        if function_name not in allowed_tools:
            warning = {"error": f"Tool '{function_name}' không được phép", "success": False}
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(warning, ensure_ascii=False),
                }
            )
            await connection.response.create()
            return None

        try:
            arguments = json.loads(arguments_str)
            result = await self.tool_service.execute_tool(
                function_name, arguments, session_manager
            )

            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )
            await connection.response.create()

            return {"tool": function_name, "arguments": arguments, "result": result}
        except json.JSONDecodeError as exc:
            logger.error("Delegated agent args decode failed: %s", exc)
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {"error": f"Invalid JSON arguments: {exc}", "success": False},
                        ensure_ascii=False,
                    ),
                }
            )
            await connection.response.create()
            return None
        except Exception as exc:
            logger.error("Error in delegated tool %s: %s", function_name, exc, exc_info=True)
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {"error": str(exc), "success": False}, ensure_ascii=False
                    ),
                }
            )
            await connection.response.create()
            return {"tool": function_name, "error": str(exc), "success": False}
