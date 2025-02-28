#!/bin/bash

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Helper Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
    exit 1
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARDENING_DIR="$(dirname "$SCRIPT_DIR")"

# Script paths
VALIDATE_SCRIPT="${HARDENING_DIR}/validate_security.sh"
SECURE_BUILD_SCRIPT="${HARDENING_DIR}/secure_build.sh"

# Test configuration
TEST_PORTS=(18002 18003)
TEST_PORT_RANGE=(19000 19010)
TEST_INTERFACES=("lo" "eth0" "ens*")
TEST_LOAD_DURATION=10  # seconds

# Test metrics
declare -A TEST_METRICS=(
    ["test_start_time"]=""
    ["test_end_time"]=""
    ["total_tests"]=0
    ["passed_tests"]=0
    ["failed_tests"]=0
    ["skipped_tests"]=0
    ["performance_retransmits"]=0
    ["performance_max_conn"]=0
    ["rate_limit_max_req"]=0
)

# Test reporting
REPORT_FILE="/tmp/nvflare_test/security_test_report.json"
METRICS_FILE="/tmp/nvflare_test/security_test_metrics.json"

# Map packages to commands
declare -A PKG_COMMANDS=(
    ["lvm2"]="lvm"
    ["cryptsetup"]="cryptsetup"
    ["parted"]="parted"
    ["systemd"]="systemctl"
    ["iptables"]="iptables"
    ["dmsetup"]="dmsetup"
)

# Initialize test metrics
init_metrics() {
    TEST_METRICS["test_start_time"]=$(date +%s)
    mkdir -p "$(dirname "$REPORT_FILE")"
    mkdir -p "$(dirname "$METRICS_FILE")"
}

# Update test metrics
update_metrics() {
    local test_name="$1"
    local status="$2"  # pass/fail/skip
    
    ((TEST_METRICS["total_tests"]++))
    case "$status" in
        pass) ((TEST_METRICS["passed_tests"]++)) ;;
        fail) ((TEST_METRICS["failed_tests"]++)) ;;
        skip) ((TEST_METRICS["skipped_tests"]++)) ;;
    esac
    
    # Record test result
    echo "{\"test\":\"$test_name\",\"status\":\"$status\",\"timestamp\":\"$(date -Iseconds)\"}" >> "$REPORT_FILE"
}

# Generate final report
generate_report() {
    TEST_METRICS["test_end_time"]=$(date +%s)
    local duration=$((TEST_METRICS["test_end_time"] - TEST_METRICS["test_start_time"]))
    
    # Generate metrics JSON
    cat > "$METRICS_FILE" <<EOF
{
    "summary": {
        "total_tests": ${TEST_METRICS["total_tests"]},
        "passed_tests": ${TEST_METRICS["passed_tests"]},
        "failed_tests": ${TEST_METRICS["failed_tests"]},
        "skipped_tests": ${TEST_METRICS["skipped_tests"]},
        "duration_seconds": $duration
    },
    "performance": {
        "retransmits": ${TEST_METRICS["performance_retransmits"]},
        "max_connections": ${TEST_METRICS["performance_max_conn"]},
        "max_requests_per_minute": ${TEST_METRICS["rate_limit_max_req"]}
    }
}
EOF

    # Print summary
    log "Test Summary:"
    log "  Total Tests: ${TEST_METRICS["total_tests"]}"
    log "  Passed: ${TEST_METRICS["passed_tests"]}"
    log "  Failed: ${TEST_METRICS["failed_tests"]}"
    log "  Skipped: ${TEST_METRICS["skipped_tests"]}"
    log "  Duration: ${duration}s"
    log "  Report: $REPORT_FILE"
    log "  Metrics: $METRICS_FILE"
}

# Create test environment
setup_test_env() {
    log "Setting up test environment..."
    
    # Create test config directory
    TEST_CONFIG_DIR="/tmp/nvflare_security_test"
    mkdir -p "$TEST_CONFIG_DIR"
    
    # Create test security config
    cat > "$TEST_CONFIG_DIR/security.conf" <<EOF
# Test configuration
ALLOWED_PORTS=(
    "test_fl:18002:tcp:Test FL port"
    "test_admin:18003:tcp:Test admin port"
)

ALLOWED_PORT_RANGES=(
    "test_range:19000:19010:tcp:Test port range"
)

# System configuration
DISABLE_SSH=true
DEFAULT_PORT_POLICY="deny"

# Network configuration
ALLOWED_INTERFACES=(
    "lo"      # Loopback
    "eth0"    # Primary network
    "ens*"    # Cloud provider interfaces
)

# Rate limiting
RATE_LIMIT="100/minute"
MAX_CONNECTIONS_FL=20

# Test paths
SYSTEM_PATHS="/tmp/nvflare_test/etc,/tmp/nvflare_test/ssl"
TMPFS_PATHS="/tmp/nvflare_test/tmp,/tmp/nvflare_test/shm"
ENCRYPT_RW_PATHS="/tmp/nvflare_test/workspace/*.pt"
EOF

    # Check required commands
    local required_cmds=(
        "cryptsetup"
        "lvm"
        "parted"
        "systemctl"
        "iptables"
        "dmsetup"
    )
    
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "Required command not found: $cmd"
        fi
    done
}

