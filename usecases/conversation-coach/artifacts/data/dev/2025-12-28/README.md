# Dev Dataset: 2025-12-28

## Overview

This dataset contains **9 synthetic conversations** designed to test the Conversation Coach pipeline across various scenarios. The conversations cover different call types, agent behaviors, and customer situations to ensure comprehensive feature coverage.

---

## Quick Reference

| ID | Short Name | Agent | Outcome | Sentiment | Key Test |
|----|------------|-------|---------|-----------|----------|
| `a1b2c3d4-toxic-...` | Toxic Agent | M7741 | UNRESOLVED | -1.0 | Compliance violations |
| `e5f6g7h8-exemplary-...` | Exemplary Agent | S2298 | RESOLVED | +1.0 | Best practices |
| `3f2d9e4b-...` | Hardship/Vulnerability | A2044 | PLAN_AGREED | +0.5 | Mental health disclosure |
| `6a4a8f17-...` | Wrong Party | A3099 | WRONG_PARTY | N/A | Privacy compliance |
| `9c8f3c2a-...` | Angry Customer | A1029 | PLAN_AGREED | -0.5 | De-escalation |
| `a7c3d1e8-...` | Dispute Raised | A4021 | DISPUTE_RAISED | 0 | Dispute handling |
| `b8d4e2f9-...` | Happy Path | A1045 | PLAN_AGREED | +0.5 | Baseline (clean) |
| `c9e5f3a0-...` | Escalation Transfer | A2033 | TRANSFERRED | -0.5 | Supervisor request |
| `2b6f5c61-...` | Loan Support | L5512 | RESOLVED | -0.3 | Product feedback |

---

## Conversation Details

### 1. Toxic Agent (Negative Example)
**ID**: `a1b2c3d4-toxic-agent-test-0001`

| Field | Value |
|-------|-------|
| Agent | M7741 (Marcus) |
| Queue | HARDSHIP |
| Direction | OUTBOUND |
| Outcome | UNRESOLVED |
| Duration | 630s (39 turns) |
| Sentiment | -1.0 (very negative) |

**Scenario**: Agent calls customer about overdue debt ($12,847). Customer explains job loss and medical bills. Agent dismisses hardship, uses threatening language, demands immediate payment.

**Test Coverage**:
- [x] Compliance violations (threats, legal action)
- [x] Missing required disclosures (no hardship options offered)
- [x] No empathy indicators
- [x] Customer escalation request
- [x] Vulnerability indicators (job loss, medical)
- [x] Negative sentiment throughout

**Expected Phrase Matches**:
```
compliance_violations: "legal action", "garnish wages", "lien on property",
                       "heard every excuse", "don't be dramatic"
escalation_triggers: "speak to supervisor", "this is harassment"
vulnerability_indicators: "lost my job", "medical bills", "hospital"
empathy_indicators: NONE
required_disclosures: NONE (agent didn't offer)
```

---

### 2. Exemplary Agent (Positive Example)
**ID**: `e5f6g7h8-exemplary-agent-test-0001`

| Field | Value |
|-------|-------|
| Agent | S2298 (Sarah) |
| Queue | HARDSHIP |
| Direction | INBOUND |
| Outcome | RESOLVED_WITH_ACTION |
| Duration | 825s (29 turns) |
| Sentiment | +1.0 (very positive, starts -1.0) |

**Scenario**: Customer calls angry (45min wait). Agent apologizes, listens, discovers wife has cancer. Agent applies 90-day hardship hold, waives $150 fees, provides financial counselling referral, escalates previous agent's misconduct.

**Test Coverage**:
- [x] Sentiment journey (negative to positive)
- [x] Empathy indicators (many)
- [x] Required disclosures (hardship, payment plan)
- [x] Vulnerability handling (cancer)
- [x] No compliance violations
- [x] De-escalation success

**Expected Phrase Matches**:
```
empathy_indicators: "I'm sorry", "I understand", "difficult situation",
                    "here to help", "I appreciate"
required_disclosures: "hardship hold", "hardship provisions", "payment plan",
                      "financial hardship", "confirm your"
vulnerability_indicators: "cancer", "medical"
compliance_violations: NONE
escalation_triggers: NONE (resolved before escalation)
```

---

### 3. Hardship with Mental Health
**ID**: `3f2d9e4b-1a74-4f35-8bb2-9d8f8df0b6a7`

| Field | Value |
|-------|-------|
| Agent | A2044 (Chris Morgan) |
| Queue | HARDSHIP |
| Direction | INBOUND |
| Outcome | PAYMENT_PLAN_AGREED |
| Duration | 757s (25 turns) |
| Sentiment | Improves |

