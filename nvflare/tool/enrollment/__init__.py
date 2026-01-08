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

"""FLARE Enrollment CLI Tools.

This package provides CLI tools for enrollment token generation and management.
The TokenService requires PyJWT as an optional dependency.

For certificate enrollment (client-side), see nvflare.security.enrollment.

CLI Usage:
    nvflare token generate -n site-1 --cert-service https://... --project myproj --fl-server grpc://server:8002
    nvflare token batch --pattern "site-{001..010}" -o tokens.csv ...
    nvflare token info -t <jwt_token>
    nvflare enrollment list --cert-service https://...
    nvflare policy list --cert-service https://...
"""

from typing import TYPE_CHECKING

# Static imports for IDE type checking (not executed at runtime)
if TYPE_CHECKING:
    from nvflare.tool.enrollment.enrollment_cli import define_enrollment_parser, handle_enrollment_cmd
    from nvflare.tool.enrollment.policy_cli import define_policy_parser, handle_policy_cmd
    from nvflare.tool.enrollment.token_cli import def_token_parser, handle_token_cmd
    from nvflare.tool.enrollment.token_service import TokenService

__all__ = [
    "TokenService",
    "def_token_parser",
    "handle_token_cmd",
    "define_enrollment_parser",
    "handle_enrollment_cmd",
    "define_policy_parser",
    "handle_policy_cmd",
]


def __getattr__(name: str):
    """Lazy import to avoid requiring jwt/requests/yaml dependency at import time."""
    if name == "TokenService":
        from nvflare.tool.enrollment.token_service import TokenService

        return TokenService
    if name == "def_token_parser":
        from nvflare.tool.enrollment.token_cli import def_token_parser

        return def_token_parser
    if name == "handle_token_cmd":
        from nvflare.tool.enrollment.token_cli import handle_token_cmd

        return handle_token_cmd
    if name == "define_enrollment_parser":
        from nvflare.tool.enrollment.enrollment_cli import define_enrollment_parser

        return define_enrollment_parser
    if name == "handle_enrollment_cmd":
        from nvflare.tool.enrollment.enrollment_cli import handle_enrollment_cmd

        return handle_enrollment_cmd
    if name == "define_policy_parser":
        from nvflare.tool.enrollment.policy_cli import define_policy_parser

        return define_policy_parser
    if name == "handle_policy_cmd":
        from nvflare.tool.enrollment.policy_cli import handle_policy_cmd

        return handle_policy_cmd
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
