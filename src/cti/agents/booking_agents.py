"""
Booking Agents - Multi-agent system for phone-based appointment booking
Uses the OpenAI Agents SDK with handoffs between specialized agents
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from agents import function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from agents.realtime import RealtimeAgent

from cti.core.connection_context import get_session_manager
from cti.tools.booking_api import CreateBookingTool
from cti.tools.department_api import GetDepartmentListTool
from cti.tools.employee_api import GetAvailableEmployeesTool, GetEmployeeListTool
from cti.tools.service_api import GetServiceListTool

logger = logging.getLogger(__name__)

# =============================================================================
# TOOL WRAPPER FUNCTIONS
# =============================================================================


def _format_service_list(data: dict) -> str:
    """Format service list data for agent consumption."""
    if not data:
        return "Không tìm thấy dịch vụ nào."

    items = data.get("items", data.get("data", []))
    if not items:
        return "Không tìm thấy dịch vụ nào."

    lines = ["Danh sách dịch vụ:"]
    for svc in items[:10]:  # Limit to 10 items
        name = svc.get("name", "N/A")
        duration = svc.get("durationMinutes", "N/A")
        price = svc.get("price", "N/A")
        svc_id = svc.get("id", "N/A")
        lines.append(f"- {name} ({duration} phút, {price} VND) [ID: {svc_id}]")

    return "\n".join(lines)


def _format_employee_list(data: dict) -> str:
    """Format employee list data for agent consumption."""
    if not data:
        return "Không tìm thấy nhân viên nào."

    items = data.get("items", data.get("data", []))
    if not items:
        return "Không tìm thấy nhân viên nào."

    lines = ["Danh sách nhân viên:"]
    for emp in items[:10]:
        name = emp.get("name", "N/A")
        emp_id = emp.get("id", "N/A")
        lines.append(f"- {name} [ID: {emp_id}]")

    return "\n".join(lines)


def _format_department_list(data: dict) -> str:
    """Format department list data for agent consumption."""
    if not data:
        return "Không tìm thấy chi nhánh nào."

    items = data.get("items", data.get("data", []))
    if not items:
        return "Không tìm thấy chi nhánh nào."

    lines = ["Danh sách chi nhánh:"]
    for dept in items[:10]:
        name = dept.get("name", "N/A")
        address = dept.get("address", "N/A")
        dept_id = dept.get("id", "N/A")
        lines.append(f"- {name} ({address}) [ID: {dept_id}]")

    return "\n".join(lines)


def _format_availability_result(data: dict, employee_name: str = None) -> str:
    """Format availability check result."""
    if not data:
        return "Không thể kiểm tra lịch trống."

    is_available = data.get("available", False)
    if is_available:
        if employee_name:
            return f"Nhân viên {employee_name} có thể phục vụ trong khung giờ này."
        return "Có lịch trống trong khung giờ này."
    else:
        if employee_name:
            return f"Nhân viên {employee_name} không có lịch trống trong khung giờ này."
        return "Không có lịch trống trong khung giờ này."


# -----------------------------------------------------------------------------
# Catalog Tools
# -----------------------------------------------------------------------------


@function_tool(
    name_override="search_services",
    description_override="Tìm kiếm dịch vụ theo tên hoặc thời lượng (phút). Trả về danh sách dịch vụ với ID.",
)
async def search_services_tool(
    name: Optional[str] = None, duration_minutes: Optional[int] = None
) -> str:
    """Search for services by name or duration."""
    logger.info(f"=== SEARCH SERVICES === name={name}, duration={duration_minutes}")

    session_manager = get_session_manager()
    tool = GetServiceListTool()

    kwargs = {}
    if name:
        kwargs["name"] = name
    if duration_minutes:
        kwargs["minDurationMinutes"] = duration_minutes
        kwargs["maxDurationMinutes"] = duration_minutes

    result = await tool.execute(session_manager=session_manager, **kwargs)

    if result.get("success"):
        return _format_service_list(result.get("data", {}))
    return f"Lỗi khi tìm dịch vụ: {result.get('error', 'Unknown error')}"


@function_tool(
    name_override="search_employees",
    description_override="Tìm kiếm nhân viên theo tên. Trả về danh sách nhân viên với ID.",
)
async def search_employees_tool(name: Optional[str] = None) -> str:
    """Search for employees by name."""
    logger.info(f"=== SEARCH EMPLOYEES === name={name}")

    session_manager = get_session_manager()
    tool = GetEmployeeListTool()

    result = await tool.execute(session_manager=session_manager, page=1, size=20)

    if result.get("success"):
        data = result.get("data", {})
        items = data.get("items", data.get("data", []))

        # Filter by name if provided
        if name and items:
            name_lower = name.lower()
            items = [e for e in items if name_lower in e.get("name", "").lower()]
            data = {"items": items}

        return _format_employee_list(data)
    return f"Lỗi khi tìm nhân viên: {result.get('error', 'Unknown error')}"


@function_tool(
    name_override="search_departments",
    description_override="Tìm kiếm chi nhánh/địa điểm theo tên hoặc địa chỉ. Trả về danh sách chi nhánh với ID.",
)
async def search_departments_tool(
    name: Optional[str] = None, address: Optional[str] = None
) -> str:
    """Search for departments by name or address."""
    logger.info(f"=== SEARCH DEPARTMENTS === name={name}, address={address}")

    session_manager = get_session_manager()
    tool = GetDepartmentListTool()

    kwargs = {"size": 0}  # Get all
    if name:
        kwargs["name"] = name
    if address:
        kwargs["address"] = address

    result = await tool.execute(session_manager=session_manager, **kwargs)

    if result.get("success"):
        return _format_department_list(result.get("data", {}))
    return f"Lỗi khi tìm chi nhánh: {result.get('error', 'Unknown error')}"


# -----------------------------------------------------------------------------
# Availability Tools
# -----------------------------------------------------------------------------


@function_tool(
    name_override="check_employee_availability",
    description_override="Kiểm tra xem nhân viên cụ thể có lịch trống không. Yêu cầu employee_id, start_time, end_time (format: YYYY-MM-DD HH:mm).",
)
async def check_employee_availability_tool(
    employee_id: str, start_time: str, end_time: str
) -> str:
    """Check if a specific employee is available."""
    logger.info(
        f"=== CHECK AVAILABILITY === employee_id={employee_id}, start={start_time}, end={end_time}"
    )

    session_manager = get_session_manager()
    tool = GetAvailableEmployeesTool()

    result = await tool.execute(
        session_manager=session_manager,
        employeeId=employee_id,
        startTime=start_time,
        endTime=end_time,
    )

    if result.get("success"):
        data = result.get("data", {})
        items = data.get("items", data.get("data", []))
        is_available = len(items) > 0 if items else False
        return _format_availability_result({"available": is_available})
    return f"Lỗi kiểm tra lịch: {result.get('error', 'Unknown error')}"


@function_tool(
    name_override="find_available_employee",
    description_override="Tìm nhân viên có lịch trống khi khách không chỉ định. Yêu cầu start_time, end_time (format: YYYY-MM-DD HH:mm). Trả về nhân viên đầu tiên có lịch trống.",
)
async def find_available_employee_tool(start_time: str, end_time: str) -> str:
    """Find any available employee when user doesn't specify one."""
    logger.info(f"=== FIND AVAILABLE EMPLOYEE === start={start_time}, end={end_time}")

    session_manager = get_session_manager()

    # Step 1: Get employee list
    emp_tool = GetEmployeeListTool()
    emp_result = await emp_tool.execute(
        session_manager=session_manager, page=1, size=10
    )

    if not emp_result.get("success"):
        return f"Lỗi lấy danh sách nhân viên: {emp_result.get('error')}"

    employees = emp_result.get("data", {}).get("items", [])
    if not employees:
        return "Không tìm thấy nhân viên nào trong hệ thống."

    # Step 2: Check each employee's availability (limit to 5 to avoid too many calls)
    avail_tool = GetAvailableEmployeesTool()
    available_employees = []

    for emp in employees[:5]:
        emp_id = emp.get("id")
        emp_name = emp.get("name", "N/A")

        result = await avail_tool.execute(
            session_manager=session_manager,
            employeeId=emp_id,
            startTime=start_time,
            endTime=end_time,
        )

        if result.get("success"):
            data = result.get("data", {})
            items = data.get("items", data.get("data", []))
            if items:  # Has availability
                available_employees.append({"id": emp_id, "name": emp_name})
                break  # Found one, stop searching

    if available_employees:
        emp = available_employees[0]
        return f"Tìm thấy nhân viên có lịch trống: {emp['name']} [ID: {emp['id']}]"
    else:
        return "Không tìm thấy nhân viên nào có lịch trống trong khung giờ này. Bạn có muốn đổi sang giờ khác không?"


