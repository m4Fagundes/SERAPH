"""
grid-image-analyzer — app package root.

Configures the package-level logger so that library consumers and the
application entry-point can control log output without boilerplate.
"""

import logging

# Best practice for library/package code: attach a NullHandler so no
# output appears unless the caller (main.py or tests) configures a handler.
logging.getLogger(__name__).addHandler(logging.NullHandler())
