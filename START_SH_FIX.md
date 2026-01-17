# Fix for start.sh - Add BatchnodeI9 Requirements Installation

## Problem
Your start.sh only installs requirements from ZIT_REPO_DIR, but NOT from BATCHNODE_REPO_DIR or SAVEZIP_REPO_DIR.

## Solution
Find this section in your start.sh (around line 270):

```bash
# Install node requirements (SEQUENTIAL to avoid pip race conditions)
INSTALL_NODE_REQS="${INSTALL_NODE_REQS:-1}"
REQ_MARK="${PERSIST_DIR}/.node-reqs-installed"

if [ "$INSTALL_NODE_REQS" = "1" ]; then
  if [ ! -f "$REQ_MARK" ] || [ "$UPDATE_NODES" = "1" ]; then
    echo "[pip] Installing node requirements (constrained)..."

    # Process all requirements sequentially to avoid pip corruption
    for dir in "${ZIT_REPO_DIR}"/*; do
      [ -d "$dir" ] || continue
      req="${dir}/requirements.txt"
      if [ -f "$req" ]; then
        echo "  - [pip] $(basename "$dir")/requirements.txt"
        safe_pip_install_req "$req"
      fi
    done

    touch "$REQ_MARK"
  else
    echo "[pip] Node requirements already installed (skip)"
  fi
fi
```

## Replace with:

```bash
# Install node requirements (SEQUENTIAL to avoid pip race conditions)
INSTALL_NODE_REQS="${INSTALL_NODE_REQS:-1}"
REQ_MARK="${PERSIST_DIR}/.node-reqs-installed"

if [ "$INSTALL_NODE_REQS" = "1" ]; then
  if [ ! -f "$REQ_MARK" ] || [ "$UPDATE_NODES" = "1" ] || [ "$UPDATE_BATCHNODE" = "1" ] || [ "$UPDATE_SAVEZIP" = "1" ]; then
    echo "[pip] Installing node requirements (constrained)..."

    # Process ZIT node pack requirements
    for dir in "${ZIT_REPO_DIR}"/*; do
      [ -d "$dir" ] || continue
      req="${dir}/requirements.txt"
      if [ -f "$req" ]; then
        echo "  - [pip] $(basename "$dir")/requirements.txt"
        safe_pip_install_req "$req"
      fi
    done

    # Process BatchnodeI9 requirements
    for dir in "${BATCHNODE_REPO_DIR}"/*; do
      [ -d "$dir" ] || continue
      req="${dir}/requirements.txt"
      if [ -f "$req" ]; then
        echo "  - [pip] BatchnodeI9/$(basename "$dir")/requirements.txt"
        safe_pip_install_req "$req"
      fi
    done

    # Process Save ZIP I9 requirements
    for dir in "${SAVEZIP_REPO_DIR}"/*; do
      [ -d "$dir" ] || continue
      req="${dir}/requirements.txt"
      if [ -f "$req" ]; then
        echo "  - [pip] Save-ZIP-I9/$(basename "$dir")/requirements.txt"
        safe_pip_install_req "$req"
      fi
    done

    touch "$REQ_MARK"
  else
    echo "[pip] Node requirements already installed (skip)"
  fi
fi
```

## What Changed:
1. Added `|| [ "$UPDATE_BATCHNODE" = "1" ] || [ "$UPDATE_SAVEZIP" = "1" ]` to the update check
2. Added loop for `BATCHNODE_REPO_DIR`
3. Added loop for `SAVEZIP_REPO_DIR`

## After Applying:
1. Delete the marker file: `rm /workspace/runpod-slim/.node-reqs-installed`
2. Restart your pod
3. Dependencies will be installed from BatchnodeI9/I9-Batch/requirements.txt

Your logs should then show:
```
[pip] Installing node requirements (constrained)...
  - [pip] BatchnodeI9/I9-Batch/requirements.txt
```
