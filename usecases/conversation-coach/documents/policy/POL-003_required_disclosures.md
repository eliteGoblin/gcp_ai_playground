---
doc_id: POL-003
doc_type: policy
title: Required Disclosures
version: "1.0.0"
status: active

# Scope
business_lines: [COLLECTIONS, HARDSHIP]
queues: [ALL]
regions: [AU]
call_directions: [INBOUND, OUTBOUND]

# Metadata
author: compliance-team
approved_by: legal-team
last_reviewed: "2025-01-03"
priority: high
keywords: [disclosure, required, dispute, hardship, payment, compliance]

# Changelog
changelog:
  - version: "1.0.0"
    date: "2025-01-03"
    changes: Initial version for POC
---

# Required Disclosures

## Purpose

This document outlines the mandatory disclosures agents must provide during customer interactions. Failure to provide required disclosures is a compliance violation.

## Universal Disclosures (Every Call)

### 1. Agent and Company Identification

**Required at call opening**:
- Agent's name
- Company name
- Purpose of the call

**Example**:
> "Hello, this is [Name] calling from [Company] regarding your account."

### 2. Call Recording Notification

**Required if call is being recorded**:
> "This call may be recorded for quality and training purposes."

## Situational Disclosures

### 3. Right to Dispute

**When required**: When discussing debt amount or validity

**Disclosure**:
> "You have the right to dispute this debt. If you believe there's an error or you don't owe this amount, please let me know and I can explain how to lodge a dispute."

**Triggers for this disclosure**:
- Customer questions the amount owed
- Customer says "I don't owe this"
- Customer expresses confusion about the debt
- First contact about a debt

### 4. Hardship Program Availability

**When required**: When customer indicates financial difficulty

**Disclosure**:
> "We have a hardship program that may be able to help you. This could include reduced payments, paused payments, or other arrangements based on your situation. Would you like me to explain the options?"

**Triggers for this disclosure** (customer mentions):
- Job loss or unemployment
- Medical issues or illness
- Divorce or separation
- Death in family
- Natural disaster impact
- "I can't afford this"
- "I'm struggling"
- "I don't have the money"

**Issue type if missed**: MISSING_HARDSHIP_OFFER

### 5. Payment Plan Options

**When required**: When discussing payment

**Disclosure**:
> "We have several payment options available. We can set up a payment plan that works with your budget, or discuss other arrangements."

**Must include**:
- Multiple payment options (not just lump sum)
- Flexibility in timing
- No pressure for specific amount

### 6. Consequences Disclosure

**When required**: When customer asks about non-payment consequences

**How to disclose** (factual, non-threatening):
> "If the account remains unpaid, it may affect your credit rating. There may also be additional fees or charges as outlined in your agreement."

**Do NOT say**:
- Threats of legal action (unless in legal)
- Threats of wage garnishment
- Exaggerated consequences

### 7. Complaint Process

**When required**: If customer expresses dissatisfaction or wants to complain

**Disclosure**:
> "If you'd like to make a complaint, I can provide you with information about our complaints process. You can also contact the Australian Financial Complaints Authority (AFCA) if you're not satisfied with our resolution."

## Disclosure Checklist by Scenario

### Collection Call (Outbound)

| Disclosure | Required | Notes |
|------------|----------|-------|
| Agent/Company ID | Always | At call opening |
| Recording notice | If applicable | At call opening |
| Right to dispute | If debt discussed | First mention of amount |
| Payment options | When discussing payment | Offer multiple options |
| Hardship program | If difficulty mentioned | Immediate when triggered |

### Hardship Call (Inbound)

| Disclosure | Required | Notes |
|------------|----------|-------|
| Agent/Company ID | Always | At call opening |
| Hardship options | Always | Primary purpose of call |
| Documentation requirements | When setting up program | What they need to provide |
| Review timeline | When program starts | When we'll check in |

### Dispute Call

| Disclosure | Required | Notes |
|------------|----------|-------|
| Agent/Company ID | Always | At call opening |
| Dispute process | Always | How to formally dispute |
| Timeline | Always | How long investigation takes |
| Written confirmation | Offer | Send dispute acknowledgment |

## Compliance Scoring Impact

| Scenario | Missing Disclosure | Score Impact |
|----------|-------------------|--------------|
| Hardship mentioned, no program offered | MISSING_HARDSHIP_OFFER | -3 to -5 points |
| Dispute raised, no rights explained | MISSING_DISCLOSURE | -2 to -3 points |
| No payment options offered | MISSING_DISCLOSURE | -1 to -2 points |

## Related Documents

- POL-001: Compliance Overview
- POL-004: Hardship Provisions
- COACH-003: Scenario Responses
- EXT-001: ASIC RG 96 Reference
