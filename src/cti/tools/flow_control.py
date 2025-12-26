"""
Flow Control Tools - Manage conversation state transitions and booking context.
"""

from contextvars import ContextVar
from logging import getLogger
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from cti.tools.base import BaseTool

if TYPE_CHECKING:
    from openai.resources.realtime.realtime import AsyncRealtimeConnection

    from cti.services.dynamic_prompt_service import DynamicPromptService

logger = getLogger(__name__)

# Context variables to store current connection and state
# Set by handler before tool execution, accessed by tools
_current_connection: ContextVar[Optional["AsyncRealtimeConnection"]] = ContextVar(
    "_current_connection", default=None
)
_current_state: ContextVar[Optional[Any]] = ContextVar("_current_state", default=None)
_prompt_service: ContextVar[Optional["DynamicPromptService"]] = ContextVar(
    "_prompt_service", default=None
)


def set_flow_context(
    connection: "AsyncRealtimeConnection",
    state: Any,
    prompt_service: "DynamicPromptService",
) -> None:
    """Set the flow context for tools to access.

    Called by the handler before executing tools.

    Args:
        connection: The OpenAI Realtime connection.
        state: The ConnectionState instance.
        prompt_service: The DynamicPromptService instance.
    """
    _current_connection.set(connection)
    _current_state.set(state)
    _prompt_service.set(prompt_service)


def get_flow_context() -> tuple[
    Optional["AsyncRealtimeConnection"],
    Optional[Any],
    Optional["DynamicPromptService"],
]:
    """Get the current flow context.

    Returns:
        Tuple of (connection, state, prompt_service).
    """
    return (
        _current_connection.get(),
        _current_state.get(),
        _prompt_service.get(),
    )


class TransitionToStateTool(BaseTool):
    """Tool to transition to a new flow state and update session instructions."""

    @property
    def name(self) -> str:
        return "transition_to_state"

    def get_definition(self) -> Dict[str, Any]:
        from cti.services.dynamic_prompt_service import FlowState

        return {
            "type": "function",
            "name": self.name,
            "description": (
                "Transition to a new conversation state. "
                "Call this when moving to the next step in the booking flow. "
                "This will update the assistant's instructions for the new state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_state": {
                        "type": "string",
                        "enum": [s.value for s in FlowState],
                        "description": "The state to transition to",
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "Brief reason for transition "
                            "(e.g., 'customer confirmed today', 'booking created')"
                        ),
                    },
                },
                "required": ["target_state"],
            },
        }

    async def execute(
        self,
        session_manager: Any,
        target_state: str,
        reason: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute the state transition.

        Args:
            session_manager: The session manager (not used directly, but required by interface).
            target_state: The target state name.
            reason: The reason for the transition.
            **kwargs: Additional arguments (ignored).

        Returns:
            Result dictionary with success status and message.
        """
        from cti.services.dynamic_prompt_service import FlowState

        connection, state, prompt_service = get_flow_context()

        if not all([connection, state, prompt_service]):
            logger.error("Flow context not initialized for transition")
            return {"success": False, "error": "Flow context not initialized"}

        try:
            new_state = FlowState(target_state)
        except ValueError:
            return {"success": False, "error": f"Invalid state: {target_state}"}

        # Validate transition
        current_state = state.current_flow_state
        if not prompt_service.can_transition(current_state, new_state):
            logger.warning(
                f"Invalid transition: {current_state.value} -> {new_state.value}"
            )
            return {
                "success": False,
                "error": f"Cannot transition from {current_state.value} to {new_state.value}",
            }

        # Update state
        old_state = state.current_flow_state
        state.current_flow_state = new_state

        # Get new prompt and tools
        new_prompt = prompt_service.get_prompt(new_state, state.booking_context)
        new_tools = prompt_service.get_tools_definitions(new_state)

        # Dynamic instruction update!
        try:
            await connection.session.update(
                session={
                    "type": "realtime",
                    "instructions": new_prompt,
                    "tools": new_tools,
                }
            )
            logger.info(
                f"State transition: {old_state.value} -> {new_state.value} ({reason})"
            )
        except Exception as exc:
            logger.error(f"Failed to update session: {exc}")
            # Revert state on failure
            state.current_flow_state = old_state
            return {"success": False, "error": f"Failed to update session: {exc}"}

        return {
            "success": True,
            "message": f"Transitioned to {new_state.value}",
            "previous_state": old_state.value,
            "new_state": new_state.value,
            "reason": reason,
        }


class SaveBookingContextTool(BaseTool):
    """Tool to save booking information to context."""

    @property
    def name(self) -> str:
        return "save_booking_context"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": (
                "Save booking information to the context. "
                "Call this to store collected information like employee_id, start_time, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": [
                            "booking_date",
                            "employee_id",
                            "employee_name",
                            "start_time",
                            "end_time",
                            "service_id",
                            "service_name",
                            "service_duration",
                            "department_id",
                            "department_name",
                            "options",
                            "payment_method",
                            "customer_name",
                        ],
                        "description": "The field name to save",
                    },
                    "value": {
                        "type": "string",
                        "description": "The value to save (use JSON string for arrays like options)",
                    },
                },
                "required": ["field", "value"],
            },
        }

    async def execute(
        self,
        session_manager: Any,
        field: str,
        value: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Save a field to the booking context.

        Args:
            session_manager: The session manager (not used directly).
            field: The field name to save.
            value: The value to save.
            **kwargs: Additional arguments (ignored).

        Returns:
            Result dictionary with success status and current context.
        """
        import json

        _, state, _ = get_flow_context()

        if state is None:
            return {"success": False, "error": "Flow context not initialized"}

        # Parse JSON values for list fields
        if field == "options":
            try:
                value = json.loads(value) if value.startswith("[") else [value]
            except json.JSONDecodeError:
                value = [value] if value else []

        # Save to context
        state.booking_context[field] = value

        logger.info(f"Saved booking context: {field} = {value}")

        return {
            "success": True,
            "message": f"Saved {field}",
            "field": field,
            "value": value,
            "current_context": state.booking_context.copy(),
        }


class GetBookingContextTool(BaseTool):
    """Tool to retrieve current booking context."""

    @property
    def name(self) -> str:
        return "get_booking_context"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": (
                "Get the current booking context with all collected information. "
                "Call this to review what has been collected before creating a booking."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    async def execute(
        self,
        session_manager: Any,
        **kwargs,
    ) -> Dict[str, Any]:
        """Get the current booking context.

        Args:
            session_manager: The session manager (not used directly).
            **kwargs: Additional arguments (ignored).

        Returns:
            Result dictionary with the booking context.
        """
        _, state, _ = get_flow_context()

        if state is None:
            return {"success": False, "error": "Flow context not initialized"}

        context = state.booking_context.copy()

        # Add current state info
        context["current_state"] = state.current_flow_state.value

        logger.info(f"Retrieved booking context: {context}")

        return {
            "success": True,
            "context": context,
            "message": "Current booking context retrieved",
        }


# List of all flow control tools for easy registration
FLOW_CONTROL_TOOLS: List[type] = [
    TransitionToStateTool,
    SaveBookingContextTool,
    GetBookingContextTool,
]
