#!/bin/bash

# This script acts as a supervisor for maestrocat.py to ensure a clean shutdown.

# Function to clean up all related processes on exit
cleanup() {
    echo -e "\n\nCTRL+C detected. Shutting down MaestroCat and all related processes..."
    
    # Check if the PID file exists and the process is running
    if [ -n "$MAESTROCAT_PID" ] && ps -p "$MAESTROCAT_PID" > /dev/null; then
        # Use pkill with -P to kill all children of the main script's process.
        # This is the most reliable way to ensure whisper-stream and other subprocesses are terminated.
        pkill -P "$MAESTROCAT_PID"
        
        # For good measure, send a kill signal to the main process itself.
        # Use SIGTERM first for a graceful attempt, then SIGKILL if needed.
        kill "$MAESTROCAT_PID" &>/dev/null
        sleep 0.5
        kill -9 "$MAESTROCAT_PID" &>/dev/null
    fi
    
    echo "Cleanup complete. Goodbye!"
    # Exit the script
    exit 0
}

# Trap the INT signal (CTRL+C) to run the cleanup function.
trap cleanup SIGINT

# Run the python script in the background, passing along any command-line arguments.
echo "Starting MaestroCat... (Press CTRL+C to exit cleanly)"
python maestrocat.py "$@" &

# Store the Process ID (PID) of the background process.
MAESTROCAT_PID=$!

# Wait for the background process to finish.
# The 'wait' command will be interrupted by CTRL+C, which then triggers the trap.
wait "$MAESTROCAT_PID"
