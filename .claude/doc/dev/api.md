# API Documentation

**Collection:** v1  
**Collection ID:** `37162149-c5646be9-be26-4d2a-921b-278757701bdc`  
**Last Updated:** 2025-12-09T06:48:08.000Z

## Overview

This API collection contains endpoints for managing bookings, employees, services, departments, and customers. The API uses a base URL variable `{{api_url}}` and follows RESTful conventions.

---

## 📁 Bookings

### GET Calendar

**Endpoint:** `GET {{api_url}}/bookings/calendar`

**Description:** Retrieves booking calendar information for a specific date.

**Query Parameters:**
- `date` (required): Date in format `YYYY-MM-DD` (e.g., `2025-12-01`)

**Example Request:**
```
GET {{api_url}}/bookings/calendar?date=2025-12-01
```

**Response:** No example response available in collection.

---

### Make Booking

**Endpoint:** `POST {{api_url}}/bookings`

**Description:** Creates a new booking. Supports phone-based bookings with Twilio integration.

**Headers:**
- `Content-Type: application/json`

**Request Body:**
```json
{
    "source": "phone",
    "twilioCallSid": "test",
    "bookingInfo": {
      "employeeId": "6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01",
      "serviceId": "e1b918f2-bf4c-4a94-8997-1b02e3ad2b04",
      "startTime": "2025-12-01T10:00:00.000Z",
      "endTime": "2025-12-01T11:00:00.000Z",
      "notes": "Customer requested morning slot"
    },
    "customerInfo": {
      "name": "山田 太郎",
      "furiganaName": "ヤマダ タロウ",
      "phoneNumber": "090-1234-5678",
      "age": 30,
      "gender": "male"
    }
}
```

**Request Body Schema:**
- `source` (string): Booking source (e.g., "phone")
- `twilioCallSid` (string, optional): Twilio call SID for phone bookings
- `bookingInfo` (object):
  - `employeeId` (UUID): Employee ID
  - `serviceId` (UUID): Service ID
  - `startTime` (ISO 8601): Booking start time
  - `endTime` (ISO 8601): Booking end time
  - `notes` (string, optional): Additional notes
- `customerInfo` (object):
  - `name` (string): Customer name (supports Japanese characters)
  - `furiganaName` (string): Furigana name (phonetic reading)
  - `phoneNumber` (string): Phone number
  - `age` (number): Customer age
  - `gender` (string): Gender (e.g., "male", "female")

**Example Response:**
```json
{
    "source": "phone",
    "twilioCallSid": "test",
    "bookingInfo": {
      "employeeId": "6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01",
      "serviceId": "e1b918f2-bf4c-4a94-8997-1b02e3ad2b04",
      "startTime": "2025-12-01T10:00:00.000Z",
      "endTime": "2025-12-01T11:00:00.000Z",
      "notes": "Customer requested morning slot"
    },
    "customerInfo": {
      "name": "山田 太郎",
      "furiganaName": "ヤマダ タロウ",
      "phoneNumber": "090-1234-5678",
      "age": 30,
      "gender": "male"
    }
}
```

---

## 👥 Employees

### GET List Employees

**Endpoint:** `GET {{api_url}}/employees`

**Description:** Retrieves a paginated list of employees.

**Query Parameters:**
- `page` (required): Page number (default: `1`)
- `size` (required): Page size (default: `0` for all)

**Example Request:**
```
GET {{api_url}}/employees?page=1&size=0
```

**Example Response (200 OK):**
```json
{
    "total": 1,
    "resultCount": 1,
    "data": [
        {
            "id": "6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01",
            "fullName": "山田 太郎",
            "displayName": "山田 太郎",
            "age": 28,
            "gender": "male",
            "role": "admin"
        }
    ],
    "page": 1,
    "size": 5
}
```

---

### GET List Available Employees

**Endpoint:** `GET {{api_url}}/employees/availables`

**Description:** Retrieves a list of employees available within a specified time range.

**Query Parameters:**
- `page` (required): Page number (default: `1`)
- `size` (required): Page size (default: `5`)
- `employeeName` (optional): Filter by employee name (e.g., `山田 太郎`)
- `startTime` (optional): Start time filter (format: `YYYY-MM-DD HH:mm`, e.g., `2025-12-01 16:00`)
- `endTime` (optional): End time filter (format: `YYYY-MM-DD HH:mm`, e.g., `2025-12-01 19:00`)

**Example Request:**
```
GET {{api_url}}/employees/availables?page=1&size=5
```

**With Filters:**
```
GET {{api_url}}/employees/availables?employeeName=山田 太郎&startTime=2025-12-01 16:00&endTime=2025-12-01 18:00&page=1&size=5
```

