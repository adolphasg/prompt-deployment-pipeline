# generate_and_upload.py
import json
import os
import pathlib
import boto3
import jinja2

# ---------- Constants ----------
MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
BETA_PREFIX = os.getenv("BETA_PREFIX", "beta/")
PROD_PREFIX = os.getenv("PROD_PREFIX", "prod/")

# ---------- Helpers ----------
def render_prompt(template_path: str, config: dict) -> str:
    """Fill a Jinja2 template with variables from a JSON config file."""
    template = jinja2.Template(pathlib.Path(template_path).read_text())
    return template.render(**config["variables"])


def construct_body(prompt: str, max_tokens: int = 2000) -> dict:
    """Build the Bedrock request payload."""
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [
            {"role": "user", "content": f"Human: {prompt}"}
        ],
    }


def call_bedrock(prompt: str, max_tokens: int = 2000) -> str:
    """Send the prompt to Bedrock and return Claude’s text completion."""
    br = boto3.client("bedrock-runtime")
    resp = br.invoke_model(
        body=json.dumps(construct_body(prompt, max_tokens)),
        modelId=MODEL_ID,
    )
    result = json.loads(resp["body"].read())
    # Claude 3 returns an array of chunks in result["content"]
    return "".join(chunk["text"] for chunk in result["content"])


# ---------- Main workflow ----------
def main(env: str = "beta") -> None:
    s3 = boto3.client("s3")

    # Pick the bucket for this environment
    bucket = (
        os.getenv("S3_BUCKET_BETA")
        if env == "beta"
        else os.getenv("S3_BUCKET_PROD")
    )

    # 🔒  Guard clause — keep this INSIDE main()
    if not bucket:
        raise ValueError(
            f"[❌] No S3 bucket defined for environment '{env}'.\n"
            f"➡️  Set "
            f"{'S3_BUCKET_BETA' if env == 'beta' else 'S3_BUCKET_PROD'} "
            f"and try again."
        )

    prefix = BETA_PREFIX if env == "beta" else PROD_PREFIX
    pathlib.Path("outputs").mkdir(exist_ok=True)

    for config_path in pathlib.Path("prompts").glob("*.json"):
        cfg = json.loads(config_path.read_text())

        # 1️⃣ Render template → prompt text
        tmpl_file = f"prompt_templates/{config_path.stem.replace('_prompt', '')}.txt"
        rendered_prompt = render_prompt(tmpl_file, cfg)

        # 2️⃣ Send to Bedrock → completion
        completion = call_bedrock(rendered_prompt)

        # 3️⃣ Write to disk
        out_file = pathlib.Path("outputs") / cfg["output_file"]
        out_file.write_text(completion, encoding="utf-8")

        # 4️⃣ Upload to S3
        s3_key = f"{prefix}{out_file.name}"
        s3.upload_file(out_file.as_posix(), bucket, s3_key, ExtraArgs={"ContentType": "text/html"})
        print(f"Uploaded ➜  s3://{bucket}/{s3_key}")


if __name__ == "__main__":
    # Default to “beta” if DEPLOY_ENV isn’t set
    main(os.getenv("DEPLOY_ENV", "beta"))
    
