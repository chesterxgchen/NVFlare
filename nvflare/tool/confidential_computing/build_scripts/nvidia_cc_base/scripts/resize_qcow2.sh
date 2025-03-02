#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"

usage() {
    echo "Usage: $0 [OPTIONS] QCOW2_IMAGE PARTITION_NUMBER"
    echo "Resize partitions in a QCOW2 image"
    echo ""
    echo "Options:"
    echo "  -h, --help                Show this help message"
    echo "  -s, --size SIZE          New size for the partition (e.g., '+10G')"
    echo "  -i, --image-size SIZE    New size for the entire QCOW2 image (e.g., '50G')"
    echo "  -d, --dry-run            Show what would be done without making changes"
    echo "  -v, --verbose            Show detailed progress"
    echo "  -b, --backup             Create backup before resizing"
    echo "  -f, --force              Skip safety checks"
    echo "  --verify                 Verify image after resize"
    echo ""
    echo "Supported partitions:"
    echo "  2  - /boot partition"
    echo "  3  - root partition (encrypted)"
    echo "  5  - dynamic partition (encrypted)"
    echo ""
    echo "Example:"
    echo "  $0 -i 50G -s +10G cc-base.qcow2 3    # Extend image to 50G and root partition by 10G"
    echo "  $0 -i +20G cc-base.qcow2 5           # Extend image by 20G and dynamic partition"
    echo "  $0 -d -i +20G cc-base.qcow2 5        # Show what would happen without changes"
}

validate_size() {
    local size="$1"
    local type="$2"  # 'image' or 'partition'

    # Check size format
    if ! [[ "$size" =~ ^[+]?[0-9]+[KMGT]$ ]]; then
        error "Invalid $type size format: $size (should be like '50G' or '+10G')"
        return 1
    }

    # Extract numeric value and unit
    local value=${size//[^0-9]/}
    local unit=${size//[^KMGT]/}

    # Validate minimum size
    case $unit in
        G)
            if [ "$value" -lt 1 ]; then
                error "Minimum $type size is 1G"
                return 1
            fi
            ;;
        T)
            # Allow terabyte sizes
            ;;
        *)
            error "$type size must be specified in GB or TB"
            return 1
            ;;
    esac
}

check_image_format() {
    local image="$1"

    # Check if it's a QCOW2 image
    local format=$(qemu-img info "$image" | grep "file format" | awk '{print $3}')
    if [ "$format" != "qcow2" ]; then
        error "Image is not in QCOW2 format: $image"
        return 1
    }

    # Check if image is not corrupted
    if ! qemu-img check "$image" >/dev/null 2>&1; then
        error "Image appears to be corrupted: $image"
        return 1
    }
}

check_partition_table() {
    local device="$1"
    local part_num="$2"

    # Wait for partition table to be readable
    local retries=5
    while [ $retries -gt 0 ]; do
        if sfdisk -d "$device" >/dev/null 2>&1; then
            break
        fi
        sleep 1
        retries=$((retries - 1))
    done

    if [ $retries -eq 0 ]; then
        error "Failed to read partition table from device: $device"
        return 1
    }

    # Check if partition exists
    if ! sfdisk -d "$device" | grep -q "^${device}p${part_num}"; then
        error "Partition ${part_num} not found in partition table"
        return 1
    }
}

# Verbose logging
vlog() {
    if [ "$verbose" = "true" ]; then
        log "$@"
    fi
}

# Error logging with details in verbose mode
error_verbose() {
    local msg="$1"
    local detail="$2"

    error "$msg"
    if [ "$verbose" = "true" ] && [ -n "$detail" ]; then
        log "Error details:"
        echo "$detail" | while IFS= read -r line; do
            log "  $line"
        done
    fi
}

# Show detailed command output in verbose mode
run_verbose() {
    local cmd="$1"
    local msg="$2"
    local output

    if [ "$verbose" = "true" ]; then
        log "Executing: $cmd"
    fi

    output=$($cmd 2>&1)
    local ret=$?

    if [ $ret -ne 0 ]; then
        error_verbose "$msg" "$output"
        return $ret
    elif [ "$verbose" = "true" ]; then
        log "Command output:"
        echo "$output" | while IFS= read -r line; do
            log "  $line"
        done
    fi
    return 0
}

show_image_info() {
    local image="$1"
    local label="$2"

    if [ "$verbose" = "true" ]; then
        log "$label Image Information:"
        qemu-img info "$image" | while IFS= read -r line; do
            log "  $line"
        done
        
        # Show partition information if mounted
        if [ -b /dev/nbd0 ]; then
            log "Partition Layout:"
            fdisk -l /dev/nbd0 | grep "^/dev" | while IFS= read -r line; do
                log "  $line"
            done
            
            log "Partition Usage:"
            df -h /dev/nbd0* 2>/dev/null | grep "^/dev" | while IFS= read -r line; do
                log "  $line"
            done
        fi
    fi
}

