# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
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

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nvflare import cli as cli_mod
from nvflare.fuel.flare_api.api_spec import AuthenticationError


def test_auth_hint_for_unknown_study():
    assert cli_mod._auth_hint_from_detail("unknown study 'cancer_research'") == (
        "Add the study under 'studies:' in project.yml with api_version: 4, reprovision, redeploy or restart the server, then try again."
    )


def test_auth_hint_for_missing_study_mapping():
    assert cli_mod._auth_hint_from_detail("user 'admin@nvidia.com' is not mapped to study 'cancer_research'") == (
        "Add this user under the study's admins mapping in project.yml, reprovision, redeploy or restart the server, then try again."
    )


def test_auth_hint_for_invalid_study_name():
    assert cli_mod._auth_hint_from_detail("invalid study name 'bad study'") == (
        "Use a valid study name in project.yml, reprovision, redeploy or restart the server, then try again."
    )


def test_auth_hint_defaults_to_credentials():
    assert cli_mod._auth_hint_from_detail("Incorrect user name or password") == "Check startup kit credentials."


def test_run_outputs_cert_auth_hint_in_json_mode(capsys):
    args = SimpleNamespace(sub_command="system", version=False, out_format="json", connect_timeout=5.0, debug=False)

    with patch.object(cli_mod, "parse_args", return_value=(MagicMock(), args, {"system": MagicMock()})):
        with patch.object(
            cli_mod, "handlers", {"system": MagicMock(side_effect=AuthenticationError("certificate validation failed"))}
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.run("nvflare")

    assert exc_info.value.code == 2
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["error_code"] == "AUTH_FAILED"
    assert envelope["hint"] == "Check startup kit credentials."
