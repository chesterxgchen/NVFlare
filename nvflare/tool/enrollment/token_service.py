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

"""FLARE Enrollment Token (FET) Service.

This module handles JWT-based enrollment token:
- Single token generation with policy_id reference (policies stored server-side)
- Batch token generation for multiple clients
- Token metadata embedding (project, fl_server, cert_service)
- Token inspection

Token generation is separate from certificate services to maintain separation of concerns.

Token Structure (JWT Claims):
- Standard: jti, sub, iat, exp, iss
- Required Metadata: project, fl_server, cert_service, subject_type
- Policy: policy_id (references server-side policy, defaults to "default")
- Optional: roles, source_ips
"""

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt
from cryptography import x509
from cryptography.x509.oid import NameOID

from nvflare.lighter.constants import DEFINED_PARTICIPANT_TYPES, AdminRole, ParticipantType
from nvflare.lighter.utils import load_crt, load_private_key_file


def _get_cert_cn(cert: x509.Certificate) -> str:
    """Extract Common Name from certificate."""
    for attr in cert.subject:
        if attr.oid == NameOID.COMMON_NAME:
            return attr.value
    return "nvflare"


class TokenService:
    """Manage enrollment token (JWT) generation and inspection.

    The enrollment token (FET - FLARE Enrollment Token) is a signed JWT that contains:
    - Participant identity (sub, subject_type)
    - Required metadata (project, fl_server, cert_service)
    - Policy reference (policy_id - points to server-side policy)

    Token Security:
    - Signed with root CA private key (cannot be forged)
    - Multi-use but participant-bound (one token = one participant = one enrollment)
    - Policies are server-side (not embedded, preventing policy leakage)

    This service handles:
    - Token generation (signed with root CA private key)
    - Batch token generation for multiple clients
    - Token inspection (decode without verification)

    Token validation and certificate signing are handled by CertService.
    Both services use the same root CA key pair for consistency.
    """

    # JWT algorithm - using RS256 (RSA + SHA256) for asymmetric signing
    JWT_ALGORITHM = "RS256"

    # Subject type for pattern matching (not a participant type)
    SUBJECT_TYPE_PATTERN = "pattern"

    def __init__(
        self,
        root_ca_path: Optional[str] = None,
        root_ca_cert: Optional[Any] = None,
        signing_key: Optional[Any] = None,
        jwt_signing_key_path: Optional[str] = None,
    ):
        """Initialize the token service.

        Can be initialized with either file paths OR pre-loaded objects.
        If both are provided, pre-loaded objects take precedence (avoids re-loading).

        Args:
            root_ca_path: Path to the provisioned workspace directory.
                          This should be the directory created by 'nvflare provision'.
                          The service will look for the root CA in:
                          1. state/cert.json (provisioning state file)
                          2. rootCA.pem and rootCA.key files (fallback)
            root_ca_cert: Pre-loaded root CA certificate object
            signing_key: Pre-loaded signing key object (root CA private key or separate JWT key)
            jwt_signing_key_path: Optional path to a separate private key for JWT signing.
                                  If not provided, uses the root CA private key (default).
                                  If provided, CertService must use the matching public key
                                  for verification (via verification_key_path).

        Note:
            By default, uses the same root CA as CertService for consistent key pair.
            TokenService signs with private key, CertService verifies with public key.
            For separate JWT keys, ensure both services use the same key pair.

        Example (from paths):
            service = TokenService(root_ca_path="/path/to/ca")

        Example (from objects - avoids disk I/O):
            service = TokenService(root_ca_cert=cert, signing_key=key)
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        # Use pre-loaded objects if provided
        if root_ca_cert is not None and signing_key is not None:
            self.root_cert = root_ca_cert
            self.signing_key = signing_key
            self.issuer = _get_cert_cn(self.root_cert)
        elif root_ca_path:
            # Load from paths
            # Try to load from state/cert.json first (created by provisioning)
            state_file = os.path.join(root_ca_path, "state", "cert.json")
            if os.path.exists(state_file):
                self._load_from_state_file(state_file)
            else:
                # Fallback: look for rootCA.pem and rootCA.key directly
                cert_file = os.path.join(root_ca_path, "rootCA.pem")
                key_file = os.path.join(root_ca_path, "rootCA.key")

                if not os.path.exists(cert_file):
                    raise FileNotFoundError(
                        f"Root CA not found. Expected either:\n"
                        f"  - {state_file} (from 'nvflare provision')\n"
                        f"  - {cert_file} and {key_file}"
                    )

                self.root_cert = load_crt(cert_file)
                self.signing_key = load_private_key_file(key_file)
                self.issuer = _get_cert_cn(self.root_cert)
        else:
            raise ValueError("Must provide either root_ca_path or (root_ca_cert, signing_key)")

        # Optional: use separate JWT signing key (overrides signing_key)
        if jwt_signing_key_path:
            self.logger.info(f"Using separate JWT signing key: {jwt_signing_key_path}")
            self.signing_key = load_private_key_file(jwt_signing_key_path)

    def _load_from_state_file(self, state_file: str):
        """Load root CA certificate and key from provisioning state file."""
        import json

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.x509 import load_pem_x509_certificate

        with open(state_file, "r") as f:
            state = json.load(f)

        root_cert_pem = state.get("root_cert")
        root_key_pem = state.get("root_pri_key")

        if not root_cert_pem or not root_key_pem:
            raise ValueError(f"Invalid state file: missing root_cert or root_pri_key in {state_file}")

        self.root_cert = load_pem_x509_certificate(root_cert_pem.encode(), default_backend())
        self.signing_key = serialization.load_pem_private_key(
            root_key_pem.encode(), password=None, backend=default_backend()
        )
        self.issuer = _get_cert_cn(self.root_cert)

    def generate_token(
        self,
        subject: str,
        subject_type: str = ParticipantType.CLIENT,
        project: Optional[str] = None,
        fl_server: Optional[str] = None,
        cert_service: Optional[str] = None,
        policy_id: str = "default",
        validity: Optional[str] = None,
        **claims,
    ) -> str:
        """Generate a signed enrollment token (JWT) with policy_id reference.

        Tokens contain metadata (project, fl_server, cert_service) that enables
        simplified packaging workflow where nvflare package extracts all necessary
        information from the token.

        Args:
            subject: The subject identifier (site name, user id, or pattern)
            subject_type: Type of subject from ParticipantType (client, admin, relay)
                         or "pattern" for wildcard matching
            project: Project name (required for production tokens)
            fl_server: FL Server endpoint URI (e.g., "grpc://server:8002")
            cert_service: Certificate Service URL (e.g., "https://cert:8443")
            policy_id: Reference to server-side policy (default: "default")
            validity: Token validity duration (e.g., "7d", "24h"). Defaults to "7d"
            **claims: Additional claims to embed in the token (flexible).
                      Examples: roles, source_ips

        Returns:
            Signed JWT token string

        Examples:
            # Client (site) token with full metadata
            token = service.generate_token(
                subject="hospital-01",
                subject_type=ParticipantType.CLIENT,
                project="healthcare-fl",
                fl_server="grpc://server.example.com:8002",
                cert_service="https://cert.example.com:8443",
                policy_id="trusted"
            )

            # Admin (user) token with roles
            token = service.generate_token(
                subject="user@example.com",
                subject_type=ParticipantType.ADMIN,
                project="my-project",
                fl_server="grpc://server:8002",
                cert_service="https://cert:8443",
                roles=["org_admin", "lead"]
            )

            # Token with IP restriction
            token = service.generate_token(
                subject="dc-server-01",
                subject_type=ParticipantType.CLIENT,
                project="secure-fl",
                fl_server="grpc://server:8002",
                cert_service="https://cert:8443",
                source_ips=["10.0.0.0/8"]
            )
        """
        if not subject:
            raise ValueError("subject is required")

        # Validate subject_type
        valid_types = list(DEFINED_PARTICIPANT_TYPES) + [self.SUBJECT_TYPE_PATTERN]
        if subject_type not in valid_types:
            raise ValueError(f"subject_type must be one of: {valid_types}")

        # Parse validity duration
        validity_str = validity or "7d"
        validity_delta = self._parse_duration(validity_str)

        now = datetime.now(timezone.utc)

        # Build JWT payload with standard claims
        payload = {
            # Standard JWT claims
            "jti": str(uuid.uuid4()),  # Unique token ID
            "sub": subject,  # Subject (site/user)
            "iat": now,  # Issued at
            "exp": now + validity_delta,  # Expiration
            "iss": self.issuer,  # Issuer
            # FLARE-specific claims
            "subject_type": subject_type,
            "policy_id": policy_id,  # Reference to server-side policy
        }

        # Add required metadata claims (for simplified packaging)
        if project:
            payload["project"] = project
        if fl_server:
            payload["fl_server"] = fl_server
        if cert_service:
            payload["cert_service"] = cert_service

        # Merge any additional claims (flexible - no code changes needed)
        for key, value in claims.items():
            if value is not None:
                payload[key] = value

        # Sign and encode the token
        signed_token = jwt.encode(
            payload,
            self.signing_key,
            algorithm=self.JWT_ALGORITHM,  # RS256 = RSA signature with SHA-256
        )

        self.logger.info(f"Generated enrollment token: jti={payload['jti']}, subject={subject}, type={subject_type}")
        return signed_token

    def generate_site_token(
        self,
        site_name: str,
        project: Optional[str] = None,
        fl_server: Optional[str] = None,
        cert_service: Optional[str] = None,
        policy_id: str = "default",
        valid_days: int = 7,
        **claims,
    ) -> str:
        """Convenience method for generating site enrollment tokens.

        Args:
            site_name: Site identifier
            project: Project name
            fl_server: FL Server endpoint URI
            cert_service: Certificate Service URL
            policy_id: Reference to server-side policy (default: "default")
            valid_days: Token validity in days (default: 7)
            **claims: Additional claims

        Returns:
            Signed JWT token string
        """
        return self.generate_token(
            subject=site_name,
            subject_type=ParticipantType.CLIENT,
            project=project,
            fl_server=fl_server,
            cert_service=cert_service,
            policy_id=policy_id,
            validity=f"{valid_days}d",
            **claims,
        )

    def generate_admin_token(
        self,
        user_id: str,
        project: Optional[str] = None,
        fl_server: Optional[str] = None,
        cert_service: Optional[str] = None,
        policy_id: str = "default",
        valid_days: int = 7,
        roles: Optional[list] = None,
        **claims,
    ) -> str:
        """Convenience method for generating admin (user) enrollment tokens.

        Args:
            user_id: User identifier (email)
            project: Project name
            fl_server: FL Server endpoint URI
            cert_service: Certificate Service URL
            policy_id: Reference to server-side policy (default: "default")
            valid_days: Token validity in days (default: 7)
            roles: List of roles for the admin (default: [AdminRole.LEAD])
            **claims: Additional claims

        Returns:
            Signed JWT token string
        """
        # Default to LEAD role (has job submission permissions)
        return self.generate_token(
            subject=user_id,
            subject_type=ParticipantType.ADMIN,
            project=project,
            fl_server=fl_server,
            cert_service=cert_service,
            policy_id=policy_id,
            validity=f"{valid_days}d",
            roles=roles or [AdminRole.LEAD],
            **claims,
        )

    def generate_relay_token(
        self,
        relay_name: str,
        project: Optional[str] = None,
        fl_server: Optional[str] = None,
        cert_service: Optional[str] = None,
        policy_id: str = "default",
        valid_days: int = 7,
        **claims,
    ) -> str:
        """Convenience method for generating relay enrollment tokens.

        Args:
            relay_name: Relay node identifier
            project: Project name
            fl_server: FL Server endpoint URI
            cert_service: Certificate Service URL
            policy_id: Reference to server-side policy (default: "default")
            valid_days: Token validity in days (default: 7)
            **claims: Additional claims

        Returns:
            Signed JWT token string
        """
        return self.generate_token(
            subject=relay_name,
            subject_type=ParticipantType.RELAY,
            project=project,
            fl_server=fl_server,
            cert_service=cert_service,
            policy_id=policy_id,
            validity=f"{valid_days}d",
            **claims,
        )

    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string like '7d', '24h', '30m' to timedelta."""
        match = re.match(r"^(\d+)([dhms])$", duration_str.lower())
        if not match:
            raise ValueError(f"Invalid duration format: {duration_str}")

        value = int(match.group(1))
        unit = match.group(2)

        if unit == "d":
            return timedelta(days=value)
        elif unit == "h":
            return timedelta(hours=value)
        elif unit == "m":
            return timedelta(minutes=value)
        elif unit == "s":
            return timedelta(seconds=value)
        else:
            raise ValueError(f"Unknown duration unit: {unit}")

    def get_public_key_pem(self) -> bytes:
        """Get the public key in PEM format for token verification.

        This can be shared with CertService for token validation.
        """
        from cryptography.hazmat.primitives import serialization

        return self.signing_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    # =========================================================================
    # Batch Token Generation
    # =========================================================================

    def batch_generate_tokens(
        self,
        count: int = 0,
        name_prefix: Optional[str] = None,
        names: Optional[List[str]] = None,
        subject_type: str = ParticipantType.CLIENT,
        project: Optional[str] = None,
        fl_server: Optional[str] = None,
        cert_service: Optional[str] = None,
        policy_id: str = "default",
        validity: Optional[str] = None,
        output_file: Optional[str] = None,
        **claims,
    ) -> List[Dict[str, str]]:
        """Generate multiple enrollment tokens in batch.

        This is useful for pre-generating tokens for multiple clients.
        Tokens are multi-use but participant-bound (one token = one participant).

        Args:
            count: Number of tokens to generate (ignored if names provided)
            name_prefix: Prefix for auto-generated names (e.g., "site" -> "site-001")
            names: Explicit list of names (overrides count and name_prefix)
            subject_type: Type of participant (client, admin, relay)
            project: Project name (embedded in all tokens)
            fl_server: FL Server endpoint URI (embedded in all tokens)
            cert_service: Certificate Service URL (embedded in all tokens)
            policy_id: Reference to server-side policy (default: "default")
            validity: Token validity duration (e.g., "7d", "24h")
            output_file: Optional file path to save tokens (CSV or TXT format)
            **claims: Additional claims to embed in each token

        Returns:
            List of dicts with "name" and "token" keys

        Example:
            # Generate 100 client tokens with auto-generated names
            tokens = service.batch_generate_tokens(
                count=100,
                name_prefix="hospital",
                project="healthcare-fl",
                fl_server="grpc://server:8002",
                cert_service="https://cert:8443",
                policy_id="trusted",
                validity="30d"
            )
            # Result: [{"name": "hospital-001", "token": "eyJ..."}, ...]

            # Generate tokens for specific clients
            tokens = service.batch_generate_tokens(
                names=["site-a", "site-b", "site-c"],
                project="my-project",
                fl_server="grpc://server:8002",
                cert_service="https://cert:8443"
            )
        """
        # Determine names
        if names:
            name_list = names
        else:
            if not name_prefix:
                name_prefix = "client"
            # Generate numbered names with zero-padding
            padding = max(len(str(count)), 3)  # At least 3 digits
            name_list = [f"{name_prefix}-{str(i+1).zfill(padding)}" for i in range(count)]

        results = []
        for name in name_list:
            token = self.generate_token(
                subject=name,
                subject_type=subject_type,
                project=project,
                fl_server=fl_server,
                cert_service=cert_service,
                policy_id=policy_id,
                validity=validity,
                **claims,
            )
            results.append(
                {
                    "name": name,
                    "token": token,
                }
            )

        # Optionally save to file
        if output_file:
            self._save_tokens_to_file(results, output_file)
            self.logger.info(f"Saved {len(results)} tokens to {output_file}")

        self.logger.info(f"Generated {len(results)} enrollment tokens")
        return results

    def _save_tokens_to_file(self, tokens: List[Dict[str, str]], output_file: str) -> None:
        """Save generated tokens to a file.

        Args:
            tokens: List of token dicts with name and token
            output_file: Output file path (.csv or .txt)
        """
        ext = os.path.splitext(output_file)[1].lower()

        with open(output_file, "w") as f:
            if ext == ".csv":
                f.write("name,token\n")
                for t in tokens:
                    f.write(f"{t['name']},{t['token']}\n")
            else:
                # Simple text format - one token per line with name
                for t in tokens:
                    f.write(f"{t['name']}: {t['token']}\n")

    def get_token_info(self, jwt_token: str) -> Dict[str, Any]:
        """Get token information without full validation (for inspection).

        Args:
            jwt_token: The JWT token string

        Returns:
            Dictionary with token details (from embedded claims)
        """
        try:
            # Decode without verification to inspect claims
            payload = jwt.decode(jwt_token, options={"verify_signature": False})

            return {
                "token_id": payload.get("jti"),
                "subject": payload.get("sub"),
                "subject_type": payload.get("subject_type"),
                "issuer": payload.get("iss"),
                "issued_at": datetime.fromtimestamp(payload.get("iat", 0), tz=timezone.utc).isoformat(),
                "expires_at": datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc).isoformat(),
                # Metadata claims
                "project": payload.get("project"),
                "fl_server": payload.get("fl_server"),
                "cert_service": payload.get("cert_service"),
                "policy_id": payload.get("policy_id", "default"),
                # Optional claims
                "roles": payload.get("roles"),
                "source_ips": payload.get("source_ips"),
            }
        except Exception as e:
            raise ValueError(f"Failed to decode token: {e}")
