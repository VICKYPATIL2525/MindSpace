#!/bin/bash
# Quick logging commands for MindSpace project
# Usage: Source this file or copy commands as needed
# Example: bash log_commands.sh

# Activate conda environment
# conda activate mindspace

# Example 1: Log a model change
# python manage.py log_change models CREATE "Added UserProgress model for tracking user activity"

# Example 2: Log a view update
# python manage.py log_change views UPDATE --details "Fixed authentication bug in dashboard"

# Example 3: Log a template modification
# python manage.py log_change templates UPDATE "Updated navbar responsive design"

# Example 4: Log settings change
# python manage.py log_change settings UPDATE "Added new environment variable for API"

# Example 5: Log migration
# python manage.py log_change migrations CREATE "Migration 0004: Added assessment feedback"

# Example 6: Log static files update
# python manage.py log_change static UPDATE "Added new CSS for activity cards"

# Example 7: Log bug fix
# python manage.py log_change "assessments_views" "BUGFIX" --details "Fixed score calculation bug in scenario assessment"

# Example 8: Log feature addition
# python manage.py log_change "chat_feature" "FEATURE" --details "Implemented real-time chat with WebSocket"

# Common log viewing commands:
# tail -50 changes.log                    # Last 50 lines
# tail -f changes.log                     # Real-time monitoring
# grep "ERROR" changes.log                # Find all errors
# grep "models" changes.log               # Find changes to models
# grep "2026-05-23" changes.log          # Logs from specific date
# wc -l changes.log                       # Total number of log entries