# -----------------------------------------------------------------------------
# Booking Tool
# -----------------------------------------------------------------------------


@function_tool(
    name_override="create_booking",
    description_override="Tạo booking mới. Yêu cầu: service_id, employee_id, start_time (YYYY-MM-DD HH:mm:ss), end_time (YYYY-MM-DD HH:mm:ss), customer_name. Tùy chọn: department_id, options, payment_method, notes.",
)
async def create_booking_tool(
    service_id: str,
    employee_id: str,
    start_time: str,
    end_time: str,
    customer_name: str,
    department_id: Optional[str] = None,
    options: Optional[list] = None,
    payment_method: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Create a new booking."""
    logger.info(
        f"=== CREATE BOOKING === service={service_id}, employee={employee_id}, "
        f"start={start_time}, end={end_time}, customer={customer_name}"
    )

    session_manager = get_session_manager()
    tool = CreateBookingTool()

    kwargs = {
        "source": "phone",
        "serviceId": service_id,
        "employeeId": employee_id,
        "startTime": start_time,
        "endTime": end_time,
        "customerName": customer_name,
    }

    if department_id:
        kwargs["departmentId"] = department_id
    if options:
        kwargs["options"] = options
    if payment_method:
        kwargs["paymentMethod"] = payment_method
    if notes:
        kwargs["notes"] = notes

    result = await tool.execute(session_manager=session_manager, **kwargs)

    if result.get("success"):
        booking_data = result.get("data", {})
        booking_id = booking_data.get("id", "N/A")
        return f"Đặt lịch thành công! Mã booking: {booking_id}. Cảm ơn quý khách."
    return f"Lỗi khi tạo booking: {result.get('error', 'Unknown error')}"


# -----------------------------------------------------------------------------
# Utility Tools
# -----------------------------------------------------------------------------


@function_tool(
    name_override="calculate_end_time",
    description_override="Tính thời gian kết thúc từ thời gian bắt đầu và thời lượng (phút). Input: start_time (YYYY-MM-DD HH:mm), duration_minutes. Output: end_time (YYYY-MM-DD HH:mm).",
)
async def calculate_end_time_tool(start_time: str, duration_minutes: int) -> str:
    """Calculate end time from start time and duration."""
    logger.info(
        f"=== CALCULATE END TIME === start={start_time}, duration={duration_minutes}"
    )

    try:
        # Parse start time
        if len(start_time) == 16:  # YYYY-MM-DD HH:mm
            dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
        else:
            dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")

        # Calculate end time
        end_dt = dt + timedelta(minutes=duration_minutes)
        end_time = end_dt.strftime("%Y-%m-%d %H:%M")

        return f"Thời gian kết thúc: {end_time}"
    except ValueError as e:
        return f"Lỗi: Không thể phân tích thời gian. Định dạng đúng: YYYY-MM-DD HH:mm. Chi tiết: {e}"


@function_tool(
    name_override="get_current_datetime",
    description_override="Lấy ngày giờ hiện tại. Sử dụng để xác định 'hôm nay' khi khách đặt lịch.",
)
async def get_current_datetime_tool() -> str:
    """Get current date and time."""
    now = datetime.now()
    return f"Ngày giờ hiện tại: {now.strftime('%Y-%m-%d %H:%M:%S')} (ngày {now.strftime('%d/%m/%Y')}, {now.strftime('%H:%M')})"


# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

# Available options enum (from create_booking tool)
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

# =============================================================================
# COMMON INSTRUCTIONS - Applied to all agents for unified behavior
# =============================================================================

UNIFIED_ASSISTANT_PREFIX = """
QUAN TRỌNG - QUY TẮC GIAO TIẾP:
- Bạn là trợ lý đặt lịch qua điện thoại. KHÔNG BAO GIỜ tiết lộ bạn là "agent" hay có nhiều agent.
- KHÔNG BAO GIỜ nói "tôi sẽ chuyển", "để tôi kiểm tra với hệ thống", hay bất kỳ điều gì tiết lộ kiến trúc nội bộ.
- Luôn nói như MỘT người duy nhất đang hỗ trợ khách từ đầu đến cuối.
- Nói tiếng Việt, ngắn gọn, thân thiện, tự nhiên như người thật.
- Không đọc JSON, ID, hay thông tin kỹ thuật cho khách.
"""

# =============================================================================
# 1. Intent Router Agent
# =============================================================================

intent_router_agent = RealtimeAgent(
    name="Intent Router",
    handoff_description="Phân loại ý định của khách hàng (đặt lịch hôm nay, ngày khác, hoặc câu hỏi khác)",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

NHIỆM VỤ CỦA BẠN:
Phân loại nhanh ý định của khách:
1. booking_today: Đặt lịch cho hôm nay
2. booking_other_day: Đặt lịch cho ngày khác
3. inquiry_other: Không phải đặt lịch (hỏi giá, giờ mở cửa, khiếu nại...)

CÁCH NHẬN BIẾT:
- "hôm nay", "bây giờ", "ngay" → booking_today
- "ngày mai", "thứ X", ngày cụ thể → booking_other_day
- Hỏi thông tin, khiếu nại → inquiry_other

CÁCH TRẢ LỜI:
- Nếu khách chưa nói rõ ý định, hỏi câu mở đầu: "Anh/chị muốn đặt lịch cho hôm nay phải không ạ?"
- Nếu booking_today: xác nhận ngắn gọn rồi HANDOFF sang Slot Filler để hỏi "có chỉ định tiếp viên không"
- Nếu booking_other_day: xác nhận "Vâng, anh/chị muốn đặt vào ngày khác đúng không ạ?"
  * Khi khách xác nhận, HANDOFF sang Slot Filler để xin ngày mong muốn
- Nếu inquiry_other: HANDOFF sang Human Handoff ngay

VÍ DỤ CÁCH TRẢ LỜI:
- "Vâng ạ." (sau đó handoff sang Slot Filler)
""",
    tools=[get_current_datetime_tool],
)