show_partition_info() {
    local part_num="$1"
    local device="/dev/nbd0p${part_num}"

    if [ "$verbose" = "true" ]; then
        case $part_num in
            2)
                log "Boot Partition Details:"
                tune2fs -l "$device" | grep -E "Block (count|size)|Filesystem|Mount count" | while IFS= read -r line; do
                    log "  $line"
                done
                ;;
            3)
                log "Root Partition Details:"
                cryptsetup status root_crypt
                lvs vg_root -o lv_name,lv_size,lv_path --noheadings
                ;;
            5)
                log "Dynamic Partition Details:"
                cryptsetup status dynamic_crypt
                ;;
        esac
    fi
}

# Time estimation
declare -A operation_times=(
    ["backup"]=30    # ~30s per GB
    ["verify"]=15    # ~15s per GB
    ["resize"]=10    # ~10s per GB
    ["growpart"]=5   # ~5s per operation
    ["cryptsetup"]=3 # ~3s per operation
    ["resize2fs"]=20 # ~20s per GB
)

# Calculate estimated time
estimate_time() {
    local op="$1"
    local size_gb="$2"  # Size in GB
    local base_time=${operation_times[$op]}
    
    if [[ "$op" =~ ^(backup|verify|resize|resize2fs)$ ]]; then
        echo $((base_time * size_gb))
    else
        echo $base_time
    fi
}

