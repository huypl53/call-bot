# API vs Call Flow Review

**Date:** 2025-12-09 (Updated)  
**Reviewer:** AI Assistant  
**API Documentation Version:** Updated with full request/response examples

This document analyzes the gap between the intended Call Bot logic (`call-flow.md`) and the existing API capabilities (`api.md`).

---

## ✅ Supported Features

The following flow requirements are adequately supported by the current API:

### 1. Staff Selection
- **Flow Requirement:** Bot asks if customer wants to select a specific employee (mentions "female employee").
- **API Support:**
  - `GET /employees` - Returns list of all employees with `gender` field
  - `GET /employees/availables` - Supports filtering by `employeeName` and time range
- **Implementation Note:** Client-side filtering by `gender` is possible from the employee list response.

### 2. Service/Duration Selection
- **Flow Requirement:** Bot asks for "service package duration" (in minutes).
- **API Support:**
  - `GET /services` - Returns services with `durationMinutes` field
  - Supports filtering by `minDurationMinutes` and `maxDurationMinutes`
- **Implementation Note:** Bot can map user's spoken duration (e.g., "60 minutes") to a `serviceId` by querying services.

### 3. Date Selection & Calendar View
- **Flow Requirement:** Bot asks if booking is for "today" or another date.
- **API Support:**
  - `GET /bookings/calendar?date=YYYY-MM-DD` - Retrieves calendar information for a specific date
- **Implementation Note:** Response structure is unknown (no example in collection), but endpoint exists for date-based queries.

### 4. Customer Information Collection
- **Flow Requirement:** Bot collects name and contact information before finalizing booking.
- **API Support:**
  - `POST /bookings` - Accepts comprehensive `customerInfo` object:
    - `name`, `furiganaName`, `phoneNumber`, `age`, `gender`
  - `POST /customers` - Can create customer records separately if needed
- **Implementation Note:** Full customer data structure is documented with example request/response.

### 5. Booking Creation
- **Flow Requirement:** Finalize booking after collecting all information.
- **API Support:**
  - `POST /bookings` - Creates booking with:
    - `bookingInfo` (employeeId, serviceId, startTime, endTime, notes)
    - `customerInfo` (complete customer details)
    - `source: "phone"` and `twilioCallSid` for call tracking
- **Implementation Note:** Request/response examples are now fully documented.

---

## ⚠️ Critical Gaps & Missing Resources

The following features described in the call flow **cannot** be fully implemented with the current API:

### 1. Room / Location Management (🔴 Major Gap)

**Flow Requirement:**
- Bot asks: *"Do you have a preference for location/branch or specific room?"*
- Bot says: *"Checking for empty rooms"* (specifically mentions "room" - *phòng*)
- Bot can note specific location or suggest a suitable one

**Current API Status:**
- `POST /bookings` request body **does not** include:
  - `locationId`
  - `branchId` 
  - `roomId`
  - `departmentId`
- Only links `employeeId` and `serviceId`
- `GET /departments` exists but cannot be used to filter availability or assign bookings
- No endpoint to check room availability (`GET /rooms` or `GET /rooms/availability`)

**Impact:**
- Cannot fulfill location preference requests
- Cannot check if specific rooms are available
- Cannot assign bookings to specific locations/branches

**Action Required:**
1. **Update `POST /bookings`:** Add optional fields:
   ```json
   {
     "bookingInfo": {
       "roomId": "uuid",        // NEW
       "locationId": "uuid",    // NEW
       "departmentId": "uuid"   // NEW (or use existing department)
     }
   }
   ```
2. **New Endpoint:** `GET /rooms/availability?date=YYYY-MM-DD&startTime=HH:mm&endTime=HH:mm`
3. **Update `GET /employees/availables`:** Add `departmentId` or `locationId` filter parameter

---

### 2. "Next Available" Time Suggestions (🔴 Major Gap)

**Flow Requirement:**
- If requested slot is unavailable, bot must suggest: *"We have slots available after XX:XX today"*
- Bot needs to find alternative times when exact time is busy
- Flow loops back to availability check with new suggested time

**Current API Status:**
- `GET /employees/availables` requires **specific** `startTime` and `endTime` parameters
- No endpoint to:
  - Get all available slots for a day
  - Find "next available" slots after a given time
  - Get suggested alternatives when a time slot is busy
- `GET /bookings/calendar` exists but response structure unknown (might help, but no documentation)

**Impact:**
- Cannot efficiently suggest alternative times
- Would require multiple API calls with trial-and-error time ranges
- Poor user experience (slow, inefficient)

