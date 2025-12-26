"""
Dynamic Prompt Service - Manages flow states, prompts, and transitions for booking flow.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from cti.services.tool_service import ToolService
from openai.types.realtime import RealtimeFunctionToolParam


class FlowState(str, Enum):
    """Flow states for the booking conversation."""

    GREETING = "greeting"
    DATE_SELECTION = "date_selection"
    EMPLOYEE_SELECTION = "employee_selection"
    TIME_SERVICE = "time_service"
    LOCATION = "location"
    AVAILABILITY_CHECK = "availability_check"
    OPTIONS = "options"
    PAYMENT = "payment"
    CUSTOMER_INFO = "customer_info"
    CONFIRMATION = "confirmation"
    BOOKING_SUCCESS = "booking_success"
    HUMAN_HANDOFF = "human_handoff"
    END = "end"


# Valid state transitions based on the booking flowchart
VALID_TRANSITIONS: Dict[FlowState, List[FlowState]] = {
    FlowState.GREETING: [
        FlowState.EMPLOYEE_SELECTION,  # booking today
        FlowState.DATE_SELECTION,  # booking other day
        FlowState.HUMAN_HANDOFF,  # non-booking question
    ],
    FlowState.DATE_SELECTION: [FlowState.EMPLOYEE_SELECTION],
    FlowState.EMPLOYEE_SELECTION: [FlowState.TIME_SERVICE],
    FlowState.TIME_SERVICE: [FlowState.LOCATION],
    FlowState.LOCATION: [FlowState.AVAILABILITY_CHECK],
    FlowState.AVAILABILITY_CHECK: [
        FlowState.OPTIONS,  # available
        FlowState.TIME_SERVICE,  # not available, try different time
        FlowState.DATE_SELECTION,  # fully booked, try different day
        FlowState.END,  # customer declines alternatives
    ],
    FlowState.OPTIONS: [FlowState.PAYMENT],
    FlowState.PAYMENT: [FlowState.CUSTOMER_INFO],
    FlowState.CUSTOMER_INFO: [FlowState.CONFIRMATION],
    FlowState.CONFIRMATION: [
        FlowState.BOOKING_SUCCESS,  # confirmed
        FlowState.TIME_SERVICE,  # wants to change time/service
        FlowState.EMPLOYEE_SELECTION,  # wants different employee
    ],
    FlowState.BOOKING_SUCCESS: [FlowState.END],
    FlowState.HUMAN_HANDOFF: [FlowState.END],
    FlowState.END: [],
}

# Tools available per state (uses tool_service.py tool names)
STATE_TOOLS: Dict[FlowState, List[str]] = {
    FlowState.GREETING: ["transition_to_state"],
    FlowState.DATE_SELECTION: ["transition_to_state", "save_booking_context"],
    FlowState.EMPLOYEE_SELECTION: [
        "transition_to_state",
        "save_booking_context",
        "get_employee_list",
    ],
    FlowState.TIME_SERVICE: [
        "transition_to_state",
        "save_booking_context",
        "get_service_list",
    ],
    FlowState.LOCATION: [
        "transition_to_state",
        "save_booking_context",
        "get_department_list",
    ],
    FlowState.AVAILABILITY_CHECK: [
        "transition_to_state",
        "save_booking_context",
        "get_employee_list",
        "get_available_employees",
    ],
    FlowState.OPTIONS: ["transition_to_state", "save_booking_context"],
    FlowState.PAYMENT: ["transition_to_state", "save_booking_context"],
    FlowState.CUSTOMER_INFO: ["transition_to_state", "save_booking_context"],
    FlowState.CONFIRMATION: [
        "transition_to_state",
        "get_booking_context",
        "create_booking",
    ],
    FlowState.BOOKING_SUCCESS: ["transition_to_state"],
    FlowState.HUMAN_HANDOFF: [],
    FlowState.END: [],
}

# Unified assistant prefix applied to all state prompts
UNIFIED_ASSISTANT_PREFIX = """
QUAN TRỌNG - QUY TẮC GIAO TIẾP:
- Bạn là trợ lý đặt lịch qua điện thoại. KHÔNG BAO GIỜ tiết lộ bạn là "agent" hay có nhiều agent.
- KHÔNG BAO GIỜ nói "tôi sẽ chuyển", "để tôi kiểm tra với hệ thống", hay bất kỳ điều gì tiết lộ kiến trúc nội bộ.
- Luôn nói như MỘT người duy nhất đang hỗ trợ khách từ đầu đến cuối.
- Nói tiếng Việt, ngắn gọn, thân thiện, tự nhiên như người thật.
- Không đọc JSON, ID, hay thông tin kỹ thuật cho khách.
- Khi cần chuyển trạng thái, GỌI TOOL transition_to_state NGAY LẬP TỨC.
"""

# Available options for booking
AVAILABLE_OPTIONS = [
    "ローター",
    "アイマスク",
    "パンスト",
    "コスプレ",
    "口内発射",
    "パイプ",
    "オナニー",
    "電マ",
    "顔無し撮影",
    "顔有撮影",
]
OPTIONS_LIST_TEXT = "\n".join([f"- {opt}" for opt in AVAILABLE_OPTIONS])

# State-specific prompts
STATE_PROMPTS: Dict[FlowState, str] = {
    FlowState.GREETING: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: GREETING
NHIỆM VỤ: Chào khách và hỏi xem họ muốn đặt lịch cho hôm nay không.

HÀNH ĐỘNG:
- Khách nói CÓ/hôm nay/bây giờ → GỌI transition_to_state(target_state="employee_selection", reason="booking today")
- Khách nói KHÔNG/ngày khác → GỌI transition_to_state(target_state="date_selection", reason="booking other day")
- Khách hỏi ngoài flow và bạn không xử lý được → GỌI transition_to_state(target_state="human_handoff", reason="out-of-flow question")
- Nếu câu hỏi vẫn trong flow → trả lời bình thường và dẫn dắt sang bước phù hợp

CÂU TRẢ LỜI: "Xin chào! Anh/chị muốn đặt lịch cho hôm nay phải không ạ?"
""",
    FlowState.DATE_SELECTION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: DATE_SELECTION