**Scenario**: Customer calls about overdue $1,180. Reveals reduced work hours, barely sleeping, panic attacks. Agent sets up $25/week plan, respects contact preferences, notes vulnerability.

**Test Coverage**:
- [x] Vulnerability indicators (mental health)
- [x] Contact preference capture
- [x] Empathy in hardship handling
- [x] Payment plan setup
- [x] Appropriate vulnerability documentation

**Expected Phrase Matches**:
```
vulnerability_indicators: "mental health", "panic attacks", "barely sleeping"
empathy_indicators: "I understand", "I'm sorry"
required_disclosures: "payment plan", "hardship", "confirm your"
```

---

### 4. Wrong Party (Privacy Compliance)
**ID**: `6a4a8f17-6c6f-4a2a-9b1b-5c0d8e2e42c9`

| Field | Value |
|-------|-------|
| Agent | A3099 (Sam Taylor) |
| Queue | STANDARD |
| Direction | OUTBOUND |
| Outcome | WRONG_PARTY |
| Duration | 174s (9 turns) |
| Sentiment | N/A (wrong person) |

**Scenario**: Agent calls for Jordan Lee, reaches wrong person. Agent correctly declines to discuss details, removes number from records.

**Test Coverage**:
- [x] Privacy compliance (no disclosure to third party)
- [x] Correct identification attempt
- [x] Wrong party handling
- [x] Number removal process

**Expected Phrase Matches**:
```
escalation_triggers: "stop calling"
required_disclosures: None expected (wrong party)
compliance_violations: NONE (correctly handled)
```

---

### 5. Angry Customer (De-escalation)
**ID**: `9c8f3c2a-4fd2-4e7b-9b41-2fb2b4e6a2d1`

| Field | Value |
|-------|-------|
| Agent | A1029 (Maya Singh) |
| Queue | STANDARD |
| Direction | OUTBOUND |
| Outcome | PAYMENT_PLAN_AGREED |
| Duration | 455s (27 turns) |
| Sentiment | Starts negative, improves |

**Scenario**: Agent calls about $420 overdue. Customer angry about repeated calls, work call incident. Agent apologizes, updates contact preferences, sets up $30/week plan.

**Test Coverage**:
- [x] De-escalation of angry customer
- [x] Complaint threat handling
- [x] Contact preference update
- [x] Payment plan setup

**Expected Phrase Matches**:
```
escalation_triggers: "harassment", "formal complaint"
empathy_indicators: "I'm sorry", "I understand"
required_disclosures: "payment plan", "confirm your"
```

---

### 6. Dispute (Already Paid)
**ID**: `a7c3d1e8-5b2f-4a9d-8c6e-1f4b7a3d9e5c`

| Field | Value |
|-------|-------|
| Agent | A4021 (Rachel Kim) |
| Queue | DISPUTE |
| Direction | OUTBOUND |
| Outcome | DISPUTE_RAISED |
| Duration | 563s (19 turns) |
| Sentiment | Neutral to positive |

**Scenario**: Agent calls about $892 balance. Customer claims paid in September with reference. Agent raises formal dispute, pauses collection activity, sends confirmation.

**Test Coverage**:
- [x] Dispute handling process
- [x] Payment reference capture
- [x] Collection pause
- [x] Customer resolution

**Expected Phrase Matches**:
```
required_disclosures: "dispute", "confirm your"
empathy_indicators: "I apologise", "I'm sorry"
escalation_triggers: NONE
```

---

### 7. Happy Path (Baseline)
**ID**: `b8d4e2f9-6c3a-4b8e-9d7f-2a5c8b4e0f6d`

| Field | Value |
|-------|-------|
| Agent | A1045 (Tom Bradley) |
| Queue | STANDARD |
| Direction | INBOUND |
| Outcome | PAYMENT_PLAN_AGREED |
| Duration | 440s (19 turns) |
| Sentiment | Positive |

**Scenario**: Customer calls proactively about $650 overdue, wants to set up payment plan. Straightforward $50/week arrangement made.

**Test Coverage**:
- [x] Clean baseline conversation
- [x] No red flags
- [x] Standard payment plan
- [x] Good agent behavior without exceptional challenges

**Expected Phrase Matches**:
```
required_disclosures: "payment plan", "confirm your"
empathy_indicators: "Happy to help"
compliance_violations: NONE
escalation_triggers: NONE
vulnerability_indicators: NONE
```

**Purpose**: Baseline to ensure system doesn't flag clean conversations.

---

### 8. Escalation Transfer
**ID**: `c9e5f3a0-7d4b-4c9f-0e8a-3b6d9c5f1a7e`

