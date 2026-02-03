# Testing Strategy

This directory contains multiple test approaches for the dict model config and checkpoint features. Start simple and add complexity incrementally.

## Test 1: Local POC (Recommended First)

**Purpose**: Verify dict config and checkpoint work in basic POC without Docker complexity.

**Run:**
```bash
# Test with dict config only (no checkpoint)
python test_local_poc.py --use_dict_config

# Test with dict config + checkpoint
python test_local_poc.py --use_dict_config --checkpoint /tmp/test_checkpoint.pt

# Test with model instance + checkpoint (baseline)
python test_local_poc.py --checkpoint /tmp/test_checkpoint.pt
```

**What it tests:**
- ✓ Dict model config: `{"path": "model.SimpleNetwork"}`
- ✓ Checkpoint loading: `initial_ckpt` parameter
- ✓ All processes run locally (no containers)
- ✓ Quick feedback (< 1 minute)

**Expected outcome:**
- Job completes with "FINISHED" status
- No "EXECUTION_EXCEPTION"
- Results directory created

---

## Test 2: Docker POC (After Test 1 passes)

**Purpose**: Test with server in Docker container (production-like setup).

**Run:**
```bash
# Automated test
./test.sh

# Interactive step-by-step
./test_interactive.sh
```

**What it tests:**
- ✓ Everything from Test 1
- ✓ Server runs in Docker with dev code
- ✓ Clients run locally
- ✓ Checkpoint accessible only in server container
- ✓ Volume mounts and networking
- ✓ FLARE API job submission and monitoring

**Expected outcome:**
- Docker container starts successfully
- Job completes with "FINISHED" status
- Automatic log display on error

---

## Troubleshooting

### Test 1 fails
**Problem**: Dict config or checkpoint not working
**Action**: 
1. Check error in console output (runs in foreground)
2. Inspect `/tmp/nvflare/poc/.../server/run_*/log.txt`
3. Fix the core issue before moving to Docker

### Test 2 fails
**Problem**: Could be Docker setup, networking, or volume mounts
**Action**:
1. Verify Test 1 passes first
2. Check Docker logs: `docker logs flserver`
3. Run interactive version: `./test_interactive.sh`
4. Automatic error logs will show in output

---

## Files

- `test_local_poc.py` - Test 1: Simple local POC (start here)
- `test.sh` - Test 2: Automated Docker test
- `test_interactive.sh` - Test 2: Interactive Docker test
- `submit_and_monitor.py` - FLARE API submission helper
- `job.py` - Export job config (for manual testing)
- `client.py` - Client training wrapper
- `model.py` - SimpleNetwork model
- `prepare_data.py` - Generate checkpoint file