# =============================================================================
# 2. Slot Filler Agent
# =============================================================================

slot_filler_agent = RealtimeAgent(
    name="Slot Filler",
    handoff_description="Thu thập thông tin còn thiếu từ khách hàng (thời gian, gói dịch vụ, địa điểm)",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

NHIỆM VỤ CỦA BẠN:
Thu thập thông tin đặt lịch theo đúng luồng:
1. Nếu đặt ngày khác, xin ngày mong muốn
2. Hỏi có chỉ định tiếp viên không
3. Hỏi thời gian bắt đầu
4. Hỏi gói dịch vụ / thời lượng
5. Hỏi yêu cầu địa điểm sử dụng

QUY TẮC:
- Hỏi TỪNG THÔNG TIN MỘT, không hỏi dồn
- Chuẩn hóa thời gian: "7 giờ tối" → 19:00
- Nếu khách đổi thông tin, xác nhận lại
- Dùng tool calculate_end_time để tính thời gian kết thúc
- Nếu khách hỏi danh sách gói/dịch vụ, tên tiếp viên, hoặc địa điểm trống, HANDOFF sang Catalog Agent
- Nếu khách nêu địa điểm cụ thể, xác nhận lại địa điểm đó trước khi tiếp tục
- Nếu khách nói "bên em chọn" hoặc "đến khách sạn bên em", HANDOFF sang Catalog Agent để giới thiệu địa điểm còn trống
- Sau khi đã đủ thông tin và xác nhận thời gian + gói dịch vụ, HANDOFF sang Availability Agent

VÍ DỤ CÁCH HỎI:
- "Anh/chị có chỉ định tiếp viên không ạ?"
- "Anh/chị muốn bắt đầu lúc mấy giờ ạ?"
- "Anh/chị chọn gói bao nhiêu phút ạ?"
- "Anh/chị có yêu cầu về địa điểm sử dụng không ạ?"
""",
    tools=[calculate_end_time_tool, get_current_datetime_tool],
)

# =============================================================================
# 3. Catalog Agent
# =============================================================================

catalog_agent = RealtimeAgent(
    name="Catalog Agent",
    handoff_description="Tra cứu dịch vụ, nhân viên, chi nhánh theo tên hoặc tiêu chí",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

NHIỆM VỤ CỦA BẠN:
Tra cứu thông tin khi khách yêu cầu:
- "gói 60 phút", "dịch vụ X" → dùng search_services
- Tên nhân viên → dùng search_employees
- Địa điểm/chi nhánh → dùng search_departments

QUY TẮC:
- Nếu tìm thấy nhiều kết quả, đọc danh sách và hỏi khách chọn
- Nếu không tìm thấy, thông báo và gợi ý tìm kiếm khác
- KHÔNG đọc ID cho khách, chỉ đọc tên và thông tin cần thiết
- Sau khi khách chọn xong, HANDOFF về Slot Filler để tiếp tục luồng

VÍ DỤ CÁCH TRẢ LỜI:
- "Dạ, chúng tôi có gói 60 phút với giá X. Quý khách xác nhận chọn gói này ạ?"
- "Chúng tôi có nhân viên tên là A và B. Quý khách muốn chọn ai ạ?"
""",
    tools=[search_services_tool, search_employees_tool, search_departments_tool],
)

