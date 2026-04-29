"""
Upload NuClick model to HuggingFace Model Hub.

Usage:
  1) Authenticate in your terminal (do NOT share token here):
     hf auth login

  2) Run this script from project root:
     python upload_nuclick.py --username YOUR_HF_USERNAME

The script will:
  - create repo `YOUR_HF_USERNAME/grid-image-analyzer` (if missing)
  - upload `app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth`
  - print the public URL for the model

Requires: huggingface_hub
  pip install huggingface_hub
"""

import argparse
import sys
from huggingface_hub import HfApi
from pathlib import Path

LOCAL_PATH = Path("app/infrastructure/ml_models/nuclick_torch/weights/nuclick.pth")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True, help="Your HuggingFace username")
    parser.add_argument("--private", action='store_true', help="Create private repo (default public)")
    args = parser.parse_args()

    if not LOCAL_PATH.exists():
        print(f"ERROR: local file not found: {LOCAL_PATH}")
        sys.exit(2)

    api = HfApi()
    repo_id = f"{args.username}/grid-image-analyzer"

    # Create repo if it doesn't exist
    try:
        print(f"Creating repo {repo_id} (public={not args.private}) if missing...")
        api.create_repo(repo_id=repo_id, repo_type="model", private=args.private)
    except Exception as e:
        print(f"Note: create_repo returned: {e}")

    print("Uploading file...")
    try:
        api.upload_file(
            path_or_fileobj=str(LOCAL_PATH),
            path_in_repo="nuclick.pth",
            repo_id=repo_id,
            repo_type="model",
            create_pr=False,
        )
    except Exception as e:
        print("Upload failed:", e)
        sys.exit(1)

    url = f"https://huggingface.co/{repo_id}/resolve/main/nuclick.pth"
    print("Upload complete. Public URL:")
    print(url)


if __name__ == '__main__':
    main()
