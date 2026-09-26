# MainTen / CFMS Agent API Specification

Contract between CFMS backend and the locally installed Windows Desktop Agent (Iteration 6).

## Overview
The Windows agent polls the backend at regular intervals (or receives WebSocket push) to display native Windows toast notifications with clickable links opening the date picker page for assigned computers.

## Endpoints

### 1. `GET /api/agent/notifications`
Fetch unacknowledged notifications for a target user.

- **Query Parameters**:
  - `user_id` (int, required): Target user ID.
  - `unacknowledged_only` (bool, default `true`): Filter out acknowledged notifications.
- **Authentication**: Session cookie or Magic Link token header.
- **Response 200 OK**:
  ```json
  {
    "notifications": [
      {
        "id": 42,
        "user_id": 5,
        "computer_id": 12,
        "event_id": null,
        "channel": "windows_agent",
        "payload": {
          "type": "daily_reminder",
          "computer_hostname": "PC-FINANCE-01",
          "due_date": "2026-10-15",
          "window_end": "2026-10-25",
          "message": "Пожалуйста, выберите дату технического обслуживания для PC-FINANCE-01."
        },
        "sent_at": "2026-09-26T10:00:00Z",
        "acknowledged_at": null
      }
    ],
    "count": 1
  }
  ```

### 2. `POST /api/agent/notifications/{notification_id}/ack`
Acknowledge receipt and display of a notification toast.

- **URL Parameter**: `notification_id` (int)
- **Response 200 OK**:
  ```json
  {
    "status": "success",
    "notification_id": 42,
    "acknowledged_at": "2026-09-26T10:05:00Z"
  }
  ```
