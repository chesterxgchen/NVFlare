#!/usr/bin/env python3
"""
Submit exported job and monitor progress using FLARE API.
This avoids "cannot schedule new futures after shutdown" error by properly managing session lifecycle.
"""

import argparse
import os
import sys
import time

from nvflare.fuel.flare_api.api_spec import MonitorReturnCode
from nvflare.fuel.flare_api.flare_api import new_secure_session


def job_monitor_callback(session, job_id, job_meta, *cb_args, **cb_kwargs):
    """Callback to print job progress during monitoring."""
    cb_run_counter = cb_kwargs.get("cb_run_counter", {"count": 0})
    
    # Print header on first call
    if cb_run_counter["count"] == 0:
        print(f"\nJob ID: {job_id}")
        print(f"Initial Status: {job_meta.get('status', 'UNKNOWN')}")
        print("Monitoring progress", end="", flush=True)
    
    # Print progress dots for RUNNING status
    if job_meta.get("status") == "RUNNING":
        print(".", end="", flush=True)
    else:
        # Print final status
        print(f"\n\nFinal Job Status: {job_meta.get('status', 'UNKNOWN')}")
        if "duration" in job_meta:
            print(f"Duration: {job_meta['duration']}")
    
    cb_run_counter["count"] += 1
    cb_kwargs["cb_run_counter"] = cb_run_counter
    return True


def submit_and_monitor_job(job_dir: str, startup_kit: str, timeout: float = 300.0):
    """
    Submit job and monitor until completion or timeout.
    
    Args:
        job_dir: Path to exported job directory
        startup_kit: Path to admin startup kit directory
        timeout: Max time to wait for job completion (seconds), 0 = no timeout
    
    Returns:
        Tuple of (success: bool, job_id: str, final_status: str)
    """
    if not os.path.isdir(job_dir):
        print(f"ERROR: Job directory not found: {job_dir}")
        return False, None, None
    
    if not os.path.isdir(startup_kit):
        print(f"ERROR: Startup kit not found: {startup_kit}")
        return False, None, None
    
    print("=" * 80)
    print("Submitting and Monitoring Job")
    print("=" * 80)
    print(f"Job directory: {job_dir}")
    print(f"Startup kit: {startup_kit}")
    print(f"Timeout: {timeout}s (0 = no timeout)")
    print()
    
    # Create session
    print("Connecting to FLARE...")
    try:
        sess = new_secure_session(
            username="admin@nvidia.com",
            startup_kit_location=startup_kit
        )
    except Exception as e:
        print(f"ERROR: Failed to create session: {e}")
        return False, None, None
    
    job_id = None
    try:
        # Submit job
        print("Submitting job...")
        job_id = sess.submit_job(job_dir)
        print(f"✓ Job submitted with ID: {job_id}")
        
        # Wait a moment for job to start
        time.sleep(2)
        
        # Monitor job progress
        print("\nMonitoring job progress...")
        cb_run_counter = {"count": 0}
        rc, job_meta = sess.monitor_job_and_return_job_meta(
            job_id,
            timeout=timeout,
            poll_interval=2.0,
            cb=job_monitor_callback,
            cb_run_counter=cb_run_counter
        )
        
        print()
        print("=" * 80)
        print("Monitoring Result")
        print("=" * 80)
        print(f"Return Code: {rc}")
        
        if rc == MonitorReturnCode.JOB_FINISHED:
            final_status = job_meta.get("status", "UNKNOWN")
            print(f"✓ Job completed: {final_status}")
            
            # Download results if job finished successfully
            if "EXECUTION_EXCEPTION" in final_status or "ERROR" in final_status:
                print("\n⚠ Job finished with error status")
                return False, job_id, final_status
            else:
                print("\n✓ Job finished successfully")
                result_location = sess.download_job_result(job_id)
                print(f"Results downloaded to: {result_location}")
                return True, job_id, final_status
                
        elif rc == MonitorReturnCode.TIMEOUT:
            print(f"⚠ Job monitoring timed out after {timeout}s")
            print("Job may still be running. Check status manually.")
            return False, job_id, "TIMEOUT"
        else:
            print(f"⚠ Unexpected monitor return code: {rc}")
            return False, job_id, "UNKNOWN"
            
    except Exception as e:
        print(f"\nERROR during job submission/monitoring: {e}")
        import traceback
        traceback.print_exc()
        return False, job_id, "ERROR"
    finally:
        # Always close session to avoid "cannot schedule new futures" error
        print("\nClosing session...")
        try:
            sess.close()
            print("✓ Session closed")
        except Exception as e:
            print(f"Warning: Error closing session: {e}")


def main():
    parser = argparse.ArgumentParser(description="Submit and monitor NVFlare job")
    parser.add_argument("-j", "--job_dir", required=True, help="Path to exported job directory")
    parser.add_argument(
        "-s", "--startup_kit",
        default="/tmp/nvflare/poc/example_project/prod_00/admin@nvidia.com",
        help="Path to admin workspace directory (contains startup/ folder)"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=300.0,
        help="Timeout in seconds (0 = no timeout)"
    )
    
    args = parser.parse_args()
    
    success, job_id, status = submit_and_monitor_job(
        args.job_dir,
        args.startup_kit,
        args.timeout
    )
    
    # Exit with appropriate code
    if success:
        sys.exit(0)
    else:
        print(f"\nJob failed or timed out. Job ID: {job_id}, Status: {status}")
        sys.exit(1)


if __name__ == "__main__":
    main()
