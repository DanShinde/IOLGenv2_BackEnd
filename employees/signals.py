# employees/signals.py
"""
Signals for the employees app.

After migration from Pace to Employee, the tracker.Pace model no longer exists.
Employees are now managed directly in this app and serve as the unified
personnel model for all apps (tracker, planner, etc.).

Team leads in tracker now directly reference employees.Employee.
No sync signals are needed as Employee is the single source of truth.
"""

# Placeholder for future employee-related signals
# Example: Send notifications when employees are created, updated, or deactivated
