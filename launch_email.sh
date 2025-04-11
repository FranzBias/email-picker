#!/bin/bash
# Python GUI that allows you to select one of multiple predefined email addresses and automatically copy it to your clipboard.
# Copyright (c) 2025 FranzBias
# https://github.com/FranzBias
#
# Licensed under the MIT License. See LICENSE file in the root for full license.

# Activate virtual environment and run the script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/venv/bin/activate"
python "$DIR/choose_email.py"
