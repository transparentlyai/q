#!/bin/bash

# portkill.sh - A script to kill processes running on specific ports
# Enhanced with multiple options for better control

# Display help information
show_help() {
    echo "Usage: $0 [OPTIONS] [PORT_NUMBER]"
    echo
    echo "Options:"
    echo "  -h, --help        Display this help message"
    echo "  -l, --list        List all processes using network ports"
    echo "  -f, --force       Force kill the process (SIGKILL/9)"
    echo "  -g, --graceful    Gracefully terminate the process (SIGTERM/15)"
    echo "  -p, --protocol    Specify protocol (tcp/udp), default is both"
    echo "  -v, --verbose     Show verbose output"
    echo "  -m, --multiple    Kill all processes on the specified port (not just the first)"
    echo "  -w, --wait        Wait time in seconds before checking if process is killed (default: 0.5)"
    echo "  -i, --interactive Confirm before killing each process"
    echo "  -n, --dry-run     Show what would be killed without actually killing"
    echo "  -s, --search      Search for processes by name using the port number"
    echo "  -a, --all-info    Show detailed information about processes before killing"
    echo "  -t, --timeout     Timeout in seconds before force killing if graceful kill fails"
    echo
    echo "Examples:"
    echo "  $0 8080                   Kill process on port 8080"
    echo "  $0 -g 3000                Gracefully terminate process on port 3000"
    echo "  $0 -f 5000                Force kill process on port 5000"
    echo "  $0 -p tcp -m 8080         Kill all TCP processes on port 8080"
    echo "  $0 -l                     List all processes using network ports"
    echo "  $0 -i -m 8080             Interactively kill all processes on port 8080"
    echo "  $0 -n 3000                Show what would be killed on port 3000"
    echo "  $0 -t 5 -g 8080           Try graceful kill, force kill after 5 seconds if still running"
    echo "  $0 -s node                Search for node processes using ports"
}

# Default values
FORCE=false
GRACEFUL=false
VERBOSE=false
MULTIPLE=false
PROTOCOL=""
LIST=false
DRY_RUN=false
INTERACTIVE=false
WAIT_TIME=0.5
TIMEOUT=0
SEARCH=""
ALL_INFO=false

# Parse command line options
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        -l|--list)
            LIST=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -g|--graceful)
            GRACEFUL=true
            shift
            ;;
        -p|--protocol)
            PROTOCOL="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -m|--multiple)
            MULTIPLE=true
            shift
            ;;
        -w|--wait)
            WAIT_TIME="$2"
            shift 2
            ;;
        -i|--interactive)
            INTERACTIVE=true
            shift
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -s|--search)
            SEARCH="$2"
            shift 2
            ;;
        -a|--all-info)
            ALL_INFO=true
            shift
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -*)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
        *)
            PORT="$1"
            shift
            ;;
    esac
done

# Function to show process details
show_process_details() {
    local pid=$1
    echo "Process Details for PID $pid:"
    echo "----------------------------"
    ps -p $pid -o pid,ppid,user,%cpu,%mem,vsz,rss,tty,stat,start,time,command
    echo
    echo "Open Files and Connections:"
    lsof -p $pid | head -20
    if [ $(lsof -p $pid | wc -l) -gt 20 ]; then
        echo "... (more files/connections omitted) ..."
    fi
    echo
}

# List all processes using network ports
if [ "$LIST" = true ]; then
    echo "Listing all processes using network ports:"
    echo "----------------------------------------"
    if [ ! -z "$SEARCH" ]; then
        echo "Filtering for processes containing: $SEARCH"
        lsof -i -P -n | grep -i "$SEARCH"
    else
        lsof -i -P -n | grep LISTEN
    fi
    exit 0
fi

# Check if port is provided (unless we're just searching)
if [ -z "$PORT" ] && [ -z "$SEARCH" ]; then
    echo "Error: Port number is required"
    show_help
    exit 1
fi

# If we're just searching without a port
if [ ! -z "$SEARCH" ] && [ -z "$PORT" ]; then
    echo "Searching for processes containing '$SEARCH' using any port:"
    lsof -i -P -n | grep -i "$SEARCH"
    exit 0
