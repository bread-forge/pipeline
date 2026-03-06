"""Pipeline budget module.

Exports BudgetTracker for per-cycle USD cost accumulation and cap enforcement.
"""

from pipeline.budget.tracker import BudgetTracker

__all__ = ["BudgetTracker"]
