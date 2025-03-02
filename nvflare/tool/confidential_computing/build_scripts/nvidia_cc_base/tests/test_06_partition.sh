#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_partitions() {
    local test_dir=$(mktemp -d)
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"

    # Test partition layout
    test_partition_layout() {
        # Check all required partitions exist
        local required_partitions=(
            "${DEVICE}p1"  # Boot partition (unencrypted, host visible)
            "${DEVICE}p2"  # Host-visible CC config partition (unencrypted)
            "${DEVICE}p3"  # Root partition (encrypted)
            "${DEVICE}p4"  # CC Applications partition (encrypted)
            "${DEVICE}p5"  # Dynamic partition
        )

        for part in "${required_partitions[@]}"; do
            if ! blkid "$part" > /dev/null 2>&1; then
                error "Required partition '$part' not found"
            fi
        done

        # Test partition sizes
        local min_sizes=(
            "512M"    # Boot min size
            "256M"    # CC config min size
            "20G"     # Root min size
            "5G"      # CC Apps min size
            "*"       # Dynamic uses remaining space
        )
        
        for i in "${!required_partitions[@]}"; do
            local size=$(blockdev --getsize64 "${required_partitions[$i]}")
            local min_bytes=$(numfmt --from=iec "${min_sizes[$i]}")
            if [ "$size" -lt "$min_bytes" ]; then
                error "Partition ${required_partitions[$i]} smaller than ${min_sizes[$i]}"
            fi
        done
    }

    # Test LUKS setup
    test_luks_setup() {
        local encrypted_parts=("p2" "p3")  # Root and App partitions
        for part in "${encrypted_parts[@]}"; do
            if ! cryptsetup isLuks "${DEVICE}${part}"; then
                error "LUKS not setup on partition ${part}"
            fi

            # Verify LUKS configuration
            local header_info=$(cryptsetup luksDump "${DEVICE}${part}")
            if ! echo "$header_info" | grep -q "cipher: ${LUKS_CIPHER}"; then
                error "Wrong cipher on partition ${part}"
            fi
            if ! echo "$header_info" | grep -q "key-size: ${LUKS_KEY_SIZE}"; then
                error "Wrong key size on partition ${part}"
            fi
            
            # Test LUKS2 specific features
            if ! echo "$header_info" | grep -q "LUKS2"; then
                error "Not using LUKS2 on partition ${part}"
            fi
            
            # Verify integrity protection
            if ! echo "$header_info" | grep -q "integrity: ${LUKS_INTEGRITY}"; then
                error "Integrity protection not enabled on partition ${part}"
            fi
        done
    }

    # Test verity setup
    test_verity_setup() {
        if ! veritysetup verify "${DEVICE}p4" "${DEVICE}p4.verity"; then
            error "Verity verification failed for read-only partition"
        fi

        local root_hash=$(veritysetup dump "${DEVICE}p4" | grep "Root hash:" | cut -d: -f2)
        if [ -z "$root_hash" ]; then
            error "Verity root hash not found"
        fi
        
        # Test verity configuration
        local verity_info=$(veritysetup dump "${DEVICE}p4")
        if ! echo "$verity_info" | grep -q "hash_algorithm: ${VERITY_HASH}"; then
            error "Wrong hash algorithm for verity"
        fi
        if ! echo "$verity_info" | grep -q "data_block_size: ${VERITY_BLOCK_SIZE}"; then
            error "Wrong block size for verity"
        fi
    }

    # Test mount points
    test_mount_points() {
        local fstab="${test_dir}/etc/fstab"
        
        # Check boot partition
        if ! grep -q "^UUID=$(blkid -s UUID -o value ${DEVICE}p1) /boot.*noauto,noatime" "$fstab"; then
            error "Boot partition not properly configured in fstab"
        fi

        # Check CC config partition
        if ! grep -q "^UUID=$(blkid -s UUID -o value ${DEVICE}p2) /host/cc.*noauto,noatime,ro" "$fstab"; then
            error "CC config partition not properly configured in fstab"
        fi

        # Check root partition
        if ! grep -q "^/dev/mapper/root_crypt /.*defaults,noatime,resize" "$fstab"; then
            error "Root partition not properly configured in fstab"
        fi

        # Check CC apps partition
        if ! grep -q "^/dev/mapper/cc_crypt /etc/cc.*defaults,noatime,resize" "$fstab"; then
            error "CC apps partition not properly configured in fstab"
        fi

        # Test dynamic partition mount
        if ! grep -q "^/dev/mapper/dynamic_crypt /dynamic.*defaults,noatime" "$fstab"; then
            error "Dynamic partition not properly configured in fstab"
        fi
    }

    # Test crypttab
    test_crypttab() {
        local crypttab="${test_dir}/etc/crypttab"
        
        if ! grep -q "^root_crypt UUID=$(blkid -s UUID -o value ${DEVICE}p2) none luks" "$crypttab"; then
            error "Root partition not in crypttab"
        fi

        if ! grep -q "^app_crypt UUID=$(blkid -s UUID -o value ${DEVICE}p3) none luks" "$crypttab"; then
            error "App partition not in crypttab"
        fi
        
        # Test crypttab options
        if ! grep -q "luks,discard,no-read-workqueue,no-write-workqueue" "$crypttab"; then
            error "Crypttab performance options not set"
        fi
        
        # Test dynamic partition setup
        test_dynamic_partition() {
            # Check dynamic partition is not mounted by default
            if mount | grep -q "$DYNAMIC_MOUNT"; then
                error "Dynamic partition mounted at boot"
            fi
            
            # Test dynamic partition script
            if [ ! -x "${test_dir}/usr/local/sbin/setup_dynamic_partition.sh" ]; then
                error "Dynamic partition setup script not found or not executable"
            fi
            
            # Test dynamic partition configuration
            if [ ! -f "${test_dir}/etc/cc/dynamic_partition.conf" ]; then
                error "Dynamic partition config not found"
            fi
        }

        # Test key slots
        for part in root_crypt app_crypt; do
            if ! cryptsetup luksDump "/dev/mapper/$part" | grep -q "Key Slot 0: ENABLED"; then
                error "Primary key slot not enabled for $part"
            fi
        done
    }

    # Test secure boot setup
    test_secure_boot() {
        # Check UEFI secure boot keys
        if [ ! -d "${test_dir}/etc/secureboot/keys" ]; then
            error "Secure boot keys not found"
        fi
        
        # Check boot partition signature
        if ! sbverify --cert "${test_dir}/etc/secureboot/keys/db.crt" "${test_dir}/boot/vmlinuz"; then
            error "Kernel not signed for secure boot"
        fi
    }

    # Run all tests
    test_partition_layout
    test_luks_setup
    test_verity_setup
    test_mount_points
    test_crypttab
    test_secure_boot
    test_dynamic_partition

    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_partitions 