NHIỆM VỤ: Xin ngày khách mong muốn đặt lịch.

HÀNH ĐỘNG:
- Khách cho ngày cụ thể → GỌI save_booking_context(field="booking_date", value="YYYY-MM-DD")
- Sau khi lưu ngày → GỌI transition_to_state(target_state="employee_selection", reason="date collected")

CÂU TRẢ LỜI: "Vâng ạ, cho em xin ngày anh/chị mong muốn ạ."
""",
    FlowState.EMPLOYEE_SELECTION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: EMPLOYEE_SELECTION
NHIỆM VỤ: Hỏi khách có chỉ định tiếp viên không.

HÀNH ĐỘNG:
- Khách chỉ định tên → GỌI get_employee_list() để tìm, sau đó save_booking_context(field="employee_id", value="...")
- Khách nói không chỉ định/tùy chọn → GỌI get_employee_list(), chọn một tiếp viên phù hợp và save_booking_context(field="employee_id", value="...")
- Sau khi xác nhận → GỌI transition_to_state(target_state="time_service", reason="employee selected")

CÂU TRẢ LỜI: "Anh/chị có chỉ định tiếp viên không ạ?"
""",
    FlowState.TIME_SERVICE: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: TIME_SERVICE
NHIỆM VỤ: Thu thập thời gian bắt đầu và gói dịch vụ.

{{context_info}}

HÀNH ĐỘNG:
- Khách cho thời gian → save_booking_context(field="start_time", value="HH:mm")
- Khách cho gói dịch vụ/thời lượng → GỌI get_service_list() nếu cần, sau đó save_booking_context(field="service_id", value="...")
- Tính end_time = start_time + duration
- Sau khi có đủ thông tin → GỌI transition_to_state(target_state="location", reason="time and service collected")

LƯU Ý:
- Chuẩn hóa thời gian: "7 giờ tối" → 19:00
- Hỏi TỪNG THÔNG TIN MỘT, không hỏi dồn

CÂU TRẢ LỜI: "Anh/chị muốn bắt đầu lúc mấy giờ và chọn gói bao nhiêu phút ạ?"
""",
    FlowState.LOCATION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: LOCATION
NHIỆM VỤ: Hỏi về địa điểm sử dụng dịch vụ.

{{context_info}}

HÀNH ĐỘNG:
- Khách cho địa điểm cụ thể → save_booking_context(field="department_id", value="..."), xác nhận lại
- Khách nói "tùy bạn chọn" hoặc "đến khách sạn bên bạn" → GỌI get_department_list() để giới thiệu
- Khách không có yêu cầu → save_booking_context(field="department_id", value="any")
- Sau khi xác nhận địa điểm → GỌI transition_to_state(target_state="availability_check", reason="location confirmed")

CÂU TRẢ LỜI: "Anh/chị có yêu cầu về địa điểm sử dụng không ạ?"
""",
    FlowState.AVAILABILITY_CHECK: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: AVAILABILITY_CHECK
NHIỆM VỤ: Kiểm tra lịch trống và xử lý kết quả.

