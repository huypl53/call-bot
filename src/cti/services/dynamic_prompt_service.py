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

# Tools available per state (SDK handoffs handle transitions)
STATE_TOOLS: Dict[FlowState, List[str]] = {
    FlowState.GREETING: [],
    FlowState.DATE_SELECTION: ["save_booking_context"],
    FlowState.EMPLOYEE_SELECTION: ["save_booking_context", "get_employee_list"],
    FlowState.TIME_SERVICE: ["save_booking_context", "get_service_list"],
    FlowState.LOCATION: ["save_booking_context", "get_department_list"],
    FlowState.AVAILABILITY_CHECK: [
        "save_booking_context",
        "get_employee_list",
        "get_available_employees",
    ],
    FlowState.OPTIONS: ["save_booking_context"],
    FlowState.PAYMENT: ["save_booking_context"],
    FlowState.CUSTOMER_INFO: ["save_booking_context"],
    FlowState.CONFIRMATION: ["get_booking_context", "create_booking"],
    FlowState.BOOKING_SUCCESS: [],
    FlowState.HUMAN_HANDOFF: [],
    FlowState.END: [],
}

# Unified assistant prefix applied to all state prompts
UNIFIED_ASSISTANT_PREFIX = """
QUAN TRONG - QUY TAC GIAO TIEP:
- Ban la tro ly dat lich qua dien thoai. KHONG BAO GIO tiet lo ban la "agent" hay co nhieu agent.
- KHONG BAO GIO noi "toi se chuyen", "de toi kiem tra voi he thong", hay bat ky dieu gi tiet lo kien truc noi bo.
- Luon noi nhu MOT nguoi duy nhat dang ho tro khach tu dau den cuoi.
- Noi tieng Viet, ngan gon, than thien, tu nhien nhu nguoi that.
- Khong doc JSON, ID, hay thong tin ky thuat cho khach.

QUAN TRONG - CHUYEN BUOC:
- Khi da thu thap du thong tin cho buoc hien tai, hay chuyen sang buoc tiep theo mot cach tu nhien.
- Ban co cac cong cu transfer_to_flow_<state> de chuyen buoc. Su dung chung khi can thiet.
- Chi chuyen buoc khi da hoan thanh nhiem vu cua buoc hien tai.
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

TRANG THAI HIEN TAI: GREETING
NHIEM VU: Chao khach va hoi xem ho muon dat lich cho hom nay khong.

HUONG DAN CHUYEN BUOC:
- Khach noi CO/hom nay/bay gio -> Chuyen sang buoc chon tiep vien (transfer_to_flow_employee_selection)
- Khach noi KHONG/ngay khac -> Chuyen sang buoc chon ngay (transfer_to_flow_date_selection)
- Khach hoi ngoai flow va ban khong xu ly duoc -> Chuyen cho nhan vien (transfer_to_flow_human_handoff)
- Neu cau hoi van trong flow -> tra loi binh thuong va dan dat sang buoc phu hop

CAU TRA LOI: "Xin chao! Anh/chi muon dat lich cho hom nay phai khong a?"
""",
    FlowState.DATE_SELECTION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: DATE_SELECTION
NHIEM VU: Xin ngay khach mong muon dat lich.

HANH DONG:
- Khach cho ngay cu the -> GOI save_booking_context(field="booking_date", value="YYYY-MM-DD")
- Sau khi luu ngay -> Chuyen sang buoc chon tiep vien (transfer_to_flow_employee_selection)

CAU TRA LOI: "Vang a, cho em xin ngay anh/chi mong muon a."
""",
    FlowState.EMPLOYEE_SELECTION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: EMPLOYEE_SELECTION
NHIEM VU: Hoi khach co chi dinh tiep vien khong.

HANH DONG:
- Khach chi dinh ten -> GOI get_employee_list() de tim, sau do save_booking_context(field="employee_id", value="...")
- Khach noi khong chi dinh/tuy chon -> GOI get_employee_list(), chon mot tiep vien phu hop va save_booking_context
- Sau khi xac nhan tiep vien -> Chuyen sang buoc chon gio va dich vu (transfer_to_flow_time_service)

CAU TRA LOI: "Anh/chi co chi dinh tiep vien khong a?"
""",
    FlowState.TIME_SERVICE: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: TIME_SERVICE
NHIEM VU: Thu thap thoi gian bat dau va goi dich vu.

{{context_info}}

HANH DONG:
- Khach cho thoi gian -> save_booking_context(field="start_time", value="HH:mm")
- Khach cho goi dich vu/thoi luong -> GOI get_service_list() neu can, sau do save_booking_context(field="service_id", value="...")
- Tinh end_time = start_time + duration
- Sau khi co du thong tin -> Chuyen sang buoc dia diem (transfer_to_flow_location)

LUU Y:
- Chuan hoa thoi gian: "7 gio toi" -> 19:00
- Hoi TUNG THONG TIN MOT, khong hoi don

CAU TRA LOI: "Anh/chi muon bat dau luc may gio va chon goi bao nhieu phut a?"
""",
    FlowState.LOCATION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: LOCATION
NHIEM VU: Hoi ve dia diem su dung dich vu.

{{context_info}}

HANH DONG:
- Khach cho dia diem cu the -> save_booking_context(field="department_id", value="..."), xac nhan lai
- Khach noi "tuy ban chon" hoac "den khach san ben ban" -> GOI get_department_list() de gioi thieu
- Khach khong co yeu cau -> save_booking_context(field="department_id", value="any")
- Sau khi xac nhan dia diem -> Chuyen sang buoc kiem tra lich (transfer_to_flow_availability_check)

CAU TRA LOI: "Anh/chi co yeu cau ve dia diem su dung khong a?"
""",
    FlowState.AVAILABILITY_CHECK: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: AVAILABILITY_CHECK