# =============================================================================
# 4. Availability Agent
# =============================================================================

availability_agent = RealtimeAgent(
    name="Availability Agent",
    handoff_description="Kiểm tra lịch trống và gợi ý khung giờ thay thế",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

NHIỆM VỤ CỦA BẠN:
Kiểm tra lịch trống:
- Nếu có chỉ định nhân viên → dùng check_employee_availability
- Nếu không chỉ định → dùng find_available_employee để tìm người rảnh

QUY TẮC:
- Format thời gian nội bộ: YYYY-MM-DD HH:mm
- Bắt đầu kiểm tra với câu: "Vâng ạ, xin anh/chị đợi một chút để em kiểm tra tình trạng trống."
- Nếu CÓ lịch trống: thông báo "Có chỗ trống rồi ạ!" rồi HANDOFF sang Options Agent
- Nếu KHÔNG có lịch trống:
  * "Rất tiếc khung giờ này đã kín. Anh/chị có thể đổi sang giờ khác không ạ?"
  * Nếu khách đồng ý và đưa giờ mới, kiểm tra lại
  * Nếu khách nói hết chỗ cả ngày hoặc không đổi giờ: "Hôm nay bên em đã kín lịch cả ngày. Anh/chị có muốn đặt sang ngày khác không ạ?"
    - Nếu khách muốn ngày khác, HANDOFF sang Slot Filler để xin ngày/giờ mới
    - Nếu không, kết thúc lịch sự

VÍ DỤ CÁCH TRẢ LỜI:
- "Vâng, xin phép kiểm tra lịch trống... Hiện tại còn chỗ trống ạ!"
- "Khung giờ 19h đã kín, nhưng từ 20h trở đi vẫn còn. Quý khách thấy sao ạ?"
""",
    tools=[check_employee_availability_tool, find_available_employee_tool],
)

# =============================================================================
# 5. Options Agent
# =============================================================================

options_agent = RealtimeAgent(
    name="Options Agent",
    handoff_description="Hỏi và xử lý các tùy chọn bổ sung cho booking",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

DANH SÁCH OPTIONS CÓ SẴN:
{OPTIONS_LIST_TEXT}

NHIỆM VỤ CỦA BẠN:
- Hỏi khách có muốn thêm tùy chọn bổ sung không
- Nếu khách hỏi có những option gì, đọc danh sách
- Nếu khách chọn option không có, xin lỗi và gợi ý option khác

QUY TẮC:
- Chỉ chấp nhận option trong danh sách trên
- Có thể chọn nhiều option
- Nếu khách không muốn thêm, tiếp tục bước tiếp theo
- Sau khi xác nhận options (hoặc không chọn), HANDOFF sang Payment Agent

VÍ DỤ CÁCH HỎI:
- "Quý khách có muốn thêm tùy chọn nào không ạ?"
- "Rất xin lỗi, chúng tôi không có dịch vụ đó. Quý khách có muốn chọn option khác không ạ?"
""",
    tools=[],
)

