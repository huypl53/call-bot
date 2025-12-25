# KIAI Assistant - Trợ Lý Ảo Đặt Phòng Khách Sạn

Hệ thống trợ lý ảo thông minh sử dụng OpenAI Realtime API, Twilio Voice và FastAPI để hỗ trợ khách hàng đặt phòng khách sạn qua cuộc gọi điện thoại.

## 🎯 Tính Năng

- ✅ Giao tiếp bằng tiếng Việt tự nhiên
- ✅ Thu thập thông tin đặt phòng đầy đủ (tên, tuổi, giới tính, ngày, loại phòng)
- ✅ Kiểm tra phòng trống realtime
- ✅ Lưu trữ session tự động sau mỗi update
- ✅ Hỗ trợ ngắt lời (interruption handling)
- ✅ Docker support

## 📋 Yêu Cầu Hệ Thống

- Python 3.9+
- OpenAI API key (với quyền truy cập Realtime API)
- Twilio account với số điện thoại có Voice capabilities
- ngrok (cho development local)
- Docker & Docker Compose (optional)

## 🚀 Cài Đặt

### Option 1: Chạy Local

```bash
# 0. Clone repository
git clone git@gitlab.kiaisoft.com:k25/cti-auto-reservation/poc-ai-reservation.git
cd poc-ai-reservation 

```bash
# 1. Build và chạy với docker-compose
cd docker
docker-compose up -d

# 2. Xem logs
docker-compose logs -f

# 3. Dừng service
docker-compose down
```

## ⚙️ Cấu Hình

Tạo file `.env` với các biến sau:

```env
# Required
OPENAI_API_KEY=sk-your-api-key-here

# Optional (có defaults)
PORT=5050
TEMPERATURE=0.8
VOICE=alloy
DEBUG=false
LOG_LEVEL=INFO
```

### Các Voice Options

- `alloy` (default)
- `echo`
- `fable`  
- `onyx`
- `nova`
- `shimmer`

## 🏗️ Kiến Trúc Hệ Thống

```
src/
├── config/              # Configuration
│   ├── constants.py     # Hằng số
│   ├── prompts.py       # System prompts
│   └── settings.py      # Settings với validation
├── core/                # Core business logic
│   └── session_manager.py
├── services/            # Services layer
│   ├── tool_service.py
│   └── twilio_service.py
├── tools/               # AI Tools
│   ├── base.py          # Abstract base class
│   ├── booking_api.py   # Booking API tool
│   ├── department_api.py
│   ├── employee_api.py
│   └── service_api.py
├── api/                 # API layer
│   ├── routes.py
│   └── websocket_handler.py
└── main.py             # Entry point
```

## 🔧 Setup Twilio

### 1. Mua số điện thoại Twilio

Truy cập [Twilio Console](https://console.twilio.com/) và mua số có Voice capabilities.

### 2. Cấu hình Webhook

1. Vào **Phone Numbers** → **Manage** → **Active Numbers**
2. Click vào số điện thoại
3. Trong phần **Voice Configuration**:
   - **A CALL COMES IN**: Webhook
   - **URL**: `https://your-ngrok-url.ngrok.app/incoming-call`
   - **HTTP**: POST
4. **Save**

### 3. Setup ngrok (Development)

```bash
# Mở terminal mới
ngrok http 5050

# Copy URL dạng: https://xxxx.ngrok.app
# Dùng URL này cho Twilio webhook
```

## 📞 Sử Dụng

1. Start application (local hoặc Docker)
2. Start ngrok: `ngrok http 5050`
3. Cập nhật Twilio webhook với ngrok URL
4. Gọi số Twilio sử dụng Test Phone
5. KIAI assistant sẽ trả lời và hỗ trợ đặt phòng

## 📊 Session Data

Mỗi cuộc gọi tạo 1 file JSON trong thư mục `sessions/`:

```json
{
  "stream_sid": "MZ1234567890",
  "start_time": "2025-10-23T10:00:00",
  "end_time": "2025-10-23T10:05:00",
  "last_updated": "2025-10-23T10:05:00",
  "booking_info": {
    "full_name": "Nguyễn Văn A",
    "age": 30,
    "gender": "male",
    "check_in_date": "2025-11-01",
    "check_out_date": "2025-11-03",
    "room_type": "vip",
    "special_requests": "Phòng tầng cao"
  },
  "room_checks": [...],
  "completion_status": {
    "total_fields": 6,
    "filled_fields": 6,
    "is_complete": true
  }
}
```

## 🧪 Testing

```bash
# Run tests
pytest tests/

# Test specific module
pytest tests/test_tools.py

# With coverage
pytest --cov=src tests/
```

## 🐛 Troubleshooting

### Issue: Tools không được gọi
**Solution**: Check logs, đảm bảo prompt rõ ràng và tool definitions đúng.

### Issue: Session file không tạo
**Solution**: Check permissions thư mục `sessions/`, đảm bảo app có quyền write.

### Issue: Tiếng Việt phát âm không chuẩn
**Solution**: Thử các voice khác (shimmer, echo) hoặc đợi OpenAI cải thiện.

### Issue: Docker container không start
**Solution**: 
```bash
docker-compose logs kiai-assistant
```

## 📚 API Documentation

Khi app chạy, truy cập:
- Swagger UI: `http://localhost:5050/docs`
- ReDoc: `http://localhost:5050/redoc`

## 🔒 Security Notes

- Không commit `.env` file
- Không share OPENAI_API_KEY
- Sử dụng HTTPS cho production
- Implement rate limiting cho production
- Validate Twilio webhook signatures

## 📈 Monitoring

Console logs hiển thị:

```
============================================================
🔧 TOOL CALLED: save_booking_info
============================================================
📝 Arguments: {"full_name": "Nguyễn Văn A"}
📝 Updated: full_name=Nguyễn Văn A
💾 Auto-saved → sessions/MZ123.json (1/6 fields)
✅ Result: {"success": true, ...}
============================================================
```

## 🤝 Contributing

1. Fork repository
2. Tạo feature branch: `git checkout -b feature/AmazingFeature`
3. Commit changes: `git commit -m 'Add some AmazingFeature'`
4. Push to branch: `git push origin feature/AmazingFeature`
5. Open Pull Request

## 🙏 Credits

- OpenAI Realtime API
- Twilio Voice & Media Streams
- FastAPI Framework

## 📞 Support

Nếu gặp vấn đề:
1. Check [CHANGELOG.md](CHANGELOG.md)
2. Search existing issues
3. Create new issue với detailed description

---

**Version**: 2.0.0  
**Last Updated**: 2025-10-23  
**Author**: KIAI Development Team