{{context_info}}

CÁC BƯỚC:
1. Nói "Vâng ạ, xin anh/chị đợi một chút để em kiểm tra tình trạng trống."
2. Đảm bảo có employee_id; nếu chưa có hoặc chưa rõ → GỌI get_employee_list(), chọn một tiếp viên và save_booking_context(field="employee_id", value="...")
3. GỌI get_available_employees() với thông tin đã thu thập
4. Dựa trên kết quả:
   - CÓ lịch trống → GỌI transition_to_state(target_state="options", reason="slot available")
   - KHÔNG có lịch trống → hỏi khách có muốn đổi giờ không
     - Khách đồng ý đổi giờ → GỌI transition_to_state(target_state="time_service", reason="try different time")
     - Khách không đổi được/hết cả ngày → GỌI transition_to_state(target_state="date_selection", reason="try different day")
     - Khách từ chối → GỌI transition_to_state(target_state="end", reason="customer declined")

CÂU TRẢ LỜI KHI CÓ: "Có chỗ trống rồi ạ!"
CÂU TRẢ LỜI KHI KHÔNG: "Rất xin lỗi ạ, khung giờ này đã kín. Anh/chị có thể đổi sang giờ khác không ạ?"
""",
    FlowState.OPTIONS: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: OPTIONS
NHIỆM VỤ: Hỏi và xử lý các tùy chọn bổ sung.

{{context_info}}

DANH SÁCH OPTIONS CÓ SẴN:
{OPTIONS_LIST_TEXT}

HÀNH ĐỘNG:
- Khách hỏi có những option gì → đọc danh sách
- Khách chọn option → save_booking_context(field="options", value="[...]")
- Khách chọn option không có → xin lỗi và gợi ý option khác
- Khách không muốn thêm → save_booking_context(field="options", value="[]")
- Sau khi xác nhận → GỌI transition_to_state(target_state="payment", reason="options selected")

CÂU TRẢ LỜI: "Anh/chị có muốn thêm tùy chọn/dịch vụ bổ sung nào không ạ?"
""",
    FlowState.PAYMENT: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: PAYMENT
NHIỆM VỤ: Thu thập phương thức thanh toán.

{{context_info}}

PHƯƠNG THỨC THANH TOÁN:
- cash: Tiền mặt
- credit_card: Thẻ tín dụng

HÀNH ĐỘNG:
- "tiền mặt", "cash" → save_booking_context(field="payment_method", value="cash")
- "thẻ", "card", "visa" → save_booking_context(field="payment_method", value="credit_card")
- Sau khi xác nhận → GỌI transition_to_state(target_state="customer_info", reason="payment selected")

CÂU TRẢ LỜI: "Anh/chị muốn thanh toán bằng tiền mặt hay thẻ ạ?"
""",
    FlowState.CUSTOMER_INFO: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: CUSTOMER_INFO
NHIỆM VỤ: Thu thập tên khách hàng.

{{context_info}}

HÀNH ĐỘNG:
- Khách cho tên → save_booking_context(field="customer_name", value="...")
- Xác nhận lại tên
- Sau khi xác nhận → GỌI transition_to_state(target_state="confirmation", reason="customer info collected")

CÂU TRẢ LỜI: "Cho em xin tên của anh/chị ạ."
""",
    FlowState.CONFIRMATION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: CONFIRMATION
NHIỆM VỤ: Đọc lại thông tin và tạo booking.

{{context_info}}

CÁC BƯỚC:
1. GỌI get_booking_context() để lấy toàn bộ thông tin
2. Đọc lại: ngày giờ, gói dịch vụ, tiếp viên, địa điểm, options, thanh toán, tên khách
3. Hỏi xác nhận
4. Nếu khách OK:
   - GỌI create_booking(...) với các thông tin đã thu thập
   - Sau đó GỌI transition_to_state(target_state="booking_success", reason="booking created")
5. Nếu khách muốn sửa → GỌI transition_to_state về state phù hợp

ĐỊNH DẠNG THỜI GIAN CHO create_booking: YYYY-MM-DD HH:mm:ss

CÂU TRẢ LỜI: "Xin xác nhận lại: Quý khách đặt lịch [ngày] lúc [giờ], gói [X] phút, tiếp viên [tên], thanh toán [phương thức]. Quý khách xác nhận đúng không ạ?"
""",
    FlowState.BOOKING_SUCCESS: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: BOOKING_SUCCESS
NHIỆM VỤ: Thông báo thành công và kết thúc cuộc gọi.

{{context_info}}

HÀNH ĐỘNG:
- Thông báo booking thành công
- Cảm ơn khách
- GỌI transition_to_state(target_state="end", reason="booking completed")

CÂU TRẢ LỜI: "Đặt lịch thành công! Cô gái sẽ đến gặp quý khách vào lúc [giờ hẹn]. Chúng tôi sẽ gọi xác nhận trước giờ hẹn. Cảm ơn quý khách!"
""",
    FlowState.HUMAN_HANDOFF: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: HUMAN_HANDOFF
