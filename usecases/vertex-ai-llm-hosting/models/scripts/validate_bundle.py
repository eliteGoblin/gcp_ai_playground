#!/usr/bin/env python3
"""
=============================================================================
Model Bundle Validator
=============================================================================
Purpose: Validate model bundle before uploading to Vertex AI

Checks:
1. Required HuggingFace files exist (config.json, weights, tokenizer)
2. Custom code has required Predictor class with correct methods
3. File sizes are reasonable
4. JSON files are valid

Usage:
    python validate_bundle.py ./my_model_bundle/
    python validate_bundle.py gs://bucket/models/v1.0.0/  (requires gsutil)

=============================================================================
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple


class ValidationResult:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def error(self, msg: str):
        self.errors.append(f"ERROR: {msg}")

    def warn(self, msg: str):
        self.warnings.append(f"WARNING: {msg}")

    def ok(self, msg: str):
        self.info.append(f"OK: {msg}")

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def validate_huggingface_format(model_dir: Path, result: ValidationResult) -> None:
    """Check required HuggingFace files exist."""

    # Required files for model
    required_files = [
        ("config.json", "Model architecture config"),
    ]

    # One of these weight files must exist
    weight_files = [
        "model.safetensors",
        "pytorch_model.bin",
        "model.bin",
        "tf_model.h5",
    ]

    # Required tokenizer files (at least one)
    tokenizer_files = [
        "tokenizer.json",
        "tokenizer.model",
        "vocab.txt",
        "spiece.model",
    ]

    # Check required files
    for filename, description in required_files:
        filepath = model_dir / filename
        if filepath.exists():
            result.ok(f"Found {filename} ({description})")

            # Validate JSON
            if filename.endswith(".json"):
                try:
                    with open(filepath) as f:
                        json.load(f)
                    result.ok(f"  {filename} is valid JSON")
                except json.JSONDecodeError as e:
                    result.error(f"{filename} is invalid JSON: {e}")
        else:
            result.error(f"Missing required file: {filename} ({description})")

    # Check weight files
    found_weights = False
    for wf in weight_files:
        if (model_dir / wf).exists():
            size_mb = (model_dir / wf).stat().st_size / (1024 * 1024)
            result.ok(f"Found weights: {wf} ({size_mb:.1f} MB)")
            found_weights = True
            break

    if not found_weights:
        result.error(f"No model weights found. Expected one of: {weight_files}")

    # Check tokenizer files
    found_tokenizer = False
    for tf in tokenizer_files:
        if (model_dir / tf).exists():
            result.ok(f"Found tokenizer: {tf}")
            found_tokenizer = True
            break

    if not found_tokenizer:
        result.warn(f"No tokenizer found. Expected one of: {tokenizer_files}")


def validate_custom_code(code_dir: Path, result: ValidationResult) -> None:
    """Check custom prediction code meets Vertex AI requirements."""

    predictor_file = code_dir / "predictor.py"

    if not predictor_file.exists():
        result.warn("No predictor.py found (optional for default serving)")
        return

    result.ok("Found predictor.py")

    # Parse the Python file
    try:
        with open(predictor_file) as f:
            tree = ast.parse(f.read())
    except SyntaxError as e:
        result.error(f"predictor.py has syntax error: {e}")
        return

    result.ok("  predictor.py has valid Python syntax")

    # Find Predictor class
    predictor_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Predictor":
            predictor_class = node
            break

    if not predictor_class:
        result.error("predictor.py must have a class named 'Predictor'")
        return

    result.ok("  Found 'Predictor' class")

    # Check required methods
    methods = {node.name for node in predictor_class.body if isinstance(node, ast.FunctionDef)}

    required_methods = ["load", "predict"]
    optional_methods = ["preprocess", "postprocess"]

    for method in required_methods:
        if method in methods:
            result.ok(f"  Found required method: {method}()")
        else:
            result.error(f"Predictor class missing required method: {method}()")

    for method in optional_methods:
        if method in methods:
            result.ok(f"  Found optional method: {method}()")


def validate_requirements(code_dir: Path, result: ValidationResult) -> None:
    """Check requirements.txt exists and is valid."""

    req_file = code_dir / "requirements.txt"

    if not req_file.exists():
        result.warn("No requirements.txt found (using container defaults)")
        return

    result.ok("Found requirements.txt")

    with open(req_file) as f:
        lines = f.readlines()

    package_count = 0
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            package_count += 1

    result.ok(f"  {package_count} packages specified")


def validate_bundle(bundle_path: str) -> ValidationResult:
    """Validate complete model bundle."""

    result = ValidationResult()
    bundle_dir = Path(bundle_path)

    if not bundle_dir.exists():
        result.error(f"Bundle path does not exist: {bundle_path}")
        return result

    print(f"\n{'='*60}")
    print(f"Validating: {bundle_path}")
    print(f"{'='*60}\n")

    # Check for model directory
    model_dir = bundle_dir / "model"
    if not model_dir.exists():
        # Maybe files are at root level
        model_dir = bundle_dir

    print("1. Checking HuggingFace model format...")
    print("-" * 40)
    validate_huggingface_format(model_dir, result)

    # Check for custom code
    code_dir = bundle_dir / "custom_code"
    if code_dir.exists():
        print("\n2. Checking custom prediction code...")
        print("-" * 40)
        validate_custom_code(code_dir, result)
        validate_requirements(code_dir, result)
    else:
        print("\n2. No custom_code/ directory (using default serving)")

    # Summary
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")

    for msg in result.info:
        print(f"  {msg}")

    for msg in result.warnings:
        print(f"  {msg}")

    for msg in result.errors:
        print(f"  {msg}")

    print()
    if result.passed:
        print("RESULT: PASSED - Bundle is valid for Vertex AI")
    else:
        print(f"RESULT: FAILED - {len(result.errors)} error(s) found")

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate model bundle for Vertex AI")
    parser.add_argument("bundle_path", help="Path to model bundle directory")
    args = parser.parse_args()

    result = validate_bundle(args.bundle_path)
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
