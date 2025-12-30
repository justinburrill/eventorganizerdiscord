#!/bin/bash

# src="$(dirname "$0")"

python3.14 -m pytest test_time_parsing.py --tb=short

