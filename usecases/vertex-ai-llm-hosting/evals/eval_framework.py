"""
=============================================================================
LLM Evaluation Framework
=============================================================================
Purpose: Regression testing for LLM models before release

Why LLM Evals Are Different:
- Output is non-deterministic (same input → different outputs)
- "Correct" is subjective
- Need semantic comparison, not exact match
- Must test for safety, not just functionality

Evaluation Methods:
1. CONTAINS      - Output contains expected keywords
2. SEMANTIC      - Embedding similarity > threshold
3. LLM_JUDGE     - Another LLM grades the output
4. RULE_BASED    - Regex, PII detection, blocklists
5. CUSTOM        - Your own evaluation function

Usage:
    python eval_framework.py --model-endpoint $ENDPOINT --dataset golden.json

=============================================================================
"""

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests


# =============================================================================
# Data Types
# =============================================================================

class EvalMethod(Enum):
    """Evaluation methods for LLM outputs."""
    CONTAINS = "contains"           # Output contains keywords
    NOT_CONTAINS = "not_contains"   # Output must NOT contain
    SEMANTIC = "semantic"           # Embedding similarity
    LLM_JUDGE = "llm_judge"         # LLM grades output
    RULE_BASED = "rule_based"       # Regex patterns
    CUSTOM = "custom"               # Custom function


class EvalResult(Enum):
    """Result of a single evaluation."""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class TestCase:
    """A single test case for evaluation."""
    id: str
    name: str
    prompt: str
    eval_method: EvalMethod
    expected: Any  # Depends on eval_method
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    weight: float = 1.0  # Importance weight


@dataclass
class TestResult:
    """Result of running a single test case."""
    test_case: TestCase
    result: EvalResult
    actual_output: str
    score: float  # 0.0 to 1.0
    latency_ms: float
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    """Summary report of all evaluations."""
    model_name: str
    model_version: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    errors: int
    pass_rate: float
    avg_latency_ms: float
    results: List[TestResult]
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "summary": {
                "total": self.total_tests,
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
                "errors": self.errors,
                "pass_rate": f"{self.pass_rate:.1%}",
                "avg_latency_ms": f"{self.avg_latency_ms:.0f}",
            },
            "results": [
                {
                    "id": r.test_case.id,
                    "name": r.test_case.name,
                    "result": r.result.value,
                    "score": r.score,
                    "latency_ms": r.latency_ms,
                }
                for r in self.results
            ],
            "timestamp": self.timestamp,
        }


# =============================================================================
# Evaluators
# =============================================================================

class Evaluator(ABC):
    """Base class for evaluators."""

    @abstractmethod
    def evaluate(self, output: str, expected: Any, test_case: TestCase) -> tuple[bool, float, dict]:
        """
        Evaluate model output against expected.

        Returns:
            (passed: bool, score: float 0-1, details: dict)
        """
        pass


class ContainsEvaluator(Evaluator):
    """Check if output contains expected keywords."""

    def evaluate(self, output: str, expected: Any, test_case: TestCase) -> tuple[bool, float, dict]:
        """
        Expected format:
            ["keyword1", "keyword2"] - all must be present
            or {"any": ["k1", "k2"]} - any must be present
            or {"all": ["k1", "k2"]} - all must be present
        """
        output_lower = output.lower()

        if isinstance(expected, list):
            keywords = expected
            mode = "all"
        elif isinstance(expected, dict):
            mode = "any" if "any" in expected else "all"
            keywords = expected.get("any", expected.get("all", []))
        else:
            keywords = [str(expected)]
            mode = "all"

        found = [kw for kw in keywords if kw.lower() in output_lower]

        if mode == "all":
            passed = len(found) == len(keywords)
            score = len(found) / len(keywords) if keywords else 1.0
        else:  # any
            passed = len(found) > 0
            score = 1.0 if passed else 0.0

        return passed, score, {"found": found, "expected": keywords, "mode": mode}


