"""
Booking Agents - Flow-state agents powered by DynamicPromptService.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, cast

from agents import RunContextWrapper, Tool, function_tool
from agents.realtime import RealtimeAgent, RealtimeSession

from cti.core.connection_context import get_session_manager
from cti.services.dynamic_prompt_service import (
    DynamicPromptService,
    FlowState,
    STATE_TOOLS,
    VALID_TRANSITIONS,
)
from cti.tools.booking_api import CreateBookingTool
from cti.tools.department_api import GetDepartmentListTool
from cti.tools.employee_api import GetAvailableEmployeesTool, GetEmployeeListTool
from cti.tools.service_api import GetServiceListTool

# Handoff descriptions for each flow state agent
STATE_HANDOFF_DESCRIPTIONS: Dict[FlowState, str] = {
    FlowState.GREETING: "Agent chao khach va xac dinh muc dich dat lich",
    FlowState.DATE_SELECTION: "Agent thu thap ngay dat lich tu khach",
    FlowState.EMPLOYEE_SELECTION: "Agent hoi va xu ly chon tiep vien",
    FlowState.TIME_SERVICE: "Agent thu thap thoi gian va goi dich vu",
    FlowState.LOCATION: "Agent xu ly dia diem su dung dich vu",
    FlowState.AVAILABILITY_CHECK: "Agent kiem tra lich trong cua tiep vien",
    FlowState.OPTIONS: "Agent xu ly cac tuy chon bo sung",
    FlowState.PAYMENT: "Agent thu thap phuong thuc thanh toan",
    FlowState.CUSTOMER_INFO: "Agent thu thap thong tin khach hang",
    FlowState.CONFIRMATION: "Agent xac nhan va tao booking",
    FlowState.BOOKING_SUCCESS: "Agent thong bao dat lich thanh cong",
    FlowState.HUMAN_HANDOFF: "Agent chuyen cuoc goi cho nhan vien",
    FlowState.END: "Agent ket thuc cuoc goi",
}


@dataclass
class FlowAgentContext:
    """Context shared across flow agents and tools."""

    state: Any
    prompt_service: DynamicPromptService
    agents_by_state: Dict[FlowState, RealtimeAgent]
    session: Optional[RealtimeSession] = None


def _get_session_manager_or_error() -> tuple[Optional[Any], Optional[Dict[str, Any]]]:
    session_manager = get_session_manager()
    if session_manager is None:
        return None, {"success": False, "error": "Session manager not initialized"}
    return session_manager, None


@function_tool(
    name_override="save_booking_context",
    description_override=("Save booking information to the current flow context."),
)
async def save_booking_context_tool(
    run_context: RunContextWrapper[FlowAgentContext],
    field: str,
    value: str,
) -> Dict[str, Any]:
    """Save a field to the booking context."""
    context = run_context.context
    if context is None:
        return {"success": False, "error": "Flow context not initialized"}

    parsed_value: Any = value
    if field == "options":
        if value.startswith("["):
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                parsed_value = [value] if value else []
        else:
            parsed_value = [value] if value else []

    context.state.booking_context[field] = parsed_value

    return {
        "success": True,
        "message": f"Saved {field}",
        "field": field,
        "value": parsed_value,
        "current_context": context.state.booking_context.copy(),
    }


@function_tool(
    name_override="get_booking_context",
    description_override="Get the current booking context.",
)
async def get_booking_context_tool(
    run_context: RunContextWrapper[FlowAgentContext],
) -> Dict[str, Any]:
    """Get the current booking context."""
    context = run_context.context
    if context is None:
        return {"success": False, "error": "Flow context not initialized"}

    booking_context = context.state.booking_context.copy()
    booking_context["current_state"] = context.state.current_flow_state.value

    return {
        "success": True,
        "context": booking_context,
        "message": "Current booking context retrieved",
    }


@function_tool(
    name_override="get_employee_list",
    description_override="Lấy danh sách employees với phân trang.",
)
async def get_employee_list_tool(
    page: Optional[int] = None,
    size: Optional[int] = None,
) -> Dict[str, Any]:
    """Get employee list from the Employee API."""
    session_manager, error = _get_session_manager_or_error()
    if error:
        return error
    assert session_manager is not None

    tool = GetEmployeeListTool()
    return await tool.execute(session_manager=session_manager, page=page, size=size)


@function_tool(
    name_override="get_available_employees",
    description_override=(
        "Lấy danh sách nhân viên rảnh theo employeeId và khoảng thời gian."
    ),
)
async def get_available_employees_tool(
    employeeId: str,
    startTime: str,
    endTime: str,
    page: Optional[int] = None,
    size: Optional[int] = None,
    employeeName: Optional[str] = None,
) -> Dict[str, Any]:
    """Get available employees for the given time range."""
    session_manager, error = _get_session_manager_or_error()
    if error:
        return error
    assert session_manager is not None

    tool = GetAvailableEmployeesTool()
    return await tool.execute(
        session_manager=session_manager,
        page=page,
        size=size,
        employeeName=employeeName,
        employeeId=employeeId,
        startTime=startTime,
        endTime=endTime,
    )


@function_tool(
    name_override="get_service_list",
    description_override="Lấy danh sách services với phân trang.",
)
async def get_service_list_tool(
    page: Optional[int] = None,
    size: Optional[int] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    minDurationMinutes: Optional[int] = None,
    maxDurationMinutes: Optional[int] = None,
    minPrice: Optional[float] = None,
    maxPrice: Optional[float] = None,
) -> Dict[str, Any]:
    """Get service list from the Service API."""
    session_manager, error = _get_session_manager_or_error()
    if error:
        return error
    assert session_manager is not None

    tool = GetServiceListTool()
    return await tool.execute(
        session_manager=session_manager,
        page=page,
        size=size,
        name=name,
        description=description,
        minDurationMinutes=minDurationMinutes,
        maxDurationMinutes=maxDurationMinutes,
        minPrice=minPrice,
        maxPrice=maxPrice,
    )


@function_tool(
    name_override="get_department_list",
    description_override="Lấy danh sách chi nhánh/phòng ban với phân trang.",
)
async def get_department_list_tool(
    page: Optional[int] = None,
    size: Optional[int] = None,
    name: Optional[str] = None,
    address: Optional[str] = None,
) -> Dict[str, Any]:
    """Get department list from the Department API."""
    session_manager, error = _get_session_manager_or_error()
    if error:
        return error
    assert session_manager is not None

    tool = GetDepartmentListTool()
    return await tool.execute(
        session_manager=session_manager,
        page=page,
        size=size,
        name=name,
        address=address,
    )


@function_tool(
    name_override="create_booking",
    description_override="Tạo booking mới với thông tin khách hàng và booking.",
)
async def create_booking_tool(
    serviceId: str,
    employeeId: str,
    startTime: str,
    endTime: str,
    customerName: str,
    departmentId: Optional[str] = None,
    options: Optional[list[str]] = None,
    paymentMethod: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a booking via the Booking API."""
    session_manager, error = _get_session_manager_or_error()
    if error:
        return error
    assert session_manager is not None

    tool = CreateBookingTool()
    return await tool.execute(
        session_manager=session_manager,
        source="phone",
        serviceId=serviceId,
        employeeId=employeeId,
        startTime=startTime,
        endTime=endTime,
        customerName=customerName,
        departmentId=departmentId,
        options=options,
        paymentMethod=paymentMethod,
        notes=notes,
    )