**Action Required:**
1. **Enhance `GET /employees/availables`:**
   - Option A: Allow querying entire day (omit `startTime`/`endTime` to get all slots)
   - Option B: Add `findNextAvailable=true` parameter to return next available slots
   - Option C: Return `suggestedAlternatives` array in response when exact time unavailable
2. **Document `GET /bookings/calendar` response:** If it returns availability data, document it
3. **New Endpoint:** `GET /bookings/available-slots?date=YYYY-MM-DD&serviceId=uuid&employeeId=uuid&afterTime=HH:mm`

---

### 3. Gender-Based Employee Filtering (🟡 Minor Gap)

**Flow Requirement:**
- Bot specifically asks about "female employee" preference
- Should filter employees by gender

**Current API Status:**
- `GET /employees/availables` does not accept `gender` filter parameter
- `GET /employees` response includes `gender` field but no filter parameter
- Client-side filtering is possible but inefficient

**Impact:**
- Requires fetching all employees and filtering client-side
- Less efficient for large employee lists

**Action Required:**
- **Update `GET /employees/availables`:** Add optional `gender` query parameter

---

### 4. Calendar Response Structure Unknown (🟡 Documentation Gap)

**Flow Requirement:**
- Bot needs to check availability for a specific date
- May need to display calendar information

**Current API Status:**
- `GET /bookings/calendar?date=YYYY-MM-DD` endpoint exists
- **No example response** in collection
- Unknown if it returns:
  - Available time slots
  - Booked slots
  - Room availability
  - Employee schedules

**Impact:**
- Cannot determine if this endpoint can be used for availability checking
- May be duplicating functionality with `GET /employees/availables`

**Action Required:**
- **Document `GET /bookings/calendar` response structure**
- Clarify its purpose vs `GET /employees/availables`

---

## 📊 Implementation Readiness Score

| Feature | Status | API Support | Notes |
|---------|--------|-------------|-------|
| Date Selection | ✅ Ready | `GET /bookings/calendar` | Response structure unknown |
| Staff Selection | ✅ Ready | `GET /employees/availables` | Gender filter missing |
| Service Selection | ✅ Ready | `GET /services` | Full support |
| Time Selection | ⚠️ Partial | `GET /employees/availables` | Requires specific time range |
| Location Preference | ❌ Not Ready | Missing | No room/location support |
| Availability Check | ⚠️ Partial | `GET /employees/availables` | No room checking |
| Alternative Suggestions | ❌ Not Ready | Missing | No "next available" logic |
| Customer Info Collection | ✅ Ready | `POST /bookings` | Full support |
| Booking Creation | ✅ Ready | `POST /bookings` | Full support |

**Overall Readiness: 60%** - Core booking flow works, but location/room management and alternative suggestions are missing.

---

## 🎯 Recommendations

### Priority 1: Critical for Call Flow Implementation

1. **Add Location/Room Support to Bookings**
   - Update `POST /bookings` to accept `roomId`/`locationId`/`departmentId`
   - Create `GET /rooms/availability` endpoint
   - Add `departmentId` filter to `GET /employees/availables`

2. **Implement "Next Available" Logic**
   - Enhance `GET /employees/availables` to support:
     - Querying full day (without specific time range)
     - Returning suggested alternatives
   - OR create new endpoint: `GET /bookings/available-slots`

### Priority 2: Enhancements

3. **Add Gender Filter**
   - Add `gender` parameter to `GET /employees/availables`

4. **Document Calendar Endpoint**
   - Provide example response for `GET /bookings/calendar`
   - Clarify its role vs other availability endpoints

### Priority 3: Nice to Have

5. **Response Examples**
   - Add example responses for:
     - `GET /bookings/calendar`
     - `GET /customers` (list)
     - `DELETE /customers`

---

## 🔄 Workarounds (If API Changes Not Possible)

1. **Location Preference:**
   - Store location preference in `notes` field of booking
   - Use `GET /departments` to list options, but cannot enforce availability

2. **Next Available Suggestions:**
   - Make multiple `GET /employees/availables` calls with incrementing time ranges
   - Cache results client-side
   - **Performance Impact:** Slow, multiple API calls required

3. **Room Availability:**
   - Assume employee availability = room availability
   - **Limitation:** Cannot handle multiple rooms per employee or room-specific constraints

---

## 📝 Summary

The current API provides **solid foundation** for the call flow:
- ✅ Employee and service selection
- ✅ Customer information collection
- ✅ Booking creation with phone call tracking

However, **critical gaps** remain:
- ❌ Room/location management (explicitly mentioned in flow)
- ❌ Efficient alternative time suggestions
- ⚠️ Gender-based filtering (minor)

**Recommendation:** Implement Priority 1 items before deploying the call bot to ensure full feature parity with the designed flow.
