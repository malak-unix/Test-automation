#!/usr/bin/env bash
set -euo pipefail

echo "Setting up notebook environment for SMA Test Automation..."

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pip install ipykernel jupyter
python -m ipykernel install --user --name sma-test-auto --display-name "Python (sma-test-auto)"

echo
echo "Notebook kernel setup complete."
echo "Now open VS Code, click Select Kernel, choose Python Environments or Jupyter Kernel, then select Python (sma-test-auto)."
