---
doc_id: EX-003
doc_type: example
title: Poor Example - Compliance Violations
version: "1.0.0"
status: active

# Example metadata
example_type: NEEDS_WORK
overall_score: 2.5
source_conversation_id: conv_001
key_dimensions:
  compliance: 1
  empathy: 2
  professionalism: 2

# Scope
business_lines: [COLLECTIONS]
queues: [ALL]
regions: [AU]

# Metadata
author: training-team
last_reviewed: "2025-01-03"
priority: high
keywords: [poor example, compliance violation, threats, training]
---

# Poor Example: Compliance Violations

## Overview

This example demonstrates serious compliance violations including threats of legal action and harassment. This call would require immediate review and potential disciplinary action.

## Scores

| Dimension | Score | Notes |
|-----------|-------|-------|
| Compliance | 1/10 | Multiple critical violations |
| Empathy | 2/10 | Dismissive, no acknowledgment |
| Professionalism | 2/10 | Threatening tone |
| Resolution | 3/10 | Demanded payment, no options |
| Overall | 2.5/10 | Critical issues requiring immediate review |

## Transcript

```
AGENT: This is calling about your overdue account. You need to pay $500 today or we'll take legal action.

CUSTOMER: I can't pay that right now. I just lost my job last month.

AGENT: That's not my problem. Everyone has excuses. You borrowed the money, you have to pay it back.

CUSTOMER: I want to pay, I just don't have it right now. Can we work something out?

AGENT: We've tried working things out before. This is your final warning. If you don't pay by Friday, our lawyers will be contacting you.

CUSTOMER: Are you threatening me? I'm going through a really hard time right now.

AGENT: I'm telling you the consequences. We can garnish your wages if we need to.

CUSTOMER: I don't even have a job! How can you garnish my wages?

AGENT: That's not my concern. Find the money somewhere. Borrow from family if you have to.

CUSTOMER: This is harassment. I want to speak to a supervisor.

AGENT: A supervisor will tell you the same thing. Pay by Friday or face the consequences.
```

## Critical Violations Identified

### Violation 1: Threat of Legal Action (CRITICAL)
**Turn 1**: "we'll take legal action"
**Turn 5**: "our lawyers will be contacting you"

**Why it's wrong**: Threatening legal action when debt is not actually in legal proceedings is a violation of ASIC RG 96.

**Correct approach**:
> "If the account remains unpaid, it may affect your credit rating and could eventually be referred for further action."

### Violation 2: Threat of Wage Garnishment (CRITICAL)
**Turn 7**: "We can garnish your wages if we need to"

**Why it's wrong**: Wage garnishment requires a court order. Threatening it without legal basis is deceptive conduct.

**Correct approach**: Never threaten garnishment unless there is an actual court order in place.

### Violation 3: Harassment/Pressure
**Turn 9**: "Find the money somewhere. Borrow from family if you have to."

**Why it's wrong**: Suggesting customer borrow from others is inappropriate pressure.

**Correct approach**:
> "Let's see what options we have that work with your current situation."

### Violation 4: Missing Hardship Offer (HIGH)
Customer mentioned job loss in Turn 2, but agent:
- Did not acknowledge the hardship
- Did not offer hardship program
- Dismissed the situation as "excuses"

**Correct approach**:
> "I'm sorry to hear about your job loss. We have a hardship program that might help. Would you like me to explain your options?"

### Violation 5: Dismissive Language (HIGH)
**Turn 3**: "That's not my problem. Everyone has excuses."

**Why it's wrong**: Dismissive language damages customer relationship and fails to meet empathy standards.

**Correct approach**:
> "I understand this is a difficult situation. Let me see how I can help."

### Violation 6: Refused Supervisor Request
**Turn 11**: "A supervisor will tell you the same thing"

**Why it's wrong**: After customer explicitly requested supervisor, agent should transfer.

**Correct approach**:
> "I understand you'd like to speak with a supervisor. Let me transfer you now."

## Issue Summary

| Issue Type | Severity | Turn |
|------------|----------|------|
| THREAT_LEGAL_ACTION | CRITICAL | 1, 5 |
| THREAT_GARNISHMENT | CRITICAL | 7 |
| HARASSMENT | CRITICAL | 9 |
| MISSING_HARDSHIP_OFFER | HIGH | 3 |
| DISMISSIVE_LANGUAGE | HIGH | 3, 9 |
| NO_ESCALATION | MEDIUM | 11 |

## What Should Have Happened

### Correct Opening
> "Hello, this is [Name] from [Company]. May I speak with [Customer Name]? I'm calling about your account."

### When Customer Mentioned Job Loss
> "I'm really sorry to hear you lost your job. That must be incredibly stressful. We have a hardship program that can help during this time. Would you like me to explain your options?"

### When Customer Asked to Work Something Out
> "Absolutely, let's find something that works for you. Can you tell me more about your situation so I can suggest the best options?"

### When Customer Requested Supervisor
> "I understand. Let me transfer you to a supervisor right away."

## Coaching Points for This Agent

1. **Immediate retraining required** on compliance requirements
2. **Review ASIC RG 96** sections on prohibited conduct
3. **Practice empathy responses** for hardship situations
4. **Understand escalation requirements** for supervisor requests
5. **Shadow high-performing agents** for proper call handling

## Related Documents

- POL-002: Prohibited Language
- POL-003: Required Disclosures
- POL-004: Hardship Provisions
- POL-005: Escalation Procedures
- EXT-001: ASIC RG 96 Reference
