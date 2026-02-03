#!/usr/bin/env python3
"""
Submit exported job and monitor progress using FLARE API.
This avoids "cannot schedule new futures after shutdown" error by properly managing session lifecycle.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from nvflare.fuel.flare_api.api_spec import MonitorReturnCode
from nvflare.fuel.flare_api.flare_api import new_secure_session


def job_monitor_callback(session, job_id, job_meta, *cb_args, **cb_kwargs):
    """Callback to print job progress during monitoring."""
    cb_run_counter = cb_kwargs.get("cb_run_counter", {"count": 0})
    
    # Print header on first call
    if cb_run_counter["count"] == 0:
        print(f"\nJob ID: {job_id}")
        print(f"Initial Status: {job_meta.get('status', 'UNKNOWN')}")
        print(f"Submitter: {job_meta.get('submitter_name', 'unknown')}")
        print(f"Start Time: {job_meta.get('start_time', 'N/A')}")
        print()
        print("Monitoring progress...")
    
    status = job_meta.get("status", "UNKNOWN")
    
    # Print status updates
    if status == "RUNNING":
        # Show periodic updates instead of just dots
        if cb_run_counter["count"] % 5 == 0:
            duration = job_meta.get("duration", "N/A")
            print(f"  [{cb_run_counter['count'] * 2}s] Status: RUNNING, Duration: {duration}")
    elif status.startswith("FINISHED"):
        # Print detailed final status
        print()
        print("=" * 80)
        print(f"Final Status: {status}")
        print(f"Duration: {job_meta.get('duration', 'N/A')}")
        
        # Show deployment details
        deploy_detail = job_meta.get("job_deploy_detail", [])
        if deploy_detail:
            print(f"Deployment: {', '.join(deploy_detail)}")
        
        # Show schedule history if available
        schedule_history = job_meta.get("schedule_history", [])
        if schedule_history:
            print(f"Schedule History: {', '.join(schedule_history)}")
        
        print("=" * 80)
    else:
        # Other statuses
        print(f"  Status changed to: {status}")
    
    cb_run_counter["count"] += 1
    cb_kwargs["cb_run_counter"] = cb_run_counter
    return True


def find_errors_in_log(log_path: str, context_lines: int = 10) -> list:
    """Find ERROR, Exception, or Traceback lines in log with context."""
    if not os.path.exists(log_path):
        return []
    
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
        
        error_sections = []
        error_keywords = ['ERROR', 'Exception', 'Traceback', 'Error:', 'Failed']
        
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in error_keywords):
                # Get context before and after
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                error_sections.append({
                    'line_num': i + 1,
                    'context': lines[start:end],
                    'start_line': start + 1
                })
        
        return error_sections
    except Exception as e:
        return []


def print_log_errors(log_path: str, context_lines: int = 10):
    """Print errors found in log with context."""
    if not os.path.exists(log_path):
        print(f"  (Log file not found: {log_path})")
        return False
    
    errors = find_errors_in_log(log_path, context_lines)
    
    if not errors:
        # No errors found, show last lines
        print(f"  No ERROR/Exception found, showing last 50 lines from {log_path}:")
        print_last_log_lines(log_path, num_lines=50)
        return False
    
    print(f"  Found {len(errors)} error(s) in {log_path}:")
    for idx, error in enumerate(errors, 1):
        print(f"\n  --- Error {idx} (around line {error['line_num']}) ---")
        print("  " + "-" * 76)
        for line in error['context']:
            print(f"  {line.rstrip()}")
        print("  " + "-" * 76)
    
    return True


def print_last_log_lines(log_path: str, num_lines: int = 30):
    """Print last N lines of a log file."""
    if not os.path.exists(log_path):
        print(f"  (Log file not found: {log_path})")
        return
    
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
            last_lines = lines[-num_lines:]
            print("  " + "-" * 76)
            for line in last_lines:
                print(f"  {line.rstrip()}")
            print("  " + "-" * 76)
    except Exception as e:
        print(f"  (Could not read log: {e})")


def find_latest_run_dir(workspace_dir: str) -> str:
    """Find the latest run_* directory in a workspace."""
    if not os.path.exists(workspace_dir):
        return None
    
    run_dirs = [d for d in os.listdir(workspace_dir) if d.startswith('run_')]
    if not run_dirs:
        return None
    
    # Sort by modification time, newest first
    run_dirs.sort(key=lambda d: os.path.getmtime(os.path.join(workspace_dir, d)), reverse=True)
    return os.path.join(workspace_dir, run_dirs[0])


def submit_and_monitor_job(job_dir: str, startup_kit: str, timeout: float = 300.0, show_logs_on_error: bool = True):
    """
    Submit job and monitor until completion or timeout.
    
    Args:
        job_dir: Path to exported job directory
        startup_kit: Path to admin startup kit directory
        timeout: Max time to wait for job completion (seconds), 0 = no timeout
        show_logs_on_error: If True, print last lines of server/client logs on error
    
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
    print("Submitting and Monitoring Job via FLARE API")
    print("=" * 80)
    print(f"Job directory: {job_dir}")
    print(f"Admin workspace: {startup_kit}")
    print(f"Timeout: {timeout}s (0 = no timeout)")
    print()
    
    # Create session
    print("Connecting to FLARE system via API...")
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
        # Submit job via FLARE API
        print("Submitting job via FLARE API...")
        job_id = sess.submit_job(job_dir)
        print(f"✓ Job submitted with ID: {job_id}")
        
        # Wait a moment for job to start
        time.sleep(2)
        
        # Monitor job progress via FLARE API
        print("\nMonitoring job progress via FLARE API...")
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
        print("FLARE API Monitoring Result")
        print("=" * 80)
        print(f"Return Code: {rc}")
        
        if rc == MonitorReturnCode.JOB_FINISHED:
            final_status = job_meta.get("status", "UNKNOWN")
            
            # Check if job completed successfully
            # FINISHED:COMPLETED = success
            # FINISHED:EXECUTION_EXCEPTION, FINISHED:ABORTED, etc. = failure
            if final_status == "FINISHED:COMPLETED":
                print("\n" + "=" * 80)
                print("✓ JOB COMPLETED SUCCESSFULLY")
                print("=" * 80)
                result_location = sess.download_job_result(job_id)
                print(f"Results downloaded to: {result_location}")
                print("=" * 80)
                return True, job_id, final_status
            else:
                # Job finished but not successfully
                print("\n" + "=" * 80)
                print("⚠ JOB FAILED")
                print("=" * 80)
                print(f"Status: {final_status}")
                print()
                
                # Automatically show recent logs to help with debugging
                if show_logs_on_error:
                    print("Searching for errors in logs...")
                    
                    workspace_parent = os.path.dirname(startup_kit)
                    
                    # Server JOB logs (run_* directory - this is where the actual error is)
                    server_workspace = os.path.join(workspace_parent, "server")
                    server_run_dir = find_latest_run_dir(server_workspace)
                    if server_run_dir:
                        print(f"\n📋 Server JOB logs: {server_run_dir}/log.txt")
                        server_job_log = os.path.join(server_run_dir, "log.txt")
                        found_errors = print_log_errors(server_job_log, context_lines=15)
                        
                        # Also check for stderr/stdout files
                        stderr_file = os.path.join(server_run_dir, "stderr.log")
                        stdout_file = os.path.join(server_run_dir, "stdout.log")
                        if os.path.exists(stderr_file):
                            print(f"\n📋 Server stderr: {stderr_file}")
                            print_log_errors(stderr_file, context_lines=10)
                        if os.path.exists(stdout_file):
                            print(f"\n📋 Server stdout: {stdout_file}")
                            print_log_errors(stdout_file, context_lines=10)
                    else:
                        print("\n📋 Server JOB logs: (run_* directory not found)")
                        server_log = os.path.join(server_workspace, "log.txt")
                        print(f"  Checking startup log: {server_log}")
                        print_log_errors(server_log, context_lines=20)
                    
                    # Site-1 JOB logs
                    site1_workspace = os.path.join(workspace_parent, "site-1")
                    site1_run_dir = find_latest_run_dir(site1_workspace)
                    if site1_run_dir:
                        print(f"\n📋 Site-1 JOB logs: {site1_run_dir}/log.txt")
                        site1_job_log = os.path.join(site1_run_dir, "log.txt")
                        print_log_errors(site1_job_log, context_lines=15)
                    else:
                        print("\n📋 Site-1 JOB logs: (run_* directory not found)")
                
                print("\n" + "=" * 80)
                print("Common issues to check:")
                print("  - Model import errors (check model.py path)")
                print("  - Checkpoint file not found or wrong path")
                print("  - Client connection issues")
                print("  - Training script errors")
                print("=" * 80)
                return False, job_id, final_status
                
        elif rc == MonitorReturnCode.TIMEOUT:
            print(f"⚠ Job monitoring timed out after {timeout}s")
            print("Job may still be running. Check status manually.")
            return False, job_id, "TIMEOUT"
        else:
            print(f"⚠ Unexpected monitor return code: {rc}")
            return False, job_id, "UNKNOWN"
            
    except Exception as e:
        print(f"\nERROR during FLARE API job submission/monitoring: {e}")
        import traceback
        traceback.print_exc()
        return False, job_id, "ERROR"
    finally:
        # Always close FLARE API session to avoid "cannot schedule new futures" error
        print("\nClosing FLARE API session...")
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
    parser.add_argument(
        "--no-logs",
        action="store_true",
        help="Don't automatically show logs on error"
    )
    
    args = parser.parse_args()
    
    success, job_id, status = submit_and_monitor_job(
        args.job_dir,
        args.startup_kit,
        args.timeout,
        show_logs_on_error=not args.no_logs
    )
    
    # Exit with appropriate code
    if success:
        sys.exit(0)
    else:
        print(f"\nJob failed or timed out. Job ID: {job_id}, Status: {status}")
        sys.exit(1)


if __name__ == "__main__":
    main()
