# Conversation Coach - Cost Estimation

## Overview

This document provides cost estimates for the Conversation Coach pipeline running on GCP. Estimates are based on December 2025 pricing and typical usage patterns for a debt collection contact center.

## Assumptions

- **Daily conversation volume**: 500 conversations/day
- **Average conversation duration**: 5 minutes
- **Average transcript size**: 10 KB per conversation
- **Region**: us-central1

## Component Cost Breakdown

### 1. CCAI Insights

Contact Center AI Insights pricing is based on analyzed audio minutes.

| Tier | Price | Monthly Volume |
|------|-------|----------------|
| First 20,000 minutes | $0.024/minute | 500 × 5 min × 30 days = 75,000 min |
| 20,001 - 250,000 min | $0.018/minute | |

**Calculation:**
- First 20,000 min: 20,000 × $0.024 = $480
- Remaining 55,000 min: 55,000 × $0.018 = $990
- **Monthly CCAI cost**: ~$1,470

**Note:** For text-only transcripts (no audio), pricing may differ. Check current CCAI pricing.

### 2. BigQuery

| Component | Unit Price | Monthly Usage | Cost |
|-----------|------------|---------------|------|
| Storage | $0.02/GB/month | ~50 MB data | $0.001 |
| Queries (on-demand) | $5/TB scanned | ~1 GB/month | $0.005 |

**Monthly BigQuery cost**: ~$1 (negligible)

### 3. Cloud Storage (GCS)

| Component | Unit Price | Monthly Usage | Cost |
|-----------|------------|---------------|------|
| Standard storage | $0.020/GB/month | ~500 MB | $0.01 |
| Class A ops (write) | $0.005/1K ops | ~30K | $0.15 |
| Class B ops (read) | $0.0004/1K ops | ~60K | $0.024 |

**Monthly GCS cost**: ~$1 (negligible)

### 4. Future: Cloud Run (if deployed)

For event-driven processing:

| Component | Unit Price | Monthly Usage | Cost |
|-----------|------------|---------------|------|
| CPU | $0.00002400/vCPU-second | 500 × 30 × 60 sec = 900K sec | $21.60 |
| Memory | $0.00000250/GiB-second | 512 MB × 900K sec | $1.15 |
| Requests | $0.40/million | 15K requests | $0.006 |

**Monthly Cloud Run cost**: ~$25

### 5. Future: Vertex AI (CoachAgent)

For AI coaching card generation:

| Model | Price | Monthly Usage | Cost |
|-------|-------|---------------|------|
| Gemini 1.5 Pro (input) | $0.00125/1K chars | 500 × 30 × 5K chars = 75M chars | $93.75 |
| Gemini 1.5 Pro (output) | $0.00375/1K chars | 500 × 30 × 1K chars = 15M chars | $56.25 |

**Monthly Vertex AI cost**: ~$150

## Summary

### Current MVP Costs (Monthly)

| Component | Cost |
|-----------|------|
| CCAI Insights | $1,470 |
| BigQuery | $1 |
| GCS | $1 |
| **Total** | **~$1,472/month** |

### Per-Conversation Cost

- **CCAI Insights only**: $1,470 / (500 × 30) = **$0.098/conversation**
- **Full solution**: ~$1,472 / 15,000 = **$0.098/conversation**

### With Future Components (Monthly)

| Component | Cost |
|-----------|------|
| CCAI Insights | $1,470 |
| BigQuery | $1 |
| GCS | $1 |
| Cloud Run | $25 |
| Vertex AI | $150 |
| **Total** | **~$1,647/month** |

**Full solution per-conversation**: ~$0.11/conversation

## Daily Cost Breakdown

| Component | Daily Cost |
|-----------|------------|
| CCAI Insights | $49 |
| BigQuery | $0.03 |
| GCS | $0.03 |
| **Total MVP** | **~$49/day** |

With future components:
| Component | Daily Cost |
|-----------|------------|
| CCAI Insights | $49 |
| Cloud Run | $0.83 |
| Vertex AI | $5 |
| **Total Full** | **~$55/day** |

## Cost Optimization Strategies

### 1. CCAI Insights
- Use batch processing during off-peak hours
- Filter out very short calls (< 30 seconds)
- Consider sampling for quality monitoring vs. 100% analysis

### 2. BigQuery
- Use partitioned tables (by date)
- Set table expiration for old data
- Use clustering for frequently filtered columns

### 3. Cloud Run
- Configure minimum instances = 0 for cost savings
- Use concurrency settings to handle bursts
- Consider Cloud Functions for simpler workloads

### 4. Vertex AI
- Use Gemini Flash for simpler tasks
- Cache common coaching patterns
- Batch similar conversations

## Scaling Considerations

| Volume | Monthly CCAI Cost | Per-Conv Cost |
|--------|-------------------|---------------|
| 100/day | ~$300 | $0.10 |
| 500/day | ~$1,470 | $0.098 |
| 1,000/day | ~$2,700 | $0.09 |
| 5,000/day | ~$8,100 | $0.054 |

CCAI Insights has volume discounts - higher volumes reduce per-conversation costs.

## References

- [CCAI Insights Pricing](https://cloud.google.com/contact-center/insights/pricing)
- [BigQuery Pricing](https://cloud.google.com/bigquery/pricing)
- [Cloud Storage Pricing](https://cloud.google.com/storage/pricing)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Vertex AI Pricing](https://cloud.google.com/vertex-ai/pricing)
