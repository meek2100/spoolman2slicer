#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Modularized entry point for spoolman2slicer sync tool."""

import argparse
import asyncio
import logging
import os
import sys
import time

from .constants import VERSION, VALID_SPOOL_MODES, Slicers
from .utils import get_user_config_dir, get_arg_default, get_env_choice
from .plugins import PluginManager
from .spoolman_common.api import SpoolmanClient
from .renderer import FilamentRenderer
from .engine import SyncEngine

# Global objects
ARGS = None
TEMPLATES = None

def get_parser() -> argparse.ArgumentParser:
    """Initialize the argument parser."""
    parser = argparse.ArgumentParser(
        prog="spoolman2slicer",
        description="Fetches data from Spoolman and creates slicer filament config files.",
    )

    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)

    parser.add_argument(
        "-d", "--dir",
        metavar="DIR",
        default=os.environ.get("SM2S_SLICER_CONFIG_DIR"),
        help="The folder where your slicer stores its configurations.",
    )

    parser.add_argument(
        "-s", "--slicer",
        type=str.lower,
        default=get_env_choice(
            parser, "SM2S_SLICER", Slicers.choices(), legacy_name="SLICER", default=Slicers.SUPERSLICER
        ),
        choices=Slicers.choices(),
        help="The name of your slicer (e.g., OrcaSlicer, PrusaSlicer).",
    )

    parser.add_argument(
        "-u", "--url",
        metavar="URL",
        default=os.environ.get(
            "SM2S_SPOOLMAN_URL",
            os.environ.get("SPOOLMAN_URL", "http://localhost:8000"),
        ),
        help="The web address of your Spoolman server.",
    )

    parser.add_argument(
        "-U", "--live-sync", "--updates",
        action="store_true",
        dest="live_sync",
        default=get_arg_default(parser, "SM2S_LIVE_SYNC", default_val=False),
        help="Keep the tool running to automatically sync changes from Spoolman in real-time.",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=get_arg_default(parser, "SM2S_VERBOSE_LOGGING", default_val=False),
        help="Show detailed progress and error information for troubleshooting.",
    )

    parser.add_argument(
        "-V", "--variants",
        metavar="VALUE1,VALUE2..",
        default=os.environ.get("SM2S_VARIANTS", ""),
        help="Create different filament versions for different printers (e.g., 'Printer1,Printer2').",
    )

    parser.add_argument(
        "-D", "--startup-tidy", "--delete-all",
        action="store_true",
        dest="startup_tidy",
        default=get_arg_default(parser, "SM2S_STARTUP_TIDY", default_val=False),
        help="Clear out previously generated filament files before starting (keeps your folders tidy).",
    )

    parser.add_argument(
        "--create-per-spool",
        type=str.lower,
        choices=VALID_SPOOL_MODES,
        default=get_env_choice(parser, "SM2S_CREATE_PER_SPOOL", VALID_SPOOL_MODES),
        help="create one output file per spool instead of per filament.",
    )

    parser.add_argument(
        "--with-s2k",
        action="store_true",
        default=get_arg_default(parser, "SM2S_WITH_S2K", legacy_name="S2S_WITH_S2K"),
        help="enable Spool2Klipper plugin (manages macro updates when spool IDs change)",
    )

    parser.add_argument(
        "--with-n2k",
        action="store_true",
        default=get_arg_default(parser, "SM2S_WITH_N2K", legacy_name="S2S_WITH_N2K"),
        help="enable NFC2Klipper plugin (manages NFC tag reading/writing)",
    )

    return parser

def main():
    global ARGS
    parser = get_parser()
    ARGS = parser.parse_args()
    ARGS.slicer = Slicers(ARGS.slicer)

    # Validation
    if not ARGS.dir:
        parser.error("The following arguments are required: -d/--dir (or set SM2S_SLICER_CONFIG_DIR)")
    
    if not os.path.exists(ARGS.dir):
        print(f"ERROR: Output directory does not exist: {ARGS.dir}", file=sys.stderr)
        sys.exit(1)

    # Setup Logging
    log_level = logging.DEBUG if ARGS.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Determine Template Path
    config_dir = get_user_config_dir()
    template_path = os.path.join(config_dir, f"templates-{ARGS.slicer}")
    
    if not os.path.exists(template_path):
        print(f"ERROR: No templates found in {template_path}. Please run setup or install templates.", file=sys.stderr)
        sys.exit(1)

    # Initialize Components
    client = SpoolmanClient(ARGS.url)
    renderer = FilamentRenderer(template_path, ARGS.dir, ARGS.slicer)
    
    engine = SyncEngine(
        client=client,
        renderer=renderer,
        variants=ARGS.variants.split(",") if ARGS.variants else [""],
        create_per_spool=ARGS.create_per_spool,
        verbose=ARGS.verbose
    )

    # Initialize Plugin Manager
    plugin_mgr = PluginManager(ARGS.url, verbose=ARGS.verbose)
    if ARGS.with_s2k:
        plugin_mgr.load_plugin("s2k")
    if ARGS.with_n2k:
        plugin_mgr.load_plugin("n2k")

    # Execution
    try:
        # Initial sync with retry logic for update mode
        while True:
            try:
                engine.sync_all(tidy=ARGS.startup_tidy)
                break
            except Exception as e:
                if not ARGS.live_sync:
                    raise
                logging.warning(f"Initial sync failed: {e}. Retrying in 5s...")
                time.sleep(5)
        
        # Real-time monitoring
        if ARGS.live_sync:
            print("Sync complete. Monitoring Spoolman for updates...")
            loop = asyncio.get_event_loop()
            plugin_mgr.start_plugins(loop=loop)
            asyncio.run(engine.run_loop())
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        plugin_mgr.stop_plugins()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        if ARGS.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
