import json
import os
import pathlib
import boto3
import jinja2
from jinja2 import Template

# ---------- Constants ----------
MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
BETA_PREFIX = os.getenv("BETA_PREFIX", "beta/")
PROD_PREFIX = os.getenv("PROD_PREFIX", "prod/")

# ---------- Helpers ----------

def get_region() -> str:
    """Return AWS region from env vars or raise a helpful error."""
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise ValueError(
            "[❌] No AWS region specified.\n"
            "➡️  Set AWS_REGION or AWS_DEFAULT_REGION (e.g., 'us-east-1')."
        )
    return region


def render_prompt(template_path: str, config: dict) -> str:
    """Render a Jinja2 prompt template with variables from config."""
    template = jinja2.Template(pathlib.Path(template_path).read_text())
    return template.render(**config["variables"])


def construct_body(prompt: str, max_tokens: int = 300) -> dict:
    """Create the invoke‑body expected by Amazon Bedrock."""
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [
            {"role": "user", "content": f"Human: {prompt}"}
        ],
    }


def call_bedrock(prompt: str, max_tokens: int, region: str) -> str:
    """Invoke Claude 3 via Bedrock and return the full text response."""
    br = boto3.client("bedrock-runtime", region_name=region)
    resp = br.invoke_model(
        body=json.dumps(construct_body(prompt, max_tokens)),
        modelId=MODEL_ID,
    )
    result = json.loads(resp["body"].read())
    return "".join(chunk["text"] for chunk in result["content"])


# ---------- Main workflow ----------
def main(env: str = "beta") -> None:
    """Render prompts, get completions, and upload results to S3."""
    region = get_region()
    s3 = boto3.client("s3", region_name=region)

    bucket = (
        os.getenv("S3_BUCKET_BETA")
        if env == "beta"
        else os.getenv("S3_BUCKET_PROD")
    )
    if not bucket:
        raise ValueError(
            f"[❌] No S3 bucket defined for environment '{env}'.\n"
            f"➡️  Set {'S3_BUCKET_BETA' if env == 'beta' else 'S3_BUCKET_PROD'}."
        )

    prefix = BETA_PREFIX if env == "beta" else PROD_PREFIX
    pathlib.Path("outputs").mkdir(exist_ok=True)

    for config_path in pathlib.Path("prompts").glob("*.json"):
        cfg = json.loads(config_path.read_text())

        # 1️⃣ Prompt text
        tmpl_file = f"prompt_templates/{config_path.stem.replace('_prompt', '')}.txt"
        rendered_prompt = render_prompt(tmpl_file, cfg)

        # 2️⃣ Output filename (render placeholders)
        filename_rendered = Template(cfg["output_file"]).render(**cfg["variables"])

        # 3️⃣ Claude 3 completion
        completion = call_bedrock(rendered_prompt, max_tokens=300, region=region)

        # 4️⃣ Write local file
        out_file = pathlib.Path("outputs") / filename_rendered
        out_file.write_text(completion, encoding="utf-8")

        # 5️⃣ Upload original file
        s3_key = f"{prefix}{filename_rendered}"
        s3.upload_file(
            out_file.as_posix(),
            bucket,
            s3_key,
            ExtraArgs={"ContentType": "text/html"}
        )
        print(f"✅ Uploaded ➜  s3://{bucket}/{s3_key}")

        # 6️⃣ OPTIONAL: also publish as index.html when requested
        if cfg.get("make_index", False):
            index_key = f"{prefix}index.html"
            s3.upload_file(
                out_file.as_posix(),
                bucket,
                index_key,
                ExtraArgs={"ContentType": "text/html"}
            )
            print(f"   ↪️  Also published as s3://{bucket}/{index_key}")

if __name__ == "__main__":
    main(os.getenv("DEPLOY_ENV", "beta"))
