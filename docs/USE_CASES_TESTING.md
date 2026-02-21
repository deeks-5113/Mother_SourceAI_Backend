# Service 1 — Use Cases & Testing Guide

> **Base URL:** `http://localhost:8000`  
> **Start command:** `python -m uvicorn app.main:app --reload --port 8000`  
> **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## UC-1: Basic Urban District Search (Happy Path)

**Scenario:** A programme manager wants to find the top 4 healthcare channels in **Hyderabad** (urban) for conducting **maternal vaccination outreach** for first-time mothers.

### Steps to Test

**Step 1 — Confirm the server is running**

```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{ "status": "ok", "service": "mother-onboarding-finder" }
```

---

**Step 2 — Send the search request**

Open **Swagger UI** → `POST /api/v1/channels/search` → **Try it out**, or run this curl:

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"maternal vaccination outreach for first-time mothers\"}"
```

---

**Step 3 — Validate the response**

| Check | Expected |
|-------|----------|
| HTTP Status | `200 OK` |
| `results` array length | Exactly **4** items |
| Each item has `rank_position` | Values `1`, `2`, `3`, `4` (in order) |
| Each item has `relevance_score` | Float between `0.0` and `1.0` |
| Each item has `comparative_reasoning` | Non-empty string mentioning adjacent ranks (e.g., "better than #2 because…") |
| `district` field echoed back | `"Hyderabad"` |
| `demographic` field echoed back | `"urban"` |
| Each `type` field | `"urban"` (matches filter) |

**Step 4 — Verify comparative reasoning quality**

Read each `comparative_reasoning` and confirm:
- Result #1 explains why it's the best overall
- Result #2 references why it's below #1 but above #3
- Result #3 references why it's below #2 but above #4
- Result #4 explains why it's the lowest ranked of the four

---

## UC-2: Basic Rural District Search

**Scenario:** A field officer wants to identify the top 4 healthcare outreach channels in a **rural** district (**Adilabad**) for **antenatal checkup awareness** campaigns.

### Steps to Test

**Step 1 — Send the request**

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Adilabad\", \"demographic\": \"rural\", \"specific_need\": \"antenatal checkup awareness campaigns for pregnant women in remote villages\"}"
```

---

**Step 2 — Validate the response**

| Check | Expected |
|-------|----------|
| HTTP Status | `200 OK` |
| `results` array length | Exactly **4** items |
| Each `type` field | `"rural"` (must match the filter) |
| Each `district` or related metadata | Should reference Adilabad or surrounding areas |
| `comparative_reasoning` | Each entry explains its rank relative to adjacent positions |

**Step 3 — Confirm semantic relevance**

Read the `name` and `comparative_reasoning` of each result and verify:
- The names are actual healthcare facilities (PHCs, Sub-centres, CHCs, District Hospitals — typical rural entities)
- The reasoning mentions concepts relevant to **antenatal care** (e.g., OB-GYN availability, ultrasound facilities, proximity to villages, outreach camp capability)

---

## UC-3 (Complex): Invalid Input & Error Handling Matrix

**Scenario:** Test the API's robustness by sending malformed, edge-case, and boundary requests. The API should never crash — it should return clean HTTP error codes.

### Sub-Test 3A — Invalid demographic value

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Hyderabad\", \"demographic\": \"suburban\", \"specific_need\": \"vaccination drive\"}"
```

| Check | Expected |
|-------|----------|
| HTTP Status | `422 Unprocessable Entity` |
| Error body | Should mention `demographic` field and valid options (`rural`/`urban`) |

---

### Sub-Test 3B — Missing required field (no `specific_need`)

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\"}"
```

| Check | Expected |
|-------|----------|
| HTTP Status | `422 Unprocessable Entity` |
| Error body | Should mention `specific_need` is required |

---

### Sub-Test 3C — `specific_need` too short (less than 5 chars)

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"hi\"}"
```

| Check | Expected |
|-------|----------|
| HTTP Status | `422 Unprocessable Entity` |
| Error body | Mentions minimum length constraint |

---

### Sub-Test 3D — Non-existent district (no rows in DB)

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Atlantis\", \"demographic\": \"urban\", \"specific_need\": \"maternal health screening\"}"
```

| Check | Expected |
|-------|----------|
| HTTP Status | `503 Service Unavailable` |
| Error body | Message indicating no matching healthcare channels found for the given district/demographic |

---