# Progress tracking
progress() {
    local current="$1"
    local total="$2"
    local msg="$3"
    local start_time="$4"
    local width=50  # Progress bar width
    local percent=$((current * 100 / total))
    local filled=$((width * current / total))
    local empty=$((width - filled))

    # Calculate time elapsed and estimate remaining
    local now=$(date +%s)
    local elapsed=$((now - start_time))
    local rate=$(echo "scale=2; $current/$elapsed" | bc 2>/dev/null)
    local remaining=0
    
    if [ "$rate" != "0" ] && [ "$rate" != "" ]; then
        remaining=$(echo "scale=0; ($total - $current)/$rate" | bc 2>/dev/null)
    fi

    # Create the progress bar
    printf -v bar "%${filled}s" ""
    printf -v space "%${empty}s" ""
    bar=${bar// /#}
    space=${space// /-}

    # Print progress
    printf "\r[%s%s] %3d%% %s (ETA: %02d:%02d)" \
        "$bar" "$space" "$percent" "$msg" \
        $((remaining / 60)) $((remaining % 60))

    if [ "$current" -eq "$total" ]; then
        printf " [Done in %02d:%02d]\n" \
            $((elapsed / 60)) $((elapsed % 60))
    fi
}

# Copy with progress
copy_with_progress() {
    local src="$1"
    local dst="$2"
    local size=$(stat -f %z "$src")
    local block_size=1048576  # 1MB blocks
    local copied=0
    local start_time=$(date +%s)
    local size_gb=$(echo "scale=0; $size/1024/1024/1024 + 1" | bc)
    local estimated=$(estimate_time "backup" $size_gb)
    
    vlog "Estimated time for copy: ${estimated}s (${size_gb}GB)"

    dd if="$src" bs=$block_size 2>/dev/null | {
        while IFS= read -r -n $block_size block; do
            copied=$((copied + ${#block}))
            progress $copied $size "Copying..." $start_time
            echo -n "$block" >> "$dst"
        done
    }
    echo
}

create_backup() {
    local image="$1"
    local backup="${image}.backup-$(date +%Y%m%d-%H%M%S)"

    log "Creating backup of image to: $backup"
    copy_with_progress "$image" "$backup"
    
    # Verify backup
    log "Verifying backup..."
    local total_size=$(stat -f %z "$image")
    local verified=0

    if ! cmp -s "$image" "$backup"; then
        error "Backup verification failed"
        rm -f "$backup"
        return 1
    fi
    
    vlog "Backup created and verified"
}

verify_image() {
    local image="$1"
    
    vlog "Verifying image integrity"
    
    # Check filesystem
    if ! qemu-img check "$image"; then
        error "Image verification failed"
        return 1
    fi
    
    # Check partition table
    if ! qemu-nbd --connect=/dev/nbd0 "$image"; then
        error "Failed to connect image for verification"
        return 1
    fi
    
    if ! sfdisk -V /dev/nbd0; then
        qemu-nbd --disconnect /dev/nbd0
        error "Partition table verification failed"
        return 1
    fi
    
    qemu-nbd --disconnect /dev/nbd0
    vlog "Image verification passed"
}

check_space() {
    local image="$1"
    local new_size="$2"
    
    # Get available space
    local dir=$(dirname "$image")
    local available=$(df -BG "$dir" | awk 'NR==2 {print $4}' | tr -d 'G')
    local required=${new_size//[^0-9]/}
    
    if [ "$available" -lt "$required" ]; then
        error "Insufficient space: need ${required}G, have ${available}G"
        return 1
    fi
    
    vlog "Space check passed: ${available}G available"
}

resize_qcow2() {
    local image="$1"
    local new_size="$2"
    local dry_run="$3"
    local start_time=$(date +%s)

    # Get image size in GB
    local current_size=$(qemu-img info "$image" | grep 'virtual size' | awk '{print $4}' | tr -d '()')
    local target_size=${new_size//[^0-9]/}
    local size_diff=$((target_size - current_size))
    
    # Calculate total estimated time
    local total_est=0
    [ "$backup" = "true" ] && total_est=$((total_est + $(estimate_time "backup" $current_size)))
    total_est=$((total_est + $(estimate_time "resize" $size_diff)))
    [ "$verify" = "true" ] && total_est=$((total_est + $(estimate_time "verify" $target_size)))
    
    vlog "Estimated total time: ${total_est}s"

    show_image_info "$image" "Current"
    vlog "Starting QCOW2 resize operation:"
    vlog "  Image: $image"
    vlog "  Target size: $new_size"
    vlog "  Current time: $(date)"
    vlog "  Estimated completion: $(date -d "@$(($(date +%s) + total_est))")"

    # Calculate total steps
    local total_steps=1  # Base resize
    [ "$backup" = "true" ] && total_steps=$((total_steps + 2))  # Backup + verify
    [ "$verify" = "true" ] && total_steps=$((total_steps + 1))  # Final verify
    local current_step=0

    if [ "$dry_run" = "true" ]; then
        log "(dry-run) Would execute: qemu-img resize $image $new_size"
        return
    fi

    if [ "$backup" = "true" ]; then
        create_backup "$image" || return 1
        current_step=$((current_step + 2))
        progress $current_step $total_steps "Backup completed" $start_time
    fi

    if ! check_space "$image" "$new_size"; then
        return 1
    fi

    run_verbose "qemu-img resize '$image' '$new_size'" "Failed to resize image" || return 1
    current_step=$((current_step + 1))
    progress $current_step $total_steps "Image resize completed" $start_time

    if [ "$verify" = "true" ]; then
        verify_image "$image" || return 1
        current_step=$((current_step + 1))
        progress $current_step $total_steps "Verification completed" $start_time
    fi

    show_image_info "$image" "Updated"
    vlog "Resize operation completed at: $(date)"
}

mount_qcow2() {
    local image="$1"
    local mount_dir="$2"
    local dry_run="$3"

    log "Mounting QCOW2 image"
    if [ "$dry_run" = "true" ]; then
        log "(dry-run) Would mount $image to $mount_dir"
        return
    fi
    modprobe nbd max_part=8
    qemu-nbd --connect=/dev/nbd0 "$image"
    mkdir -p "$mount_dir"
    # Wait for device
    sleep 2

    # Verify mount
    if ! [ -b /dev/nbd0 ]; then
        error "Failed to create NBD device"
        return 1
    }
}

unmount_qcow2() {
    local mount_dir="$1"

    log "Unmounting QCOW2 image"
    if mountpoint -q "$mount_dir"; then
        umount "$mount_dir"
    fi
    qemu-nbd --disconnect /dev/nbd0
    rm -rf "$mount_dir"
}

resize_partition() {
    local part_num="$1"
    local size="$2"
    local dry_run="$3"

    # Calculate total steps for this partition
    local total_steps
    case $part_num in
        2) total_steps=2 ;;  # growpart + resize2fs
        3) total_steps=5 ;;  # growpart + luks + pv + lv + resize2fs
        5) total_steps=3 ;;  # growpart + luks + resize2fs
    esac
    local current_step=0

    vlog "Starting partition resize operation:"
    vlog "  Partition: $part_num"
    vlog "  Target size: ${size:-'all available space'}"
    vlog "  Current time: $(date)"

    # Check partition table before resizing
    check_partition_table /dev/nbd0 "$part_num" || return 1

    show_partition_info "$part_num"
    case $part_num in
        2)
            log "Resizing /boot partition"
            if [ "$dry_run" = "true" ]; then
                log "(dry-run) Would resize /boot partition"
                return
            fi
            run_verbose "growpart /dev/nbd0 2" "Failed to grow partition" || return 1
            current_step=$((current_step + 1))
            progress $current_step $total_steps "Partition extended" $start_time
            run_verbose "resize2fs /dev/nbd0p2" "Failed to resize filesystem" || return 1
            current_step=$((current_step + 1))
            progress $current_step $total_steps "Filesystem resized" $start_time
            show_partition_info "2"
            ;;
        3)
            log "Resizing root partition"
            if [ "$dry_run" = "true" ]; then
                log "(dry-run) Would resize encrypted root partition"
                return
            fi
            run_verbose "growpart /dev/nbd0 3" "Failed to grow partition" || return 1
            run_verbose "cryptsetup luksOpen /dev/nbd0p3 root_crypt" "Failed to open LUKS container" || return 1
            run_verbose "pvresize /dev/mapper/root_crypt" "Failed to resize physical volume" || return 1
            if [ -n "$size" ]; then
                run_verbose "lvextend -L '$size' /dev/mapper/vg_root-lv_root" "Failed to extend logical volume" || return 1
            else
                run_verbose "lvextend -l +100%FREE /dev/mapper/vg_root-lv_root" "Failed to extend logical volume" || return 1
            fi
            run_verbose "resize2fs /dev/mapper/vg_root-lv_root" "Failed to resize filesystem" || return 1
            cryptsetup luksClose root_crypt
            show_partition_info "3"
            ;;
        5)
            log "Resizing dynamic partition"
            if [ "$dry_run" = "true" ]; then
                log "(dry-run) Would resize encrypted dynamic partition"
                return
            fi
            run_verbose "growpart /dev/nbd0 5" "Failed to grow partition" || return 1
            run_verbose "cryptsetup luksOpen /dev/nbd0p5 dynamic_crypt" "Failed to open LUKS container" || return 1
            run_verbose "resize2fs /dev/mapper/dynamic_crypt" "Failed to resize filesystem" || return 1
            cryptsetup luksClose dynamic_crypt
            show_partition_info "5"
            ;;
        *)
            error "Unsupported partition number: $part_num"
            return 1
            ;;
    esac

    vlog "Partition resize operation completed at: $(date)"
}

