"""
Aggregation service for computing summary metrics from coach_analysis.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from google.cloud import bigquery

from cc_coach.config import get_settings
from cc_coach.schemas.summary import (
    DailySummaryInput,
    ExampleConversation,
    WeeklySummaryInput,
)

logger = logging.getLogger(__name__)


class AggregationService:
    """Aggregates coaching data for summary generation."""

    def __init__(self):
        self.settings = get_settings()
        self.client = bigquery.Client(project=self.settings.project_id)
        self.dataset = self.settings.bq_dataset_id

    def get_daily_aggregation(
        self, agent_id: str, target_date: date
    ) -> Optional[DailySummaryInput]:
        """
        Aggregate coaching data for a single agent on a single day.

        Returns None if no data found for the agent/date.
        """
        prev_date = target_date - timedelta(days=1)

        query = f"""
        WITH current_day_base AS (
            SELECT
                agent_id,
                business_line,
                team,
                COUNT(*) as call_count,
                AVG(empathy_score) as avg_empathy,
                AVG(compliance_score) as avg_compliance,
                AVG(resolution_score) as avg_resolution,
                AVG(professionalism_score) as avg_professionalism,
                AVG(efficiency_score) as avg_efficiency,
                AVG(de_escalation_score) as avg_de_escalation,
                AVG(overall_score) as avg_overall,
                COUNTIF(resolution_achieved = TRUE) / COUNT(*) as resolution_rate
            FROM `{self.dataset}.coach_analysis`
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) = @target_date
            GROUP BY agent_id, business_line, team
        ),
        all_issues AS (
            SELECT issue
            FROM `{self.dataset}.coach_analysis`, UNNEST(issue_types) as issue
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) = @target_date
        ),
        top_issues AS (
            SELECT ARRAY_AGG(issue ORDER BY cnt DESC LIMIT 5) as top_issues
            FROM (
                SELECT issue, COUNT(*) as cnt
                FROM all_issues
                GROUP BY issue
                ORDER BY cnt DESC
                LIMIT 5
            )
        ),
        all_strengths AS (
            SELECT strength
            FROM `{self.dataset}.coach_analysis`, UNNEST(strengths) as strength
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) = @target_date
        ),
        top_strengths AS (
            SELECT ARRAY_AGG(strength ORDER BY cnt DESC LIMIT 5) as top_strengths
            FROM (
                SELECT strength, COUNT(*) as cnt
                FROM all_strengths
                GROUP BY strength
                ORDER BY cnt DESC
                LIMIT 5
            )
        ),
        prev_day AS (
            SELECT
                AVG(overall_score) as prev_avg_overall,
                COUNT(*) as prev_call_count
            FROM `{self.dataset}.coach_analysis`
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) = @prev_date
        )
        SELECT
            c.*,
            i.top_issues,
            s.top_strengths,
            p.prev_avg_overall,
            p.prev_call_count
        FROM current_day_base c
        CROSS JOIN top_issues i
        CROSS JOIN top_strengths s
        CROSS JOIN prev_day p
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
                bigquery.ScalarQueryParameter("target_date", "DATE", target_date),
                bigquery.ScalarQueryParameter("prev_date", "DATE", prev_date),
            ]
        )

        result = list(self.client.query(query, job_config=job_config).result())

        if not result or result[0]["call_count"] is None:
            logger.info(f"No coaching data found for {agent_id} on {target_date}")
            return None

        row = result[0]

        # Calculate delta
        overall_delta = None
        trend = None
        if row["prev_avg_overall"]:
            overall_delta = row["avg_overall"] - row["prev_avg_overall"]
            if overall_delta > 0.5:
                trend = "improving"
            elif overall_delta < -0.5:
                trend = "declining"
            else:
                trend = "stable"

        # Get example conversations
        best = self._get_example_conversation(
            agent_id, target_date, example_type="GOOD_EXAMPLE"
        )
        worst = self._get_example_conversation(
            agent_id, target_date, example_type="NEEDS_WORK"
        )

        return DailySummaryInput(
            agent_id=agent_id,
            date=target_date,
            business_line=row["business_line"],
            team=row["team"],
            call_count=row["call_count"],
            avg_empathy=round(row["avg_empathy"], 1),
            avg_compliance=round(row["avg_compliance"], 1),
            avg_resolution=round(row["avg_resolution"], 1),
            avg_professionalism=round(row["avg_professionalism"], 1),
            avg_efficiency=round(row["avg_efficiency"], 1),
            avg_de_escalation=round(row["avg_de_escalation"], 1),
            avg_overall=round(row["avg_overall"], 1),
            resolution_rate=round(row["resolution_rate"], 2),
            prev_day_avg_overall=round(row["prev_avg_overall"], 1)
            if row["prev_avg_overall"]
            else None,
            prev_day_call_count=row["prev_call_count"],
            overall_delta=round(overall_delta, 1) if overall_delta else None,
            trend_direction=trend,
            top_issues=list(row["top_issues"]) if row["top_issues"] else [],
            top_strengths=list(row["top_strengths"]) if row["top_strengths"] else [],
            best_conversation=best,
            worst_conversation=worst,
        )

    def _get_example_conversation(
        self, agent_id: str, target_date: date, example_type: str
    ) -> Optional[ExampleConversation]:
        """Get best or worst conversation for the day."""
        order = "DESC" if example_type == "GOOD_EXAMPLE" else "ASC"

        query = f"""
        SELECT
            conversation_id,
            call_type,
            overall_score,
            empathy_score,
            compliance_score,
            resolution_score,
            key_moment,
            call_outcome,
            customer_sentiment_start,
            customer_sentiment_end,
            situation_summary
        FROM `{self.dataset}.coach_analysis`
        WHERE agent_id = @agent_id
          AND DATE(analyzed_at) = @target_date
        ORDER BY overall_score {order}
        LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
                bigquery.ScalarQueryParameter("target_date", "DATE", target_date),
            ]
        )

        result = list(self.client.query(query, job_config=job_config).result())

        if not result:
            return None

        row = result[0]

        # Determine sentiment journey
        sentiment_journey = None
        if row["customer_sentiment_start"] and row["customer_sentiment_end"]:
            start = row["customer_sentiment_start"]
            end = row["customer_sentiment_end"]
            sentiment_journey = f"{start:.1f} -> {end:.1f}"

        return ExampleConversation(
            conversation_id=row["conversation_id"],
            example_type=example_type,
            headline=row["situation_summary"] or row["call_type"] or "Call",
            key_moment=dict(row["key_moment"]) if row["key_moment"] else None,
            outcome=row["call_outcome"],
            sentiment_journey=sentiment_journey,
            scores={
                "overall": row["overall_score"],
                "empathy": row["empathy_score"],
                "compliance": row["compliance_score"],
            },
            call_type=row["call_type"],
        )

    def get_weekly_aggregation(
        self, agent_id: str, week_start: date
    ) -> Optional[WeeklySummaryInput]:
        """
        Aggregate coaching data for an agent for a week.

        week_start should be a Monday.
        """
        week_end = week_start + timedelta(days=6)
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start - timedelta(days=1)

        query = f"""
        WITH current_week_base AS (
            SELECT
                agent_id,
                business_line,
                team,
                COUNT(*) as total_calls,
                COUNT(DISTINCT DATE(analyzed_at)) as days_with_calls,
                AVG(empathy_score) as avg_empathy,
                AVG(compliance_score) as avg_compliance,
                AVG(resolution_score) as avg_resolution,
                AVG(professionalism_score) as avg_professionalism,
                AVG(efficiency_score) as avg_efficiency,
                AVG(de_escalation_score) as avg_de_escalation,
                AVG(overall_score) as avg_overall,
                COUNTIF(resolution_achieved = TRUE) / COUNT(*) as resolution_rate,
                SUM(compliance_breach_count) as total_compliance_breaches
            FROM `{self.dataset}.coach_analysis`
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) BETWEEN @week_start AND @week_end
            GROUP BY agent_id, business_line, team
        ),
        all_issues AS (
            SELECT issue
            FROM `{self.dataset}.coach_analysis`, UNNEST(issue_types) as issue
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) BETWEEN @week_start AND @week_end
        ),
        top_issues AS (
            SELECT ARRAY_AGG(issue ORDER BY cnt DESC LIMIT 5) as top_issues
            FROM (
                SELECT issue, COUNT(*) as cnt
                FROM all_issues
                GROUP BY issue
                ORDER BY cnt DESC
                LIMIT 5
            )
        ),
        all_strengths AS (
            SELECT strength
            FROM `{self.dataset}.coach_analysis`, UNNEST(strengths) as strength
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) BETWEEN @week_start AND @week_end
        ),
        top_strengths AS (
            SELECT ARRAY_AGG(strength ORDER BY cnt DESC LIMIT 5) as top_strengths
            FROM (
                SELECT strength, COUNT(*) as cnt
                FROM all_strengths
                GROUP BY strength
                ORDER BY cnt DESC
                LIMIT 5
            )
        ),
        prev_week AS (
            SELECT
                AVG(overall_score) as prev_avg_overall,
                AVG(empathy_score) as prev_avg_empathy,
                AVG(compliance_score) as prev_avg_compliance,
                AVG(resolution_score) as prev_avg_resolution,
                COUNT(*) as prev_total_calls
            FROM `{self.dataset}.coach_analysis`
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) BETWEEN @prev_week_start AND @prev_week_end
        ),
        daily_breakdown AS (
            SELECT
                DATE(analyzed_at) as call_date,
                COUNT(*) as call_count,
                AVG(empathy_score) as avg_empathy,
                AVG(compliance_score) as avg_compliance,
                AVG(resolution_score) as avg_resolution
            FROM `{self.dataset}.coach_analysis`
            WHERE agent_id = @agent_id
              AND DATE(analyzed_at) BETWEEN @week_start AND @week_end
            GROUP BY call_date
            ORDER BY call_date
        )
        SELECT
            c.*,
            i.top_issues,
            s.top_strengths,
            p.prev_avg_overall,
            p.prev_avg_empathy,
            p.prev_avg_compliance,
            p.prev_avg_resolution,
            p.prev_total_calls,
            ARRAY_AGG(STRUCT(
                d.call_date as date,
                d.call_count,
                d.avg_empathy,
                d.avg_compliance,
                d.avg_resolution
            )) as daily_scores
        FROM current_week_base c
        CROSS JOIN top_issues i
        CROSS JOIN top_strengths s
        CROSS JOIN prev_week p
        LEFT JOIN daily_breakdown d ON TRUE
        GROUP BY
            c.agent_id, c.business_line, c.team, c.total_calls, c.days_with_calls,
            c.avg_empathy, c.avg_compliance, c.avg_resolution, c.avg_professionalism,
            c.avg_efficiency, c.avg_de_escalation, c.avg_overall, c.resolution_rate,
            c.total_compliance_breaches, i.top_issues, s.top_strengths,
            p.prev_avg_overall, p.prev_avg_empathy, p.prev_avg_compliance,
            p.prev_avg_resolution, p.prev_total_calls
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
                bigquery.ScalarQueryParameter("week_start", "DATE", week_start),
                bigquery.ScalarQueryParameter("week_end", "DATE", week_end),
                bigquery.ScalarQueryParameter(
                    "prev_week_start", "DATE", prev_week_start
                ),
                bigquery.ScalarQueryParameter("prev_week_end", "DATE", prev_week_end),
            ]
        )

        result = list(self.client.query(query, job_config=job_config).result())

        if not result or result[0]["total_calls"] is None:
            logger.info(f"No coaching data found for {agent_id} for week of {week_start}")
            return None

        row = result[0]

        # Calculate deltas
        empathy_delta = None
        compliance_delta = None
        resolution_delta = None
        overall_delta = None

        if row["prev_avg_empathy"]:
            empathy_delta = round(row["avg_empathy"] - row["prev_avg_empathy"], 1)
        if row["prev_avg_compliance"]:
            compliance_delta = round(
                row["avg_compliance"] - row["prev_avg_compliance"], 1
            )
        if row["prev_avg_resolution"]:
            resolution_delta = round(
                row["avg_resolution"] - row["prev_avg_resolution"], 1
            )
        if row["prev_avg_overall"]:
            overall_delta = round(row["avg_overall"] - row["prev_avg_overall"], 1)

        # Get example conversations
        exemplary = self._get_week_examples(
            agent_id, week_start, week_end, example_type="GOOD_EXAMPLE", limit=2
        )
        needs_review = self._get_week_examples(
            agent_id, week_start, week_end, example_type="NEEDS_WORK", limit=2
        )

        # Format daily scores
        daily_scores = []
        for ds in row["daily_scores"] or []:
            if ds and ds.get("date"):
                daily_scores.append(
                    {
                        "date": ds["date"].isoformat() if hasattr(ds["date"], "isoformat") else str(ds["date"]),
                        "call_count": ds["call_count"],
                        "avg_empathy": round(ds["avg_empathy"], 1) if ds["avg_empathy"] else None,
                        "avg_compliance": round(ds["avg_compliance"], 1) if ds["avg_compliance"] else None,
                        "avg_resolution": round(ds["avg_resolution"], 1) if ds["avg_resolution"] else None,
                    }
                )

        return WeeklySummaryInput(
            agent_id=agent_id,
            week_start=week_start,
            week_end=week_end,
            business_line=row["business_line"],
            team=row["team"],
            total_calls=row["total_calls"],
            days_with_calls=row["days_with_calls"],
            week_avg_empathy=round(row["avg_empathy"], 1),
            week_avg_compliance=round(row["avg_compliance"], 1),
            week_avg_resolution=round(row["avg_resolution"], 1),
            week_avg_professionalism=round(row["avg_professionalism"], 1),
            week_avg_efficiency=round(row["avg_efficiency"], 1),
            week_avg_de_escalation=round(row["avg_de_escalation"], 1),
            week_avg_overall=round(row["avg_overall"], 1),
            week_resolution_rate=round(row["resolution_rate"], 2),
            prev_week_avg_overall=round(row["prev_avg_overall"], 1)
            if row["prev_avg_overall"]
            else None,
            prev_week_total_calls=row["prev_total_calls"],
            empathy_delta=empathy_delta,
            compliance_delta=compliance_delta,
            resolution_delta=resolution_delta,
            overall_delta=overall_delta,
            daily_scores=daily_scores,
            top_issues=list(row["top_issues"]) if row["top_issues"] else [],
            top_strengths=list(row["top_strengths"]) if row["top_strengths"] else [],
            exemplary_conversations=exemplary,
            needs_review_conversations=needs_review,
        )

    def _get_week_examples(
        self,
        agent_id: str,
        week_start: date,
        week_end: date,
        example_type: str,
        limit: int = 2,
    ) -> list[ExampleConversation]:
        """Get best or worst conversations for the week."""
        order = "DESC" if example_type == "GOOD_EXAMPLE" else "ASC"

        query = f"""
        SELECT
            conversation_id,
            DATE(analyzed_at) as call_date,
            call_type,
            overall_score,
            empathy_score,
            compliance_score,
            resolution_score,
            key_moment,
            call_outcome,
            customer_sentiment_start,
            customer_sentiment_end,
            situation_summary
        FROM `{self.dataset}.coach_analysis`
        WHERE agent_id = @agent_id
          AND DATE(analyzed_at) BETWEEN @week_start AND @week_end
        ORDER BY overall_score {order}
        LIMIT @limit
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
                bigquery.ScalarQueryParameter("week_start", "DATE", week_start),
                bigquery.ScalarQueryParameter("week_end", "DATE", week_end),
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
            ]
        )

        results = list(self.client.query(query, job_config=job_config).result())
        examples = []

        for row in results:
            sentiment_journey = None
            if row["customer_sentiment_start"] and row["customer_sentiment_end"]:
                start = row["customer_sentiment_start"]
                end = row["customer_sentiment_end"]
                sentiment_journey = f"{start:.1f} -> {end:.1f}"

            examples.append(
                ExampleConversation(
                    conversation_id=row["conversation_id"],
                    example_type=example_type,
                    headline=row["situation_summary"] or row["call_type"] or "Call",
                    key_moment=dict(row["key_moment"]) if row["key_moment"] else None,
                    outcome=row["call_outcome"],
                    sentiment_journey=sentiment_journey,
                    scores={
                        "overall": row["overall_score"],
                        "empathy": row["empathy_score"],
                        "compliance": row["compliance_score"],
                    },
                    call_type=row["call_type"],
                    call_date=row["call_date"],
                )
            )

        return examples

    def get_agents_with_data(self, target_date: date) -> list[str]:
        """Get list of agents who have coaching data on a given date."""
        query = f"""
        SELECT DISTINCT agent_id
        FROM `{self.dataset}.coach_analysis`
        WHERE DATE(analyzed_at) = @target_date
        ORDER BY agent_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("target_date", "DATE", target_date),
            ]
        )

        result = self.client.query(query, job_config=job_config).result()
        return [row["agent_id"] for row in result]

    def get_agents_with_weekly_data(self, week_start: date) -> list[str]:
        """Get list of agents who have coaching data for a given week."""
        week_end = week_start + timedelta(days=6)

        query = f"""
        SELECT DISTINCT agent_id
        FROM `{self.dataset}.coach_analysis`
        WHERE DATE(analyzed_at) BETWEEN @week_start AND @week_end
        ORDER BY agent_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("week_start", "DATE", week_start),
                bigquery.ScalarQueryParameter("week_end", "DATE", week_end),
            ]
        )

        result = self.client.query(query, job_config=job_config).result()
        return [row["agent_id"] for row in result]
