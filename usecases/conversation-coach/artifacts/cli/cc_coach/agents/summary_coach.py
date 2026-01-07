"""
Summary Coach ADK Agents.

Generates daily and weekly coaching summaries using Google ADK framework.
"""

import json
import logging
import time
import uuid
from typing import Optional

from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from cc_coach.schemas.summary import (
    DailySummaryInput,
    DailySummaryOutput,
    WeeklySummaryInput,
    WeeklySummaryOutput,
)

logger = logging.getLogger(__name__)

MODEL_VERSION = "gemini-2.5-flash"

# Daily Summary Prompt
DAILY_SUMMARY_PROMPT = """You are a contact center coaching analyst. Your task is to generate a brief, actionable daily summary for an agent based on their coaching metrics.

## Input Format
You will receive:
- Agent metrics for the day (scores, call count)
- Comparison to previous day (if available)
- Top issues and strengths identified
- Example conversations (best and worst of the day)

## Output Requirements

Generate a JSON object with:

1. `daily_narrative`: A 2-3 sentence evidence-based summary. Must:
   - Start with the agent's overall performance level
   - Reference specific metrics or examples
   - Be constructive, not discouraging
   - If no previous day data, don't mention trends

2. `focus_area`: Single dimension to focus on (empathy, compliance, resolution, professionalism, de_escalation, efficiency)
   - Choose based on lowest score OR biggest drop from previous day
   - If all scores are high (>=8), choose the one that could still improve

3. `coaching_advice`: One specific, actionable piece of advice related to the focus area
   - Reference specific issues or examples if available
   - Keep it practical and implementable

4. `quick_wins`: 1-3 easy improvements the agent can make tomorrow
   - Based on the issues and examples provided
   - Should be specific and actionable

## Example Output

```json
{
  "daily_narrative": "Strong performance today with an 8.2 overall score across 5 calls. Empathy was your standout at 9.0, particularly in the hardship call where you acknowledged the customer's situation. Compliance dipped slightly to 7.0 - review the disclosure requirements.",
  "focus_area": "compliance",
  "coaching_advice": "When discussing payment arrangements, ensure you complete the Mini-Miranda disclosure before discussing amounts.",
  "quick_wins": [
    "Use the compliance checklist before ending hardship calls",
    "Pause after disclosures to confirm customer understanding"
  ]
}
```

## Handling Edge Cases

- If no previous day data: Focus on absolute performance, don't mention trends
- If call_count is low (1-2): Note it's a small sample, focus on specific call feedback
- If all scores are high: Acknowledge excellence, suggest refinement not major changes
- If scores are concerning (<6): Be encouraging but direct about improvement areas
"""

# Weekly Summary Prompt
WEEKLY_SUMMARY_PROMPT = """You are a contact center coaching analyst. Your task is to generate a comprehensive weekly performance summary for an agent.

## Input Format
You will receive:
- Week metrics (total calls, average scores)
- Daily score breakdown
- Comparison to previous week (if available)
- Top issues and strengths patterns
- Exemplary and needs-review conversation examples

## Output Requirements

Generate a JSON object with:

1. `weekly_summary`: A 3-5 sentence evidence-based summary covering:
   - Overall performance assessment for the week
   - Key trends observed (improving/declining areas)
   - Notable patterns in issues or strengths
   - Reference specific examples or metrics

2. `trend_analysis`: 1-2 sentences specifically about what's improving or declining
   - Compare to previous week if data available
   - If no previous week, analyze day-over-day within the week
   - Be specific about which dimensions

3. `action_plan`: 2-3 specific, prioritized actions for next week
   - Based on the identified issues
   - Should be measurable or observable
   - Prioritize compliance/critical issues first

4. `recommended_training`: 0-3 suggested training modules (only if clearly needed)
   - Map to common training modules: "Active Listening", "Compliance Basics", "De-escalation Techniques", "Empathy Building", "Efficient Call Handling", "Hardship Program Guide"
   - Only suggest if scores in that area are consistently below 7

## Example Output

```json
{
  "weekly_summary": "Solid week with 24 calls and an 8.1 average overall score. Empathy remained consistently strong (8.5 avg), showing genuine care for customers in hardship situations. Compliance showed improvement mid-week after the Monday dip, ending at 8.0. Resolution was the growth opportunity at 7.2, with 3 calls requiring callbacks that could have been handled in one contact.",
  "trend_analysis": "Empathy improved from 7.8 last week to 8.5 this week - the active listening focus is paying off. Efficiency declined slightly (7.5 to 7.0) likely due to longer empathy-building conversations, which is an acceptable trade-off.",
  "action_plan": "1. Before callbacks: verify you have all information needed for resolution. 2. Use the payment calculator during calls rather than promising to call back with amounts. 3. Continue the strong empathy approach - it's driving customer satisfaction.",
  "recommended_training": ["Efficient Call Handling"]
}
```

## Handling Edge Cases

- No previous week data: Focus on within-week trends and absolute performance
- Low call volume (<5): Note small sample, focus on qualitative feedback
- All scores high: Acknowledge excellence, suggest stretch goals
- Concerning patterns: Be direct but constructive about improvement needs
"""


