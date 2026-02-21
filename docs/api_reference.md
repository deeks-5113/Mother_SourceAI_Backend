# MotherSource AI — API Reference

This document provides technical details for the MotherSource AI Backend (Service 1: Mother Onboarding Finder).

## Base Configuration
- **Base URL**: `http://127.0.0.1:8000/api/v1`
- **Content-Type**: `application/json`

---

## 1. Health Check
Check if the service is running.

**URL**: `/health` (Note: This is outside the `/api/v1` prefix by default in `main.py`)
**Method**: `GET`

### Response
- **Status Code**: `200 OK`
- **Body**:
```json
{
  "status": "ok",
  "service": "mother-onboarding-finder"
}
```

---

## 2. Channel Search
Find and rank the Top-4 healthcare channels based on a specific outreach need.

**URL**: `/channels/search`
**Method**: `POST`

### Request Body
| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `district` | `string` | Target district name (case-insensitive). | `"Hyderabad"` |
| `demographic` | `string` | Environment segment: `Urban`, `Rural`, or `General`. | `"Urban"` |
| `specific_need` | `string` | Free-text description of the outreach need. | `"maternal vaccination outreach for first-time mothers"` |

**Example Request**:
```json
{
  "district": "Hyderabad",
  "demographic": "Urban",
  "specific_need": "maternal vaccination outreach for first-time mothers"
}
```

### Response Body
The response returns a ranked list of up to 4 healthcare entities.

| Field | Type | Description |
| :--- | :--- | :--- |
| `results` | `array` | List of ranked `ChannelResponseItem` objects. |
| `district` | `string` | The district from the request. |
| `demographic` | `string` | The demographic from the request. |

#### ChannelResponseItem Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `entity_id` | `string` | Unique identifier (UUID) of the entity. |
| `name` | `string` | Name/Title of the healthcare channel. |
| `type` | `string` | Environment type (Urban/Rural/General). |
| `content` | `string` | (Optional) The descriptive text content. |
| `semantic_summary` | `string` | (Optional) Summary of the parent section. |
| `rank_position` | `integer` | Rank (1 to 4). |
| `relevance_score` | `float` | AI-assigned score (0.0 to 1.0). |
| `comparative_reasoning` | `string` | Explanation of why this rank was assigned. |

**Example Response**:
```json
{
  "results": [
    {
      "entity_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Community Health Center A",
      "type": "Urban",
      "content": "Focuses on infant immunization...",
      "semantic_summary": "Immunization services...",
      "rank_position": 1,
      "relevance_score": 0.95,
      "comparative_reasoning": "Highest density of first-time mothers in the database."
    }
  ],
  "district": "Hyderabad",
  "demographic": "Urban"
}
```

### Error Codes
- `422 Unprocessable Entity`: Validation error (e.g., missing fields or strings too short).
- `503 Service Unavailable`: LLM or Database service failure.
- `500 Internal Server Error`: Unexpected system error.