# Test security configuration validation
test_config_validation() {
    log "Testing configuration validation..."
    
    # Save original config
    cp "$TEST_CONFIG_DIR/security.conf" "$TEST_CONFIG_DIR/security.conf.bak"
    
    # Test valid configuration
    SECURITY_CONF="$TEST_CONFIG_DIR/security.conf" "$VALIDATE_SCRIPT" || error "Valid config failed validation"
    
    # Test invalid configurations
    local INVALID_CONFIGS=(
        'ALLOWED_PORTS=("invalid:port:tcp:Bad port")'
        'ALLOWED_PORT_RANGES=("bad:range:-1:100:tcp:Negative port")'
        'DEFAULT_PORT_POLICY="invalid"'
        'SYSTEM_PATHS=""'
    )
    
    for invalid in "${INVALID_CONFIGS[@]}"; do
        log "Testing invalid config: $invalid"
        # Restore original config
        cp "$TEST_CONFIG_DIR/security.conf.bak" "$TEST_CONFIG_DIR/security.conf"
        # Add invalid config
        echo "$invalid" >> "$TEST_CONFIG_DIR/security.conf"
        if SECURITY_CONF="$TEST_CONFIG_DIR/security.conf" "$VALIDATE_SCRIPT" 2>/dev/null; then
            error "Configuration validation should fail for: $invalid"
        fi
    done
    
    # Restore original config
    cp "$TEST_CONFIG_DIR/security.conf.bak" "$TEST_CONFIG_DIR/security.conf"
    rm -f "$TEST_CONFIG_DIR/security.conf.bak"
}

# Test firewall configuration
test_firewall_rules() {
    log "Testing firewall rules..."
    
    # Apply security configuration
    SECURITY_CONF="$TEST_CONFIG_DIR/security.conf" "$SECURE_BUILD_SCRIPT"
    
    # Test allowed ports
    nc -zv localhost 18002 2>/dev/null && log "✓ Port 18002 open" || error "Port 18002 should be open"
    nc -zv localhost 18003 2>/dev/null && log "✓ Port 18003 open" || error "Port 18003 should be open"
    
    # Test port range
    for port in $(seq 19000 19010); do
        nc -zv localhost $port 2>/dev/null && log "✓ Port $port open" || error "Port $port should be open"
    done
    
    # Test blocked ports
    nc -zv localhost 22 2>/dev/null && error "SSH port should be blocked" || log "✓ SSH blocked"
    nc -zv localhost 23 2>/dev/null && error "Telnet port should be blocked" || log "✓ Telnet blocked"
}

# Test SSH hardening
test_ssh_hardening() {
    log "Testing SSH hardening..."
    
    # Apply security configuration
    SECURITY_CONF="$TEST_CONFIG_DIR/security.conf" "$SECURE_BUILD_SCRIPT"
    
    # Check SSH service status
    systemctl is-active ssh &>/dev/null && error "SSH service should be disabled" || log "✓ SSH service disabled"
    systemctl is-active sshd &>/dev/null && error "SSHD service should be disabled" || log "✓ SSHD service disabled"
    
    # Check SSH files
    [ -d "/etc/ssh" ] && error "SSH directory should be removed" || log "✓ SSH directory removed"
    [ -f "/etc/ssh/sshd_config" ] && error "SSH config should be removed" || log "✓ SSH config removed"
}

# Test path permissions
test_path_permissions() {
    log "Testing path permissions..."
    
    # Create test paths
    mkdir -p /tmp/nvflare_test/{etc,ssl,tmp,shm,workspace}
    touch /tmp/nvflare_test/workspace/model.pt
    
    # Apply security configuration
    SECURITY_CONF="$TEST_CONFIG_DIR/security.conf" "$SECURE_BUILD_SCRIPT"
    
    # Check permissions
    [ "$(stat -c %a /tmp/nvflare_test/etc)" = "644" ] || error "System path permissions incorrect"
    [ "$(stat -c %a /tmp/nvflare_test/tmp)" = "700" ] || error "Tmpfs path permissions incorrect"
    
    log "✓ Path permissions correct"
}

# Test network isolation
test_network_isolation() {
    log "Testing network isolation..."
    
    # Test interface restrictions
    for iface in "${TEST_INTERFACES[@]}"; do
        if ! ip link show | grep -q "$iface"; then
            continue  # Skip if interface doesn't exist
        fi
        
        # Test outbound connectivity
        if ! ping -I "$iface" -c 1 127.0.0.1 &>/dev/null; then
            error "Interface $iface should allow loopback traffic"
        fi
        
        # Test interface firewall rules
        if ! iptables -L INPUT -v -n | grep -q "$iface"; then
            error "Missing firewall rules for interface $iface"
        fi
    done
    
    # Test network segmentation
    for port in "${TEST_PORTS[@]}"; do
        # Test localhost access
        nc -zv localhost "$port" &>/dev/null || error "Port $port not accessible on localhost"
        
        # Test external access (should fail)
        if nc -zv 0.0.0.0 "$port" &>/dev/null; then
            error "Port $port should not be externally accessible"
        fi
    done
    
    log "✓ Network isolation tests passed"
}

