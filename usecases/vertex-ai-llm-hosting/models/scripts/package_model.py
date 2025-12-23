#!/usr/bin/env python3
"""
=============================================================================
Model Packaging Script
=============================================================================
Purpose: Package model artifacts into a versioned bundle for Vertex AI

What this script does:
1. Downloads base model from HuggingFace (or uses fine-tuned weights)
2. Copies custom code (predictor, guardrails)
3. Creates proper directory structure
4. Uploads to GCS with version tag
5. Registers in Vertex AI Model Registry

Usage:
    python package_model.py \
        --model-name loan-assessor \
        --version v1.0.0 \
        --base-model google/gemma-3-1b-it \
        --bucket gs://vertexdemo-481519-model-artifacts

=============================================================================
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


def run_cmd(cmd: str, check: bool = True) -> str:
    """Run shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result.stdout.strip()


def download_base_model(model_id: str, output_dir: Path) -> None:
    """Download model from HuggingFace."""
    print(f"Downloading base model: {model_id}")

    # Using huggingface_hub to download
    # In real setup, use: huggingface-cli download {model_id} --local-dir {output_dir}
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=model_id,
        local_dir=str(output_dir / "model"),
        local_dir_use_symlinks=False,
    )
    print(f"Downloaded to: {output_dir / 'model'}")


def copy_custom_code(source_dir: Path, output_dir: Path) -> None:
    """Copy custom predictor code to bundle."""
    custom_code_dir = output_dir / "custom_code"
    custom_code_dir.mkdir(exist_ok=True)

    # Copy predictor and requirements
    for file in ["predictor.py", "guardrails.py", "requirements.txt"]:
        src = source_dir / file
        if src.exists():
            shutil.copy(src, custom_code_dir / file)
            print(f"Copied: {file}")


def create_model_card(output_dir: Path, config: dict) -> None:
    """Create model card with metadata."""
    model_card = f"""# {config['model_name']} - {config['version']}

## Model Information

| Field | Value |
|-------|-------|
| **Name** | {config['model_name']} |
| **Version** | {config['version']} |
| **Base Model** | {config['base_model']} |
| **Created** | {config['created_at']} |
| **Owner** | {config.get('owner', 'ml-team')} |

## Description

{config.get('description', 'No description provided.')}

## Usage

```python
from google.cloud import aiplatform

endpoint = aiplatform.Endpoint('{config.get("endpoint_id", "YOUR_ENDPOINT_ID")}')
response = endpoint.predict(instances=[{{"prompt": "Hello"}}])
```

## Training Data

{config.get('training_data_description', 'Base model, no fine-tuning.')}

## Evaluation

{config.get('evaluation_results', 'No evaluation results available.')}

## Changelog

- **{config['version']}** ({config['created_at']}): {config.get('changelog', 'Initial release')}
"""

    with open(output_dir / "model_card.md", "w") as f:
        f.write(model_card)
    print("Created: model_card.md")


def create_serving_config(output_dir: Path, config: dict) -> None:
    """Create serving configuration."""
    serving_config = {
        "model_name": config["model_name"],
        "version": config["version"],
        "container": {
            "image": config.get(
                "container_image",
                "us-docker.pkg.dev/vertex-ai/prediction/pytorch-vllm-serve:latest"
            ),
            "predict_route": "/predict",
            "health_route": "/health",
            "ports": [8080],
        },
        "resources": {
            "machine_type": config.get("machine_type", "g2-standard-12"),
            "accelerator_type": config.get("accelerator_type", "NVIDIA_L4"),
            "accelerator_count": config.get("accelerator_count", 1),
        },
        "autoscaling": {
            "min_replicas": config.get("min_replicas", 1),
            "max_replicas": config.get("max_replicas", 1),
        },
    }

    with open(output_dir / "serving_config.json", "w") as f:
        json.dump(serving_config, f, indent=2)
    print("Created: serving_config.json")


