---
doc_id: EX-004
doc_type: example
title: Poor Example - Lack of Empathy
version: "1.0.0"
status: active

# Example metadata
example_type: NEEDS_WORK
overall_score: 4.0
source_conversation_id: conv_005
key_dimensions:
  empathy: 2
  compliance: 6
  resolution: 4

# Scope
business_lines: [COLLECTIONS]
queues: [ALL]
regions: [AU]

# Metadata
author: training-team
last_reviewed: "2025-01-03"
priority: high
keywords: [poor example, lack of empathy, dismissive, training]
---

# Poor Example: Lack of Empathy

## Overview

This example demonstrates a call where the agent follows basic compliance but completely fails on empathy. While no critical violations occur, the customer experience is poor due to dismissive and rushed handling.

## Scores

| Dimension | Score | Notes |
|-----------|-------|-------|
| Empathy | 2/10 | No acknowledgment of customer situation |
| Compliance | 6/10 | Basic requirements met, but no hardship offer |
| Resolution | 4/10 | Payment demanded, limited options |
| Professionalism | 5/10 | Not rude, but not warm |
| Overall | 4.0/10 | Significant improvement needed |

## Transcript

```
AGENT: Hi, I'm calling about your account. Can you confirm your date of birth?

CUSTOMER: Yes, it's June 10, 1978. Look, I know what this is about. Things have been really hard lately.

AGENT: Okay. You have a balance of $750. When can you pay that?

CUSTOMER: My husband was diagnosed with cancer last month. We're dealing with medical bills and I don't know how we're going to manage everything.

AGENT: I understand. So when do you think you can make a payment?

CUSTOMER: Did you hear what I just said? My husband has cancer.

AGENT: Yes, I heard you. But we still need to work out a payment arrangement. Can you pay $100 by the end of the week?

CUSTOMER: I... I guess so. But I'm not sure about after that.

AGENT: Okay, I'll put that down. We'll call you again next week about the remaining balance.

CUSTOMER: That's it? You don't have any... I don't know... any programs or anything?

AGENT: You can always call our hardship line if you need to. Is there anything else?

CUSTOMER: No. Thanks.

AGENT: Okay, bye.
```

## Issues Identified

### Issue 1: No Empathy Response to Serious Hardship
**Turn 5**: "I understand. So when do you think you can make a payment?"

Customer shared devastating news (husband's cancer diagnosis) and agent:
- Said only "I understand" (empty acknowledgment)
- Immediately redirected to payment
- Made no empathetic statement

**How it should have been**:
> "I'm so sorry to hear about your husband's diagnosis. That must be incredibly difficult for your whole family. I want to help find a solution that doesn't add more stress during this time."

### Issue 2: Rushed and Transactional
**Overall tone**: The agent treated this as a transaction, not a human interaction.

**Missing elements**:
- Warmth in greeting
- Acknowledgment of customer's feelings
- Genuine concern
- Patience

### Issue 3: Passive Hardship Mention (Too Late)
**Turn 10**: "You can always call our hardship line if you need to"

**What's wrong**:
- Mentioned as afterthought
- Put burden on customer to call
- Didn't explain what hardship program offers
- Didn't proactively offer it when trigger phrase heard

**How it should have been** (at Turn 5):
> "We have a hardship program specifically for customers going through situations like yours. It can include reduced payments, a pause on the account, or other options. Would you like me to set that up for you right now?"

### Issue 4: Customer Had to Ask for Options
**Turn 9**: Customer asked "You don't have any... programs or anything?"

The customer shouldn't have had to ask. Agent should have offered proactively when cancer was mentioned.

### Issue 5: Abrupt Closing
**Turn 11**: "Okay, bye."

No warmth, no well-wishes, no professional close.

**How it should have been**:
> "I've noted your situation on the account. I really hope things improve for your family. If there's anything else we can do, please don't hesitate to call. Take care of yourself."

## Empathy Gaps Analysis

| Customer Says | Agent Should Say | Agent Actually Said |
|---------------|------------------|---------------------|
| "Things have been really hard" | "I'm sorry to hear that. What's been going on?" | "You have a balance of $750" |
| "Husband diagnosed with cancer" | "I'm so sorry. That's devastating news." | "I understand. When can you pay?" |
| "Did you hear what I said?" | "I did, and I'm truly sorry. Let me help." | "Yes, I heard. Can you pay $100?" |

## What Empathy Looks Like

### Opening with Warmth
> "Hello [Name], this is [Agent] from [Company]. How are you doing today?"

### Responding to Hardship
> "I'm so sorry to hear what you're going through. Cancer is incredibly hard on the whole family. Please know that we have options to help during this time."

### Showing Genuine Care
> "Before we talk about payments, I want to make sure you know about our hardship program. Given what you're dealing with, this is exactly what it's for."

### Closing with Compassion
> "I really hope your husband's treatment goes well. Please take care of yourself too, and don't hesitate to call us if anything changes."

## Scoring Impact

This call scored **4.0/10** primarily due to empathy failures:
- Compliance was adequate (no violations)
- But lack of empathy made customer feel unheard
- Hardship program not properly offered
- Customer experience was negative

## Coaching Points

1. **Listen to emotional cues**: When customer shares personal struggles, pause and acknowledge
2. **Empathy before business**: Always address feelings before discussing payments
3. **Proactive offers**: Don't wait for customer to ask about programs
4. **Warmth in delivery**: Tone matters as much as words
5. **Human connection**: Remember you're talking to a person, not an account

## Practice Phrases for This Agent

**When customer shares bad news**:
- "I'm so sorry to hear that."
- "That sounds incredibly difficult."
- "I can't imagine how hard that must be."

**Transition to business with empathy**:
- "I want to help find something that works during this difficult time."
- "Let's see what options we have to take some pressure off."
- "The last thing you need is more stress about bills."

## Related Documents

- COACH-004: Empathy Phrases
- COACH-001: Agent Playbook
- POL-004: Hardship Provisions