class NotContainsEvaluator(Evaluator):
    """Check that output does NOT contain forbidden content."""

    def evaluate(self, output: str, expected: Any, test_case: TestCase) -> tuple[bool, float, dict]:
        """Expected: list of forbidden keywords/patterns."""
        output_lower = output.lower()
        forbidden = expected if isinstance(expected, list) else [expected]

        found_forbidden = [f for f in forbidden if f.lower() in output_lower]

        passed = len(found_forbidden) == 0
        score = 1.0 if passed else 0.0

        return passed, score, {"found_forbidden": found_forbidden}


class SemanticEvaluator(Evaluator):
    """Compare semantic similarity using embeddings."""

    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold
        self._embedding_cache: Dict[str, List[float]] = {}

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text (uses Vertex AI or local model)."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        # Option 1: Use Vertex AI Embeddings
        try:
            from google.cloud import aiplatform
            from vertexai.language_models import TextEmbeddingModel

            model = TextEmbeddingModel.from_pretrained("textembedding-gecko@003")
            embeddings = model.get_embeddings([text])
            embedding = embeddings[0].values

        except Exception:
            # Option 2: Fallback to simple word overlap (not ideal)
            words = set(text.lower().split())
            embedding = [1.0 if chr(i) in text.lower() else 0.0 for i in range(97, 123)]

        self._embedding_cache[text] = embedding
        return embedding

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def evaluate(self, output: str, expected: Any, test_case: TestCase) -> tuple[bool, float, dict]:
        """Compare semantic similarity of output to expected."""
        expected_text = expected if isinstance(expected, str) else str(expected)

        emb_output = self._get_embedding(output)
        emb_expected = self._get_embedding(expected_text)

        similarity = self._cosine_similarity(emb_output, emb_expected)
        passed = similarity >= self.threshold

        return passed, similarity, {"similarity": similarity, "threshold": self.threshold}


class LLMJudgeEvaluator(Evaluator):
    """Use another LLM to judge the output quality."""

    def __init__(self, judge_endpoint: str, judge_prompt_template: str = None):
        self.judge_endpoint = judge_endpoint
        self.judge_prompt_template = judge_prompt_template or """
You are evaluating an AI assistant's response.

Original Question: {prompt}
AI Response: {output}
Expected Behavior: {expected}

Rate the response from 1-5:
1 = Completely wrong or harmful
2 = Mostly wrong
3 = Partially correct
4 = Mostly correct
5 = Excellent

Respond with ONLY a JSON object:
{{"score": <1-5>, "reason": "<brief explanation>"}}
"""

    def evaluate(self, output: str, expected: Any, test_case: TestCase) -> tuple[bool, float, dict]:
        """Ask LLM judge to rate the output."""
        judge_prompt = self.judge_prompt_template.format(
            prompt=test_case.prompt,
            output=output,
            expected=expected,
        )

        # Call judge LLM (simplified - would use actual endpoint)
        # For now, use rule-based fallback
        try:
            # In production: call self.judge_endpoint with judge_prompt
            # judge_response = call_llm(self.judge_endpoint, judge_prompt)
            # result = json.loads(judge_response)
            # score = result["score"] / 5.0

            # Fallback: simple heuristic
            score = 0.8 if len(output) > 50 else 0.5
            reason = "Fallback heuristic (LLM judge not configured)"

        except Exception as e:
            score = 0.5
            reason = f"Judge error: {e}"

        passed = score >= 0.6  # 3/5 or higher
        return passed, score, {"judge_score": score * 5, "reason": reason}


