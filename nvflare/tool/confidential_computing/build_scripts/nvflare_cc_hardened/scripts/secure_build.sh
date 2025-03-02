#!/bin/bash

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Required packages with minimum versions
REQUIRED_PACKAGES=(
    "cryptsetup:2.2"
    "lvm2:2.03"
    "parted:3.3"
    "iptables:1.8"
    "systemd:245"
    "dmsetup:1.02"
    # Additional security packages
    "apparmor:3.0"
    "selinux-utils:3.1"
    "auditd:3.0"
    "fail2ban:0.11"
    "rkhunter:1.4"
    # Monitoring packages
    "sysstat:12.0"
    "prometheus-node-exporter:1.0"
    # Backup tools
    "rsync:3.1"
    "duplicity:0.8"
)

# System requirements
MIN_MEMORY_GB=4
MIN_DISK_GB=20
REQUIRED_CPU_FLAGS=("aes" "sse4_1" "avx" "avx2")
MIN_KERNEL_VERSION="5.4"

# Backup configuration
BACKUP_ROOT="/var/backups/nvflare"
BACKUP_RETENTION_DAYS=30

# Helper Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
    exit 1
}

# Version comparison function
version_compare() {
    local v1="$1"
    local v2="$2"
    
    if [[ "$v1" == "$v2" ]]; then
        return 0
    fi
    
    local IFS=.
    local i ver1=($v1) ver2=($v2)
    
    # Fill empty positions with zeros
    for ((i=${#ver1[@]}; i<${#ver2[@]}; i++)); do
        ver1[i]=0
    done
    for ((i=${#ver2[@]}; i<${#ver1[@]}; i++)); do
        ver2[i]=0
    done
    
    # Compare version numbers
    for ((i=0; i<${#ver1[@]}; i++)); do
        if [[ -z ${ver2[i]} ]]; then
            ver2[i]=0
        fi
        if ((10#${ver1[i]} > 10#${ver2[i]})); then
            return 1
        fi
        if ((10#${ver1[i]} < 10#${ver2[i]})); then
            return 2
        fi
    done
    return 0
}

# Check package version
check_package_version() {
    local pkg="$1"
    local min_version="$2"
    local current_version
    
    # Get installed version
    current_version=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null | sed 's/[^0-9.]*\([0-9.]*\).*/\1/')
    if [ -z "$current_version" ]; then
        return 1
    fi
    
    # Compare versions
    version_compare "$current_version" "$min_version"
    local result=$?
    
    if [ "$result" -eq 2 ]; then
        return 1
    fi
    return 0
}

# Check dependencies
check_dependencies() {
    log "Checking dependencies..."
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
    fi
    
    # Map package names to commands
    declare -A CMD_MAP=(
        ["lvm2"]="lvm"
        ["cryptsetup"]="cryptsetup"
        ["parted"]="parted"
        ["systemd"]="systemctl"
        ["iptables"]="iptables"
        ["dmsetup"]="dmsetup"
    )
    
    # Check required packages and versions
    for pkg_spec in "${REQUIRED_PACKAGES[@]}"; do
        IFS=':' read -r pkg min_version <<< "$pkg_spec"
        
        # Check if package is installed
        if ! dpkg -l | grep -q "^ii.*$pkg"; then
            error "Required package not installed: $pkg"
        fi
        
        # Check version
        if ! check_package_version "$pkg" "$min_version"; then
            error "Package $pkg version $(dpkg-query -W -f='${Version}' "$pkg") is lower than required $min_version"
        fi
        
        # Check command availability if it's in our map
        if [[ -n "${CMD_MAP[$pkg]}" ]]; then
            if ! command -v "${CMD_MAP[$pkg]}" >/dev/null 2>&1; then
                error "Required command not found: ${CMD_MAP[$pkg]} (from package $pkg)"
            fi
        fi
    done
    
    # Check kernel modules
    local required_modules=(
        "dm_crypt"
        "dm_verity"
    )
    
    for module in "${required_modules[@]}"; do
        if ! lsmod | grep -q "^${module}"; then
            if ! modprobe "$module" 2>/dev/null; then
                error "Required kernel module not available: $module"
            fi
        fi
    done
    
    log "All dependencies satisfied"
}

# Check system compatibility
check_system_compatibility() {
    log "Checking system compatibility..."

    # Check CPU features
    local cpu_flags=$(grep -m1 '^flags' /proc/cpuinfo | cut -d: -f2)
    for flag in "${REQUIRED_CPU_FLAGS[@]}"; do
        if ! echo "$cpu_flags" | grep -q "$flag"; then
            error "Required CPU feature missing: $flag"
        fi
    done

    # Check memory
    local total_mem_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local total_mem_gb=$((total_mem_kb / 1024 / 1024))
    if [ "$total_mem_gb" -lt "$MIN_MEMORY_GB" ]; then
        error "Insufficient memory: ${total_mem_gb}GB (minimum ${MIN_MEMORY_GB}GB required)"
    fi

    # Check disk space
    local root_disk_gb=$(df -BG / | awk 'NR==2 {print $4}' | tr -d 'G')
    if [ "$root_disk_gb" -lt "$MIN_DISK_GB" ]; then
        error "Insufficient disk space: ${root_disk_gb}GB (minimum ${MIN_DISK_GB}GB required)"
    fi

    # Check kernel version
    local kernel_version=$(uname -r | cut -d'-' -f1)
    if ! version_compare "$kernel_version" "$MIN_KERNEL_VERSION"; then
        error "Kernel version $kernel_version is lower than required $MIN_KERNEL_VERSION"
    fi

    # Check virtualization support
    if ! grep -q -E '^flags.*\b(vmx|svm)\b' /proc/cpuinfo; then
        log "WARNING: No hardware virtualization support detected"
    fi

    log "System compatibility checks passed"
}

# Backup system configuration
backup_configuration() {
    log "Backing up system configuration..."

    local backup_dir="${BACKUP_ROOT}/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"

    # Backup configuration files
    local configs=(
        "/etc/nvflare"
        "/etc/iptables"
        "/etc/systemd/system/nvflare-*"
        "/etc/apparmor.d/local"
        "/etc/audit/rules.d"
    )

    for config in "${configs[@]}"; do
        if [ -e "$config" ]; then
            cp -r "$config" "$backup_dir/"
        fi
    done

    # Backup iptables rules
    iptables-save > "$backup_dir/iptables.rules"

    # Create backup manifest
    {
        echo "Backup created: $(date -Iseconds)"
        echo "Hostname: $(hostname)"
        echo "Kernel: $(uname -r)"
        echo "Packages:"
        dpkg -l | grep -E "$(echo "${REQUIRED_PACKAGES[@]%%:*}" | tr ' ' '|')"
    } > "$backup_dir/manifest.txt"

    # Compress backup
    tar czf "$backup_dir.tar.gz" -C "$backup_dir" .
    rm -rf "$backup_dir"

    # Cleanup old backups
    find "$BACKUP_ROOT" -name "*.tar.gz" -mtime +"$BACKUP_RETENTION_DAYS" -delete

    log "Backup created: $backup_dir.tar.gz"
}

# Restore system configuration
restore_configuration() {
    local backup_file="$1"
    if [ ! -f "$backup_file" ]; then
        error "Backup file not found: $backup_file"
    }

    log "Restoring system configuration from $backup_file..."

    local restore_dir="/tmp/nvflare_restore_$$"
    mkdir -p "$restore_dir"

    # Extract backup
    tar xzf "$backup_file" -C "$restore_dir"

    # Verify manifest
    if [ ! -f "$restore_dir/manifest.txt" ]; then
        rm -rf "$restore_dir"
        error "Invalid backup: manifest not found"
    fi

    # Restore configurations
    for dir in "$restore_dir"/*; do
        if [ -d "$dir" ]; then
            cp -r "$dir" "/"
        fi
    done

    # Restore iptables rules
    if [ -f "$restore_dir/iptables.rules" ]; then
        iptables-restore < "$restore_dir/iptables.rules"
    fi

    # Cleanup
    rm -rf "$restore_dir"

    log "Configuration restored successfully"
}

# Load configuration
CONFIG_FILE="/etc/nvflare/security.conf"

# Load required configuration
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Security configuration file $CONFIG_FILE not found"
    exit 1
fi

source "$CONFIG_FILE"

# Check system compatibility
check_system_compatibility

# Check dependencies before proceeding
check_dependencies

# Backup existing configuration
backup_configuration

# Set encryption patterns
export NVFLARE_ENCRYPT_RW_PATHS="$ENCRYPT_RW_PATHS"
export NVFLARE_ENCRYPT_WO_PATHS="$ENCRYPT_WO_PATHS"

# System service configuration
configure_services() {
    echo "Configuring system services..."
    
    # Check required commands before proceeding
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

    # Disable SSH if configured
    if [ "$DISABLE_SSH" = true ]; then
        log "Disabling SSH..."
        # Stop and disable SSH
        systemctl stop ssh sshd
        systemctl disable ssh sshd
        # Remove SSH completely
        apt-get remove -y openssh-server openssh-client
        rm -rf /etc/ssh
        # Block SSH port in firewall
        iptables -A INPUT -p tcp --dport 22 -j DROP
        iptables -A OUTPUT -p tcp --dport 22 -j DROP
    fi
}

setup_network_security() {
    # 1. Port Management
    configure_ports() {
        # Configure FL and monitoring ports from config
        IFS=',' read -ra FL_PORT_LIST <<< "$FL_PORTS"
        for port in "${FL_PORT_LIST[@]}"; do
            iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
        done
        
        # Block SSH ports explicitly
        iptables -A INPUT -p tcp --dport 22 -j DROP   # SSH
        iptables -A INPUT -p tcp --dport 2222 -j DROP # Alternative SSH
        
        # Configure monitoring ports if monitoring network is set
        if [ ! -z "$MONITOR_NETWORK" ]; then
            IFS=',' read -ra MONITOR_PORT_LIST <<< "$MONITOR_PORTS"
            for port_spec in "${MONITOR_PORT_LIST[@]}"; do
                port="${port_spec%:*}"
                proto="${port_spec#*:}"
                iptables -A INPUT -p "$proto" -s "$MONITOR_NETWORK" --dport "$port" -j ACCEPT
            done
        fi
        
        # Configure attestation service ports
        if [ ! -z "$ATTESTATION_NETWORKS" ]; then
            IFS=',' read -ra ATTESTATION_PORT_LIST <<< "$ATTESTATION_PORTS"
            for port_spec in "${ATTESTATION_PORT_LIST[@]}"; do
                # Parse port:protocol:vendor format
                port="${port_spec%%:*}"
                proto="${port_spec#*:}"; proto="${proto%%:*}"
                vendor="${port_spec##*:}"
                
                # Apply rules for each attestation network
                IFS=',' read -ra ATT_NETWORKS <<< "$ATTESTATION_NETWORKS"
                for network in "${ATT_NETWORKS[@]}"; do
                    iptables -A INPUT -p "$proto" -s "$network" --dport "$port" \
                            -m comment --comment "Attestation-${vendor}" -j ACCEPT
                done
            done
        fi
        
        # Block all other incoming
        iptables -P INPUT DROP
    }

    # 2. Network Isolation
    setup_network_isolation() {
        # Allow monitoring from specific networks only
        iptables -A INPUT -p tcp -s "$MONITOR_NETWORK" --dport 9090 -j ACCEPT
        iptables -A INPUT -p tcp -s "$MONITOR_NETWORK" --dport 9102 -j ACCEPT
        
        # Allow loopback
        iptables -A INPUT -i lo -j ACCEPT
    }

    # 3. Traffic Control
    setup_traffic_control() {
        # Allow established connections only for FL ports
        for port in "${PORTS[@]}"; do
            iptables -A INPUT -p tcp --dport "$port" -m state --state ESTABLISHED,RELATED -j ACCEPT
        done
    }

    # Configure path permissions
    configure_paths() {
        # Set up system paths
        IFS=',' read -ra SYS_PATHS <<< "$SYSTEM_PATHS"
        for path in "${SYS_PATHS[@]}"; do
            chmod 644 "$path"
            register_system_path "$path"
        done

        # Set up tmpfs paths
        IFS=',' read -ra TMP_PATHS <<< "$TMPFS_PATHS"
        for path in "${TMP_PATHS[@]}"; do
            mkdir -p "$path"
            chmod 700 "$path"
            register_tmpfs_path "$path"
        done
    }
}

# Configure FL-specific rate limiting
setup_fl_rate_limits() {
    for rule in "${RATE_LIMIT_RULES[@]}"; do
        IFS=':' read -r port limit desc <<< "$rule"
        iptables -A INPUT -p tcp --dport "$port" -m limit --limit "$limit" -j ACCEPT
        iptables -A INPUT -p tcp --dport "$port" -j DROP
    done
}

# Configure FL-specific audit rules
setup_fl_audit() {
    for rule in "${AUDIT_RULES[@]}"; do
        auditctl "$rule"
    done
}

# Set FL process limits
setup_fl_process_limits() {
    for limit in "${PROCESS_LIMITS[@]}"; do
        echo "$limit" >> /etc/security/limits.d/nvflare.conf
    done
}

# Validate attestation endpoints
validate_attestation_endpoints() {
    local failed=0
    
    # Validate each endpoint
    for service in "${ATTESTATION_SERVICES[@]}"; do
        IFS=':' read -r svc port protocol endpoint desc <<< "$service"
        
        # Try to resolve endpoint
        if ! host "$endpoint" >/dev/null 2>&1; then
            error "Failed to resolve attestation endpoint: $endpoint ($desc)"
            failed=1
            continue
        fi
        
        # Get IP addresses for endpoint
        ip_addresses=$(host "$endpoint" | grep "has address" | cut -d " " -f 4)
        
        if [ -z "$ip_addresses" ]; then
            error "No IP addresses found for endpoint: $endpoint ($desc)"
            failed=1
            continue
        fi
        
        # Add resolved IPs to allowed list
        for ip in $ip_addresses; do
            echo "$svc:$port:$protocol:$ip" >> "/etc/nvflare/attestation_ips"
        done
    done
    
    return $failed
}

# Validate monitoring configuration
validate_monitoring_config() {
    local failed=0
    local ml_metrics_count=0
    local system_metrics_count=0
    local enabled_monitoring=""
    
    # Check enabled ports in MONITORING_PORTS
    for port_config in "${MONITORING_PORTS[@]}"; do
        # Skip commented lines
        [[ "$port_config" =~ ^[[:space:]]*# ]] && continue
        
        IFS=':' read -r name port protocol direction desc <<< "$port_config"
        
        # Validate protocol and direction
        if [ "$protocol" != "tcp" ] || [ "$direction" != "outbound" ]; then
            error "Invalid monitoring configuration for $name: must be tcp/outbound"
            failed=1
            continue
        }
        
        case "$name" in
            "statsd")
                system_metrics_count=$((system_metrics_count + 1))
                enabled_monitoring="$enabled_monitoring\nSystem monitoring: StatsD exporter (port $port)"
                ;;
            "tensorboard"|"mlflow"|"wandb")
                ml_metrics_count=$((ml_metrics_count + 1))
                enabled_monitoring="$enabled_monitoring\nML metrics: $name (port $port)"
                ;;
            *)
                error "Unknown monitoring service: $name"
                failed=1
                ;;
        esac
    done
    
    # Validate only one ML metrics service is enabled
    if [ $ml_metrics_count -gt 1 ]; then
        error "Multiple ML metrics services enabled. Please enable only one."
        failed=1
    fi
    
    # Validate system metrics
    if [ $system_metrics_count -gt 1 ]; then
        error "Multiple system metrics services enabled."
        failed=1
    fi
    
    # Log enabled monitoring
    if [ -n "$enabled_monitoring" ]; then
        log "Enabled monitoring services:$enabled_monitoring"
    fi
    
    return $failed
}

setup_fl_network() {
    # Validate monitoring configuration first
    if ! validate_monitoring_config; then
        error "Monitoring configuration validation failed"
        exit 1
    fi
    
    # Validate endpoints - fail if any attestation endpoint is unreachable
    if ! validate_attestation_endpoints; then
        error "Attestation endpoint validation failed - cannot establish secure environment"
        exit 1
    fi
    
    # Default deny all traffic
    iptables -P INPUT DROP
    iptables -P OUTPUT DROP
    iptables -P FORWARD DROP
    
    # Allow established connections and loopback
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A INPUT -i lo -j ACCEPT
    iptables -A OUTPUT -o lo -j ACCEPT

    # Configure FL ports
    for port_config in "${ALLOWED_PORTS[@]}"; do
        # Skip commented lines
        [[ "$port_config" =~ ^[[:space:]]*# ]] && continue
        
        IFS=':' read -r port protocol direction desc <<< "$port_config"
        case "$direction" in
            "bidirectional")
                iptables -A INPUT -p "$protocol" --dport "$port" -m state --state NEW -j ACCEPT
                iptables -A OUTPUT -p "$protocol" --dport "$port" -m state --state NEW -j ACCEPT
                ;;
            "inbound")
                iptables -A INPUT -p "$protocol" --dport "$port" -m state --state NEW -j ACCEPT
                ;;
            "outbound")
                iptables -A OUTPUT -p "$protocol" --dport "$port" -m state --state NEW -j ACCEPT
                ;;
        esac
    done
    
    # Configure monitoring ports
    for port_config in "${MONITORING_PORTS[@]}"; do
        # Skip commented lines
        [[ "$port_config" =~ ^[[:space:]]*# ]] && continue
        
        IFS=':' read -r name port protocol direction desc <<< "$port_config"
        # All monitoring ports are outbound only
        iptables -A OUTPUT -p "$protocol" --dport "$port" -m state --state NEW -j ACCEPT
    done

    # Configure attestation traffic using resolved IPs
    while IFS=':' read -r svc port protocol ip <<< "$(cat /etc/nvflare/attestation_ips)"; do
        # Allow only outbound attestation traffic to specific IPs
        iptables -A OUTPUT -p "$protocol" -d "$ip" --dport "$port" -m state --state NEW -j ACCEPT
        iptables -A OUTPUT -p "$protocol" -d "$ip" --dport "$port" -m conntrack --ctstate NEW -m limit --limit 10/min -j ACCEPT
        iptables -A OUTPUT -p "$protocol" -d "$ip" --dport "$port" -j LOG --log-prefix "BLOCKED-ATTESTATION: "
    done

    # Log all dropped traffic
    iptables -A INPUT -j LOG --log-prefix "DROP-INPUT: "
    iptables -A OUTPUT -j LOG --log-prefix "DROP-OUTPUT: "
    
    # Apply network hardening parameters
    for param in "${NETWORK_HARDENING[@]}"; do
        sysctl -w "$param"
    done
}

# Helper to get attestation network from config
get_attestation_network() {
    local service="$1"
    for network in "${ATTESTATION_NETWORKS[@]}"; do
        IFS=':' read -r svc net <<< "$network"
        if [ "$svc" = "$service" ]; then
            echo "$net"
            return 0
        fi
    done
    return 1
}

# Periodic endpoint validation (runs every hour by default)
setup_endpoint_validation() {
    local validation_script="/usr/local/bin/validate_attestation_endpoints.sh"
    
    cat > "$validation_script" << 'EOF'
#!/bin/bash

ATTESTATION_IPS_FILE="/etc/nvflare/attestation_ips"
ATTESTATION_IPS_NEW="${ATTESTATION_IPS_FILE}.new"
ATTESTATION_IPS_OLD="${ATTESTATION_IPS_FILE}.old"

# Source configuration
source /etc/nvflare/hardening.conf

validate_endpoints() {
    local failed=0
    > "$ATTESTATION_IPS_NEW"

    for service in "${ATTESTATION_SERVICES[@]}"; do
        IFS=':' read -r svc port protocol endpoint desc <<< "$service"
        
        # Try to resolve endpoint
        if ! host "$endpoint" >/dev/null 2>&1; then
            logger -t attestation-validation "Failed to resolve endpoint: $endpoint ($desc)"
            failed=1
            continue
        fi
        
        # Get current IPs
        ip_addresses=$(host "$endpoint" | grep "has address" | cut -d " " -f 4)
        
        if [ -z "$ip_addresses" ]; then
            logger -t attestation-validation "No IP addresses found for endpoint: $endpoint ($desc)"
            failed=1
            continue
        fi
        
        # Add resolved IPs to new list
        for ip in $ip_addresses; do
            echo "$svc:$port:$protocol:$ip" >> "$ATTESTATION_IPS_NEW"
        done
    done

    if [ $failed -eq 0 ]; then
        if ! diff -q "$ATTESTATION_IPS_FILE" "$ATTESTATION_IPS_NEW" >/dev/null 2>&1; then
            cp "$ATTESTATION_IPS_FILE" "$ATTESTATION_IPS_OLD"
            mv "$ATTESTATION_IPS_NEW" "$ATTESTATION_IPS_FILE"
            /usr/local/bin/update_attestation_rules.sh
            logger -t attestation-validation "Updated attestation endpoints"
        fi
    else
        rm -f "$ATTESTATION_IPS_NEW"
    fi
}

validate_endpoints
EOF

    chmod +x "$validation_script"
    echo "0 * * * * root $validation_script" > "/etc/cron.d/attestation-validation"
    chmod 644 "/etc/cron.d/attestation-validation"
}

main() {
    setup_fl_network
    setup_fl_rate_limits
    setup_fl_audit
    setup_fl_process_limits
    setup_endpoint_validation
    log "FL-specific security hardening completed"
}

main "$@" 