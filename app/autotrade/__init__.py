"""NEXUS AutoTrade package bootstrap.

Install delivery-safety guards before API/routes or bot workers use the shared DB
reconciliation helpers.  The installers are idempotent and have no network side
effects.
"""

from .history_reconcile_guard import install_history_reconcile_delivery_guard
from .lifecycle_identity_guard import install_lifecycle_identity_guard

install_history_reconcile_delivery_guard()
install_lifecycle_identity_guard()

__all__ = [
    "install_history_reconcile_delivery_guard",
    "install_lifecycle_identity_guard",
]
