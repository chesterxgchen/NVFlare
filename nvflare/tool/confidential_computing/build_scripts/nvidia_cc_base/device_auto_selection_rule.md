# Device Auto-Selection Rules

This document describes the rules used for automatic device selection during installation.

## Scoring System

Devices are scored based on:

1. Device Type:
   - NVMe devices: 100 base points
   - SATA/SCSI devices: 50 base points

2. Size Bonus:
   - +1 point per GB over minimum (32GB)
   - Example: 1TB NVMe = 100 + (1024-32) = 1092 points

## Disqualification Rules

Devices are automatically disqualified if:

1. Size Requirements:
   - Less than 32GB total size
   - Insufficient space for required partitions

2. System Safety:
   - Contains OS partitions (EFI or boot)
   - Currently mounted
   - System boot drive

3. Hardware Compatibility:
   - Unsupported device types
   - Virtual devices

## Selection Process

1. Device Discovery:
   - Scan for NVMe devices (/dev/nvme*)
   - Scan for SATA devices (/dev/sd*)

2. Initial Filtering:
   - Apply disqualification rules
   - Calculate scores for remaining devices

3. Device Selection:
   - Choose highest scoring device
   - Log selection reasoning
   - Allow manual override if AUTO_SELECT=false

## Example Scoring

```
Device         Base   Size   Total   Selected
/dev/nvme0n1   100 + 992  = 1092   No (OS disk)
/dev/nvme1n1   100 + 480  = 580    Yes
/dev/sda       50  + 224  = 274    No (lower score)
/dev/sdb       50  + 96   = 146    No (mounted)
/dev/sdc       50  + 0    = 50     No (too small)
``` 