# GCP AI Playground

Learning and experimentation repository for GCP AI/ML services, focusing on AIOps best practices.

## Structure

```
gcp_ai_playground/
│
├── usecases/                        # Project-based learning
│   │
│   ├── vertex-ai-llm-hosting/       # LLM deployment on Vertex AI
│   │   ├── requirement.md           # Goals and status
│   │   ├── terraform/               # Infrastructure as Code
│   │   ├── models/                  # Model packaging, custom code
│   │   ├── evals/                   # Evaluation framework
│   │   └── docs/                    # Technical documentation
│   │
│   ├── langfuse-observability/      # LLM observability with Langfuse
│   │   ├── requirement.md
│   │   ├── scripts/                 # Demo scripts
│   │   └── docs/
│   │
│   └── conversation-coach/          # AI coaching for contact center
│       ├── requirement.md           # Main focus area
│       ├── design/                  # HLD, LLD documents
│       ├── agents/                  # ADK agents
│       └── pipelines/               # Data pipelines
│
├── docs/                            # Shared documentation
│   ├── aiops-framework.md
│   ├── aiops_mindset.md
│   └── governance/
│
└── .github/
    └── workflows/                   # CI/CD pipelines
```

## Usecases

| Usecase | Description | Status |
|---------|-------------|--------|
| **vertex-ai-llm-hosting** | Deploy and manage LLMs on Vertex AI | Completed |
| **langfuse-observability** | LLM tracing and prompt management | Demo ready |
| **conversation-coach** | AI agent for contact center coaching | In Progress |

## Key Learnings

### AIOps Pillars

1. **Infrastructure as Code** - Terraform for Vertex AI
2. **Model Lifecycle** - Registry, versioning, deployment
3. **CI/CD** - GitHub Actions for model builds
4. **Observability** - Langfuse for tracing
5. **Evaluation** - Golden datasets, LLM-as-judge
6. **Governance** - PII handling, compliance

### Technologies

- GCP Vertex AI
- Terraform
- Python
- GitHub Actions
- Langfuse
- ADK (Agent Development Kit)
