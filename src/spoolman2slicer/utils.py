#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Common utility functions for spoolman2slicer.
"""

import os
import tempfile
import appdirs
from .constants import APP_NAME, APP_AUTHOR, Slicers
from .spoolman_common.utils import get_env_bool, get_arg_default, get_env_choice, atomic_write


def get_user_config_dir():
    """Returns the standardized roaming configuration directory."""
    return appdirs.user_config_dir(appname=APP_NAME, appauthor=APP_AUTHOR, roaming=True)


def is_json_slicer(slicer_name):
    """Returns True if the slicer uses JSON-based configuration (Orca/Creality)."""
    try:
        return Slicers(slicer_name).is_json
    except ValueError:
        return False


