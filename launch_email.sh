#!/bin/bash
# Activate virtual environment and run the script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/venv/bin/activate"
python "$DIR/choose_email.py"