TOOL_REGISTRY = {
    "save_booking_context": save_booking_context_tool,
    "get_booking_context": get_booking_context_tool,
    "get_employee_list": get_employee_list_tool,
    "get_available_employees": get_available_employees_tool,
    "get_service_list": get_service_list_tool,
    "get_department_list": get_department_list_tool,
    "create_booking": create_booking_tool,
}


def _build_state_instructions(
    flow_state: FlowState, prompt_service: DynamicPromptService
):
    def _instructions(
        run_context: RunContextWrapper[FlowAgentContext],
        agent: RealtimeAgent,
    ) -> str:
        context = run_context.context
        if context is None:
            return prompt_service.get_prompt(flow_state, {})
        booking_context = getattr(context.state, "booking_context", {})
        return context.prompt_service.get_prompt(flow_state, booking_context)

    return _instructions


def _make_state_agent(
    flow_state: FlowState, prompt_service: DynamicPromptService
) -> RealtimeAgent:
    tool_names = STATE_TOOLS.get(flow_state, [])
    tools = [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]
    return RealtimeAgent(
        name=f"flow_{flow_state.value}",
        handoff_description=STATE_HANDOFF_DESCRIPTIONS.get(flow_state, ""),
        instructions=_build_state_instructions(flow_state, prompt_service),
        tools=cast(list[Tool], tools),
    )


