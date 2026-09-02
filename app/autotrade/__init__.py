"""NEXUS AutoTrade package bootstrap.

Install delivery-safety guards before API/routes or bot workers use the shared DB
reconciliation helpers.  The installer is idempotent and has no network side
effects.
"""

from .history_reconcile_guard import install_history_reconcile_delivery_guard

install_history_reconcile_delivery_guard()

__all__ = ["install_history_reconcile_delivery_guard"]
