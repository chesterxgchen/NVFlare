# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Policy Manager - Server-side Policy Storage and Lookup.

This module manages approval policies for the Certificate Service.
Policies are stored as YAML files (one file per policy) and loaded
into memory for fast lookup.

Key Features:
- One policy per YAML file (e.g., default.yaml, trusted.yaml)
- In-memory dict for O(1) lookup by policy_id
- Hot reload support without service restart
- Default policy fallback when policy_id not found

Storage Layout:
    /var/lib/cert_service/
    └── policies/
        ├── default.yaml      # Default policy (required)
        ├── trusted.yaml      # Auto-approve for trusted partners
        ├── strict.yaml       # Manual approval required
        └── asia.yaml         # Regional policy

Policy Structure (YAML):
    policy_id: default
    description: Default approval policy
    approval:
      rules:
        - name: auto-approve-all
          match: {}
          action: approve
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class PolicyManager:
    """Manages server-side approval policies.

    Policies are loaded from YAML files at startup and cached in memory.
    Supports multiple named policies with hot reload capability.

    Usage:
        manager = PolicyManager("/var/lib/cert_service/policies")
        policy = manager.get_policy("trusted")
        if policy:
            rules = policy.get("approval", {}).get("rules", [])
    """

    DEFAULT_POLICY_ID = "default"

    def __init__(self, policy_dir: str = "/var/lib/cert_service/policies"):
        """Initialize the policy manager.

        Args:
            policy_dir: Directory containing policy YAML files.
                        Each file should be named {policy_id}.yaml
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.policy_dir = Path(policy_dir)
        self._policies: Dict[str, Dict[str, Any]] = {}
        self._load_policies()

    def _load_policies(self) -> None:
        """Load all policies from the policy directory."""
        self._policies.clear()

        if not self.policy_dir.exists():
            self.logger.warning(f"Policy directory does not exist: {self.policy_dir}")
            self._create_default_policy()
            return

        # Load all .yaml/.yml files in the directory
        policy_files = list(self.policy_dir.glob("*.yaml")) + list(self.policy_dir.glob("*.yml"))

        if not policy_files:
            self.logger.warning(f"No policy files found in: {self.policy_dir}")
            self._create_default_policy()
            return

        for policy_file in policy_files:
            try:
                self._load_policy_file(policy_file)
            except Exception as e:
                self.logger.error(f"Failed to load policy file {policy_file}: {e}")

        # Ensure default policy exists
        if self.DEFAULT_POLICY_ID not in self._policies:
            self.logger.warning("No default policy found, creating one")
            self._create_default_policy()

        self.logger.info(f"Loaded {len(self._policies)} policies: {list(self._policies.keys())}")

    def _load_policy_file(self, policy_file: Path) -> None:
        """Load a single policy file."""
        with open(policy_file, "r") as f:
            policy = yaml.safe_load(f)

        if not policy:
            self.logger.warning(f"Empty policy file: {policy_file}")
            return

        # Get policy_id from file content or derive from filename
        policy_id = policy.get("policy_id") or policy_file.stem

        # Store the policy
        self._policies[policy_id] = policy
        self.logger.debug(f"Loaded policy '{policy_id}' from {policy_file}")

    def _create_default_policy(self) -> None:
        """Create a default auto-approve policy."""
        self._policies[self.DEFAULT_POLICY_ID] = {
            "policy_id": self.DEFAULT_POLICY_ID,
            "description": "Default auto-approve policy",
            "approval": {
                "rules": [
                    {
                        "name": "auto-approve-all",
                        "match": {},
                        "action": "approve",
                        "description": "Auto-approve all enrollment requests",
                    }
                ]
            },
        }

    def reload(self) -> int:
        """Reload policies from disk.

        Returns:
            Number of policies loaded
        """
        self.logger.info("Reloading policies...")
        self._load_policies()
        return len(self._policies)

    def get_policy(self, policy_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a policy by ID.

        Args:
            policy_id: Policy ID to look up. If None or not found,
                      returns the default policy.

        Returns:
            Policy dict or None if not found and no default exists
        """
        if policy_id and policy_id in self._policies:
            return self._policies[policy_id]

        # Fall back to default policy
        if self.DEFAULT_POLICY_ID in self._policies:
            if policy_id and policy_id != self.DEFAULT_POLICY_ID:
                self.logger.warning(f"Policy '{policy_id}' not found, using default")
            return self._policies[self.DEFAULT_POLICY_ID]

        self.logger.error(f"Policy '{policy_id}' not found and no default policy exists")
        return None

    def list_policies(self) -> List[Dict[str, Any]]:
        """List all available policies.

        Returns:
            List of policy summaries (id, description)
        """
        return [
            {
                "policy_id": policy_id,
                "description": policy.get("description", ""),
            }
            for policy_id, policy in self._policies.items()
        ]

    def get_policy_ids(self) -> List[str]:
        """Get list of all policy IDs.

        Returns:
            List of policy ID strings
        """
        return list(self._policies.keys())

    def policy_exists(self, policy_id: str) -> bool:
        """Check if a policy exists.

        Args:
            policy_id: Policy ID to check

        Returns:
            True if policy exists
        """
        return policy_id in self._policies

    def add_policy(self, policy_id: str, policy: Dict[str, Any], persist: bool = True) -> bool:
        """Add a new policy.

        Args:
            policy_id: ID for the new policy
            policy: Policy definition dict
            persist: If True, save to disk

        Returns:
            True if added successfully
        """
        if policy_id in self._policies:
            self.logger.warning(f"Policy '{policy_id}' already exists, use update_policy instead")
            return False

        # Ensure policy_id is set in the policy dict
        policy["policy_id"] = policy_id

        self._policies[policy_id] = policy

        if persist:
            self._save_policy_to_disk(policy_id, policy)

        self.logger.info(f"Added policy: {policy_id}")
        return True

    def update_policy(self, policy_id: str, policy: Dict[str, Any], persist: bool = True) -> bool:
        """Update an existing policy.

        Args:
            policy_id: ID of the policy to update
            policy: New policy definition
            persist: If True, save to disk

        Returns:
            True if updated successfully
        """
        if policy_id not in self._policies:
            self.logger.warning(f"Policy '{policy_id}' does not exist, use add_policy instead")
            return False

        # Ensure policy_id is set in the policy dict
        policy["policy_id"] = policy_id

        self._policies[policy_id] = policy

        if persist:
            self._save_policy_to_disk(policy_id, policy)

        self.logger.info(f"Updated policy: {policy_id}")
        return True

    def delete_policy(self, policy_id: str, persist: bool = True) -> bool:
        """Delete a policy.

        Args:
            policy_id: ID of the policy to delete
            persist: If True, remove from disk

        Returns:
            True if deleted successfully
        """
        if policy_id == self.DEFAULT_POLICY_ID:
            self.logger.error("Cannot delete the default policy")
            return False

        if policy_id not in self._policies:
            self.logger.warning(f"Policy '{policy_id}' does not exist")
            return False

        del self._policies[policy_id]

        if persist:
            self._delete_policy_from_disk(policy_id)

        self.logger.info(f"Deleted policy: {policy_id}")
        return True

    def _save_policy_to_disk(self, policy_id: str, policy: Dict[str, Any]) -> None:
        """Save a policy to disk."""
        self.policy_dir.mkdir(parents=True, exist_ok=True)
        policy_file = self.policy_dir / f"{policy_id}.yaml"

        with open(policy_file, "w") as f:
            yaml.safe_dump(policy, f, default_flow_style=False, sort_keys=False)

        self.logger.debug(f"Saved policy to: {policy_file}")

    def _delete_policy_from_disk(self, policy_id: str) -> None:
        """Delete a policy file from disk."""
        policy_file = self.policy_dir / f"{policy_id}.yaml"
        if policy_file.exists():
            os.remove(policy_file)
            self.logger.debug(f"Deleted policy file: {policy_file}")

        # Also check for .yml extension
        policy_file_yml = self.policy_dir / f"{policy_id}.yml"
        if policy_file_yml.exists():
            os.remove(policy_file_yml)