def _wire_handoffs(agents_by_state: Dict[FlowState, RealtimeAgent]) -> None:
    for from_state, to_states in VALID_TRANSITIONS.items():
        from_agent = agents_by_state.get(from_state)
        if from_agent is None:
            continue
        for to_state in to_states:
            to_agent = agents_by_state.get(to_state)
            if to_agent and to_agent not in from_agent.handoffs:
                from_agent.handoffs.append(to_agent)


def _mermaid_node_id(flow_state: FlowState) -> str:
    return f"flow_{flow_state.value}"


def _mermaid_label(value: str) -> str:
    return value.replace('"', '\\"')


def build_flow_agents(
    prompt_service: DynamicPromptService,
) -> Dict[FlowState, RealtimeAgent]:
    """Build a RealtimeAgent per flow state and wire handoffs per flow chart."""
    greeting_agent = _make_state_agent(FlowState.GREETING, prompt_service)
    date_selection_agent = _make_state_agent(FlowState.DATE_SELECTION, prompt_service)
    employee_selection_agent = _make_state_agent(
        FlowState.EMPLOYEE_SELECTION, prompt_service
    )
    time_service_agent = _make_state_agent(FlowState.TIME_SERVICE, prompt_service)
    location_agent = _make_state_agent(FlowState.LOCATION, prompt_service)
    availability_check_agent = _make_state_agent(
        FlowState.AVAILABILITY_CHECK, prompt_service
    )
    options_agent = _make_state_agent(FlowState.OPTIONS, prompt_service)
    payment_agent = _make_state_agent(FlowState.PAYMENT, prompt_service)
    customer_info_agent = _make_state_agent(FlowState.CUSTOMER_INFO, prompt_service)
    confirmation_agent = _make_state_agent(FlowState.CONFIRMATION, prompt_service)
    booking_success_agent = _make_state_agent(FlowState.BOOKING_SUCCESS, prompt_service)
    human_handoff_agent = _make_state_agent(FlowState.HUMAN_HANDOFF, prompt_service)
    end_agent = _make_state_agent(FlowState.END, prompt_service)

    agents = {
        FlowState.GREETING: greeting_agent,
        FlowState.DATE_SELECTION: date_selection_agent,
        FlowState.EMPLOYEE_SELECTION: employee_selection_agent,
        FlowState.TIME_SERVICE: time_service_agent,
        FlowState.LOCATION: location_agent,
        FlowState.AVAILABILITY_CHECK: availability_check_agent,
        FlowState.OPTIONS: options_agent,
        FlowState.PAYMENT: payment_agent,
        FlowState.CUSTOMER_INFO: customer_info_agent,
        FlowState.CONFIRMATION: confirmation_agent,
        FlowState.BOOKING_SUCCESS: booking_success_agent,
        FlowState.HUMAN_HANDOFF: human_handoff_agent,
        FlowState.END: end_agent,
    }

    _wire_handoffs(agents)
    return agents


def build_flow_agents_mermaid(
    agents_by_state: Dict[FlowState, RealtimeAgent],
) -> str:
    """Build a Mermaid flowchart for the current agent handoff graph."""
    flow_state_order = {state: index for index, state in enumerate(FlowState)}
    sorted_states = sorted(agents_by_state, key=lambda state: flow_state_order[state])
    agent_id_to_state = {
        id(agent): state for state, agent in agents_by_state.items()
    }
    node_ids = {state: _mermaid_node_id(state) for state in sorted_states}

    lines = ["flowchart TD"]
    for state in sorted_states:
        agent = agents_by_state[state]
        node_id = node_ids[state]
        lines.append(f'    {node_id}["{_mermaid_label(agent.name)}"]')

    for state in sorted_states:
        from_agent = agents_by_state[state]
        from_id = node_ids[state]
        to_states = [
            agent_id_to_state[to_agent_id]
            for to_agent_id in (id(to_agent) for to_agent in from_agent.handoffs)
            if to_agent_id in agent_id_to_state
        ]
        for to_state in sorted(to_states, key=lambda state: flow_state_order[state]):
            lines.append(f"    {from_id} --> {node_ids[to_state]}")

    return "\n".join(lines)


def get_starting_agent(
    prompt_service: DynamicPromptService,
) -> tuple[RealtimeAgent, Dict[FlowState, RealtimeAgent]]:
    """Return the initial agent and the full flow agent map."""
    agents = build_flow_agents(prompt_service)
    return agents[FlowState.GREETING], agents
