# PEX Builder Tool

This tool helps build Python EXecutable (PEX) packages for secure deployment environments. PEX files are self-contained Python environments that include all dependencies and can be executed directly.

## Overview

The PEX builder tool:
- Creates self-contained Python executables
- Includes all dependencies
- Generates verification hashes
- Works offline (no PyPI access needed during execution)
- Supports custom requirements
- Verifies package integrity

## Requirements

### Python Version
- Python >3.8 (3.9, 3.10, 3.11)
- CPython implementation only
- Virtual environment support

### System Requirements
- pex tool (auto-installed if missing)
- virtualenv
- pip >= 20.0

### Operating System
- Linux (Ubuntu 20.04 or later recommended)
- Sufficient disk space for dependencies

## Usage

### Basic Usage

1. Build with default requirements:
```bash
./build_pex.sh
```
This will:
- Use default `requirements.txt` in the same directory
- Output to `./output/` directory
- Create `package.pex` and `package.pex.sha512`

2. Build with custom requirements and output:
```bash
./build_pex.sh /path/to/requirements.txt /path/to/output/
```

3. Build with entry point (specific package):
```bash
./build_pex.sh requirements.txt output/ "nvflare==2.5.2"
```
This creates `nvflare-2.5.2.pex` and its hash file.

### Requirements File

Create a requirements.txt file with your dependencies:
```text
# Main package
nvflare==2.5.2

# Dependencies
numpy>=1.21.0
torch>=1.10.0
...
```

### Output Files

The tool generates:
- `<package>-<version>.pex`: The executable package
- `<package>-<version>.pex.sha512`: SHA512 hash for verification

### Verification

The tool automatically verifies:
- Package hash integrity
- Basic execution test
- Package contents

## Examples

1. Build NVFLARE package:
```bash
./build_pex.sh nvflare_requirements.txt output/ "nvflare==2.5.2"
```

2. Build application package:
```bash
./build_pex.sh app_requirements.txt output/ "myapp==1.0.0"
```

3. Build dependency bundle without entry point:
```bash
./build_pex.sh requirements.txt output/
```

## Security Features

- Offline building capability (--no-pypi)
- SHA512 hash verification
- Dependency isolation
- No network access needed during execution
- Package integrity verification

## Common Issues

1. Python version not supported:
```bash
# Check Python version
python3 --version  # Must be >3.8

# If needed, install supported version:
sudo apt install python3.9  # or 3.10, 3.11
```

2. Missing dependencies:
```bash
# Install build requirements
pip install pex virtualenv
```

3. Permission issues:
```bash
# Make script executable
chmod +x build_pex.sh
```

4. Python path specification:
```bash
# Specify Python version explicitly
./build_pex.sh requirements.txt output/ "package==1.0.0" --python-path /usr/bin/python3.9
```

## Best Practices

1. Always pin exact versions in requirements.txt:
```text
nvflare==2.5.2
numpy==1.21.0
```

2. Verify hashes after copying:
```bash
sha512sum -c package-1.0.0.pex.sha512
```

3. Test in isolated environment:
```bash
# Create test directory
mkdir test && cd test
# Copy PEX file
cp ../output/package-1.0.0.pex .
# Test execution
./package-1.0.0.pex --version
```

4. Use specific Python version:
```bash
# Create venv with specific version
python3.9 -m venv venv
source venv/bin/activate

# Build PEX
./build_pex.sh requirements.txt output/ "package==1.0.0"
```

## Integration with Build Systems

The tool can be integrated into secure build pipelines:

```bash
# Phase 1: Build base packages
./build_pex.sh base_requirements.txt /mnt/secure/base/ "nvflare==2.5.2"

# Phase 2: Build application
./build_pex.sh app_requirements.txt /mnt/secure/app/ "app==1.0.0"

# Verify all packages
for pex in /mnt/secure/*/*.pex; do
    sha512sum -c "${pex}.sha512"
done
```

## License

Copyright (c) 2024, NVIDIA Corporation. All rights reserved. 