"""Cost calculation for AI system monitoring.

Tracks token usage and estimates costs for Gemini API, BigQuery, and other services.
"""

from dataclasses import dataclass
from typing import Optional


# Gemini pricing (as of 2025) - per 1M tokens
# https://cloud.google.com/vertex-ai/generative-ai/pricing
GEMINI_PRICING = {
    "gemini-2.5-flash": {
        "input": 0.075,   # $0.075 per 1M input tokens
        "output": 0.30,   # $0.30 per 1M output tokens
    },
    "gemini-1.5-flash": {
        "input": 0.075,
        "output": 0.30,
    },
    "gemini-1.5-flash-002": {
        "input": 0.075,
        "output": 0.30,
    },
    "gemini-1.5-pro": {
        "input": 1.25,    # $1.25 per 1M input tokens
        "output": 5.00,   # $5.00 per 1M output tokens
    },
}

# BigQuery pricing
BQ_PRICING = {
    "query_per_tb": 5.00,     # $5 per TB scanned
    "storage_per_tb": 0.02,   # $0.02 per GB per month (active)
}

# Vertex AI Search pricing
VERTEX_SEARCH_PRICING = {
    "query": 0.002,  # Approximate per query
}


@dataclass
class TokenUsage:
    """Token usage for a model call."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class CostBreakdown:
    """Detailed cost breakdown for a request."""

    gemini_input_cost: float = 0.0
    gemini_output_cost: float = 0.0
    gemini_total_cost: float = 0.0
    bigquery_cost: float = 0.0
    vertex_search_cost: float = 0.0
    total_cost: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "gemini_input_cost_usd": round(self.gemini_input_cost, 6),
            "gemini_output_cost_usd": round(self.gemini_output_cost, 6),
            "gemini_total_cost_usd": round(self.gemini_total_cost, 6),
            "bigquery_cost_usd": round(self.bigquery_cost, 6),
            "vertex_search_cost_usd": round(self.vertex_search_cost, 6),
            "total_cost_usd": round(self.total_cost, 6),
        }


class CostCalculator:
    """Calculate costs for AI system operations."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        """Initialize calculator with model pricing.

        Args:
            model: Model name for pricing lookup
        """
        self.model = model
        self.pricing = GEMINI_PRICING.get(model, GEMINI_PRICING["gemini-2.5-flash"])

    def calculate_gemini_cost(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[float, float]:
        """Calculate Gemini API cost.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Tuple of (input_cost, output_cost) in USD
        """
        input_cost = (input_tokens / 1_000_000) * self.pricing["input"]
        output_cost = (output_tokens / 1_000_000) * self.pricing["output"]
        return input_cost, output_cost

    def calculate_bq_cost(
        self,
        bytes_scanned: int = 0,
        estimated_queries: int = 2,  # Default: CI enrichment + registry
    ) -> float:
        """Calculate BigQuery cost estimate.

        Args:
            bytes_scanned: Bytes scanned (if known)
            estimated_queries: Number of queries if bytes unknown

        Returns:
            Estimated cost in USD
        """
        if bytes_scanned > 0:
            tb_scanned = bytes_scanned / (1024**4)
            return tb_scanned * BQ_PRICING["query_per_tb"]
        else:
            # Estimate ~10KB per query for our use case
            estimated_bytes = estimated_queries * 10 * 1024
            tb_scanned = estimated_bytes / (1024**4)
            return tb_scanned * BQ_PRICING["query_per_tb"]

    def calculate_vertex_search_cost(self, num_queries: int = 1) -> float:
        """Calculate Vertex AI Search cost.

        Args:
            num_queries: Number of search queries

        Returns:
            Estimated cost in USD
        """
        return num_queries * VERTEX_SEARCH_PRICING["query"]

    def calculate_total_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        bq_queries: int = 2,
        rag_queries: int = 0,
    ) -> CostBreakdown:
        """Calculate total cost for a coaching request.

        Args:
            input_tokens: Gemini input tokens
            output_tokens: Gemini output tokens
            bq_queries: Number of BigQuery queries
            rag_queries: Number of RAG/search queries

        Returns:
            CostBreakdown with all costs
        """
        gemini_in, gemini_out = self.calculate_gemini_cost(input_tokens, output_tokens)
        bq_cost = self.calculate_bq_cost(estimated_queries=bq_queries)
        search_cost = self.calculate_vertex_search_cost(rag_queries)

        return CostBreakdown(
            gemini_input_cost=gemini_in,
            gemini_output_cost=gemini_out,
            gemini_total_cost=gemini_in + gemini_out,
            bigquery_cost=bq_cost,
            vertex_search_cost=search_cost,
            total_cost=gemini_in + gemini_out + bq_cost + search_cost,
        )


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token average for English).

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    return len(text) // 4
