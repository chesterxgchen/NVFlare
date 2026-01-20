#!/usr/bin/env python3

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

from nvflare.tool.code_pre_installer.docker_cmd import define_docker_parser
from nvflare.tool.code_pre_installer.docker_cmd import docker_build
from nvflare.tool.code_pre_installer.local_cmd import define_local_parser
from nvflare.tool.code_pre_installer.local_cmd import local_install


def def_pre_install_parser(cmd, sub_cmd):
    parser = sub_cmd.add_parser(cmd)

    # Add subcommands
    pre_install_parser = parser.add_subparsers(title=cmd, dest="pre_install_sub_cmd", help="pre-install subcommand")

    # Add docker subcommand (build Docker image with pre-installed code)
    define_docker_parser("docker", pre_install_parser)

    # Add local subcommand (install locally, no Docker)
    define_local_parser("local", pre_install_parser)

    return {cmd: parser}


def handle_pre_install_cmd(args):
    """Handle pre-install commands."""
    if args.pre_install_sub_cmd == "docker":
        docker_build(args)
    elif args.pre_install_sub_cmd == "local":
        local_install(args)
    else:
        print("Usage: nvflare pre-install <command>")
        print()
        print("Commands:")
        print("  docker    Build Docker image with pre-installed application code")
        print("  local     Install application code locally (no Docker)")
        print()
        print("Examples:")
        print("  nvflare pre-install docker -j jobs/fedavg -s site-1")
        print("  nvflare pre-install local -j jobs/fedavg -s site-1 -p /path/to/local/custom")