def upload_to_gcs(local_dir: Path, gcs_uri: str) -> None:
    """Upload bundle to GCS."""
    print(f"Uploading to: {gcs_uri}")
    run_cmd(f"gsutil -m cp -r {local_dir}/* {gcs_uri}/")
    print("Upload complete")


def register_model(
    project_id: str,
    region: str,
    model_name: str,
    version: str,
    artifact_uri: str,
    container_image: str,
) -> str:
    """Register model in Vertex AI Model Registry."""
    print(f"Registering model: {model_name}@{version}")

    # Use gcloud to register
    # This creates a model resource in Vertex AI that points to GCS artifacts
    cmd = f"""
    gcloud ai models upload \\
        --region={region} \\
        --display-name="{model_name}-{version}" \\
        --artifact-uri="{artifact_uri}" \\
        --container-image-uri="{container_image}" \\
        --container-predict-route="/predict" \\
        --container-health-route="/health" \\
        --version-aliases="{version}" \\
        --format="value(name)"
    """

    model_resource = run_cmd(cmd)
    print(f"Registered: {model_resource}")
    return model_resource


def main():
    parser = argparse.ArgumentParser(description="Package model for Vertex AI")
    parser.add_argument("--model-name", required=True, help="Model name (e.g., loan-assessor)")
    parser.add_argument("--version", required=True, help="Version tag (e.g., v1.0.0)")
    parser.add_argument("--base-model", required=True, help="HuggingFace model ID")
    parser.add_argument("--bucket", required=True, help="GCS bucket URI")
    parser.add_argument("--custom-code-dir", default="./custom_code", help="Custom code directory")
    parser.add_argument("--project-id", default="vertexdemo-481519", help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--description", default="", help="Model description")
    parser.add_argument("--skip-download", action="store_true", help="Skip model download")
    parser.add_argument("--skip-register", action="store_true", help="Skip model registration")
    parser.add_argument("--fine-tuned-weights", help="Path to fine-tuned weights (instead of download)")

    args = parser.parse_args()

    # Configuration
    config = {
        "model_name": args.model_name,
        "version": args.version,
        "base_model": args.base_model,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d"),
        "description": args.description or f"{args.model_name} based on {args.base_model}",
        "container_image": "us-docker.pkg.dev/vertex-ai/prediction/pytorch-vllm-serve:latest",
    }

    # Create temp directory for packaging
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / args.model_name / args.version
        output_dir.mkdir(parents=True)

        print(f"\n=== Packaging {args.model_name}@{args.version} ===\n")

        # Step 1: Get model weights
        if args.fine_tuned_weights:
            # Use fine-tuned weights
            print(f"Using fine-tuned weights: {args.fine_tuned_weights}")
            shutil.copytree(args.fine_tuned_weights, output_dir / "model")
        elif not args.skip_download:
            # Download base model
            download_base_model(args.base_model, output_dir)

        # Step 2: Copy custom code
        custom_code_path = Path(args.custom_code_dir)
        if custom_code_path.exists():
            copy_custom_code(custom_code_path, output_dir)

        # Step 3: Create model card
        create_model_card(output_dir, config)

        # Step 4: Create serving config
        create_serving_config(output_dir, config)

        # Step 5: Show bundle structure
        print("\n=== Bundle Structure ===")
        for f in output_dir.rglob("*"):
            if f.is_file():
                rel_path = f.relative_to(output_dir)
                print(f"  {rel_path}")

        # Step 6: Upload to GCS
        gcs_uri = f"{args.bucket}/models/{args.model_name}/{args.version}"
        upload_to_gcs(output_dir, gcs_uri)

        # Step 7: Register in Model Registry
        if not args.skip_register:
            model_resource = register_model(
                project_id=args.project_id,
                region=args.region,
                model_name=args.model_name,
                version=args.version,
                artifact_uri=gcs_uri,
                container_image=config["container_image"],
            )
            print(f"\n=== Model Registered ===")
            print(f"Resource: {model_resource}")

        print(f"\n=== Done ===")
        print(f"Artifacts: {gcs_uri}")


if __name__ == "__main__":
    main()
