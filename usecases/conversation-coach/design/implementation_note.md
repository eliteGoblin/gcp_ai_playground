
# Context

Requirement doc in /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/requirement.md

HLD doc in /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/design/HLD.md

Use requirement and HLD as context, only do task in LLD

You generate everything you generated in folder artifacts/

# MVP Task 

## Dev Data generation

Create GCS bucket, and required infra/IAM, using Terraform(everything as IaC), in folder artifacts/terraform, create a meaningful terraform file with name for this. 

### What to do
1) Pick a date folder: `2025-12-28/`
2) For each conversation, generate a UUID folder:
   - `2025-12-28/<UUID>/metadata.json`
   - `2025-12-28/<UUID>/transcription.json`
3) Upload the whole date folder to GCS (same structure).

### Data format
- `metadata.json`: deterministic business context (direction, line, queue, agent, campaign/portfolio, outcome, labels)
- `transcription.json`: realistic multi-turn transcript + timestamps offsets (seconds) + optional agent notes

Note:
* A few data been generated in folder /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/artifacts/data/dev/, check it, enrich it to correct mistake or make it more like real chat. 
* Keep PII(this is generated fake one, I want to use it to build dev pipeline for now)

### GCS upload plan
- Upload folder `2025-12-28/` to:
  - `gs://<PROJECT>-cc-dev/2025-12-28/...`

## Build initial local cli for MVP 

In local MVP, I want everything locally if can: instead of deploy code as lambda/cloud code, I want to focus on the functions of pipeline: have it implement as Python code, and call GCP cloud API/Vertex. i.e "AI coach workflow" run on my machine to "orchestrate" different parts. (instead of building event driven workflow at MVP steps)

I want you generate a python cli app for me in vertex_demo_cli/ folder

All the python code, inside this: I need function: 

* Support submit data (with data folder) into CI(provision needed CI infra in GCP, everything MUST in IaC, terraform). And also get data outside of CI. 
* Support interact with BigQuery Table

Note: 
* Also need to consider later I want to make this workflow running on GCP, e.g cloud run, etc. I want same code still mostly reusable. 
* For now, simplify things: everything cli upload all data in the local dev data, and send to CI. but when ingest into BigQuery, and when update CI exported data, need UPSERT logic, idempotent. 

### Subtask: provision BigQuery table 

* Consolodate the schema of BigQuery table
* Provision the BigQuery Table required: conversation_registry and CI exports 
* Prod grade consideration of BigQuery, not sure it need schema version/migration like plain SQL. 
* Your python code should considered using best-practice for GCP/Vertex/Data engineering for my scenario. Consider maintainable.

Note:
* I want you also create command that help me get info for human to verify the info in GCP: e.g could be CI exports, data in bigquery, etc.
* This cli can used bymyself to explore each step's data in my demo workflow. 
* So this step focus on makeing keep thing works. After MVP, we will discuss and implement the scaling.
* Python code should have proper unit test coverage, with mocking(unit test not interact with real API)

## Phrase matcher and align latest design schema with implemenation, re-analyze all conversation. 

# Task requirement stop here

IGNORE BELOW TASK and text

Next: doing each section one by one. 

Generate dev test data => ingest into GCS => Trigger job, record data in GCP etc(big query)


# Ref


Gpt conversation ref:

https://chatgpt.com/g/g-p-6949eef71b988191ad94ce159cbc075f-agentai/c/6949bd3d-82ec-8323-91b8-28fc202bac73

Mermaid Time Sequence:

