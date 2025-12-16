# Multi-Agent Realtime Call Flow Plan

## Objectives
- Keep the Twilio ↔ OpenAI realtime audio bridge stable while enabling graph-based call handling.
- Let the root agent hand off subtasks to specialized realtime agents via tool calls, and receive concise summaries back.
- Add tool functions that wrap the documented booking APIs so each agent can act on reliable data.

## Agent Architecture
- **Root Call Agent**: Maintains the Twilio media stream, drives the conversation, and decides when to delegate. Uses the full tool registry (including the new delegation tool).
- **Availability Agent**: Text-only realtime agent that checks staff/service availability, suggests alternatives, and reads from `/employees/availables`, `/bookings/calendar`, and `/employees/{id}/bookings`.
- **Booking Agent**: Text-only realtime agent that assembles booking payloads and calls `/bookings` plus customer CRUD endpoints when needed. It normalizes customer/contact info and embeds call metadata (e.g., Twilio SID).
- **Data Agent (utility)**: Text-only realtime agent for quick lookups (services, departments, employees, customers) to support the flow without blocking the root audio loop.
- All sub-agents share the same `AsyncOpenAI` client and websocket base URL from the handler instance; Twilio websocket is never passed through tool arguments.

## Delegation Flow
1. Root agent triggers a `delegate_to_agent` tool call with the target agent name and the current call context.
2. The delegation tool spins up a text-only realtime connection (no audio), injects agent-specific instructions, and exposes only the tools that agent needs.
3. Sub-agent handles any API tool calls internally and returns a structured summary (decisions, suggested times, payload drafts) to the root agent.
4. Root agent resumes the voice conversation using the summary and keeps the Twilio stream uninterrupted.

## Tooling Plan (aligned with API specs)
- **New API tools**
  - `get_booking_calendar` → `GET /bookings/calendar`
  - `get_available_employees` → `GET /employees/availables`
  - `get_employee_bookings` → `GET /employees/{id}/bookings`
  - `get_department_list` → `GET /departments`
  - Customer CRUD: list/create/update/delete
- **Enhance existing tools**
  - `create_booking`: accept `endTime`, pass `twilioCallSid`, keep notes for location preference.
  - `get_service_list`: support duration/price filters.
  - `get_employee_list`: allow optional name filter and paging defaults.
  - `check_booking_availability`: point to `/employees/availables` to match the reviewed API.
- **Delegation tool**
  - `delegate_to_agent`: routes tasks to availability/booking/data agents and returns a summary payload.

## Code Changes
1. Add a `RealtimeAgentOrchestrator` helper (new module) to run text-only realtime agents, handle their tool calls via `ToolService`, and return summaries.
2. Implement new tool classes for the missing API endpoints and register them in `ToolService`; add the delegation tool hooked to the orchestrator.
3. Update `WebSocketHandler` session setup to load full tool definitions, use call-flow-aligned instructions, and keep the Twilio stream state while delegation runs.
4. Keep logging around agent handoffs and tool execution for traceability.

## Validation
- Smoke-test tool registration (`startup` log) to confirm new tools are exposed.
- Dry-run a simulated delegation call (unit-style async call) to ensure the orchestrator executes and returns summaries without touching the Twilio websocket.