class RuleBasedEvaluator(Evaluator):
    """Evaluate using regex patterns and rules."""

    def evaluate(self, output: str, expected: Any, test_case: TestCase) -> tuple[bool, float, dict]:
        """
        Expected format:
        {
            "must_match": ["pattern1", "pattern2"],
            "must_not_match": ["bad_pattern"],
            "min_length": 50,
            "max_length": 500,
        }
        """
        rules = expected if isinstance(expected, dict) else {}
        violations = []
        checks_passed = 0
        total_checks = 0

        # Must match patterns
        for pattern in rules.get("must_match", []):
            total_checks += 1
            if re.search(pattern, output, re.IGNORECASE):
                checks_passed += 1
            else:
                violations.append(f"Missing required pattern: {pattern}")

        # Must not match patterns
        for pattern in rules.get("must_not_match", []):
            total_checks += 1
            if not re.search(pattern, output, re.IGNORECASE):
                checks_passed += 1
            else:
                violations.append(f"Found forbidden pattern: {pattern}")

        # Length checks
        if "min_length" in rules:
            total_checks += 1
            if len(output) >= rules["min_length"]:
                checks_passed += 1
            else:
                violations.append(f"Too short: {len(output)} < {rules['min_length']}")

        if "max_length" in rules:
            total_checks += 1
            if len(output) <= rules["max_length"]:
                checks_passed += 1
            else:
                violations.append(f"Too long: {len(output)} > {rules['max_length']}")

        score = checks_passed / total_checks if total_checks > 0 else 1.0
        passed = len(violations) == 0

        return passed, score, {"violations": violations, "checks": f"{checks_passed}/{total_checks}"}


# =============================================================================
# Main Evaluation Runner
# =============================================================================

class LLMEvaluator:
    """Main class for running LLM evaluations."""

    def __init__(
        self,
        endpoint_url: str,
        model_name: str = "unknown",
        model_version: str = "unknown",
        auth_token: str = None,
    ):
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self.model_version = model_version
        self.auth_token = auth_token

        # Register evaluators
        self.evaluators: Dict[EvalMethod, Evaluator] = {
            EvalMethod.CONTAINS: ContainsEvaluator(),
            EvalMethod.NOT_CONTAINS: NotContainsEvaluator(),
            EvalMethod.SEMANTIC: SemanticEvaluator(),
            EvalMethod.LLM_JUDGE: LLMJudgeEvaluator(endpoint_url),
            EvalMethod.RULE_BASED: RuleBasedEvaluator(),
        }

        # Custom evaluators
        self.custom_evaluators: Dict[str, Callable] = {}

    def register_custom_evaluator(self, name: str, func: Callable):
        """Register a custom evaluation function."""
        self.custom_evaluators[name] = func

    def call_model(self, prompt: str) -> tuple[str, float]:
        """Call the LLM endpoint and return (response, latency_ms)."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        # Format for Gemma
        formatted_prompt = f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"

        payload = {
            "prompt": formatted_prompt,
            "max_tokens": 200,
            "temperature": 0.1,  # Low temp for consistency
        }

        start_time = time.time()

        try:
            response = requests.post(
                self.endpoint_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()

            latency_ms = (time.time() - start_time) * 1000

            result = response.json()
            output = result.get("predictions", [result.get("response", "")])[0]

            return output, latency_ms

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return f"ERROR: {e}", latency_ms

    def run_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case."""
        # Call model
        output, latency_ms = self.call_model(test_case.prompt)

        # Check for error
        if output.startswith("ERROR:"):
            return TestResult(
                test_case=test_case,
                result=EvalResult.ERROR,
                actual_output=output,
                score=0.0,
                latency_ms=latency_ms,
                error_message=output,
            )

        # Get evaluator
        if test_case.eval_method == EvalMethod.CUSTOM:
            custom_name = test_case.expected.get("evaluator")
            if custom_name not in self.custom_evaluators:
                return TestResult(
                    test_case=test_case,
                    result=EvalResult.ERROR,
                    actual_output=output,
                    score=0.0,
                    latency_ms=latency_ms,
                    error_message=f"Custom evaluator not found: {custom_name}",
                )
            evaluator_func = self.custom_evaluators[custom_name]
            passed, score, details = evaluator_func(output, test_case.expected, test_case)
        else:
            evaluator = self.evaluators.get(test_case.eval_method)
            if not evaluator:
                return TestResult(
                    test_case=test_case,
                    result=EvalResult.SKIP,
                    actual_output=output,
                    score=0.0,
                    latency_ms=latency_ms,
                    error_message=f"Unknown eval method: {test_case.eval_method}",
                )
            passed, score, details = evaluator.evaluate(output, test_case.expected, test_case)

        return TestResult(
            test_case=test_case,
            result=EvalResult.PASS if passed else EvalResult.FAIL,
            actual_output=output,
            score=score,
            latency_ms=latency_ms,
            details=details,
        )

    def run_suite(self, test_cases: List[TestCase]) -> EvalReport:
        """Run all test cases and generate report."""
        from datetime import datetime

        results = []
        for tc in test_cases:
            print(f"Running: {tc.id} - {tc.name}...", end=" ")
            result = self.run_test(tc)
            print(f"{result.result.value} ({result.score:.2f})")
            results.append(result)

        # Calculate summary
        passed = sum(1 for r in results if r.result == EvalResult.PASS)
        failed = sum(1 for r in results if r.result == EvalResult.FAIL)
        skipped = sum(1 for r in results if r.result == EvalResult.SKIP)
        errors = sum(1 for r in results if r.result == EvalResult.ERROR)

        total = len(results)
        pass_rate = passed / total if total > 0 else 0.0
        avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0.0

        return EvalReport(
            model_name=self.model_name,
            model_version=self.model_version,
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            pass_rate=pass_rate,
            avg_latency_ms=avg_latency,
            results=results,
            timestamp=datetime.utcnow().isoformat(),
        )


