"""Local-only CryptoChange operator cockpit.

The first delivery is intentionally SHADOW-only.  This package observes public
market data and optional private account data, but contains no order or
withdrawal transport.
"""

from crypto_strategy_lab.operator_dashboard.service import OperatorService

__all__ = ["OperatorService"]