check_prerequisites() {
    # Check required tools
    for cmd in qemu-img qemu-nbd cryptsetup growpart resize2fs; do
        if ! command -v $cmd >/dev/null 2>&1; then
            error "Required command not found: $cmd"
            exit 1
        fi
    done
}

main() {
    local image_size=""
    local part_size=""
    local image=""
    local part_num=""
    local mount_dir="/tmp/qcow2_mount"
    local dry_run="false"
    local verbose="false"
    local backup="false"
    local force="false"
    local verify="false"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -s|--size)
                part_size="$2"
                shift 2
                ;;
            -i|--image-size)
                image_size="$2"
                shift 2
                ;;
            -d|--dry-run)
                dry_run="true"
                shift
                ;;
            -v|--verbose)
                verbose="true"
                shift
                ;;
            -b|--backup)
                backup="true"
                shift
                ;;
            -f|--force)
                force="true"
                shift
                ;;
            --verify)
                verify="true"
                shift
                ;;
            *)
                if [ -z "$image" ]; then
                    image="$1"
                elif [ -z "$part_num" ]; then
                    part_num="$1"
                else
                    error "Unknown argument: $1"
                    usage
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Validate arguments
    if [ -z "$image" ] || [ -z "$part_num" ]; then
        error "Missing required arguments"
        usage
        exit 1
    fi

    if [ ! -f "$image" ]; then
        error "Image file not found: $image"
        exit 1
    fi

    # Validate image format
    check_image_format "$image" || exit 1

    # Validate sizes if provided
    if [ -n "$image_size" ]; then
        validate_size "$image_size" "image" || exit 1
    fi
    if [ -n "$part_size" ]; then
        validate_size "$part_size" "partition" || exit 1
    fi

    check_prerequisites

    # Safety checks unless forced
    if [ "$force" != "true" ]; then
        # Check if image is in use
        if lsof "$image" >/dev/null 2>&1; then
            error "Image is in use. Use --force to override"
            exit 1
        fi

        # Check if enough free space
        if [ -n "$image_size" ]; then
            check_space "$image" "$image_size" || exit 1
        fi
    fi

    # Resize image if requested
    resize_qcow2 "$image" "$image_size" "$dry_run"

    # Mount image and resize partition
    mount_qcow2 "$image" "$mount_dir" "$dry_run"
    resize_partition "$part_num" "$part_size" "$dry_run"
    [ "$dry_run" = "false" ] && unmount_qcow2 "$mount_dir"

    if [ "$dry_run" = "true" ]; then
        success "Dry run completed - no changes made"
    else
        if [ "$verify" = "true" ]; then
            log "Verifying final image..."
            verify_image "$image" || {
                error "Final verification failed"
                exit 1
            }
        fi
        success "QCOW2 image resize completed successfully"
    fi
}

main "$@" 