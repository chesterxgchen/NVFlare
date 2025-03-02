# Source dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/key_management.sh"
source "${SCRIPT_DIR}/internal/key_settings.conf"

# Key Service Configuration
KEY_SERVICE_STATE="${TEE_MEMORY_PATH}/keys"
KEY_SERVICE_LOCK="${KEY_SERVICE_STATE}/lock"
KEY_SERVICE_STORE="${KEY_SERVICE_STATE}/store"
KEY_SERVICE_META="${KEY_SERVICE_STATE}/meta"

# Initialize Key Service
init_key_service() {
    # Setup TEE memory structure
    mkdir -p "${KEY_SERVICE_STATE}"
    mkdir -p "${KEY_SERVICE_STORE}"
    mkdir -p "${KEY_SERVICE_META}"
    chmod "${TEE_MEMORY_MODE}" "${KEY_SERVICE_STATE}"
    chown "${TEE_MEMORY_OWNER}:${TEE_MEMORY_GROUP}" "${KEY_SERVICE_STATE}" 