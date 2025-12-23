# Vertex AI LLM Hosting Demo

## Overview

Demo project for understanding LLM deployment on GCP Vertex AI with AIOps best practices.

## Goals

- Deploy LLM model on Vertex AI (Gemma 3 1B)
- Learn core concepts: Model Registry, Endpoints, machine types, GPUs
- Implement AIOps patterns: IaC, CI/CD, monitoring, governance
- Build foundation for future RAG applications

## Key Concepts Covered

- **Infrastructure**: Terraform for Vertex AI endpoints, service accounts, IAM
- **Model Lifecycle**: Model Garden → Registry → Endpoint deployment
- **Custom Code**: Predictor classes for pre/post processing
- **Evaluation**: Golden dataset testing, LLM-as-judge patterns
- **CI/CD**: GitHub Actions for model build and deployment

## Status

- [x] Model deployed (Gemma 3 1B)
- [x] Terraform infrastructure
- [x] CI/CD pipelines
- [x] Eval framework
- [x] Documentation
- [x] Cleanup (resources deleted to save cost)
