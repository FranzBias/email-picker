#!/bin/bash
# Activate virtual environment and run the script
source "$(dirname "$0")/venv/bin/activate"
python "$(dirname "$0")/choose_email.py"