**Example Response (200 OK):**
```json
{
    "total": 1,
    "resultCount": 1,
    "data": [
        {
            "id": "6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01",
            "fullName": "山田 太郎",
            "displayName": "山田 太郎",
            "age": 28,
            "gender": "male",
            "role": "admin"
        }
    ],
    "page": 1,
    "size": 5
}
```

---

### GET List Employee Bookings

**Endpoint:** `GET {{api_url}}/employees/{employeeId}/bookings`

**Description:** Retrieves bookings for a specific employee within a time range.

**Path Parameters:**
- `employeeId` (UUID): Employee ID (e.g., `6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01`)

**Query Parameters:**
- `page` (required): Page number (default: `1`)
- `size` (required): Page size (default: `10`)
- `startTime` (optional): Start time filter (format: `YYYY-MM-DD HH:mm`, e.g., `2025-12-01 19:00`)
- `endTime` (optional): End time filter (format: `YYYY-MM-DD HH:mm`, e.g., `2025-12-01 20:00`)

**Example Request:**
```
GET {{api_url}}/employees/6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01/bookings?page=1&size=10&startTime=2025-12-01 19:00&endTime=2025-12-01 20:00
```

**Example Response (200 OK):**
```json
{
    "employee": {
        "id": "6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01",
        "fullName": "山田 太郎",
        "displayName": "山田 太郎",
        "role": "admin",
        "status": true
    },
    "bookings": {
        "total": 1,
        "resultCount": 1,
        "data": [
            {
                "id": "7f5728cd-bc8d-49b8-9242-fef1bf310535",
                "startTime": "2025-12-01T10:00:00.000Z",
                "endTime": "2025-12-01T11:00:00.000Z",
                "status": "confirmed",
                "notes": "te",
                "createdAt": "2025-12-04T05:29:35.000Z"
            }
        ],
        "page": 1,
        "size": 10
    }
}
```

---

## 🛎️ Services

### GET List Services

**Endpoint:** `GET {{api_url}}/services`

**Description:** Retrieves a paginated list of services with optional filtering.

**Query Parameters:**
- `page` (required): Page number (default: `1`)
- `size` (required): Page size (default: `0` for all)
- `name` (optional): Filter by service name (e.g., `プレミアムサポート`)
- `description` (optional): Filter by description (e.g., `サービスです`)
- `minDurationMinutes` (optional): Minimum duration in minutes (e.g., `45`)
- `maxDurationMinutes` (optional): Maximum duration in minutes (e.g., `100`)
- `minPrice` (optional): Minimum price (e.g., `100`)
- `maxPrice` (optional): Maximum price (e.g., `150`)

**Example Request:**
```
GET {{api_url}}/services?page=1&size=0
```

**With Filters:**
```
GET {{api_url}}/services?page=1&size=5&minDurationMinutes=45&maxDurationMinutes=100&minPrice=100&maxPrice=150
```

**Example Response (200 OK):**
```json
{
    "total": 2,
    "resultCount": 2,
    "data": [
        {
            "id": "e1b918f2-bf4c-4a94-8997-1b02e3ad2b04",
            "name": "基本コンサルティング",
            "description": "ビジネスに関する基本的な相談サービスです。",
            "durationMinutes": 60,
            "price": "100.00"
        },
        {
            "id": "c32de0fa-5e54-4ab3-bdf9-32d1a9ce8f02",
            "name": "総合ヘルプサービス",
            "description": "問題解決を全面的にサポートします。",
            "durationMinutes": 90,
            "price": "150.00"
        }
    ],
    "page": 1,
    "size": 5
}
```

---

## 🏢 Departments

### GET List Departments

**Endpoint:** `GET {{api_url}}/departments`

**Description:** Retrieves a paginated list of departments with optional filtering.

**Query Parameters:**
- `page` (required): Page number (default: `1`)
- `size` (required): Page size (default: `0` for all)
- `name` (optional): Filter by department name (e.g., `test`)
- `address` (optional): Filter by address (can be empty)

**Example Request:**
```
GET {{api_url}}/departments?name=test&address=&page=1&size=0
```

**Example Response (200 OK):**
```json
{
    "total": 1,
    "resultCount": 1,
    "data": [
        {
            "id": "797e973c-c328-4523-8bbb-391e54cd4538",
            "name": "test",
            "address": "aaa",
            "status": true,
            "createdAt": "2025-12-05T05:58:05.000Z",
            "updatedAt": "2025-12-05T05:58:08.000Z"
        }
    ],
    "page": 1,
    "size": 5
}
```

---

## 👤 Customers

### GET List Customers

**Endpoint:** `GET {{api_url}}/customers`

**Description:** Retrieves a paginated list of customers with extensive filtering options.

