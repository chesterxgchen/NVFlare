# Initramfs Overview

The initramfs (initial RAM filesystem) is a critical part of the Linux boot process, especially for encrypted systems. Let me explain:

## Purpose of initramfs:
- It's a temporary root filesystem loaded into memory during boot
- Contains essential tools and scripts needed before the real root filesystem is mounted
- Critical for handling encrypted partitions (needs keys before mounting)

## Directory Structure
We need to create this structure:

```
nvflare/tool/confidential_computing/build_scripts/nvidia_cc_base/scripts/initramfs/
├── scripts/
│   ├── init-premount/      # Scripts run before mounting root
│   │   └── tee-init       # Our TEE initialization script
│   └── local-top/         # Scripts run early in boot
│       └── tee-setup      # TEE setup and key derivation
├── hooks/                 # Scripts to include files in initramfs
│   └── tee               # Hook to include our TEE tools
└── modules               # Required kernel modules
    └── tee              # List of TEE-related modules
    

```