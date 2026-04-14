# SPDX-FileCopyrightText: 2026 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Plugin management for spoolman2slicer."""

import importlib.util
import logging
import os
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class PluginManager:
    """Manages the lifecycle and installation of Spoolman Tools plugins."""
    PLUGINS = {
        "s2k": {
            "pkg": "spool2klipper",
            "module": "spool2klipper.spool2klipper",
            "class": "Spool2Klipper",
            "env_prefix": "S2K_"
        },
        "n2k": {
            "pkg": "nfc2klipper",
            "module": "nfc2klipper.nfc2klipper",
            "class": "Nfc2KlipperApp",
            "env_prefix": "N2K_"
        }
    }

    def __init__(self, spoolman_url: str, verbose: bool = False):
        self.spoolman_url = spoolman_url
        self.verbose = verbose
        self.active_plugins = {}
        self._setup_logging()

    def _setup_logging(self):
        if not logger.handlers:
            level = logging.DEBUG if self.verbose else logging.INFO
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s - [PluginManager] %(message)s"))
            logger.addHandler(handler)
            logger.setLevel(level)

    def _is_installed(self, pkg_name: str) -> bool:
        """Check if a package is installed."""
        return importlib.util.find_spec(pkg_name) is not None

    def _auto_install(self, pkg_name: str):
        """Attempt to install a plugin package."""
        logger.info(f"Attempting to install missing plugin: {pkg_name}")
        
        # 1. Try local sibling directory first (for dev environments)
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(pkg_dir, "..", "..", pkg_name)
        
        if os.path.exists(os.path.join(local_path, "pyproject.toml")):
            logger.info(f"Found local source for {pkg_name} at {local_path}")
            install_cmd = [sys.executable, "-m", "pip", "install", local_path]
        else:
            # 2. Try git repository as fallback (or PyPI if we have a name)
            logger.info(f"No local source found for {pkg_name}, installing from PyPI/Git")
            # For now, we'll try to install from the same repo if we were distributed together, 
            # otherwise we'd use a specific git URL.
            install_cmd = [sys.executable, "-m", "pip", "install", pkg_name]

        try:
            subprocess.check_call(install_cmd)
            logger.info(f"Successfully installed {pkg_name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install {pkg_name}: {e}")
            raise RuntimeError(f"Could not install plugin {pkg_name}") from e

    def load_plugin(self, plugin_key: str):
        """Load and initialize a plugin."""
        config = self.PLUGINS.get(plugin_key)
        if not config:
            return

        pkg_name = config["pkg"]
        if not self._is_installed(pkg_name):
            self._auto_install(pkg_name)

        # Passing through configuration via environment variables
        env_prefix = config["env_prefix"]
        os.environ[f"{env_prefix}SPOOLMAN_URL"] = self.spoolman_url
        if self.verbose:
            os.environ[f"{env_prefix}DEBUG"] = "true"

        # Dynamic import
        try:
            module = importlib.import_module(config["module"])
            plugin_class = getattr(module, config["class"])
            
            # Initialize based on plugin type
            if plugin_key == "s2k":
                # Spool2Klipper is async
                from spool2klipper.spool2klipper import load_config
                s2k_config = load_config()
                instance = plugin_class(s2k_config)
                self.active_plugins[plugin_key] = {
                    "instance": instance,
                    "type": "async"
                }
            elif plugin_key == "n2k":
                # NFC2Klipper is also async
                from nfc2klipper.lib.config import Nfc2KlipperConfig
                n2k_cfg = Nfc2KlipperConfig.get_config()
                instance = plugin_class(n2k_cfg)
                self.active_plugins[plugin_key] = {
                    "instance": instance,
                    "type": "async"
                }
            
            logger.info(f"Loaded plugin: {plugin_key}")
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_key}: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()

    def start_plugins(self, loop=None):
        """Start all loaded plugins."""
        for key, data in self.active_plugins.items():
            instance = data["instance"]
            if data["type"] == "async" and loop:
                logger.info(f"Starting {key} agent in event loop")
                loop.create_task(instance.run())
            elif data["type"] == "threaded":
                logger.info(f"Starting {key} agent in background thread")
                # We use the orchestrator's threaded mode
                thread = threading.Thread(target=instance.start_threaded, name=f"{key}_plugin")
                thread.daemon = True
                thread.start()
                data["thread"] = thread

    def stop_plugins(self):
        """Stop all active plugins."""
        logger.info("Stopping all plugins...")
        for key, data in self.active_plugins.items():
            instance = data["instance"]
            try:
                if hasattr(instance, "stop"):
                    instance.stop()
                elif hasattr(instance, "close"):
                     instance.close()
                logger.info(f"Stopped {key}")
            except Exception as e:
                logger.error(f"Error stopping {key}: {e}")