class DailySummaryService:
    """Service to generate daily coaching summaries using ADK."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or MODEL_VERSION
        self.last_latency_ms: int = 0

    def generate_summary(self, input_data: DailySummaryInput) -> DailySummaryOutput:
        """Generate daily summary narrative using ADK agent."""
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Create ADK Agent
        agent = Agent(
            name="daily_summary_coach",
            model=self.model,
            instruction=DAILY_SUMMARY_PROMPT,
            output_schema=DailySummaryOutput,
            generate_content_config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )

        # Format input for LLM
        user_message = self._format_input(input_data)

        logger.info(
            f"[{request_id}] Daily summary request: agent={input_data.agent_id} "
            f"date={input_data.date} calls={input_data.call_count}"
        )

        try:
            # Create session service and runner
            session_service = InMemorySessionService()
            runner = Runner(
                agent=agent,
                app_name="daily_summary_coach",
                session_service=session_service,
            )

            session_id = f"daily-{input_data.agent_id}-{input_data.date}"
            session_service.create_session_sync(
                app_name="daily_summary_coach",
                user_id=input_data.agent_id,
                session_id=session_id,
            )

            # Run agent
            result_text = ""
            for event in runner.run(
                user_id=input_data.agent_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=user_message)],
                ),
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            result_text += part.text

            self.last_latency_ms = int((time.time() - start_time) * 1000)

            # Parse response
            result_json = json.loads(result_text)
            output = DailySummaryOutput.model_validate(result_json)

            logger.info(
                f"[{request_id}] Daily summary generated: agent={input_data.agent_id} "
                f"focus={output.focus_area} latency_ms={self.last_latency_ms}"
            )

            return output

        except Exception as e:
            logger.error(f"[{request_id}] Daily summary failed: {e}")
            raise

    def _format_input(self, data: DailySummaryInput) -> str:
        """Format input data for LLM."""
        lines = [
            f"## Agent: {data.agent_id}",
            f"## Date: {data.date}",
            f"## Business Line: {data.business_line or 'N/A'}",
            "",
            "## Today's Metrics",
            f"- Calls: {data.call_count}",
            f"- Overall Score: {data.avg_overall}/10",
            f"- Empathy: {data.avg_empathy}/10",
            f"- Compliance: {data.avg_compliance}/10",
            f"- Resolution: {data.avg_resolution}/10",
            f"- Professionalism: {data.avg_professionalism}/10",
            f"- De-escalation: {data.avg_de_escalation}/10",
            f"- Efficiency: {data.avg_efficiency}/10",
            f"- Resolution Rate: {data.resolution_rate * 100:.0f}%",
        ]

        # Previous day comparison
        if data.prev_day_avg_overall:
            lines.extend(
                [
                    "",
                    "## Previous Day Comparison",
                    f"- Previous Overall: {data.prev_day_avg_overall}/10",
                    f"- Previous Calls: {data.prev_day_call_count}",
                    f"- Change: {data.overall_delta:+.1f} ({data.trend_direction})",
                ]
            )

        # Issues and strengths
        if data.top_issues:
            lines.extend(["", "## Top Issues Today"])
            for issue in data.top_issues[:5]:
                lines.append(f"- {issue}")

        if data.top_strengths:
            lines.extend(["", "## Top Strengths Today"])
            for strength in data.top_strengths[:5]:
                lines.append(f"- {strength}")

        # Example conversations
        if data.best_conversation:
            bc = data.best_conversation
            lines.extend(
                [
                    "",
                    "## Best Call Today",
                    f"- Type: {bc.call_type or 'N/A'}",
                    f"- Score: {bc.scores.get('overall', 'N/A')}/10",
                    f"- Headline: {bc.headline}",
                ]
            )
            if bc.key_moment:
                lines.append(f"- Key Moment: \"{bc.key_moment.get('quote', '')}\"")

        if data.worst_conversation:
            wc = data.worst_conversation
            lines.extend(
                [
                    "",
                    "## Call Needing Review",
                    f"- Type: {wc.call_type or 'N/A'}",
                    f"- Score: {wc.scores.get('overall', 'N/A')}/10",
                    f"- Headline: {wc.headline}",
                ]
            )
            if wc.key_moment:
                lines.append(f"- Key Moment: \"{wc.key_moment.get('quote', '')}\"")

        return "\n".join(lines)


class WeeklySummaryService:
    """Service to generate weekly coaching summaries using ADK."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or MODEL_VERSION
        self.last_latency_ms: int = 0

    def generate_summary(self, input_data: WeeklySummaryInput) -> WeeklySummaryOutput:
        """Generate weekly summary narrative using ADK agent."""
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Create ADK Agent
        agent = Agent(
            name="weekly_summary_coach",
            model=self.model,
            instruction=WEEKLY_SUMMARY_PROMPT,
            output_schema=WeeklySummaryOutput,
            generate_content_config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )

        # Format input for LLM
        user_message = self._format_input(input_data)

        logger.info(
            f"[{request_id}] Weekly summary request: agent={input_data.agent_id} "
            f"week={input_data.week_start} calls={input_data.total_calls}"
        )

        try:
            # Create session service and runner
            session_service = InMemorySessionService()
            runner = Runner(
                agent=agent,
                app_name="weekly_summary_coach",
                session_service=session_service,
            )

            session_id = f"weekly-{input_data.agent_id}-{input_data.week_start}"
            session_service.create_session_sync(
                app_name="weekly_summary_coach",
                user_id=input_data.agent_id,
                session_id=session_id,
            )

            # Run agent
            result_text = ""
            for event in runner.run(
                user_id=input_data.agent_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=user_message)],
                ),
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            result_text += part.text

            self.last_latency_ms = int((time.time() - start_time) * 1000)

            # Parse response
            result_json = json.loads(result_text)
            output = WeeklySummaryOutput.model_validate(result_json)

            logger.info(
                f"[{request_id}] Weekly summary generated: agent={input_data.agent_id} "
                f"training_recs={len(output.recommended_training)} latency_ms={self.last_latency_ms}"
            )

            return output

        except Exception as e:
            logger.error(f"[{request_id}] Weekly summary failed: {e}")
            raise

    def _format_input(self, data: WeeklySummaryInput) -> str:
        """Format input data for LLM."""
        lines = [
            f"## Agent: {data.agent_id}",
            f"## Week: {data.week_start} to {data.week_end}",
            f"## Business Line: {data.business_line or 'N/A'}",
            "",
            "## Week Metrics",
            f"- Total Calls: {data.total_calls}",
            f"- Days with Calls: {data.days_with_calls}",
            f"- Overall Score: {data.week_avg_overall}/10",
            f"- Empathy: {data.week_avg_empathy}/10",
            f"- Compliance: {data.week_avg_compliance}/10",
            f"- Resolution: {data.week_avg_resolution}/10",
            f"- Professionalism: {data.week_avg_professionalism}/10",
            f"- De-escalation: {data.week_avg_de_escalation}/10",
            f"- Efficiency: {data.week_avg_efficiency}/10",
            f"- Resolution Rate: {data.week_resolution_rate * 100:.0f}%",
        ]

        # Previous week comparison
        if data.prev_week_avg_overall:
            lines.extend(
                [
                    "",
                    "## Previous Week Comparison",
                    f"- Previous Overall: {data.prev_week_avg_overall}/10",
                    f"- Previous Calls: {data.prev_week_total_calls}",
                    f"- Overall Change: {data.overall_delta:+.1f}" if data.overall_delta else "- Overall Change: N/A",
                    f"- Empathy Change: {data.empathy_delta:+.1f}" if data.empathy_delta else "- Empathy Change: N/A",
                    f"- Compliance Change: {data.compliance_delta:+.1f}" if data.compliance_delta else "- Compliance Change: N/A",
                ]
            )

        # Daily breakdown
        if data.daily_scores:
            lines.extend(["", "## Daily Breakdown"])
            for day in data.daily_scores:
                lines.append(
                    f"- {day.get('date', 'N/A')}: {day.get('call_count', 0)} calls, "
                    f"empathy={day.get('avg_empathy', 'N/A')}, "
                    f"compliance={day.get('avg_compliance', 'N/A')}"
                )

        # Issues and strengths
        if data.top_issues:
            lines.extend(["", "## Top Issues This Week"])
            for issue in data.top_issues[:5]:
                lines.append(f"- {issue}")

        if data.top_strengths:
            lines.extend(["", "## Top Strengths This Week"])
            for strength in data.top_strengths[:5]:
                lines.append(f"- {strength}")

        # Example conversations
        if data.exemplary_conversations:
            lines.extend(["", "## Exemplary Calls"])
            for conv in data.exemplary_conversations:
                lines.append(
                    f"- {conv.call_date}: {conv.headline} (score: {conv.scores.get('overall', 'N/A')})"
                )

        if data.needs_review_conversations:
            lines.extend(["", "## Calls Needing Review"])
            for conv in data.needs_review_conversations:
                lines.append(
                    f"- {conv.call_date}: {conv.headline} (score: {conv.scores.get('overall', 'N/A')})"
                )

        return "\n".join(lines)