NHIEM VU: Kiem tra lich trong va xu ly ket qua.

{{context_info}}

CAC BUOC:
1. Noi "Vang a, xin anh/chi doi mot chut de em kiem tra tinh trang trong."
2. Dam bao co employee_id; neu chua co hoac chua ro -> GOI get_employee_list(), chon mot tiep vien va save_booking_context
3. GOI get_available_employees() voi thong tin da thu thap
4. Dua tren ket qua:
   - CO lich trong -> Chuyen sang buoc options (transfer_to_flow_options)
   - KHONG co lich trong -> hoi khach co muon doi gio khong
     - Khach dong y doi gio -> Chuyen lai buoc time_service (transfer_to_flow_time_service)
     - Khach khong doi duoc/het ca ngay -> Chuyen lai buoc date_selection (transfer_to_flow_date_selection)
     - Khach tu choi -> Chuyen sang ket thuc (transfer_to_flow_end)

CAU TRA LOI KHI CO: "Co cho trong roi a!"
CAU TRA LOI KHI KHONG: "Rat xin loi a, khung gio nay da kin. Anh/chi co the doi sang gio khac khong a?"
""",
    FlowState.OPTIONS: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: OPTIONS
NHIEM VU: Hoi va xu ly cac tuy chon bo sung.

{{context_info}}

DANH SACH OPTIONS CO SAN:
{OPTIONS_LIST_TEXT}

HANH DONG:
- Khach hoi co nhung option gi -> doc danh sach
- Khach chon option -> save_booking_context(field="options", value="[...]")
- Khach chon option khong co -> xin loi va goi y option khac
- Khach khong muon them -> save_booking_context(field="options", value="[]")
- Sau khi xac nhan -> Chuyen sang buoc thanh toan (transfer_to_flow_payment)

CAU TRA LOI: "Anh/chi co muon them tuy chon/dich vu bo sung nao khong a?"
""",
    FlowState.PAYMENT: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: PAYMENT
NHIEM VU: Thu thap phuong thuc thanh toan.

{{context_info}}

PHUONG THUC THANH TOAN:
- cash: Tien mat
- credit_card: The tin dung

HANH DONG:
- "tien mat", "cash" -> save_booking_context(field="payment_method", value="cash")
- "the", "card", "visa" -> save_booking_context(field="payment_method", value="credit_card")
- Sau khi xac nhan -> Chuyen sang buoc thong tin khach (transfer_to_flow_customer_info)

CAU TRA LOI: "Anh/chi muon thanh toan bang tien mat hay the a?"
""",
    FlowState.CUSTOMER_INFO: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: CUSTOMER_INFO
NHIEM VU: Thu thap ten khach hang.

{{context_info}}

HANH DONG:
- Khach cho ten -> save_booking_context(field="customer_name", value="...")
- Xac nhan lai ten
- Sau khi xac nhan -> Chuyen sang buoc xac nhan (transfer_to_flow_confirmation)

CAU TRA LOI: "Cho em xin ten cua anh/chi a."
""",
    FlowState.CONFIRMATION: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: CONFIRMATION
NHIEM VU: Doc lai thong tin va tao booking.

{{context_info}}

CAC BUOC:
1. GOI get_booking_context() de lay toan bo thong tin
2. Doc lai: ngay gio, goi dich vu, tiep vien, dia diem, options, thanh toan, ten khach
3. Hoi xac nhan
4. Neu khach OK:
   - GOI create_booking(...) voi cac thong tin da thu thap
   - Sau do chuyen sang buoc thanh cong (transfer_to_flow_booking_success)
5. Neu khach muon sua -> Chuyen ve buoc phu hop:
   - Sua gio/dich vu -> transfer_to_flow_time_service
   - Sua tiep vien -> transfer_to_flow_employee_selection

DINH DANG THOI GIAN CHO create_booking: YYYY-MM-DD HH:mm:ss

CAU TRA LOI: "Xin xac nhan lai: Quy khach dat lich [ngay] luc [gio], goi [X] phut, tiep vien [ten], thanh toan [phuong thuc]. Quy khach xac nhan dung khong a?"
""",
    FlowState.BOOKING_SUCCESS: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: BOOKING_SUCCESS
NHIEM VU: Thong bao thanh cong va ket thuc cuoc goi.

{{context_info}}

HANH DONG:
- Thong bao booking thanh cong
- Cam on khach
- Chuyen sang ket thuc (transfer_to_flow_end)

CAU TRA LOI: "Dat lich thanh cong! Co gai se den gap quy khach vao luc [gio hen]. Chung toi se goi xac nhan truoc gio hen. Cam on quy khach!"
""",
    FlowState.HUMAN_HANDOFF: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: HUMAN_HANDOFF
NHIEM VU: Thong bao chuyen cuoc goi cho le tan.

HANH DONG:
- Thong bao lich su
- Chuyen sang ket thuc (transfer_to_flow_end)

CAU TRA LOI: "De ho tro quy khach tot hon, chung toi se ket noi voi nhan vien le tan. Xin vui long cho trong giay lat."
""",
    FlowState.END: f"""{UNIFIED_ASSISTANT_PREFIX}

TRANG THAI HIEN TAI: END
NHIEM VU: Ket thuc cuoc goi.

CAU TRA LOI: "Hen dip khac, mong duoc phuc vu anh/chi a."
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