NHIỆM VỤ: Thông báo chuyển cuộc gọi cho lễ tân.

HÀNH ĐỘNG:
- Thông báo lịch sự
- GỌI transition_to_state(target_state="end", reason="handoff to human")

CÂU TRẢ LỜI: "Để hỗ trợ quý khách tốt hơn, chúng tôi sẽ kết nối với nhân viên lễ tân. Xin vui lòng chờ trong giây lát."
""",
    FlowState.END: f"""{UNIFIED_ASSISTANT_PREFIX}

TRẠNG THÁI HIỆN TẠI: END
NHIỆM VỤ: Kết thúc cuộc gọi.

CÂU TRẢ LỜI: "Hẹn dịp khác, mong được phục vụ anh/chị ạ."
""",
}


class DynamicPromptService:
    """Service for managing dynamic prompts and state transitions."""

    def __init__(self, tool_service: Optional[ToolService] = None):
        """Initialize the dynamic prompt service.

        Args:
            tool_service: Optional ToolService instance for getting tool definitions.
                         If not provided, a new instance will be created when needed.
        """
        self._tool_service = tool_service

    @property
    def tool_service(self) -> ToolService:
        """Get or create tool service instance."""
        if self._tool_service is None:
            self._tool_service = ToolService()
        return self._tool_service

    def get_prompt(self, state: FlowState, context: Dict[str, Any]) -> str:
        """Get the prompt for a given state with context interpolation.

        Args:
            state: The current flow state.
            context: The booking context dictionary.

        Returns:
            The prompt string with context interpolated.
        """
        prompt = STATE_PROMPTS.get(state, "")

        # Format context info for display
        context_info = self._format_context(context)

        # Interpolate context into prompt
        prompt = prompt.replace("{context_info}", context_info)

        # Add current datetime info
        now = datetime.now()
        datetime_suffix = f"""

THÔNG TIN THỜI GIAN:
- Ngày giờ hiện tại: {now.strftime("%Y-%m-%d %H:%M:%S")}
- Hôm nay là: {now.strftime("%d/%m/%Y")}
"""
        return prompt + datetime_suffix

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format booking context for display in prompt.

        Args:
            context: The booking context dictionary.

        Returns:
            Formatted context string.
        """
        if not context:
            return "CONTEXT: Chưa có thông tin đặt lịch."

        lines = ["CONTEXT:"]
        field_labels = {
            "booking_date": "Ngày đặt",
            "employee_id": "Tiếp viên",
            "employee_name": "Tên tiếp viên",
            "start_time": "Giờ bắt đầu",
            "end_time": "Giờ kết thúc",
            "service_id": "Gói dịch vụ",
            "service_name": "Tên gói",
            "department_id": "Địa điểm",
            "department_name": "Tên địa điểm",
            "options": "Tùy chọn",
            "payment_method": "Thanh toán",
            "customer_name": "Tên khách",
        }

        for key, value in context.items():
            if value is not None:
                label = field_labels.get(key, key)
                lines.append(f"- {label}: {value}")

        return "\n".join(lines)

    def get_tools(self, state: FlowState) -> List[str]:
        """Get the list of tool names available for a state.

        Args:
            state: The flow state.

        Returns:
            List of tool names.
        """
        return STATE_TOOLS.get(state, [])

    def get_tools_definitions(
        self, state: FlowState
    ) -> List[RealtimeFunctionToolParam]:
        """Get the full tool definitions for a state.

        Args:
            state: The flow state.

        Returns:
            List of tool definitions in OpenAI format.
        """
        tool_names = self.get_tools(state)
        return self.tool_service.get_tool_definitions_by_names(tool_names)

    def can_transition(self, from_state: FlowState, to_state: FlowState) -> bool:
        """Check if a transition is valid.

        Args:
            from_state: The current state.
            to_state: The target state.

        Returns:
            True if the transition is valid.
        """
        valid_targets = VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_targets

    def get_valid_transitions(self, state: FlowState) -> List[FlowState]:
        """Get the list of valid next states.

        Args:
            state: The current state.

        Returns:
            List of valid target states.
        """
        return VALID_TRANSITIONS.get(state, [])
