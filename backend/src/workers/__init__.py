"""Workers package.

Avoid importing worker modules at package import time to prevent
cross-module side effects during python -m startup.
"""

__all__: list[str] = []