fi

# Validate port number
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "Error: Port must be a number"
    exit 1
fi

# Set protocol filter if specified
PROTO_FILTER=""
if [ ! -z "$PROTOCOL" ]; then
    if [[ "$PROTOCOL" != "tcp" && "$PROTOCOL" != "udp" ]]; then
        echo "Error: Protocol must be tcp or udp"
        exit 1
    fi
    PROTO_FILTER="-P $PROTOCOL"
    [ "$VERBOSE" = true ] && echo "Filtering for $PROTOCOL protocol"
fi

# Find the process ID(s) using the port
if [ "$MULTIPLE" = true ]; then
    PIDS=$(lsof -t -i:$PORT $PROTO_FILTER)
else
    PIDS=$(lsof -t -i:$PORT $PROTO_FILTER | head -1)
fi

# Filter by search term if provided
if [ ! -z "$SEARCH" ] && [ ! -z "$PIDS" ]; then
    FILTERED_PIDS=""
    for PID in $PIDS; do
        if ps -p $PID -o command | grep -v "COMMAND" | grep -q -i "$SEARCH"; then
            FILTERED_PIDS="$FILTERED_PIDS $PID"
        fi
    done
    PIDS=$(echo "$FILTERED_PIDS" | tr -s ' ' '\n' | grep -v '^$')
fi

if [ -z "$PIDS" ]; then
    echo "No process found running on port $PORT"
    if [ ! -z "$SEARCH" ]; then
        echo "with search term '$SEARCH'"
    fi
    exit 1
else
    COUNT=$(echo "$PIDS" | wc -l)
    [ "$VERBOSE" = true ] && echo "Found $COUNT process(es) running on port $PORT"
    
    for PID in $PIDS; do
        echo "Found process $PID running on port $PORT"
        
        # Show process command
        COMMAND=$(ps -p $PID -o command | grep -v "COMMAND")
        echo "Command: $COMMAND"
        
        # Show detailed information if requested
        if [ "$ALL_INFO" = true ]; then
            show_process_details $PID
        fi
        
        # Interactive confirmation
        if [ "$INTERACTIVE" = true ]; then
            read -p "Kill this process? (y/n): " CONFIRM
            if [[ ! "$CONFIRM" =~ ^[Yy] ]]; then
                echo "Skipping process $PID"
                continue
            fi
        fi
        
        # Determine kill signal
        SIGNAL=15  # Default to SIGTERM
        if [ "$FORCE" = true ]; then
            SIGNAL=9  # SIGKILL
            echo "Force killing process $PID..."
        elif [ "$GRACEFUL" = true ]; then
            echo "Gracefully terminating process $PID..."
        else
            echo "Killing process $PID..."
        fi
        
        # Dry run mode
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY RUN] Would kill process $PID with signal $SIGNAL"
            continue
        fi
        
        # Kill the process
        kill -$SIGNAL $PID
        
        # Check if process was killed
        sleep $WAIT_TIME
        if ps -p $PID > /dev/null; then
            echo "Process $PID is still running."
            
            # Handle timeout for graceful termination
            if [ "$GRACEFUL" = true ] && [ "$TIMEOUT" -gt 0 ]; then
                echo "Waiting up to $TIMEOUT seconds before force killing..."
                
                for ((i=1; i<=TIMEOUT; i++)); do
                    sleep 1
                    if ! ps -p $PID > /dev/null; then
                        echo "Process $PID terminated after $i seconds"
                        break
                    fi
                    
                    if [ $i -eq $TIMEOUT ]; then
                        echo "Timeout reached. Force killing process $PID..."
                        kill -9 $PID
                        sleep $WAIT_TIME
                        if ! ps -p $PID > /dev/null; then
                            echo "Process $PID force killed successfully"
                        else
                            echo "Failed to kill process $PID even with SIGKILL"
                        fi
                    fi
                done
            else
                echo "Consider using -f option to force kill or -t option to set a timeout."
            fi
        else
            echo "Process $PID killed successfully"
        fi
    done
fi
echo "by mauro"