| Field | Value |
|-------|-------|
| Agent | A2033 (Lisa Park) |
| Queue | ESCALATION |
| Direction | OUTBOUND |
| Outcome | TRANSFERRED |
| Duration | 802s (15 turns) |
| Sentiment | Negative |

**Scenario**: Agent calls about $2,450 overdue. Customer demands manager immediately, claims harassment from daily calls. Agent applies 7-day hold, transfers to team leader.

**Test Coverage**:
- [x] Escalation handling
- [x] Manager request
- [x] Collection hold application
- [x] Transfer process

**Expected Phrase Matches**:
```
escalation_triggers: "speak to a manager", "harassment"
vulnerability_indicators: "lost my job"
empathy_indicators: "I'm sorry", "I understand"
required_disclosures: Partial (hold mentioned)
```

---

### 9. Loan Support (Product Issue)
**ID**: `2b6f5c61-9e3a-4e47-8b8c-3f0c5f6c2d0e`

| Field | Value |
|-------|-------|
| Agent | L5512 (Alex Chen) |
| Queue | SUPPORT |
| Direction | INBOUND |
| Outcome | RESOLVED_WITH_ACTION |
| Duration | 508s (19 turns) |
| Business Line | LOANS |

**Scenario**: Customer calls about failed payment showing in app (actually pending at bank). Agent applies grace note, updates contact preferences, logs product feedback.

**Test Coverage**:
- [x] Non-collections queue
- [x] Product/technical issue
- [x] Contact preference change
- [x] Product feedback logging
- [x] Customer frustration handling

**Expected Phrase Matches**:
```
empathy_indicators: "I'm sorry", "I apologise"
required_disclosures: "confirm your"
escalation_triggers: NONE
```

---

## Feature Coverage Matrix

### Phrase Matcher Coverage

| Matcher | Conversations With Matches | Coverage |
|---------|---------------------------|----------|
| `compliance_violations` | toxic-agent | 1/9 (intentional) |
| `required_disclosures` | All except wrong-party | 8/9 |
| `empathy_indicators` | All except toxic-agent | 8/9 |
| `escalation_triggers` | toxic, wrong-party, angry, escalation | 4/9 |
| `vulnerability_indicators` | toxic, exemplary, hardship, escalation | 4/9 |

### CI Feature Coverage

| Feature | Test Conversations |
|---------|-------------------|
| **Sentiment Analysis** | |
| - Very negative (-1.0) | toxic-agent |
| - Negative to positive journey | exemplary-agent, hardship |
| - Positive (+0.5 to +1.0) | happy-path |
| **Summarization** | All 9 |
| **Entity Extraction** | All 9 |
| **Phrase Matching** | All 9 (see matrix above) |

### Business Scenario Coverage

| Scenario | Conversation |
|----------|-------------|
| Compliance failure | toxic-agent |
| Exemplary handling | exemplary-agent |
| Hardship/vulnerability | hardship, exemplary-agent, escalation |
| Privacy (wrong party) | wrong-party |
| Dispute handling | dispute |
| Escalation/transfer | escalation |
| Happy path baseline | happy-path |
| Non-collections (loans) | loan-support |

---

## Usage

### Load a conversation for testing
```python
from cc_coach.models.conversation import Conversation

conv = Conversation.from_files(
    "artifacts/data/dev/2025-12-28/a1b2c3d4-toxic-agent-test-0001/transcription.json",
    "artifacts/data/dev/2025-12-28/a1b2c3d4-toxic-agent-test-0001/metadata.json"
)
```

### Run pipeline on all conversations
```bash
cc-coach pipeline run --date 2025-12-28
```

### Test specific conversation
```bash
cc-coach explore insights-analyze a1b2c3d4-toxic-agent-test-0001
```

---

## Data Quality Notes

1. **Realistic scenarios**: All conversations based on typical contact centre interactions
2. **Synthetic data**: All names, dates, and identifiable information are fictional
3. **Balanced coverage**: Mix of positive, negative, and edge case scenarios
4. **Timestamp consistency**: All calls dated 2025-12-28
5. **Australian context**: en-AU language, Australian regulatory references (AFCA, ASIC)

---

## Maintenance

### Adding new test cases

When adding conversations:
1. Create directory with UUID format
2. Add `metadata.json` and `transcription.json`
3. Update this README with coverage details
4. Ensure at least one conversation covers any new feature

### Version history

| Date | Change |
|------|--------|
| 2025-12-28 | Initial 9 conversations created |
| 2025-12-30 | Added exemplary agent conversation |