# Test rate limiting
test_rate_limiting() {
    log "Testing rate limiting..."
    
    local port=18002
    local requests=0
    local start_time=$(date +%s)
    
    # Send requests rapidly
    while [ $(($(date +%s) - start_time)) -lt 5 ]; do
        if nc -zv localhost "$port" 2>/dev/null; then
            ((requests++))
        fi
    done
    
    # Check if rate limiting worked
    if [ "$requests" -gt 100 ]; then
        error "Rate limiting failed: $requests requests in 5 seconds"
    fi
    
    log "✓ Rate limiting tests passed"
}

# Test performance under load
test_performance() {
    log "Testing performance under load..."
    
    # Start monitoring
    local monitor_file="/tmp/nvflare_test/monitor.log"
    (
        while true; do
            date +%s
            netstat -s | grep "segments retransmitted"
            grep -E '^[0-9]' /proc/net/tcp | wc -l
            sleep 1
        done
    ) > "$monitor_file" &
    local monitor_pid=$!
    
    # Generate load
    for port in "${TEST_PORTS[@]}"; do
        for i in $(seq 1 10); do
            (
                while true; do
                    nc -zv localhost "$port" &>/dev/null
                    sleep 0.1
                done
            ) &
        done
    done
    
    # Wait for test duration
    sleep "$TEST_LOAD_DURATION"
    
    # Stop monitoring and background processes
    kill "$monitor_pid"
    pkill -P $$
    
    # Analyze results
    local retrans=$(grep "retransmitted" "$monitor_file" | tail -n1 | awk '{print $1}')
    local max_conn=$(grep "^[0-9]" "$monitor_file" | sort -n | tail -n1)
    
    if [ "$retrans" -gt 100 ] || [ "$max_conn" -gt "$MAX_CONNECTIONS_FL" ]; then
        error "Performance test failed: retransmits=$retrans, max_conn=$max_conn"
    fi
    
    log "✓ Performance tests passed"
}

# Test specific security features
test_security_features() {
    log "Testing specific security features..."
    
    # Check process namespaces
    log "Testing process isolation..."
    if ! unshare --fork --pid --mount-proc true; then
        error "Process namespace isolation not working"
    fi
    update_metrics "process_isolation" "pass"
    
    # Check memory protections
    log "Testing memory protection..."
    if ! sysctl -n kernel.randomize_va_space | grep -q "2"; then
        error "ASLR not properly configured"
    fi
    if ! grep -q "noexec" /proc/mounts; then
        error "noexec mount option not set"
    fi
    update_metrics "memory_protection" "pass"
    
    # Check filesystem restrictions
    log "Testing filesystem restrictions..."
    local test_file="/tmp/nvflare_test/test_write"
    if touch "$test_file" 2>/dev/null; then
        if [ -w "$test_file" ]; then
            error "Write permission not properly restricted"
        fi
    fi
    update_metrics "fs_restrictions" "pass"
    
    log "✓ Security features tests passed"
}

# Test system hardening
test_system_hardening() {
    log "Testing system hardening..."
    
    # Check kernel parameters
    local kernel_params=(
        "kernel.randomize_va_space=2"
        "kernel.kptr_restrict=2"
        "kernel.dmesg_restrict=1"
        "kernel.perf_event_paranoid=3"
        "kernel.unprivileged_bpf_disabled=1"
    )
    
    for param in "${kernel_params[@]}"; do
        local key="${param%=*}"
        local expected="${param#*=}"
        local actual=$(sysctl -n "$key")
        if [ "$actual" != "$expected" ]; then
            error "Kernel parameter $key=$actual (expected $expected)"
        fi
    done
    
    update_metrics "system_hardening" "pass"
}

# Cleanup test environment
cleanup_test_env() {
    log "Cleaning up test environment..."
    rm -rf "$TEST_CONFIG_DIR"
    rm -rf /tmp/nvflare_test
}

# Main test function
main() {
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        error "Please run as root (sudo)"
    fi
    
    # Check required scripts exist
    for script in "$VALIDATE_SCRIPT" "$SECURE_BUILD_SCRIPT"; do
        if [ ! -f "$script" ]; then
            error "Required script not found: $script"
        fi
        if [ ! -x "$script" ]; then
            chmod +x "$script" || error "Failed to make executable: $script"
        fi
    done
    
    # Initialize metrics
    init_metrics
    
    # Setup and run tests
    trap cleanup_test_env EXIT
    setup_test_env
    
    # Run all tests
    test_config_validation
    test_firewall_rules
    test_ssh_hardening
    test_path_permissions
    test_network_isolation
    test_rate_limiting
    test_performance
    test_security_features
    test_system_hardening
    
    # Generate final report
    generate_report
    
    log "All tests passed successfully!"
}

# Run tests
main "$@" 