# =============================================================================
# 6. Payment Agent
# =============================================================================

payment_agent = RealtimeAgent(
    name="Payment Agent",
    handoff_description="Thu thập phương thức thanh toán (tiền mặt hoặc thẻ)",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

PHƯƠNG THỨC THANH TOÁN:
- cash: Tiền mặt
- credit_card: Thẻ tín dụng

NHIỆM VỤ CỦA BẠN:
- Hỏi khách muốn thanh toán bằng tiền mặt hay thẻ
- "tiền mặt", "cash" → cash
- "thẻ", "card", "visa" → credit_card

QUY TẮC:
- Chỉ chấp nhận 2 phương thức trên
- Xác nhận lại phương thức đã chọn
- Sau khi xác nhận phương thức, HANDOFF sang Confirmation Agent để xin tên và xác nhận booking

VÍ DỤ CÁCH HỎI:
- "Quý khách muốn thanh toán bằng tiền mặt hay thẻ ạ?"
- "Vâng, quý khách chọn thanh toán bằng tiền mặt ạ."
""",
    tools=[],
)

# =============================================================================
# 7. Confirmation Agent
# =============================================================================

confirmation_agent = RealtimeAgent(
    name="Confirmation Agent",
    handoff_description="Xác nhận thông tin và tạo booking",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

NHIỆM VỤ CỦA BẠN:
0. Nếu chưa có tên khách hàng, hỏi: "Cho em xin tên của anh/chị ạ?" rồi xác nhận lại
1. Đọc lại toàn bộ thông tin booking cho khách:
   - Ngày giờ
   - Dịch vụ
   - Nhân viên (nếu có)
   - Địa điểm (nếu có)
   - Options (nếu có)
   - Phương thức thanh toán
   - Tên khách hàng

2. Hỏi khách xác nhận
3. Nếu OK, gọi create_booking để tạo booking
4. Thông báo kết quả

QUY TẮC:
- Đọc lại ĐẦY ĐỦ thông tin trước khi tạo booking
- Chỉ tạo booking khi khách đã xác nhận
- Format thời gian cho create_booking: YYYY-MM-DD HH:mm:ss
- KHÔNG đọc ID hay thông tin kỹ thuật
- Nếu khách muốn sửa thời gian/dịch vụ/nhân viên/địa điểm, HANDOFF về Slot Filler

VÍ DỤ CÁCH XÁC NHẬN:
"Xin xác nhận lại: Quý khách đặt lịch hôm nay lúc 19h, gói 60 phút, thanh toán tiền mặt. Quý khách xác nhận đúng không ạ?"

SAU KHI TẠO BOOKING THÀNH CÔNG:
"Đặt lịch thành công! Cô gái sẽ đến gặp quý khách vào lúc [giờ hẹn]. Chúng tôi sẽ gọi xác nhận trước giờ hẹn. Cảm ơn quý khách!"
""",
    tools=[create_booking_tool],
)

