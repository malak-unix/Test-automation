"""Register the project virtual environment as a Jupyter kernel.

Run this script from an activated project environment after installing
requirements and the editable package:

    python scripts/setup_notebook_kernel.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys


KERNEL_NAME = "sma-test-auto"
DISPLAY_NAME = "Python (sma-test-auto)"


def main() -> int:
    """Install a user-level Jupyter kernel for the current Python executable."""

    print("Notebook kernel setup")
    print(f"Python executable: {sys.executable}")

    if importlib.util.find_spec("ipykernel") is None:
        print("ipykernel is not installed in this Python environment.")
        print("Install dependencies first:")
        print("  python -m pip install -r requirements.txt")
        print("  python -m pip install -e .")
        print("  python -m pip install jupyter ipykernel")
        return 1

    command = [
        sys.executable,
        "-m",
        "ipykernel",
        "install",
        "--user",
        "--name",
        KERNEL_NAME,
        "--display-name",
        DISPLAY_NAME,
    ]
    print("Registering Jupyter kernel:")
    print("  " + " ".join(command))
    subprocess.check_call(command)

    print()
    print("Kernel registered successfully.")
    print("Next steps in VS Code:")
    print("1. Open a notebook.")
    print("2. Click Select Kernel.")
    print("3. Choose Python Environments or Jupyter Kernel.")
    print(f"4. Select {DISPLAY_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