**Query Parameters:**
- `page` (required): Page number (default: `1`)
- `size` (required): Page size (default: `10`)
- `name` (optional): Filter by customer name (e.g., `田中`)
- `phoneNumber` (optional): Filter by phone number (e.g., `090`)
- `category` (optional): Filter by category (e.g., `NEW`)
- `code` (optional): Filter by customer code (e.g., `CUST0005`)
- `gender` (optional): Filter by gender (e.g., `male`)
- `firstContactSource` (optional): Filter by first contact source
- `ageFrom` (optional): Minimum age (e.g., `30`)
- `ageTo` (optional): Maximum age (e.g., `40`)

**Example Request:**
```
GET {{api_url}}/customers?page=1&size=10
```

**With Filters:**
```
GET {{api_url}}/customers?page=1&size=10&name=田中&phoneNumber=090&category=NEW
```

**Response:** No example response available in collection.

---

### POST Create Customer

**Endpoint:** `POST {{api_url}}/customers`

**Description:** Creates a new customer.

**Headers:**
- `Content-Type: application/json`

**Request Body:**
```json
{
    "name": "田中太郎",
    "furiganaName": "タナカタロウ",
    "phoneNumber": "090-1234-5678",
    "age": 30,
    "gender": "male",
    "category": "new",
    "firstContactSource": "website",
    "note": "New customer"
}
```

**Request Body Schema:**
- `name` (string, required): Customer name (supports Japanese characters)
- `furiganaName` (string, required): Furigana name (phonetic reading)
- `phoneNumber` (string, required): Phone number
- `age` (number, required): Customer age
- `gender` (string, required): Gender (e.g., "male", "female")
- `category` (string, required): Customer category (e.g., "new", "VIP")
- `firstContactSource` (string, optional): First contact source (e.g., "website")
- `note` (string, optional): Additional notes

**Example Response:**
```json
{
    "name": "田中太郎",
    "furiganaName": "タナカタロウ",
    "phoneNumber": "090-1234-5678",
    "age": 30,
    "gender": "male",
    "category": "new",
    "firstContactSource": "website",
    "note": "New customer"
}
```

---

### PATCH Update Customer

**Endpoint:** `PATCH {{api_url}}/customers/{customerId}`

**Description:** Updates an existing customer. Supports partial updates.

**Path Parameters:**
- `customerId` (UUID): Customer ID (e.g., `9ac60151-6c27-4a4f-b994-ac9c2e711350`)

**Headers:**
- `Content-Type: application/json`

**Request Body (all fields optional):**
```json
{
    "name": "田中太郎",
    "furiganaName": "タナカタロウ",
    "phoneNumber": "090-1234-5678",
    "age": 30,
    "gender": "male",
    "category": "new",
    "firstContactSource": "website",
    "note": "New customer"
}
```

**Example Partial Update:**
```json
{
  "age": 35,
  "category": "VIP"
}
```

**Example Response:**
```json
{
    "name": "田中太郎",
    "furiganaName": "タナカタロウ",
    "phoneNumber": "090-1234-5678",
    "age": 30,
    "gender": "male",
    "category": "new",
    "firstContactSource": "website",
    "note": "New customer"
}
```

---

### DELETE Customer

**Endpoint:** `DELETE {{api_url}}/customers/{customerId}`

**Description:** Deletes a customer.

**Path Parameters:**
- `customerId` (UUID): Customer ID (e.g., `9ac60151-6c27-4a4f-b994-ac9c2e711350`)

**Headers:**
- `Content-Type: application/json`

**Example Request:**
```
DELETE {{api_url}}/customers/9ac60151-6c27-4a4f-b994-ac9c2e711350
```

**Response:** No example response available in collection.

---

## Common Patterns

### Pagination

Most list endpoints support pagination with:
- `page`: Page number (1-indexed)
- `size`: Number of items per page (0 typically means "all")

**Response Format:**
```json
{
  "total": <total_count>,
  "resultCount": <current_page_count>,
  "data": [<items>],
  "page": <current_page>,
  "size": <page_size>
}
```

### Date/Time Formats

- **ISO 8601** (for booking times): `2025-12-01T10:00:00.000Z`
- **Date only**: `YYYY-MM-DD` (e.g., `2025-12-01`)
- **Date with time** (for filters): `YYYY-MM-DD HH:mm` (e.g., `2025-12-01 16:00`)

### Japanese Character Support

The API fully supports Japanese characters (Kanji, Hiragana, Katakana) in:
- Customer names
- Employee names
- Service names and descriptions
- Department names

### UUID Format

All IDs use UUID v4 format (e.g., `6fd9d4e1-1c13-4f5e-8ffc-01a1b11e1a01`).

---

## Notes

- All endpoints use the base URL variable `{{api_url}}`
- Most endpoints return JSON responses
- No authentication is explicitly configured in the collection (may be handled at the server level)
- Some endpoints have example responses, while others do not have saved examples in the collection
