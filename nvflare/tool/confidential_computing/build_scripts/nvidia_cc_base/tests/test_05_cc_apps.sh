#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_cc_apps() {
    local test_dir=$(mktemp -d)
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"

    # Test app directories
    test_app_directories() {
        # Test base app directory
        if [ ! -d "${test_dir}/opt/cc/apps" ]; then
            error "CC apps directory not found"
        fi
        
        # Test permissions
        if [ "$(stat -c %a ${test_dir}/opt/cc/apps)" != "755" ]; then
            error "CC apps directory has wrong permissions"
        fi
        
        if [ "$(stat -c %U:%G ${test_dir}/opt/cc/apps)" != "root:root" ]; then
            error "CC apps directory has wrong ownership"
        fi
    }

    # Test installed apps
    test_installed_apps() {
        # Test each CC app installation
        for app in "${CC_APPS[@]}"; do
            if ! verify_app_installation "$test_dir" "$app"; then
                error "App '$app' not properly installed"
            fi
        done
    }

    # Test app signatures
    test_app_signatures() {
        for app in "${CC_APPS[@]}"; do
            if ! verify_app_signature "$app"; then
                error "App signature verification failed: $app"
            fi
        done
    }

    # Test app configurations
    test_app_configs() {
        # Test app config directory
        if [ ! -d "${test_dir}/etc/cc/apps" ]; then
            error "App config directory not found"
        fi
        
        # Test each app's config
        for app in "${CC_APPS[@]}"; do
            if [ ! -f "${test_dir}/etc/cc/apps/${app}.conf" ]; then
                error "Config for app '$app' not found"
            fi
        done
    }

    # Test app permissions
    test_app_permissions() {
        for app in "${CC_APPS[@]}"; do
            local app_dir="${test_dir}/opt/cc/apps/${app}"
            
            # Check directory permissions
            if [ ! -d "$app_dir" ]; then
                error "App directory for '$app' not found"
            fi
            
            if [ "$(stat -c %a $app_dir)" != "755" ]; then
                error "App directory '$app' has wrong permissions"
            fi
            
            # Check binary permissions
            if [ -f "${app_dir}/bin/${app}" ]; then
                if [ "$(stat -c %a ${app_dir}/bin/${app})" != "755" ]; then
                    error "App binary '$app' has wrong permissions"
                fi
            fi
        done
    }

    # Test app dependencies
    test_app_dependencies() {
        for app in "${CC_APPS[@]}"; do
            # Check if all dependencies are installed
            if ! chroot "$test_dir" /bin/bash -c "ldd /opt/cc/apps/${app}/bin/${app} > /dev/null 2>&1"; then
                error "App '$app' has missing dependencies"
            fi
        done
    }

    # Run all tests
    test_app_directories
    test_installed_apps
    test_app_signatures
    test_app_configs
    test_app_permissions
    test_app_dependencies

    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_cc_apps 