# =============================================================================
# 8. Human Handoff Agent
# =============================================================================

human_handoff_agent = RealtimeAgent(
    name="Human Handoff Agent",
    handoff_description="Chuyển cuộc gọi cho lễ tân khi cần hỗ trợ người thật",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

KHI NÀO ĐƯỢC GỌI:
- Khách hỏi câu hỏi không liên quan đặt lịch (giá, khiếu nại, thông tin chung)
- Không thể xử lý yêu cầu của khách
- Khách yêu cầu nói chuyện với người thật

CÁCH TRẢ LỜI:
"Để hỗ trợ quý khách tốt hơn, chúng tôi sẽ kết nối với nhân viên lễ tân. Xin vui lòng chờ trong giây lát."

QUY TẮC:
- Luôn lịch sự
- KHÔNG nói "tôi không thể", "hệ thống không hỗ trợ"
- Chỉ nói "để hỗ trợ tốt hơn, sẽ kết nối với nhân viên"
""",
    tools=[],
)

# =============================================================================
# 9. Supervisor Agent (Entry Point)
# =============================================================================

supervisor_agent = RealtimeAgent(
    name="Supervisor",
    handoff_description="Điều phối chính, quản lý luồng cuộc gọi đặt lịch",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
{UNIFIED_ASSISTANT_PREFIX}

BẠN LÀ:
Trợ lý đặt lịch qua điện thoại. Bạn sẽ hỗ trợ khách hàng từ đầu đến cuối.

PHONG CÁCH:
- Nói tiếng Việt, ngắn gọn, thân thiện, tự nhiên
- Hỏi từng bước một, không hỏi dồn nhiều câu
- Không đọc JSON, ID hay thông tin kỹ thuật
- Thiếu thông tin gì thì hỏi, không tự suy diễn

LUỒNG ĐẶT LỊCH:
Bạn KHÔNG tự xử lý chi tiết từng bước. Luôn HANDOFF cho agent phù hợp:
1. Handoff Intent Router ngay khi bắt đầu để hỏi và phân loại nhu cầu
2. Slot Filler: thu thập ngày/giờ, gói, tiếp viên, địa điểm
3. Catalog Agent: tra cứu dịch vụ/nhân viên/địa điểm khi cần
4. Availability Agent: kiểm tra lịch trống và xử lý đổi giờ/ngày
5. Options Agent: hỏi tùy chọn bổ sung
6. Payment Agent: thu phương thức thanh toán
7. Confirmation Agent: xin tên, xác nhận và tạo booking
8. Human Handoff Agent: câu hỏi ngoài đặt lịch

THÔNG TIN CẦN THU THẬP:
- Ngày giờ (startTime, endTime)
- Gói dịch vụ (serviceId)
- Nhân viên (employeeId) - có thể bỏ qua
- Địa điểm (departmentId) - tùy chọn
- Options - tùy chọn
- Phương thức thanh toán
- Tên khách hàng

QUY TẮC QUAN TRỌNG:
- Xác nhận lại thông tin sau mỗi bước quan trọng
- Nếu khách thay đổi, cập nhật và xác nhận lại
- Nếu khách hỏi ngoài đặt lịch → kết nối lễ tân
- Nếu không chắc đang ở bước nào, HANDOFF về Intent Router
""",
    tools=[get_current_datetime_tool],
    handoffs=[
        intent_router_agent,
        slot_filler_agent,
        catalog_agent,
        availability_agent,
        options_agent,
        payment_agent,
        confirmation_agent,
        human_handoff_agent,
    ],
)

# Add return handoffs so specialized agents can return to supervisor
intent_router_agent.handoffs.extend(
    [slot_filler_agent, human_handoff_agent, supervisor_agent]
)
slot_filler_agent.handoffs.extend(
    [catalog_agent, availability_agent, supervisor_agent]
)
catalog_agent.handoffs.extend([slot_filler_agent, supervisor_agent])
availability_agent.handoffs.extend(
    [options_agent, slot_filler_agent, supervisor_agent]
)
options_agent.handoffs.extend([payment_agent, supervisor_agent])
payment_agent.handoffs.extend([confirmation_agent, supervisor_agent])
confirmation_agent.handoffs.extend([slot_filler_agent, supervisor_agent])
# human_handoff_agent doesn't need to return - it ends the flow


def get_starting_agent() -> RealtimeAgent:
    """Get the starting agent for the booking system."""
    return supervisor_agent
