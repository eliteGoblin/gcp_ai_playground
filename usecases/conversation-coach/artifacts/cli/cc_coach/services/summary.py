"""
Summary Orchestrator Service.

Orchestrates the generation and storage of daily and weekly coaching summaries.
"""

import logging
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from google.cloud import bigquery

from cc_coach.agents.summary_coach import DailySummaryService, WeeklySummaryService
from cc_coach.config import get_settings
from cc_coach.schemas.summary import (
    DailySummary,
    ExampleConversation,
    WeeklySummary,
)
from cc_coach.services.aggregation import AggregationService

logger = logging.getLogger(__name__)


class SummaryOrchestrator:
    """Orchestrates daily and weekly summary generation."""

    def __init__(self, model: Optional[str] = None):
        self.settings = get_settings()
        self.client = bigquery.Client(project=self.settings.project_id)
        self.dataset = self.settings.bq_dataset_id
        self.model = model

        self.aggregation = AggregationService()
        self.daily_service = DailySummaryService(model=model)
        self.weekly_service = WeeklySummaryService(model=model)

    def generate_daily_summary(
        self, agent_id: str, target_date: date
    ) -> Optional[DailySummary]:
        """
        Generate and store daily summary for an agent.

        Returns None if no coaching data exists for the agent/date.
        """
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        logger.info(
            f"[{request_id}] Starting daily summary: agent={agent_id} date={target_date}"
        )

        try:
            # Step 1: Aggregate metrics
            logger.debug(f"[{request_id}] Aggregating metrics...")
            input_data = self.aggregation.get_daily_aggregation(agent_id, target_date)

            if not input_data:
                logger.info(
                    f"[{request_id}] No coaching data for {agent_id} on {target_date}"
                )
                return None

            logger.info(
                f"[{request_id}] Found {input_data.call_count} calls, "
                f"avg_overall={input_data.avg_overall}"
            )

            # Step 2: Generate LLM summary
            logger.debug(f"[{request_id}] Generating LLM summary...")
            llm_output = self.daily_service.generate_summary(input_data)

            logger.info(
                f"[{request_id}] LLM summary: focus={llm_output.focus_area} "
                f"latency_ms={self.daily_service.last_latency_ms}"
            )

            # Step 3: Build complete summary record
            summary = DailySummary(
                agent_id=agent_id,
                date=target_date,
                generated_at=datetime.now(timezone.utc),
                business_line=input_data.business_line,
                team=input_data.team,
                call_count=input_data.call_count,
                avg_empathy=input_data.avg_empathy,
                avg_compliance=input_data.avg_compliance,
                avg_resolution=input_data.avg_resolution,
                avg_professionalism=input_data.avg_professionalism,
                avg_efficiency=input_data.avg_efficiency,
                avg_de_escalation=input_data.avg_de_escalation,
                resolution_rate=input_data.resolution_rate,
                top_issues=input_data.top_issues,
                top_strengths=input_data.top_strengths,
                example_conversations=self._build_example_list(input_data),
                empathy_delta=self._calc_delta(
                    input_data.avg_empathy,
                    input_data.prev_day_avg_overall,
                ),
                compliance_delta=None,
                daily_narrative=llm_output.daily_narrative,
                focus_area=llm_output.focus_area,
                quick_wins=llm_output.quick_wins,
            )

            # Step 4: Store to BigQuery
            logger.debug(f"[{request_id}] Storing to BigQuery...")
            self._store_daily_summary(summary)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"[{request_id}] Daily summary complete: agent={agent_id} "
                f"date={target_date} calls={summary.call_count} "
                f"focus={summary.focus_area} duration_ms={duration_ms}"
            )

            return summary

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception(
                f"[{request_id}] Daily summary failed: {e} duration_ms={duration_ms}"
            )
            raise

    def generate_weekly_summary(
        self, agent_id: str, week_start: date
    ) -> Optional[WeeklySummary]:
        """
        Generate and store weekly summary for an agent.

        week_start should be a Monday. Returns None if no data exists.
        """
        # Ensure week_start is a Monday
        if week_start.weekday() != 0:
            week_start = week_start - timedelta(days=week_start.weekday())

        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        logger.info(
            f"[{request_id}] Starting weekly summary: agent={agent_id} "
            f"week={week_start}"
        )

        try:
            # Step 1: Aggregate metrics
            logger.debug(f"[{request_id}] Aggregating weekly metrics...")
            input_data = self.aggregation.get_weekly_aggregation(agent_id, week_start)

            if not input_data:
                logger.info(
                    f"[{request_id}] No coaching data for {agent_id} week of {week_start}"
                )
                return None

            logger.info(
                f"[{request_id}] Found {input_data.total_calls} calls over "
                f"{input_data.days_with_calls} days, avg_overall={input_data.week_avg_overall}"
            )

            # Step 2: Generate LLM summary
            logger.debug(f"[{request_id}] Generating LLM summary...")
            llm_output = self.weekly_service.generate_summary(input_data)

            logger.info(
                f"[{request_id}] LLM summary: training_recs={len(llm_output.recommended_training)} "
                f"latency_ms={self.weekly_service.last_latency_ms}"
            )

            # Step 3: Build complete summary record
            summary = WeeklySummary(
                agent_id=agent_id,
                week_start=week_start,
                generated_at=datetime.now(timezone.utc),
                business_line=input_data.business_line,
                team=input_data.team,
                empathy_score=input_data.week_avg_empathy,
                compliance_score=input_data.week_avg_compliance,
                resolution_score=input_data.week_avg_resolution,
                professionalism_score=input_data.week_avg_professionalism,
                efficiency_score=input_data.week_avg_efficiency,
                de_escalation_score=input_data.week_avg_de_escalation,
                empathy_delta=input_data.empathy_delta,
                compliance_delta=input_data.compliance_delta,
                resolution_delta=input_data.resolution_delta,
                total_calls=input_data.total_calls,
                resolution_rate=input_data.week_resolution_rate,
                compliance_breach_count=0,
                top_issues=input_data.top_issues,
                top_strengths=input_data.top_strengths,
                recommended_training=llm_output.recommended_training,
                weekly_summary=llm_output.weekly_summary,
                trend_analysis=llm_output.trend_analysis,
                action_plan=llm_output.action_plan,
                example_conversations=self._build_weekly_examples(input_data),
                daily_scores=input_data.daily_scores,
            )

            # Step 4: Store to BigQuery
            logger.debug(f"[{request_id}] Storing to BigQuery...")
            self._store_weekly_summary(summary)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"[{request_id}] Weekly summary complete: agent={agent_id} "
                f"week={week_start} calls={summary.total_calls} "
                f"training_recs={len(summary.recommended_training)} duration_ms={duration_ms}"
            )

            return summary

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception(
                f"[{request_id}] Weekly summary failed: {e} duration_ms={duration_ms}"
            )
            raise

    def generate_all_daily_summaries(self, target_date: date) -> dict:
        """Generate daily summaries for all agents with data on target_date."""
        agents = self.aggregation.get_agents_with_data(target_date)

        results = {"success": 0, "skipped": 0, "failed": 0, "agents": []}

        for agent_id in agents:
            try:
                summary = self.generate_daily_summary(agent_id, target_date)
                if summary:
                    results["success"] += 1
                    results["agents"].append(
                        {"agent_id": agent_id, "status": "success"}
                    )
                else:
                    results["skipped"] += 1
                    results["agents"].append(
                        {"agent_id": agent_id, "status": "skipped"}
                    )
            except Exception as e:
                results["failed"] += 1
                results["agents"].append(
                    {"agent_id": agent_id, "status": "failed", "error": str(e)}
                )

        return results

    def generate_all_weekly_summaries(self, week_start: date) -> dict:
        """Generate weekly summaries for all agents with data in the week."""
        # Ensure week_start is a Monday
        if week_start.weekday() != 0:
            week_start = week_start - timedelta(days=week_start.weekday())

        agents = self.aggregation.get_agents_with_weekly_data(week_start)

        results = {"success": 0, "skipped": 0, "failed": 0, "agents": []}

        for agent_id in agents:
            try:
                summary = self.generate_weekly_summary(agent_id, week_start)
                if summary:
                    results["success"] += 1
                    results["agents"].append(
                        {"agent_id": agent_id, "status": "success"}
                    )
                else:
                    results["skipped"] += 1
                    results["agents"].append(
                        {"agent_id": agent_id, "status": "skipped"}
                    )
            except Exception as e:
                results["failed"] += 1
                results["agents"].append(
                    {"agent_id": agent_id, "status": "failed", "error": str(e)}
                )

        return results

    def _build_example_list(self, input_data) -> list[ExampleConversation]:
        """Build example conversations list from daily input."""
        examples = []
        if input_data.best_conversation:
            examples.append(input_data.best_conversation)
        if input_data.worst_conversation:
            examples.append(input_data.worst_conversation)
        return examples

    def _build_weekly_examples(self, input_data) -> list[ExampleConversation]:
        """Build example conversations list from weekly input."""
        examples = []
        examples.extend(input_data.exemplary_conversations)
        examples.extend(input_data.needs_review_conversations)
        return examples

    def _calc_delta(
        self, current: Optional[float], previous: Optional[float]
    ) -> Optional[float]:
        """Calculate delta between current and previous value."""
        if current is None or previous is None:
            return None
        return round(current - previous, 1)

    def _store_daily_summary(self, summary: DailySummary) -> None:
        """Store daily summary to BigQuery using MERGE."""
        table_id = f"{self.dataset}.daily_agent_summary"

        # Convert example conversations to dict format
        examples_json = [
            {
                "conversation_id": ex.conversation_id,
                "example_type": ex.example_type,
                "headline": ex.headline,
                "key_moment": ex.key_moment,
                "outcome": ex.outcome,
                "sentiment_journey": ex.sentiment_journey,
                "scores": ex.scores,
                "call_type": ex.call_type,
            }
            for ex in summary.example_conversations
        ]

        # Use MERGE to upsert
        query = f"""
        MERGE `{table_id}` T
        USING (SELECT @agent_id as agent_id, @date as date) S
        ON T.agent_id = S.agent_id AND T.date = S.date
        WHEN MATCHED THEN UPDATE SET
            generated_at = @generated_at,
            business_line = @business_line,
            team = @team,
            call_count = @call_count,
            avg_empathy = @avg_empathy,
            avg_compliance = @avg_compliance,
            avg_resolution = @avg_resolution,
            avg_professionalism = @avg_professionalism,
            avg_efficiency = @avg_efficiency,
            avg_de_escalation = @avg_de_escalation,
            resolution_rate = @resolution_rate,
            top_issues = @top_issues,
            top_strengths = @top_strengths,
            daily_narrative = @daily_narrative,
            focus_area = @focus_area,
            quick_wins = @quick_wins,
            example_conversations = @example_conversations,
            empathy_delta = @empathy_delta,
            compliance_delta = @compliance_delta
        WHEN NOT MATCHED THEN INSERT (
            agent_id, date, generated_at, business_line, team,
            call_count, avg_empathy, avg_compliance, avg_resolution,
            avg_professionalism, avg_efficiency, avg_de_escalation,
            resolution_rate, top_issues, top_strengths,
            daily_narrative, focus_area, quick_wins,
            example_conversations, empathy_delta, compliance_delta
        ) VALUES (
            @agent_id, @date, @generated_at, @business_line, @team,
            @call_count, @avg_empathy, @avg_compliance, @avg_resolution,
            @avg_professionalism, @avg_efficiency, @avg_de_escalation,
            @resolution_rate, @top_issues, @top_strengths,
            @daily_narrative, @focus_area, @quick_wins,
            @example_conversations, @empathy_delta, @compliance_delta
        )
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", summary.agent_id),
                bigquery.ScalarQueryParameter("date", "DATE", summary.date),
                bigquery.ScalarQueryParameter(
                    "generated_at", "TIMESTAMP", summary.generated_at
                ),
                bigquery.ScalarQueryParameter(
                    "business_line", "STRING", summary.business_line
                ),
                bigquery.ScalarQueryParameter("team", "STRING", summary.team),
                bigquery.ScalarQueryParameter("call_count", "INT64", summary.call_count),
                bigquery.ScalarQueryParameter(
                    "avg_empathy", "FLOAT64", summary.avg_empathy
                ),
                bigquery.ScalarQueryParameter(
                    "avg_compliance", "FLOAT64", summary.avg_compliance
                ),
                bigquery.ScalarQueryParameter(
                    "avg_resolution", "FLOAT64", summary.avg_resolution
                ),
                bigquery.ScalarQueryParameter(
                    "avg_professionalism", "FLOAT64", summary.avg_professionalism
                ),
                bigquery.ScalarQueryParameter(
                    "avg_efficiency", "FLOAT64", summary.avg_efficiency
                ),
                bigquery.ScalarQueryParameter(
                    "avg_de_escalation", "FLOAT64", summary.avg_de_escalation
                ),
                bigquery.ScalarQueryParameter(
                    "resolution_rate", "FLOAT64", summary.resolution_rate
                ),
                bigquery.ArrayQueryParameter("top_issues", "STRING", summary.top_issues),
                bigquery.ArrayQueryParameter(
                    "top_strengths", "STRING", summary.top_strengths
                ),
                bigquery.ScalarQueryParameter(
                    "daily_narrative", "STRING", summary.daily_narrative
                ),
                bigquery.ScalarQueryParameter("focus_area", "STRING", summary.focus_area),
                bigquery.ArrayQueryParameter("quick_wins", "STRING", summary.quick_wins),
                bigquery.ScalarQueryParameter(
                    "example_conversations", "JSON", examples_json
                ),
                bigquery.ScalarQueryParameter(
                    "empathy_delta", "FLOAT64", summary.empathy_delta
                ),
                bigquery.ScalarQueryParameter(
                    "compliance_delta", "FLOAT64", summary.compliance_delta
                ),
            ]
        )

        self.client.query(query, job_config=job_config).result()

    def _store_weekly_summary(self, summary: WeeklySummary) -> None:
        """Store weekly summary to BigQuery using MERGE."""
        table_id = f"{self.dataset}.weekly_agent_report"

        # Convert example conversations to dict format
        examples_json = [
            {
                "conversation_id": ex.conversation_id,
                "example_type": ex.example_type,
                "headline": ex.headline,
                "key_moment": ex.key_moment,
                "outcome": ex.outcome,
                "sentiment_journey": ex.sentiment_journey,
                "scores": ex.scores,
                "call_type": ex.call_type,
                "call_date": str(ex.call_date) if ex.call_date else None,
            }
            for ex in summary.example_conversations
        ]

        # Use MERGE to upsert
        query = f"""
        MERGE `{table_id}` T
        USING (SELECT @agent_id as agent_id, @week_start as week_start) S
        ON T.agent_id = S.agent_id AND T.week_start = S.week_start
        WHEN MATCHED THEN UPDATE SET
            generated_at = @generated_at,
            business_line = @business_line,
            team = @team,
            empathy_score = @empathy_score,
            compliance_score = @compliance_score,
            resolution_score = @resolution_score,
            professionalism_score = @professionalism_score,
            efficiency_score = @efficiency_score,
            de_escalation_score = @de_escalation_score,
            empathy_delta = @empathy_delta,
            compliance_delta = @compliance_delta,
            resolution_delta = @resolution_delta,
            total_calls = @total_calls,
            resolution_rate = @resolution_rate,
            compliance_breach_count = @compliance_breach_count,
            top_issues = @top_issues,
            top_strengths = @top_strengths,
            recommended_training = @recommended_training,
            weekly_summary = @weekly_summary,
            trend_analysis = @trend_analysis,
            action_plan = @action_plan,
            example_conversations = @example_conversations,
            daily_scores = @daily_scores
        WHEN NOT MATCHED THEN INSERT (
            agent_id, week_start, generated_at, business_line, team,
            empathy_score, compliance_score, resolution_score,
            professionalism_score, efficiency_score, de_escalation_score,
            empathy_delta, compliance_delta, resolution_delta,
            total_calls, resolution_rate, compliance_breach_count,
            top_issues, top_strengths, recommended_training,
            weekly_summary, trend_analysis, action_plan,
            example_conversations, daily_scores
        ) VALUES (
            @agent_id, @week_start, @generated_at, @business_line, @team,
            @empathy_score, @compliance_score, @resolution_score,
            @professionalism_score, @efficiency_score, @de_escalation_score,
            @empathy_delta, @compliance_delta, @resolution_delta,
            @total_calls, @resolution_rate, @compliance_breach_count,
            @top_issues, @top_strengths, @recommended_training,
            @weekly_summary, @trend_analysis, @action_plan,
            @example_conversations, @daily_scores
        )
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", summary.agent_id),
                bigquery.ScalarQueryParameter("week_start", "DATE", summary.week_start),
                bigquery.ScalarQueryParameter(
                    "generated_at", "TIMESTAMP", summary.generated_at
                ),
                bigquery.ScalarQueryParameter(
                    "business_line", "STRING", summary.business_line
                ),
                bigquery.ScalarQueryParameter("team", "STRING", summary.team),
                bigquery.ScalarQueryParameter(
                    "empathy_score", "FLOAT64", summary.empathy_score
                ),
                bigquery.ScalarQueryParameter(
                    "compliance_score", "FLOAT64", summary.compliance_score
                ),
                bigquery.ScalarQueryParameter(
                    "resolution_score", "FLOAT64", summary.resolution_score
                ),
                bigquery.ScalarQueryParameter(
                    "professionalism_score", "FLOAT64", summary.professionalism_score
                ),
                bigquery.ScalarQueryParameter(
                    "efficiency_score", "FLOAT64", summary.efficiency_score
                ),
                bigquery.ScalarQueryParameter(
                    "de_escalation_score", "FLOAT64", summary.de_escalation_score
                ),
                bigquery.ScalarQueryParameter(
                    "empathy_delta", "FLOAT64", summary.empathy_delta
                ),
                bigquery.ScalarQueryParameter(
                    "compliance_delta", "FLOAT64", summary.compliance_delta
                ),
                bigquery.ScalarQueryParameter(
                    "resolution_delta", "FLOAT64", summary.resolution_delta
                ),
                bigquery.ScalarQueryParameter("total_calls", "INT64", summary.total_calls),
                bigquery.ScalarQueryParameter(
                    "resolution_rate", "FLOAT64", summary.resolution_rate
                ),
                bigquery.ScalarQueryParameter(
                    "compliance_breach_count", "INT64", summary.compliance_breach_count
                ),
                bigquery.ArrayQueryParameter("top_issues", "STRING", summary.top_issues),
                bigquery.ArrayQueryParameter(
                    "top_strengths", "STRING", summary.top_strengths
                ),
                bigquery.ArrayQueryParameter(
                    "recommended_training", "STRING", summary.recommended_training
                ),
                bigquery.ScalarQueryParameter(
                    "weekly_summary", "STRING", summary.weekly_summary
                ),
                bigquery.ScalarQueryParameter(
                    "trend_analysis", "STRING", summary.trend_analysis
                ),
                bigquery.ScalarQueryParameter("action_plan", "STRING", summary.action_plan),
                bigquery.ScalarQueryParameter(
                    "example_conversations", "JSON", examples_json
                ),
                bigquery.ScalarQueryParameter(
                    "daily_scores", "JSON", summary.daily_scores
                ),
            ]
        )

        self.client.query(query, job_config=job_config).result()

    def get_daily_summary(
        self, agent_id: str, target_date: date
    ) -> Optional[dict]:
        """Retrieve existing daily summary from BQ."""
        query = f"""
        SELECT *
        FROM `{self.dataset}.daily_agent_summary`
        WHERE agent_id = @agent_id AND date = @date
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
                bigquery.ScalarQueryParameter("date", "DATE", target_date),
            ]
        )

        result = list(self.client.query(query, job_config=job_config).result())
        return dict(result[0]) if result else None

    def get_weekly_summary(
        self, agent_id: str, week_start: date
    ) -> Optional[dict]:
        """Retrieve existing weekly summary from BQ."""
        # Ensure week_start is a Monday
        if week_start.weekday() != 0:
            week_start = week_start - timedelta(days=week_start.weekday())

        query = f"""
        SELECT *
        FROM `{self.dataset}.weekly_agent_report`
        WHERE agent_id = @agent_id AND week_start = @week_start
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("agent_id", "STRING", agent_id),
                bigquery.ScalarQueryParameter("week_start", "DATE", week_start),
            ]
        )

        result = list(self.client.query(query, job_config=job_config).result())
        return dict(result[0]) if result else None
