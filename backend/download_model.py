"""
BioMistral-7B Model Downloader

Downloads BioMistral-7B-GGUF (Q4_K_M quantization) from HuggingFace.
Uses huggingface_hub for reliable, resumable downloads with progress bars.

Usage:
    python download_model.py           -- Download the model
    python download_model.py --check   -- Verify model is present and valid
"""

import argparse
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ID = "BioMistral/BioMistral-7B-GGUF"
FILENAME = "BioMistral-7B.Q4_K_M.gguf"
MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / FILENAME

# Q4_K_M is the best balance of size vs accuracy for CPU inference
# Size: ~4.4 GB | RAM needed: ~6 GB | Quality: near-lossless vs fp16
EXPECTED_SIZE_GB = 4.4


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def check_model() -> bool:
    """Return True if model file exists and has a reasonable size."""
    if not MODEL_PATH.exists():
        print(f"  ✗ Model not found at: {MODEL_PATH}")
        return False

    size_gb = MODEL_PATH.stat().st_size / (1024 ** 3)
    if size_gb < 1.0:
        print(f"  ✗ Model file looks corrupt (only {size_gb:.2f} GB). Re-downloading.")
        MODEL_PATH.unlink()
        return False

    print(f"  ✓ Model found: {MODEL_PATH}")
    print(f"  ✓ Size: {size_gb:.2f} GB")
    return True


def download_model() -> bool:
    """Download BioMistral-7B Q4_K_M from HuggingFace Hub."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub is not installed.")
        print("Run: pip install huggingface_hub")
        return False

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if check_model():
        print("\nModel already downloaded. Nothing to do.")
        return True

    print(f"\nDownloading BioMistral-7B Q4_K_M (~{EXPECTED_SIZE_GB} GB)...")
    print(f"  Repository: {REPO_ID}")
    print(f"  File:       {FILENAME}")
    print(f"  Save to:    {MODEL_PATH}")
    print(f"  Estimated RAM needed during inference: ~6 GB\n")
    print("This may take 10–30 minutes depending on your internet speed.\n")

    try:
        downloaded_path = hf_hub_download(
            repo_id=REPO_ID,
            filename=FILENAME,
            local_dir=str(MODEL_DIR),
            local_dir_use_symlinks=False,  # Copy the actual file, not a symlink
        )
        print(f"\n✓ Download complete: {downloaded_path}")

        # Verify the downloaded file
        if check_model():
            print("\n✓ Model verification passed. Ready to use.")
            return True
        else:
            print("\n✗ Model verification failed after download.")
            return False

    except KeyboardInterrupt:
        print("\n\nDownload interrupted. The partial file has been kept.")
        print("Re-run this script to resume the download.")
        return False
    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Check your internet connection")
        print("  2. Try: pip install --upgrade huggingface_hub")
        print("  3. Download manually from:")
        print(f"     https://huggingface.co/{REPO_ID}/resolve/main/{FILENAME}")
        print(f"     and save to: {MODEL_PATH}")
        return False


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download BioMistral-7B GGUF model for EvoDoc"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check if model exists, do not download",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("EvoDoc — BioMistral-7B Model Setup")
    print("=" * 60)

    if args.check:
        ok = check_model()
        sys.exit(0 if ok else 1)
    else:
        ok = download_model()
        if ok:
            print("\n✓ Run the engine with: uvicorn main:app --reload")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
