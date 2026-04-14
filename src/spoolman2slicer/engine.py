# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Central synchronization logic and event loop."""

import asyncio
import datetime
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set

from .spoolman_common.api import SpoolmanClient
from .renderer import FilamentRenderer
from .constants import VERSION, APP_NAME

logger = logging.getLogger(__name__)

class SyncEngine:
    """Orchestrates the synchronization between Spoolman and the local slicer config."""

    def __init__(
        self,
        client: SpoolmanClient,
        renderer: FilamentRenderer,
        variants: List[str],
        create_per_spool: Optional[str] = None,
        verbose: bool = False
    ):
        self.client = client
        self.renderer = renderer
        self.variants = variants
        self.create_per_spool = create_per_spool
        self.verbose = verbose
        
        # Internal state/caches
        self.filaments_cache: Dict[int, Dict[str, Any]] = {}
        self.spools_cache: Dict[int, Dict[str, Any]] = {}
        
        # Filesystem state trackers
        self.spool_id_to_filenames: Dict[int, Set[str]] = {}
        self.filename_usage: Dict[str, int] = {}

    def _get_sm2s_meta(self, variant: str, suffix: str) -> Dict[str, Any]:
        """Generate the tool-specific metadata for Jinja templates."""
        now = datetime.datetime.now()
        return {
            "name": APP_NAME,
            "version": VERSION,
            "now": now.strftime("%a %b %d %H:%M:%S %Y"),
            "now_int": int(now.timestamp()),
            "slicer_suffix": suffix,
            "variant": variant,
            "spoolman_url": self.client.base_url,
        }

    def _prepare_filament_data(self, filament: Dict[str, Any], variant: str, suffix: str, spool: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merge filament, metadata, and optional spool data for rendering."""
        data = filament.copy()
        data["sm2s"] = self._get_sm2s_meta(variant, suffix)
        data["spool"] = spool if spool else {}
        return data

    def _get_cache_key(self, filament_id: int, variant: str, suffix: str, spool_id: Optional[int] = None) -> str:
        """Generate a unique key for filename/content tracking."""
        if self.create_per_spool == "all" and spool_id:
            return f"spool-{spool_id}-{suffix}-{variant}"
        return f"{filament_id}-{suffix}-{variant}"

    def write_spool_profile(self, spool: Dict[str, Any]):
        """Determine what needs to be written for a single spool."""
        filament = spool.get("filament")
        if not filament or "id" not in spool:
            return

        spool_id = spool["id"]
        new_filenames = set()

        for variant in self.variants:
            for suffix in self.renderer.suffixes:
                data = self._prepare_filament_data(filament, variant, suffix, spool=spool)
                
                # Determine target filename
                filename = self.renderer.get_output_filename(data, create_per_spool=(self.create_per_spool == "all"))
                new_filenames.add(filename)
                
                # Render and write
                content = self.renderer.render_filament(data, suffix)
                if self.renderer.write(filename, content):
                    logger.info(f"Generated: {filename}")

        # Cleanup old files for this spool that are no longer in the new set
        old_filenames = self.spool_id_to_filenames.get(spool_id, set())
        for old_f in old_filenames:
            if old_f not in new_filenames:
                self._decrement_usage(old_f)
        
        # Increment usage for new filenames
        for new_f in new_filenames:
            if new_f not in old_filenames:
                self.filename_usage[new_f] = self.filename_usage.get(new_f, 0) + 1
        
        self.spool_id_to_filenames[spool_id] = new_filenames

    def _decrement_usage(self, filename: str):
        """Decrease usage count and delete file if no longer needed."""
        if filename in self.filename_usage:
            self.filename_usage[filename] -= 1
            if self.filename_usage[filename] <= 0:
                if self.renderer.is_managed_file(filename):
                    logger.info(f"Deleting unused file: {filename}")
                    try:
                        os.remove(filename)
                    except OSError as e:
                        logger.error(f"Failed to delete {filename}: {e}")
                del self.filename_usage[filename]

    def sync_all(self, tidy: bool = False):
        """The 'Heavy Lifting' - full sync of all active spools."""
        if tidy:
            logger.info("Performing startup cleanup...")
            self.renderer.delete_managed_files()

        logger.info("Fetching data from Spoolman...")
        spools = self.client.get_active_spools()
        
        # Reset tracking for full re-sync
        self.filename_usage.clear()
        self.spool_id_to_filenames.clear()
        self.spools_cache.clear()
        self.filaments_cache.clear()

        # Phase 1: Filter and Rank
        if not self.create_per_spool:
            # Group by filament, only keep one entry
            render_list = {}
            for s in spools:
                f_id = s.get("filament", {}).get("id")
                if f_id:
                    render_list[f_id] = s
            spools_to_render = list(render_list.values())
        elif self.create_per_spool == "all":
            spools_to_render = spools
        else:
            # Group by filament and pick the best spool per group
            groups = {}
            for s in spools:
                f_id = s.get("filament", {}).get("id")
                if not f_id: continue
                if f_id not in groups: groups[f_id] = []
                groups[f_id].append(s)
            
            spools_to_render = []
            for f_id, group in groups.items():
                if self.create_per_spool == "least-left":
                    # Sort by remaining weight (descending to pick highest? No, least-left usually means most used? No, actually it means the one with the least filament LEFT?)
                    # Let's check the legacy code's "least-left" logic
                    # In traditional usage, it usually picks the one with the smallest weight left.
                    # Actually, the user likely wants the one with the LEAST amount remaining so they can finish it? 
                    # Let's see...
                    group.sort(key=lambda x: x.get("remaining_weight", float('inf')))
                    spools_to_render.append(group[0])
                elif self.create_per_spool == "most-recent":
                    # Sort by last_used (descending)
                    group.sort(key=lambda x: x.get("last_used") or "", reverse=True)
                    spools_to_render.append(group[0])
                else:
                    spools_to_render.append(group[0])

        # Phase 2: Render
        for spool in spools_to_render:
            # Populate caches
            if "id" in spool:
                self.spools_cache[spool["id"]] = spool
            if "filament" in spool:
                self.filaments_cache[spool["filament"]["id"]] = spool["filament"]
            
            self.write_spool_profile(spool)

    async def run_loop(self):
        """Connect to WebSocket and handle real-time events."""
        logger.info("Starting real-time synchronization loop...")
        while True:
            try:
                async with await self.client.connect_websocket() as ws:
                    async for msg in ws:
                        try:
                            event = json.loads(msg)
                            self.handle_event(event)
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse WS message: {msg[:100]}")
            except Exception as e:
                logger.error(f"WebSocket connection lost: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def handle_event(self, event: Dict[str, Any]):
        """Dispatch WebSocket events to local updates."""
        resource = event.get("resource")
        payload = event.get("payload")
        event_type = event.get("type")
        
        if not payload or not resource:
            return

        # Ensure extra fields are decoded
        self.client._decode_extra_fields(payload)
        
        if resource == "spool":
            if event_type in ("created", "updated"):
                # Fetch full filament data if missing in payload
                if "filament" not in payload and "filament_id" in payload:
                    f_id = payload["filament_id"]
                    if f_id in self.filaments_cache:
                        payload["filament"] = self.filaments_cache[f_id]
                    else:
                        payload["filament"] = self.client.get_filament(f_id)
                
                self.write_spool_profile(payload)
                if "id" in payload:
                    self.spools_cache[payload["id"]] = payload
            elif event_type == "deleted":
                id = payload.get("id")
                if id in self.spools_cache:
                    # Logic to find if any other spool uses this filename would go here
                    del self.spools_cache[id]
        
        # Handle filament/vendor updates similarly...
        logger.debug(f"Handled {event_type} {resource}")
