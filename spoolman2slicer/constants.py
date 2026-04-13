#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Shared constants for spoolman2slicer.
"""

VERSION = "0.1.1-rc1"
APP_NAME = "spoolman2slicer"
APP_AUTHOR = False  # Consistent across POSIX/Windows

from enum import Enum

class Slicers(str, Enum):
    """Namespace for supported slicers and their intrinsic properties."""
    ORCA = "orcaslicer"
    CREALITY = "crealityprint"
    PRUSA = "prusaslicer"
    SLIC3R = "slic3r"
    SUPERSLICER = "superslicer"

    @property
    def is_json(self):
        """Returns True if the slicer uses JSON-based configuration."""
        return self in (self.ORCA, self.CREALITY)

    @classmethod
    def choices(cls):
        """Returns a stable list of string choices for argparse."""
        return [m.value for m in cls]


VALID_SPOOL_MODES = ["all", "least-left", "most-recent"]

# Template naming conventions
DEFAULT_TEMPLATE_PREFIX = "default."
DEFAULT_TEMPLATE_SUFFIX = ".template"
FILENAME_TEMPLATE = "filename.template"
FILENAME_FOR_SPOOL_TEMPLATE = "filename_for_spool.template"

# Operational constants
REQUEST_TIMEOUT_SECONDS = 10
