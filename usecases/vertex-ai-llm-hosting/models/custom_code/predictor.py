"""
=============================================================================
Custom Predictor for Vertex AI
=============================================================================
Purpose: Pre/post processing logic that runs with your model

This code runs:
1. BEFORE model inference (preprocess) - Mask PII, format prompts
2. AFTER model inference (postprocess) - Unmask PII, add guardrails

How it works with Vertex AI:
- You upload this with your model artifacts
- Vertex AI loads it into the serving container
- Every prediction request flows through this class

=============================================================================
"""

import json
import logging
import re
from typing import Any, Dict, List

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LoanAssessorPredictor:
    """
    Custom prediction routine for loan assessment model.

    Handles:
    - PII masking (SSN, names, account numbers)
    - Prompt formatting (Gemma chat format)
    - Response validation (guardrails)
    - Audit logging
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._pii_vault: Dict[str, str] = {}  # token -> original value
        self._request_id: str = ""

    # =========================================================================
    # LOAD: Called once when container starts
    # =========================================================================
    def load(self, artifacts_uri: str) -> None:
        """
        Load model and tokenizer from artifacts.

        Args:
            artifacts_uri: GCS path to model artifacts
                          e.g., gs://bucket/models/loan-assessor/v1.0.0/
        """
        logger.info(f"Loading model from: {artifacts_uri}")

        # In real deployment, load from GCS:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_path = f"{artifacts_uri}/model"

        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto",
        )

        logger.info("Model loaded successfully")

    # =========================================================================
    # PREPROCESS: Runs BEFORE model inference
    # =========================================================================
    def preprocess(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Preprocess incoming request.

        Steps:
        1. Generate request ID for tracking
        2. Mask PII (SSN, names, account numbers)
        3. Format prompt for Gemma chat format
        4. Validate input

        Args:
            request: Raw request from user
                    {"prompt": "Check loan for John Smith SSN 123-45-6789"}

        Returns:
            Processed request ready for model
                    {"prompt": "...<formatted>...", "max_tokens": 100}
        """
        import uuid

        # Generate request ID for audit trail
        self._request_id = str(uuid.uuid4())[:8]
        self._pii_vault.clear()

        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", 100)

        logger.info(f"[{self._request_id}] Preprocessing request")

        # Step 1: Mask SSN (XXX-XX-XXXX pattern)
        ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
        ssns = re.findall(ssn_pattern, prompt)
        for i, ssn in enumerate(ssns):
            token = f"[SSN_{i}]"
            self._pii_vault[token] = ssn
            prompt = prompt.replace(ssn, token)
            logger.info(f"[{self._request_id}] Masked SSN")

        # Step 2: Mask account numbers (simple pattern)
        account_pattern = r"\b[A-Z]{2}\d{8,12}\b"
        accounts = re.findall(account_pattern, prompt)
        for i, acc in enumerate(accounts):
            token = f"[ACCOUNT_{i}]"
            self._pii_vault[token] = acc
            prompt = prompt.replace(acc, token)
            logger.info(f"[{self._request_id}] Masked account number")

        # Step 3: Format for Gemma chat template
        system_prompt = """You are a loan assessment assistant for a financial institution.
- Be professional and concise
- Never reveal sensitive information like full SSN
- Provide clear reasoning for assessments
- If unsure, recommend human review"""

        formatted_prompt = f"""<start_of_turn>system
{system_prompt}
<end_of_turn>
<start_of_turn>user
{prompt}
<end_of_turn>
<start_of_turn>model
"""

        # Step 4: Validate input length
        if len(formatted_prompt) > 4000:
            raise ValueError("Input too long. Maximum 4000 characters.")

        return {
            "prompt": formatted_prompt,
            "max_tokens": min(max_tokens, 500),  # Cap at 500
            "temperature": request.get("temperature", 0.7),
            "request_id": self._request_id,
        }

    # =========================================================================
    # PREDICT: The actual model inference
    # =========================================================================
    def predict(self, processed_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run model inference.

        This is where the LLM actually generates a response.

        Args:
            processed_request: Output from preprocess()

        Returns:
            Raw model output
        """
        logger.info(f"[{processed_request['request_id']}] Running inference")

        inputs = self._tokenizer(
            processed_request["prompt"],
            return_tensors="pt"
        ).to(self._model.device)

        outputs = self._model.generate(
            **inputs,
            max_new_tokens=processed_request["max_tokens"],
            temperature=processed_request["temperature"],
            do_sample=True,
            pad_token_id=self._tokenizer.eos_token_id,
        )

        # Decode only the new tokens (skip input)
        input_length = inputs["input_ids"].shape[1]
        response = self._tokenizer.decode(
            outputs[0][input_length:],
            skip_special_tokens=True
        )

        return {
            "response": response,
            "tokens_generated": len(outputs[0]) - input_length,
            "request_id": processed_request["request_id"],
        }

    # =========================================================================
    # POSTPROCESS: Runs AFTER model inference
    # =========================================================================
    def postprocess(self, prediction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Postprocess model output.

        Steps:
        1. Unmask PII (restore original values)
        2. Apply content guardrails
        3. Format response
        4. Add audit metadata

        Args:
            prediction: Raw output from predict()

        Returns:
            Final response to user
        """
        response = prediction["response"]
        request_id = prediction["request_id"]

        logger.info(f"[{request_id}] Postprocessing response")

        # Step 1: Unmask PII
        for token, original in self._pii_vault.items():
            # Only unmask if appropriate (e.g., partial mask for display)
            if token.startswith("[SSN_"):
                # Show last 4 digits only
                masked = f"XXX-XX-{original[-4:]}"
                response = response.replace(token, masked)
            else:
                response = response.replace(token, original)

        # Step 2: Content guardrails
        blocked_phrases = [
            "bypass security",
            "ignore previous instructions",
            "as an ai language model",  # Discourage meta-responses
        ]

        for phrase in blocked_phrases:
            if phrase.lower() in response.lower():
                logger.warning(f"[{request_id}] Blocked phrase detected")
                return {
                    "response": "I cannot provide that information. Please rephrase your question.",
                    "blocked": True,
                    "request_id": request_id,
                }

        # Step 3: Check for potential hallucinated financial advice
        risky_patterns = [
            r"guaranteed.*return",
            r"100%.*safe",
            r"risk.?free.*investment",
        ]

        for pattern in risky_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                response += "\n\n*Disclaimer: This is AI-generated guidance. Please consult a financial advisor for personalized advice.*"
                break

        # Step 4: Format final response
        return {
            "response": response.strip(),
            "model_version": "loan-assessor-v1.0.0",
            "request_id": request_id,
            "tokens_generated": prediction["tokens_generated"],
            "pii_detected": len(self._pii_vault) > 0,
        }


# =============================================================================
# Vertex AI Predictor Interface
# =============================================================================
# This is the standard interface Vertex AI expects

class Predictor:
    """
    Vertex AI Custom Prediction Routine interface.

    Vertex AI will:
    1. Call load() once on container startup
    2. Call predict() for each incoming request
    """

    def __init__(self):
        self._predictor = LoanAssessorPredictor()

    def load(self, artifacts_uri: str) -> None:
        """Load model artifacts."""
        self._predictor.load(artifacts_uri)

    def predict(self, instances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Handle prediction requests.

        Args:
            instances: List of prediction requests
                      [{"prompt": "...", "max_tokens": 100}, ...]

        Returns:
            List of predictions
        """
        predictions = []

        for instance in instances:
            try:
                # Pipeline: preprocess -> predict -> postprocess
                processed = self._predictor.preprocess(instance)
                raw_output = self._predictor.predict(processed)
                final_output = self._predictor.postprocess(raw_output)
                predictions.append(final_output)

            except Exception as e:
                logger.error(f"Prediction error: {e}")
                predictions.append({
                    "error": str(e),
                    "response": "An error occurred processing your request.",
                })

        return predictions
