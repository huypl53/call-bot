"""
Math Agents - Realtime agents for mathematical operations
Uses the agents SDK with handoffs between specialized math agents
"""

import asyncio
import logging
import os
from agents import Agent, function_tool, Runner, set_default_openai_client
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from agents.realtime import RealtimeAgent, realtime_handoff

from cti.config.settings import settings

logger = logging.getLogger(__name__)


def get_starting_agent() -> RealtimeAgent:
    """Get the starting triage agent for math operations"""
    return triage_agent


# Define math tools using function_tool decorator with direct implementations
@function_tool(
    name_override="math_add",
    description_override="Cộng hai số (a + b).",
)
async def add_tool(a: float, b: float) -> str:
    """Add two numbers"""
    logger.info(f"=== ADD TOOL CALLED === a={a}, b={b}")
    result = a + b
    logger.info(f"=== ADD TOOL RESULT === {result}")
    return f"Tổng của {a} và {b} là {result}"


@function_tool(
    name_override="math_subtract",
    description_override="Trừ hai số (a - b).",
)
async def subtract_tool(a: float, b: float) -> str:
    """Subtract two numbers"""
    logger.info(f"=== SUBTRACT TOOL CALLED === a={a}, b={b}")
    result = a - b
    logger.info(f"=== SUBTRACT TOOL RESULT === {result}")
    return f"Hiệu của {a} trừ {b} là {result}"


@function_tool(
    name_override="math_multiply",
    description_override="Nhân hai số (a * b).",
)
async def multiply_tool(a: float, b: float) -> str:
    """Multiply two numbers"""
    logger.info(f"=== MULTIPLY TOOL CALLED === a={a}, b={b}")
    result = a * b
    logger.info(f"=== MULTIPLY TOOL RESULT === {result}")
    return f"Tích của {a} và {b} là {result}"


@function_tool(
    name_override="math_divide",
    description_override="Chia hai số (a / b).",
)
async def divide_tool(a: float, b: float) -> str:
    """Divide two numbers"""
    logger.info(f"=== DIVIDE TOOL CALLED === a={a}, b={b}")
    if b == 0:
        logger.warning(f"=== DIVIDE TOOL ERROR === Division by zero")
        return "Không thể chia cho 0"
    result = a / b
    logger.info(f"=== DIVIDE TOOL RESULT === {result}")
    return f"Thương của {a} chia cho {b} là {result}"


# Create specialized math agents
addition_agent = RealtimeAgent(
    name="Addition Agent",
    handoff_description="Một agent chuyên thực hiện phép cộng hai số",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    Bạn là Addition Agent, chuyên thực hiện phép cộng.
    Khi nhận được yêu cầu, hãy:
    1. Sử dụng công cụ math_add để tính tổng
    2. Trả về kết quả rõ ràng cho người dùng
    3. Nếu yêu cầu không phải là phép cộng, hãy chuyển lại cho Triage Agent.""",
    tools=[add_tool],
)

subtraction_agent = RealtimeAgent(
    name="Subtraction Agent",
    handoff_description="Một agent chuyên thực hiện phép trừ hai số",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    Bạn là Subtraction Agent, chuyên thực hiện phép trừ.
    Khi nhận được yêu cầu, hãy:
    1. Sử dụng công cụ math_subtract để tính hiệu
    2. Trả về kết quả rõ ràng cho người dùng
    3. Nếu yêu cầu không phải là phép trừ, hãy chuyển lại cho Triage Agent.""",
    tools=[subtract_tool],
)

multiplication_agent = RealtimeAgent(
    name="Multiplication Agent",
    handoff_description="Một agent chuyên thực hiện phép nhân hai số",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    Bạn là Multiplication Agent, chuyên thực hiện phép nhân.
    Khi nhận được yêu cầu, hãy:
    1. Sử dụng công cụ math_multiply để tính tích
    2. Trả về kết quả rõ ràng cho người dùng
    3. Nếu yêu cầu không phải là phép nhân, hãy chuyển lại cho Triage Agent.""",
    tools=[multiply_tool],
)

division_agent = RealtimeAgent(
    name="Division Agent",
    handoff_description="Một agent chuyên thực hiện phép chia hai số",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    Bạn là Division Agent, chuyên thực hiện phép chia.
    Khi nhận được yêu cầu, hãy:
    1. Sử dụng công cụ math_divide để tính thương
    2. Trả về kết quả rõ ràng cho người dùng
    3. Nếu yêu cầu không phải là phép chia, hãy chuyển lại cho Triage Agent.
    4. Kiểm tra trường hợp chia cho 0 và báo lỗi nếu cần.""",
    tools=[divide_tool],
)

# Create triage agent that delegates to math agents
triage_agent = RealtimeAgent(
    name="Triage Agent",
    handoff_description="Agent điều phối, chuyển yêu cầu toán học đến agent phù hợp",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX} "
        "Bạn là Triage Agent cho các phép toán học. Hãy lắng nghe yêu cầu của người dùng và chuyển đến agent phù hợp:\n"
        "- Nếu người dùng muốn 'cộng', 'cộng thêm', 'tổng', hãy chuyển đến Addition Agent\n"
        "- Nếu người dùng muốn 'trừ', 'trừ đi', 'hiệu', 'bớt', hãy chuyển đến Subtraction Agent\n"
        "- Nếu người dùng muốn 'nhân', 'nhân với', 'tích', hãy chuyển đến Multiplication Agent\n"
        "- Nếu người dùng muốn 'chia', 'chia cho', 'thương', hãy chuyển đến Division Agent\n"
        "Luôn thân thiện và sử dụng tiếng Việt."
    ),
    handoffs=[
        addition_agent,
        subtraction_agent,
        multiplication_agent,
        division_agent,
    ],
)

# Add return handoffs so specialized agents can return to triage
addition_agent.handoffs.append(triage_agent)
subtraction_agent.handoffs.append(triage_agent)
multiplication_agent.handoffs.append(triage_agent)
division_agent.handoffs.append(triage_agent)
