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
            os.environ.get("SPOOLMAN_URL", "http://localhost:7912"),
        ),
        help="The web address of your Spoolman server.",
    )

    parser.add_argument(
        "-U", "--updates",
        action="store_true",
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
        "-D", "--delete-all",
        action="store_true",
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
    """Main application entry point."""
    parser = get_parser()
    args = parser.parse_args()
    args.slicer = Slicers(args.slicer)

    # Validation
    if not args.dir:
        parser.error("The following arguments are required: -d/--dir (or set SM2S_SLICER_CONFIG_DIR)")
    
    if not os.path.exists(args.dir):
        print(f"ERROR: Output directory does not exist: {args.dir}", file=sys.stderr)
        sys.exit(1)

    # Setup Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Determine Template Path
    config_dir = get_user_config_dir()
    template_path = os.path.join(config_dir, f"templates-{args.slicer}")
    
    if not os.path.exists(template_path):
        print(f"ERROR: No templates found in {template_path}. Please run setup or install templates.", file=sys.stderr)
        sys.exit(1)

    # Initialize Components
    client = SpoolmanClient(args.url)
    renderer = FilamentRenderer(template_path, args.dir, args.slicer)
    
    engine = SyncEngine(
        client=client,
        renderer=renderer,
        variants=args.variants.split(",") if args.variants else [""],
        create_per_spool=args.create_per_spool,
        verbose=args.verbose
    )

    # Initialize Plugin Manager
    plugin_mgr = PluginManager(args.url, verbose=args.verbose)
    if args.with_s2k:
        plugin_mgr.load_plugin("s2k")
    if args.with_n2k:
        plugin_mgr.load_plugin("n2k")

    # Execution
    try:
        # Initial sync with retry logic for update mode
        while True:
            try:
                engine.sync_all(tidy=args.delete_all)
                break
            except Exception as e:
                if not args.updates:
                    raise
                logging.warning(f"Initial sync failed: {e}. Retrying in 5s...")
                time.sleep(5)
        
        # Real-time monitoring
        if args.updates:
            print("Sync complete. Monitoring Spoolman for updates...")
            plugin_mgr.start_plugins()
            asyncio.run(engine.run_loop())
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        plugin_mgr.stop_plugins()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