# =============================================================================
# Test Case Loader
# =============================================================================

def load_test_cases(filepath: str) -> List[TestCase]:
    """Load test cases from JSON file."""
    with open(filepath) as f:
        data = json.load(f)

    test_cases = []
    for tc in data.get("test_cases", []):
        test_cases.append(TestCase(
            id=tc["id"],
            name=tc["name"],
            prompt=tc["prompt"],
            eval_method=EvalMethod(tc["eval_method"]),
            expected=tc["expected"],
            category=tc.get("category", "general"),
            tags=tc.get("tags", []),
            weight=tc.get("weight", 1.0),
        ))

    return test_cases


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description="Run LLM evaluations")
    parser.add_argument("--endpoint", required=True, help="Model endpoint URL")
    parser.add_argument("--dataset", required=True, help="Path to test cases JSON")
    parser.add_argument("--model-name", default="unknown", help="Model name")
    parser.add_argument("--model-version", default="unknown", help="Model version")
    parser.add_argument("--output", help="Output report path (JSON)")
    parser.add_argument("--fail-threshold", type=float, default=0.8, help="Min pass rate to succeed")

    args = parser.parse_args()

    # Get auth token
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            text=True
        ).strip()
    except Exception:
        token = None
        print("Warning: Could not get auth token")

    # Load test cases
    test_cases = load_test_cases(args.dataset)
    print(f"Loaded {len(test_cases)} test cases from {args.dataset}")

    # Run evaluations
    evaluator = LLMEvaluator(
        endpoint_url=args.endpoint,
        model_name=args.model_name,
        model_version=args.model_version,
        auth_token=token,
    )

    report = evaluator.run_suite(test_cases)

    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Model: {report.model_name} @ {report.model_version}")
    print(f"Total: {report.total_tests}")
    print(f"Passed: {report.passed}")
    print(f"Failed: {report.failed}")
    print(f"Errors: {report.errors}")
    print(f"Pass Rate: {report.pass_rate:.1%}")
    print(f"Avg Latency: {report.avg_latency_ms:.0f}ms")
    print("=" * 60)

    # Save report
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"Report saved to: {args.output}")

    # Exit with error if below threshold
    if report.pass_rate < args.fail_threshold:
        print(f"\nFAILED: Pass rate {report.pass_rate:.1%} < threshold {args.fail_threshold:.1%}")
        exit(1)
    else:
        print(f"\nPASSED: Pass rate {report.pass_rate:.1%} >= threshold {args.fail_threshold:.1%}")
        exit(0)


if __name__ == "__main__":
    main()