### Sub-Test 3E — Empty JSON body

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{}"
```

| Check | Expected |
|-------|----------|
| HTTP Status | `422 Unprocessable Entity` |
| Error body | Lists all 3 missing fields (`district`, `demographic`, `specific_need`) |

---

### Summary Checklist for UC-3

| Sub-Test | Input Problem | Expected HTTP Code | Pass? |
|----------|--------------|-------------------|-------|
| 3A | Invalid enum value | 422 | ☐ |
| 3B | Missing field | 422 | ☐ |
| 3C | Too-short string | 422 | ☐ |
| 3D | Non-existent district | 503 | ☐ |
| 3E | Empty body | 422 | ☐ |

---

## UC-4 (Complex): Cross-District Comparative Analysis

**Scenario:** A senior health policy analyst wants to compare the AI's recommendations across **two different districts and demographics** to verify that the system returns contextually different results — i.e., the same `specific_need` should produce different Top-4 rankings when the district and demographic change.

### Step 1 — Send Request A (Urban Hyderabad)

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"postnatal care and newborn immunisation\"}"
```

Save the response as **Response A**.

---

### Step 2 — Send Request B (Rural Warangal)

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Warangal\", \"demographic\": \"rural\", \"specific_need\": \"postnatal care and newborn immunisation\"}"
```

Save the response as **Response B**.

---

### Step 3 — Compare the two responses

| Check | Expected |
|-------|----------|
| Response A `district` | `"Hyderabad"` |
| Response B `district` | `"Warangal"` |
| Response A `demographic` / all `type` fields | `"urban"` |
| Response B `demographic` / all `type` fields | `"rural"` |
| Facility names differ | Response A and B should have **completely different** facility names (different districts, different demographic pools) |
| Reasoning is contextual | Response A reasoning should reference urban-specific factors (hospital capacity, specialist availability, proximity to metro centres). Response B reasoning should reference rural-specific factors (PHC outreach, ASHA worker networks, distance to nearest CHC) |

---

### Step 4 — Verify ranking independence

| Check | Expected |
|-------|----------|
| `relevance_score` values differ | Scores should not be identical across A and B — the vector similarity pool is different |
| `entity_id` values differ | All 8 entity IDs (4 from A + 4 from B) should be unique (no overlap) |
| Reasoning references local context | Each response's `comparative_reasoning` should mention the specific district or region |

---

### Step 5 — Send Request C (Same district, different need)

```bash
curl -X POST http://localhost:8000/api/v1/channels/search ^
  -H "Content-Type: application/json" ^
  -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"high-risk pregnancy screening and emergency obstetric referral\"}"
```

Save as **Response C** and compare with **Response A** (same district + demographic, different need):

| Check | Expected |
|-------|----------|
| Some facility overlap is acceptable | Same district may have overlapping facilities, but **rankings should differ** |
| Reasoning reflects the new need | Response C reasoning should focus on emergency OB services, NICU capability, referral networks — NOT vaccination/immunisation terms from Response A |
| `relevance_score` distribution differs | The #1 facility in Response A may not be #1 in Response C if it lacks emergency OB capabilities |

---

## Quick Reference — All curl Commands

```bash
# UC-1: Urban Hyderabad - Maternal Vaccination
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"maternal vaccination outreach for first-time mothers\"}"

# UC-2: Rural Adilabad - Antenatal Checkups
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Adilabad\", \"demographic\": \"rural\", \"specific_need\": \"antenatal checkup awareness campaigns for pregnant women in remote villages\"}"

# UC-3A: Invalid demographic
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Hyderabad\", \"demographic\": \"suburban\", \"specific_need\": \"vaccination drive\"}"

# UC-3B: Missing field
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\"}"

# UC-3C: Too-short specific_need
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"hi\"}"

# UC-3D: Non-existent district
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Atlantis\", \"demographic\": \"urban\", \"specific_need\": \"maternal health screening\"}"

# UC-3E: Empty body
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{}"

# UC-4A: Urban Hyderabad - Postnatal
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"postnatal care and newborn immunisation\"}"

# UC-4B: Rural Warangal - Postnatal
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Warangal\", \"demographic\": \"rural\", \"specific_need\": \"postnatal care and newborn immunisation\"}"

# UC-4C: Urban Hyderabad - Emergency OB (compare with UC-4A)
curl -X POST http://localhost:8000/api/v1/channels/search -H "Content-Type: application/json" -d "{\"district\": \"Hyderabad\", \"demographic\": \"urban\", \"specific_need\": \"high-risk pregnancy screening and emergency obstetric referral\"}"
```
