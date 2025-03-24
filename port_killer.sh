#!/bin/bash

# port_killer.sh - A utility to find and kill processes using specific ports
# Created by Q for Mauro

usage() {
    echo "Usage: $0 [OPTIONS] PORT"
    echo
    echo "Kill processes using the specified PORT"
    echo
    echo "Options:"
    echo "  -l, --list       List processes without killing them"
    echo "  -f, --force      Force kill (SIGKILL) instead of graceful termination (SIGTERM)"
    echo "  -i, --interactive Confirm before killing each process"
    echo "  -a, --all        Kill all processes using the port (default: only kill the first one)"
    echo "  -s, --signal SIG Specify the signal to send (default: SIGTERM, or SIGKILL with -f)"
    echo "  -v, --verbose    Show detailed information"
    echo "  -h, --help       Display this help message"
    echo
    echo "Examples:"
    echo "  $0 8080          # Kill the first process using port 8080"
    echo "  $0 -l 3000       # List processes using port 3000 without killing"
    echo "  $0 -f -a 5432    # Force kill all processes using port 5432"
    echo "  $0 -s SIGINT 8080 # Kill process on port 8080 with SIGINT"
    exit 1
}

# Default values
LIST_ONLY=false
FORCE_KILL=false
INTERACTIVE=false
KILL_ALL=false
VERBOSE=false
SIGNAL=""
PORT=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -l|--list)
            LIST_ONLY=true
            shift
            ;;
        -f|--force)
            FORCE_KILL=true
            shift
            ;;
        -i|--interactive)
            INTERACTIVE=true
            shift
            ;;
        -a|--all)
            KILL_ALL=true
            shift
            ;;
        -s|--signal)
            shift
            if [[ $# -gt 0 ]]; then
                SIGNAL=$1
                shift
            else
                echo "Error: --signal requires an argument"
                usage
            fi
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Error: Unknown option $1"
            usage
            ;;
        *)
            if [[ -z "$PORT" ]]; then
                PORT=$1
                shift
            else
                echo "Error: Too many arguments"
                usage
            fi
            ;;
    esac
done

# Check if PORT is provided and is a number
if [[ -z "$PORT" ]]; then
    echo "Error: PORT is required"
    usage
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "Error: PORT must be a number"
    usage
fi

# Find processes using the port
if [[ "$VERBOSE" == true ]]; then
    echo "Searching for processes using port $PORT..."
fi

# Use lsof to find processes
PROCESSES=$(lsof -i :"$PORT" -t 2>/dev/null)

if [[ -z "$PROCESSES" ]]; then
    echo "No processes found using port $PORT"
    exit 0
fi

# Count processes
PROCESS_COUNT=$(echo "$PROCESSES" | wc -l)

if [[ "$VERBOSE" == true ]]; then
    echo "Found $PROCESS_COUNT process(es) using port $PORT"
fi

# Display detailed information about the processes
if [[ "$LIST_ONLY" == true || "$VERBOSE" == true || "$INTERACTIVE" == true ]]; then
    echo "Process details:"
    for PID in $PROCESSES; do
        echo "PID: $PID"
        ps -p "$PID" -o user,pid,ppid,%cpu,%mem,start,time,command
        echo "---"
    done
fi

# Exit if only listing
if [[ "$LIST_ONLY" == true ]]; then
    exit 0
fi

# Set kill signal based on signal option, force option, or default
if [[ -n "$SIGNAL" ]]; then
    # Convert signal name to number if it doesn't start with a number
    if [[ "$SIGNAL" =~ ^[0-9] ]]; then
        KILL_SIGNAL="-$SIGNAL"
    elif [[ "$SIGNAL" =~ ^SIG ]]; then
        # Handle SIGTERM, SIGKILL, etc.
        case "$SIGNAL" in
            SIGTERM) KILL_SIGNAL="-15" ;;
            SIGKILL) KILL_SIGNAL="-9" ;;
            SIGHUP) KILL_SIGNAL="-1" ;;
            SIGINT) KILL_SIGNAL="-2" ;;
            SIGQUIT) KILL_SIGNAL="-3" ;;
            SIGABRT) KILL_SIGNAL="-6" ;;
            SIGUSR1) KILL_SIGNAL="-10" ;;
            SIGUSR2) KILL_SIGNAL="-12" ;;
            SIGPIPE) KILL_SIGNAL="-13" ;;
            SIGALRM) KILL_SIGNAL="-14" ;;
            SIGCONT) KILL_SIGNAL="-18" ;;
            SIGSTOP) KILL_SIGNAL="-19" ;;
            SIGTSTP) KILL_SIGNAL="-20" ;;
            *)
                echo "Error: Unknown signal $SIGNAL"
                exit 1
                ;;
        esac
    else
        # Handle TERM, KILL, etc. without SIG prefix
        case "$SIGNAL" in
            TERM) KILL_SIGNAL="-15" ;;
            KILL) KILL_SIGNAL="-9" ;;
            HUP) KILL_SIGNAL="-1" ;;
            INT) KILL_SIGNAL="-2" ;;
            QUIT) KILL_SIGNAL="-3" ;;
            ABRT) KILL_SIGNAL="-6" ;;
            USR1) KILL_SIGNAL="-10" ;;
            USR2) KILL_SIGNAL="-12" ;;
            PIPE) KILL_SIGNAL="-13" ;;
            ALRM) KILL_SIGNAL="-14" ;;
            CONT) KILL_SIGNAL="-18" ;;
            STOP) KILL_SIGNAL="-19" ;;
            TSTP) KILL_SIGNAL="-20" ;;
            *)
                echo "Error: Unknown signal $SIGNAL"
                exit 1
                ;;
        esac
    fi
    
    if [[ "$VERBOSE" == true ]]; then
        echo "Using signal $SIGNAL ($KILL_SIGNAL)"
    fi
else
    # No signal specified, use force option or default
    KILL_SIGNAL="-15"  # SIGTERM
    if [[ "$FORCE_KILL" == true ]]; then
        KILL_SIGNAL="-9"  # SIGKILL
        if [[ "$VERBOSE" == true ]]; then
            echo "Using SIGKILL (force kill)"
        fi
    else
        if [[ "$VERBOSE" == true ]]; then
            echo "Using SIGTERM (graceful termination)"
        fi
    fi
fi

# Kill processes
KILLED=0
for PID in $PROCESSES; do
    KILL_THIS=true
    
    # Interactive confirmation
    if [[ "$INTERACTIVE" == true ]]; then
        read -p "Kill process $PID? (y/n): " CONFIRM
        if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
            KILL_THIS=false
            echo "Skipping process $PID"
        fi
    fi
    
    if [[ "$KILL_THIS" == true ]]; then
        if kill $KILL_SIGNAL "$PID" 2>/dev/null; then
            echo "Killed process $PID"
            ((KILLED++))
            
            # Exit after killing one process unless KILL_ALL is true
            if [[ "$KILL_ALL" == false ]]; then
                break
            fi
        else
            echo "Failed to kill process $PID"
        fi
    fi
done

echo "Killed $KILLED out of $PROCESS_COUNT process(es) using port $PORT"
