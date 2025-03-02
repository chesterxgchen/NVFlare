#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"

# Copy and resize base image
cp "$BASE_IMAGE" "$OUTPUT_IMAGE"

# Function to label partition
label_partition() {
    local image="$1"
    local device="$2"
    local label="$3"
    
    if ! guestfish -a "$image" run : set-label "$device" "$label"; then
        error "Failed to label partition $device as $label"
        return 1
    fi
    
    # Verify label
    local actual_label
    actual_label=$(guestfish -a "$image" run : get-label "$device")
    if [ "$actual_label" != "$label" ]; then
        error "Label verification failed for $device"
        return 1
    fi
    return 0
}

# Label all partitions
log "Labeling partitions..."

# Get partition list
partitions=$(guestfish -a "$OUTPUT_IMAGE" run : list-partitions)

# Label each partition
echo "$partitions" | while read -r device; do
    case "$device" in
        *3) label_partition "$OUTPUT_IMAGE" "$device" "${NVFLARE_ROOT_LABEL}" ;;
        *4) label_partition "$OUTPUT_IMAGE" "$device" "${NVFLARE_CONFIG_LABEL}" ;;
        *5) label_partition "$OUTPUT_IMAGE" "$device" "${NVFLARE_DYNAMIC_LABEL}" ;;
        *6) label_partition "$OUTPUT_IMAGE" "$device" "${NVFLARE_DATA_LABEL}" ;;
    esac
done

# Verify all labels
log "Verifying partition labels..."
for label in "${NVFLARE_ROOT_LABEL}" "${NVFLARE_CONFIG_LABEL}" "${NVFLARE_DYNAMIC_LABEL}" "${NVFLARE_DATA_LABEL}"; do
    if ! guestfish -a "$OUTPUT_IMAGE" run : findfs-label "$label" >/dev/null; then
        error "Could not find partition with label: $label"
        exit 1
    fi
done

"${SCRIPT_DIR}/../../nvidia_cc_base/scripts/resize_qcow2.sh" -i "$RESIZE_TO" "$OUTPUT_IMAGE" 3 