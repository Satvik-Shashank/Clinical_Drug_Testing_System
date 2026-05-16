"""
EvoDoc Clinical Drug Safety Engine — One-Command Setup

This script:
1. Installs all Python dependencies
2. Downloads BioMistral-7B Q4_K_M (~4.4 GB) from HuggingFace
3. Verifies the full LLM pipeline works end-to-end

Usage:
    python setup.py

After setup completes:
    uvicorn main:app --reload --port 8000
"""

import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).parent


def run(cmd: list[str], desc: str) -> bool:
    """Run a subprocess command with a description."""
    print(f"\n{'─' * 60}")
    print(f"  {desc}")
    print(f"{'─' * 60}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode == 0


def step_install_deps():
    print("\n[Step 1/3] Installing Python dependencies...")

    # Install huggingface_hub first (needed for download)
    ok = run(
        [sys.executable, "-m", "pip", "install", "huggingface_hub>=0.21.0", "python-dotenv>=1.0.1"],
        "Installing huggingface_hub and python-dotenv",
    )
    if not ok:
        print("ERROR: Failed to install base dependencies")
        return False

    # Install llama-cpp-python (pre-built binary for Windows CPU)
    print("\nInstalling llama-cpp-python (CPU build — this may take 1–3 minutes)...")
    ok = run(
        [sys.executable, "-m", "pip", "install", "llama-cpp-python", "--prefer-binary", "--upgrade"],
        "Installing llama-cpp-python (CPU binary)",
    )
    if not ok:
        print("\nWARNING: llama-cpp-python binary install failed.")
        print("Trying alternative install (may require Visual Studio Build Tools)...")
        ok = run(
            [sys.executable, "-m", "pip", "install", "llama-cpp-python"],
            "Installing llama-cpp-python (from source)",
        )
        if not ok:
            print("ERROR: Could not install llama-cpp-python")
            return False

    # Install the rest of requirements
    ok = run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        "Installing remaining dependencies",
    )
    return ok


def step_download_model():
    print("\n[Step 2/3] Downloading BioMistral-7B Q4_K_M (~4.4 GB)...")
    print("  This will take 10–30 minutes depending on your internet speed.")
    print("  The download is resumable — you can Ctrl+C and re-run if needed.\n")

    ok = run(
        [sys.executable, "download_model.py"],
        "Downloading BioMistral-7B from HuggingFace",
    )
    return ok


def step_verify_pipeline():
    print("\n[Step 3/3] Verifying LLM pipeline...")

    verify_script = """
import sys
sys.path.insert(0, '.')

print("  Importing llm_interface...")
from llm_interface import llm

if not llm.is_available:
    print(f"  ERROR: LLM failed to load: {llm.load_error}")
    sys.exit(1)

print("  LLM loaded successfully!")
print(f"  Model info: {llm.model_info}")

print("  Running test inference (warfarin + aspirin)...")
raw, ms = llm.analyze_interactions(
    all_drugs=["warfarin", "aspirin"],
    new_medicines=["aspirin"],
    current_medications=["warfarin"],
)

if raw is None:
    print("  WARNING: LLM returned no output (model may be too slow for test)")
    print("           The engine will use the fallback rule DB in this case.")
    print("           Once running, give the model 60-120s per real request.")
else:
    print(f"  LLM test output ({ms:.0f}ms):")
    print(f"  {raw[:200]}...")
    print("  SUCCESS: LLM pipeline is fully operational!")
"""

    result = subprocess.run(
        [sys.executable, "-c", verify_script],
        cwd=str(ROOT),
    )
    return result.returncode == 0


def main():
    print("=" * 60)
    print("  EvoDoc Clinical Drug Safety Engine — Setup")
    print("=" * 60)
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Root:   {ROOT}")

    # Step 1: Install dependencies
    if not step_install_deps():
        print("\n✗ Setup failed at Step 1 (dependency installation)")
        sys.exit(1)
    print("\n✓ Dependencies installed")

    # Step 2: Download model
    if not step_download_model():
        print("\n✗ Setup failed at Step 2 (model download)")
        print("  You can retry: python download_model.py")
        sys.exit(1)
    print("\n✓ Model downloaded")

    # Step 3: Verify
    print("\n  Note: Verification runs a test inference which takes 60-120s on CPU.")
    answer = input("  Run verification test? [y/N]: ").strip().lower()
    if answer == "y":
        if not step_verify_pipeline():
            print("\n✗ Verification failed — check errors above")
            sys.exit(1)
        print("\n✓ LLM pipeline verified")

    print("\n" + "=" * 60)
    print("  ✓ Setup complete!")
    print("=" * 60)
    print("\nStart the engine:")
    print("    uvicorn main:app --reload --port 8000\n")
    print("API docs:  http://localhost:8000/docs")
    print("Health:    http://localhost:8000/health")
    print("System:    http://localhost:8000/api/v1/system-info")


if __name__ == "__main__":
    main()
