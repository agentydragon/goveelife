#!/usr/bin/env python3
"""Deploy script for Govee Life Home Assistant integration."""

import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple, Dict

# Configuration
SOURCE_DIR = "custom_components/goveelife"
DEST = "root@10.13.13.100"
DEST_DIR = "homeassistant/custom_components/goveelife"

# ANSI color codes
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
NC = "\033[0m"  # No Color


def run_command(cmd: List[str]) -> Tuple[int, str]:
    """Run a command and return exit code and output."""
    print(shlex.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def parse_rsync_changes(output: str) -> Dict[str, List[str]]:
    """Parse rsync dry-run output and categorize changes."""
    changes = {
        "deleted": [],
        "new": [],
        "updated": [],
        "dirs": []
    }
    
    for line in output.strip().split("\n"):
        if not line or line.startswith("sending") or line.startswith("sent") or line.startswith("total size"):
            continue

        # Handle deletion lines
        if line.startswith("*deleting"):
            # Extract filename after "*deleting   "
            filename = line[12:].strip()
            if filename and not filename.endswith("/"):
                changes["deleted"].append(filename)
        # Handle itemize-changes format
        elif len(line) > 12 and line[0] in "<>ch*." and " " in line[10:]:
            # Itemize format: YXcstpoguax path/to/file
            # Y = update type (<,>,c,h,.,*)
            # X = file type (f,d,L,D,S)
            # cstpoguax = attributes
            action = line[0]
            file_type = line[1]
            # Find the first space after position 10 to get the filename
            space_idx = line.index(" ", 10)
            filename = line[space_idx:].strip()
            
            if action == "*" and line.startswith("*deleting"):
                # Already handled above
                continue
            elif file_type == "d":
                # Directory
                if action in "<>":
                    changes["dirs"].append(filename)
            elif file_type == "f":
                # File
                if action == "<":
                    # In dry-run mode, < means file would be sent to remote
                    if "+++++++++" in line[2:11]:
                        changes["new"].append(filename)
                    else:
                        changes["updated"].append(filename)
                elif action == ">":
                    # > means file would come from remote (rare in our deploy scenario)
                    changes["updated"].append(filename)

    return changes


def fetch_remote_file(filepath: str) -> str:
    """Fetch a file from the remote server."""
    cmd = ["ssh", DEST, f"cat {DEST_DIR}/{filepath} 2>/dev/null || echo ''"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


def has_content_changes(filepath: str) -> bool:
    """Check if a file has actual content changes (not just metadata)."""
    local_path = Path(SOURCE_DIR) / filepath
    
    if not local_path.exists():
        return False
    
    try:
        with open(local_path, 'r') as f:
            local_content = f.read()
    except:
        # Binary file or read error - assume changed
        return True
    
    remote_content = fetch_remote_file(filepath)
    
    # If remote doesn't exist, it's definitely a change
    if not remote_content:
        return True
    
    # Compare content
    return local_content != remote_content


def show_diff(filepath: str) -> bool:
    """Show diff between local and remote file. Returns True if there are differences."""
    local_path = Path(SOURCE_DIR) / filepath
    
    if not local_path.exists():
        print(f"{RED}Local file not found: {filepath}{NC}")
        return False
    
    # Read local content
    with open(local_path, 'r') as f:
        local_content = f.read()
    
    # Get remote content
    remote_content = fetch_remote_file(filepath)
    
    # If remote file is empty/doesn't exist, show the entire local file as new
    if not remote_content:
        print(f"{YELLOW}Remote file does not exist (will be created){NC}")
        lines = local_content.splitlines()
        if len(lines) > 50:
            print(f"{GREEN}+++ {filepath} (showing first 50 lines of {len(lines)}){NC}")
            for line in lines[:50]:
                print(f"{GREEN}+{line}{NC}")
            print(f"{GREEN}... ({len(lines) - 50} more lines){NC}")
        else:
            print(f"{GREEN}+++ {filepath}{NC}")
            for line in lines:
                print(f"{GREEN}+{line}{NC}")
        return True
    
    # Create temporary file with remote content
    with tempfile.NamedTemporaryFile(mode='w', suffix=f'_{Path(filepath).name}', delete=False) as tmp:
        tmp.write(remote_content)
        tmp_path = tmp.name
    
    try:
        # Run diff command
        cmd = ["diff", "-u", tmp_path, str(local_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"{GREEN}No changes in {filepath}{NC}")
            return False  # No differences
        
        # Show the diff with proper labels and colors
        output_lines = result.stdout.splitlines()
        for line in output_lines:
            if line.startswith("---"):
                print(f"--- {DEST}:{DEST_DIR}/{filepath}")
            elif line.startswith("+++"):
                print(f"+++ {filepath}")
            elif line.startswith("-"):
                print(f"{RED}{line}{NC}")
            elif line.startswith("+"):
                print(f"{GREEN}{line}{NC}")
            elif line.startswith("@"):
                print(f"{YELLOW}{line}{NC}")
            else:
                print(line)
        return True
    finally:
        Path(tmp_path).unlink()


def main():
    print(f"{GREEN}=== Govee Life Deploy Script ==={NC}")
    print(f"Source: {SOURCE_DIR}")
    print(f"Destination: {DEST}:{DEST_DIR}")
    print()

    # Check if source directory exists
    if not Path(SOURCE_DIR).exists():
        print(f"{RED}Error: Source directory {SOURCE_DIR} not found{NC}")
        sys.exit(1)

    # Dry run to see what will change
    print(f"{YELLOW}Analyzing changes...{NC}")

    exit_code, output = run_command(
        [
            "rsync",
            "-avzn",  # -n for dry run
            "--delete",
            "--itemize-changes",
            f"{SOURCE_DIR}/",
            f"{DEST}:{DEST_DIR}/",
        ]
    )

    if exit_code != 0:
        print(f"{RED}Error connecting to {DEST}:{NC}")
        print(output)
        sys.exit(1)

    changes = parse_rsync_changes(output)

    # Filter updated files to only include those with actual content changes
    if changes["updated"]:
        print(f"{YELLOW}Checking for actual content changes...{NC}")
        files_with_content_changes = []
        files_with_metadata_only = []
        
        for filepath in changes["updated"]:
            if has_content_changes(filepath):
                files_with_content_changes.append(filepath)
            else:
                files_with_metadata_only.append(filepath)
        
        changes["updated"] = files_with_content_changes
        
        if files_with_metadata_only:
            print(f"{GREEN}Files with metadata changes only (timestamps/permissions): {len(files_with_metadata_only)}{NC}")
            for f in files_with_metadata_only:
                print(f"  {GREEN}✓ {f}{NC}")
            print()

    total_changes = sum(len(v) for v in changes.values())
    if total_changes == 0:
        print(f"{GREEN}No content changes to deploy.{NC}")
        sys.exit(0)

    print(f"{YELLOW}Content changes detected:{NC}")
    print()
    
    # Show summary
    if changes["deleted"]:
        print(f"{RED}Files to delete: {len(changes['deleted'])}{NC}")
        for f in changes["deleted"]:
            print(f"  {RED}- {f}{NC}")
        print()
    
    if changes["new"]:
        print(f"{YELLOW}New files: {len(changes['new'])}{NC}")
        for f in changes["new"]:
            print(f"  {YELLOW}+ {f}{NC}")
        print()
    
    if changes["updated"]:
        print(f"{GREEN}Files to update: {len(changes['updated'])}{NC}")
        for f in changes["updated"]:
            print(f"  {GREEN}~ {f}{NC}")
        print()
    
    # Ask if user wants to see diffs
    if changes["updated"]:
        response = input(f"{YELLOW}Show diffs for updated files? (y/n) {NC}")
        if response.lower() in ["y", "yes"]:
            print()
            for filepath in changes["updated"]:
                print(f"{YELLOW}=== Diff for {filepath} ==={NC}")
                show_diff(filepath)
                print()

    print()
    response = input(f"{YELLOW}Deploy these changes? (y/n) {NC}")

    if response.lower() in ["y", "yes"]:
        print(f"{GREEN}Deploying...{NC}")

        # Actual rsync without dry run
        exit_code, output = run_command(
            [
                "rsync",
                "-avz",
                "--delete",
                f"{SOURCE_DIR}/",
                f"{DEST}:{DEST_DIR}/",
            ]
        )

        if exit_code == 0:
            print(f"{GREEN}✓ Deploy completed successfully!{NC}")
        else:
            print(f"{RED}✗ Deploy failed!{NC}")
            print(output)
            sys.exit(1)
    else:
        print(f"{YELLOW}Deploy cancelled.{NC}")


if __name__ == "__main__":
    main()
