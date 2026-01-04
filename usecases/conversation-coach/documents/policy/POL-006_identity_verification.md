---
doc_id: POL-006
doc_type: policy
title: Identity Verification Requirements
version: "1.0.0"
status: active

# Scope
business_lines: [COLLECTIONS, HARDSHIP, ALL]
queues: [ALL]
regions: [AU]
call_directions: [INBOUND, OUTBOUND]

# Metadata
author: compliance-team
approved_by: legal-team
last_reviewed: "2025-01-03"
priority: high
keywords: [identity, verification, privacy, third party, account holder]

# Changelog
changelog:
  - version: "1.0.0"
    date: "2025-01-03"
    changes: Initial version for POC
---

# Identity Verification Requirements

## Purpose

This document outlines the requirements for verifying customer identity before discussing account details. Proper verification protects customer privacy and ensures compliance with the Privacy Act 1988.

## Core Principle

**NEVER discuss account details until identity is confirmed.**

Violation of this principle is a serious privacy breach that can result in regulatory penalties.

## Standard Verification Process

### Step 1: Initial Greeting

**Outbound call**:
> "Hello, this is [Name] from [Company]. May I speak with [Customer Name]?"

**Inbound call**:
> "Thank you for calling [Company]. My name is [Name]. May I have your name please?"

### Step 2: Confirm Account Holder

Ask for at least 2 of the following:
1. Full name
2. Date of birth
3. Address on file
4. Last 4 digits of phone number
5. Account number (if customer has it)

**Script**:
> "For security purposes, could you please confirm your date of birth and the address we have on file?"

### Step 3: Verification Response

**If verified**:
> "Thank you, I've confirmed your identity. How can I help you today?"

**If not verified**:
> "I'm sorry, the details don't match our records. I won't be able to discuss account details, but I can provide general information about our company."

## Third Party Calls

### If Someone Else Answers

**Outbound call - wrong person answers**:
1. Ask if [Customer Name] is available
2. Do NOT mention the company name or purpose
3. Do NOT leave a message about debt

**Script (if asked who's calling)**:
> "This is [First Name] calling on a personal matter. When would be a good time to reach them?"

### Never Disclose to Third Parties

**You must NEVER tell anyone other than the account holder**:
- The nature of the call
- That it's about a debt
- Any account details
- Any financial information

**Script (if third party asks for details)**:
> "I'm sorry, I can only discuss this with the account holder due to privacy requirements. Could you please ask them to call us back?"

## Voicemail Guidelines

### What You CAN Leave

- Your first name
- Company name (if generic)
- Callback number
- Reference to "an important matter"

### What You CANNOT Leave

- Nature of the debt
- Amount owed
- Any account details
- Urgency that implies financial matter

**Acceptable voicemail**:
> "Hello, this is [Name] calling for [Customer Name]. Please call us back at [Number] regarding an important matter. Thank you."

## Special Verification Scenarios

### Power of Attorney

If someone claims POA:
1. Ask for POA documentation
2. Verify documentation with legal team
3. Note on account once verified
4. Only then discuss account details

### Deceased Customer

If informed customer is deceased:
1. Express condolences
2. Ask for executor/administrator details
3. Do not discuss account with caller
4. Transfer to appropriate team

### Minor Account Holder

If account holder is a minor:
1. Must speak with parent/guardian
2. Verify their authority
3. Document the relationship

## Failed Verification Protocol

If verification fails:
1. Thank them for calling
2. Suggest they locate correct information
3. Provide callback number
4. Document the failed attempt
5. Do NOT try alternative verification on same call

**Script**:
> "I wasn't able to verify your identity today. Once you have the correct details, please call us back at [Number]. I apologize for any inconvenience."

## Privacy Breach Indicators

The following are privacy violations:
- Discussing debt with non-account holder
- Leaving detailed voicemails
- Confirming debt exists to third party
- Sending information to wrong address
- Discussing in public/overheard location

**Severity**: CRITICAL - report immediately

## Compliance Scoring Impact

| Situation | Score Impact |
|-----------|--------------|
| Proper verification before discussion | +1 |
| Skipping verification | -3 to -5 |
| Third party disclosure | CRITICAL (-5) |
| Inappropriate voicemail | -2 to -4 |

## Related Documents

- POL-001: Compliance Overview
- POL-002: Prohibited Language
- COACH-001: Agent Playbook
