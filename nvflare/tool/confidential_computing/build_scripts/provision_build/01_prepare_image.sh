#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/provision.conf"
source "${SCRIPT_DIR}/utils/utils.sh"

# Resize partition in qcow2 image
resize_partition() {
    local image="$1"
    local size="$2"
    local part_num="$3"

    # Resize image
    qemu-img resize "$image" "+${size}"

    # Resize partition
    guestfish -a "$image" << EOF
        run
        # Expand partition table
        part-expand-gpt /dev/sda
        # Resize partition
        resize /dev/sda${part_num}
        # Resize filesystem
        resize2fs /dev/sda${part_num}
        exit
EOF
}

prepare_image() {
    local base_image="$1"
    local output_image="$2"

    # Check if base image exists
    if [[ ! -f "$base_image" ]]; then
        log_error "Base image not found: $base_image"
        return 1
    }

    # Check required tools
    for cmd in qemu-img guestfish; do
        if ! command -v $cmd &> /dev/null; then
            log_error "Required command not found: $cmd"
            return 1
        fi
    done

    # Calculate required sizes
    local app_pex_size=$(get_file_size "${APP_PEX_PATH}") || return 1
    local startup_kit_size=$(get_file_size "${STARTUP_KIT_PATH}") || return 1

    # Calculate partition sizes with safety factor
    local p4_size=$(calculate_size_gb "$app_pex_size")
    local p2_size=$(calculate_size_gb "$startup_kit_size")

    # Copy base image
    cp "$base_image" "$output_image"

    # Resize CC Apps partition (p4)
    log_info "Resizing CC Apps partition (p4) to $p4_size..."
    resize_partition "$output_image" "$p4_size" 4

    # Resize Host-visible config partition (p2)
    log_info "Resizing Host-visible config partition (p2) to $p2_size..."
    resize_partition "$output_image" "$p2_size" 2

    log_info "Image prepared with resized partitions:"
    log_info "CC Apps partition (p4) resized to: $p4_size"
    log_info "Host-visible config partition (p2) resized to: $p2_size"
}

main() {
    log_info "Starting image preparation..."

    if ! prepare_image "${BASE_IMAGE}" "${OUTPUT_IMAGE}"; then
        log_error "Image preparation failed"
        return 1
    fi

    log_info "Image preparation completed successfully"
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 