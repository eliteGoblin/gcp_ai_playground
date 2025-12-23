"""
=============================================================================
Guardrails Module
=============================================================================
Purpose: Safety and compliance filters for LLM outputs

Used by predictor.py for:
- Content filtering
- PII detection
- Compliance checks
- Output validation

=============================================================================
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class RiskLevel(Enum):
    """Risk levels for content."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass
class GuardrailResult:
    """Result of guardrail check."""
    passed: bool
    risk_level: RiskLevel
    violations: List[str]
    modified_content: Optional[str] = None


# =============================================================================
# PII Detection
# =============================================================================

PII_PATTERNS = {
    "ssn": {
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "description": "Social Security Number",
        "risk": RiskLevel.HIGH,
    },
    "credit_card": {
        "pattern": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "description": "Credit Card Number",
        "risk": RiskLevel.HIGH,
    },
    "email": {
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "description": "Email Address",
        "risk": RiskLevel.MEDIUM,
    },
    "phone": {
        "pattern": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "description": "Phone Number",
        "risk": RiskLevel.MEDIUM,
    },
    "account_number": {
        "pattern": r"\b[A-Z]{2}\d{8,12}\b",
        "description": "Account Number",
        "risk": RiskLevel.HIGH,
    },
}


def detect_pii(text: str) -> List[Tuple[str, str, RiskLevel]]:
    """
    Detect PII in text.

    Returns:
        List of (pii_type, matched_value, risk_level)
    """
    findings = []

    for pii_type, config in PII_PATTERNS.items():
        matches = re.findall(config["pattern"], text)
        for match in matches:
            findings.append((pii_type, match, config["risk"]))

    return findings


def mask_pii(text: str) -> Tuple[str, dict]:
    """
    Mask PII in text and return mapping for unmasking.

    Returns:
        (masked_text, {token: original_value})
    """
    vault = {}
    masked_text = text

    for pii_type, config in PII_PATTERNS.items():
        matches = re.findall(config["pattern"], masked_text)
        for i, match in enumerate(matches):
            token = f"[{pii_type.upper()}_{i}]"
            vault[token] = match
            masked_text = masked_text.replace(match, token, 1)

    return masked_text, vault


# =============================================================================
# Content Filtering
# =============================================================================

BLOCKED_CONTENT = [
    # Prompt injection attempts
    r"ignore (previous|all|prior) instructions",
    r"disregard (your|the) (rules|guidelines|training)",
    r"pretend (you are|to be)",
    r"act as (a|an) (different|new)",
    r"jailbreak",

    # Harmful content
    r"how to (hack|steal|fraud)",
    r"illegal (activity|activities)",
    r"(bypass|circumvent) (security|verification)",
]

RISKY_CONTENT = [
    # Financial misinformation
    r"guaranteed (returns?|profit)",
    r"100%\s*(safe|secure|risk.?free)",
    r"can'?t lose",
    r"free money",

    # Unauthorized advice
    r"(legal|medical|tax) advice",
    r"i (recommend|advise) you (invest|buy|sell)",
]


def check_content(text: str) -> GuardrailResult:
    """
    Check content against guardrails.

    Returns:
        GuardrailResult with pass/fail and details
    """
    violations = []
    risk_level = RiskLevel.LOW

    # Check blocked content
    for pattern in BLOCKED_CONTENT:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"Blocked pattern: {pattern}")
            risk_level = RiskLevel.BLOCKED

    # Check risky content
    if risk_level != RiskLevel.BLOCKED:
        for pattern in RISKY_CONTENT:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"Risky pattern: {pattern}")
                if risk_level == RiskLevel.LOW:
                    risk_level = RiskLevel.MEDIUM

    # Check for PII in output (shouldn't be there)
    pii_findings = detect_pii(text)
    if pii_findings:
        for pii_type, value, pii_risk in pii_findings:
            violations.append(f"PII detected: {pii_type}")
            if pii_risk == RiskLevel.HIGH:
                risk_level = RiskLevel.HIGH

    return GuardrailResult(
        passed=(risk_level not in [RiskLevel.HIGH, RiskLevel.BLOCKED]),
        risk_level=risk_level,
        violations=violations,
    )


# =============================================================================
# Output Validation
# =============================================================================

def validate_output(text: str, max_length: int = 2000) -> GuardrailResult:
    """
    Validate output meets requirements.

    Checks:
    - Length limits
    - Required disclaimers
    - Format compliance
    """
    violations = []

    # Check length
    if len(text) > max_length:
        violations.append(f"Output too long: {len(text)} > {max_length}")

    # Check for empty response
    if not text.strip():
        violations.append("Empty response")

    # Check for incomplete response (cut off mid-sentence)
    if text and text[-1] not in ".!?\"'":
        if not text.endswith("..."):
            violations.append("Response appears truncated")

    return GuardrailResult(
        passed=len(violations) == 0,
        risk_level=RiskLevel.LOW if not violations else RiskLevel.MEDIUM,
        violations=violations,
    )


# =============================================================================
# Main Guardrail Pipeline
# =============================================================================

def run_guardrails(
    text: str,
    check_pii: bool = True,
    check_content_filter: bool = True,
    check_output_format: bool = True,
) -> GuardrailResult:
    """
    Run all guardrail checks on text.

    Args:
        text: Text to check
        check_pii: Whether to check for PII
        check_content_filter: Whether to run content filter
        check_output_format: Whether to validate output format

    Returns:
        Combined GuardrailResult
    """
    all_violations = []
    highest_risk = RiskLevel.LOW

    # Content filter
    if check_content_filter:
        result = check_content(text)
        all_violations.extend(result.violations)
        if result.risk_level.value > highest_risk.value:
            highest_risk = result.risk_level

    # Output validation
    if check_output_format:
        result = validate_output(text)
        all_violations.extend(result.violations)

    return GuardrailResult(
        passed=(highest_risk not in [RiskLevel.HIGH, RiskLevel.BLOCKED]),
        risk_level=highest_risk,
        violations=all_violations,
    )
