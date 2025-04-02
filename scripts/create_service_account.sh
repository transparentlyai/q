#!/bin/bash

# Script to create a Google Cloud service account
# Supports both interactive and command-line argument modes
# Usage: ./create_service_account.sh [options]

set -e  # Exit immediately if a command exits with a non-zero status

# Default values
INTERACTIVE=true
PROJECT_ID=""
ACCOUNT_NAME=""
DISPLAY_NAME=""
DESCRIPTION="Service account for cloud access"
ROLES=()
KEY_FILE=""

# Function to display help
show_help() {
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  -h, --help                 Show this help message"
  echo "  -p, --project PROJECT_ID   Specify the Google Cloud project ID"
  echo "  -a, --account ACCOUNT_NAME Specify the service account name"
  echo "  -d, --display DISPLAY_NAME Specify the display name"
  echo "  -D, --desc DESCRIPTION     Specify the description"
  echo "  -r, --role ROLE            Add a role (can be used multiple times)"
  echo "  -k, --key KEY_FILE         Specify the key file name"
  echo "  -n, --non-interactive      Run in non-interactive mode"
  echo ""
  echo "Examples:"
  echo "  $0                                                # Run interactively"
  echo "  $0 --project my-project --account my-account --role roles/aiplatform.user  # Non-interactive with minimal options"
  echo "  $0 -p my-project -a my-account -r roles/aiplatform.user -r roles/storage.objectViewer  # Add multiple roles"
  echo ""
  echo "Common roles:"
  echo "  roles/aiplatform.user      - AI Platform User"
  echo "  roles/aiplatform.admin     - AI Platform Admin"
  echo "  roles/storage.objectViewer - Storage Object Viewer"
  echo "  roles/bigquery.dataViewer  - BigQuery Data Viewer"
  echo "  roles/bigquery.jobUser     - BigQuery Job User"
  echo "  roles/editor               - Editor"
  echo "  roles/viewer               - Viewer"
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    -p|--project)
      PROJECT_ID="$2"
      shift 2
      ;;
    -a|--account)
      ACCOUNT_NAME="$2"
      shift 2
      ;;
    -d|--display)
      DISPLAY_NAME="$2"
      shift 2
      ;;
    -D|--desc)
      DESCRIPTION="$2"
      shift 2
      ;;
    -r|--role)
      ROLES+=("$2")
      shift 2
      ;;
    -k|--key)
      KEY_FILE="$2"
      shift 2
      ;;
    -n|--non-interactive)
      INTERACTIVE=false
      shift
      ;;
    *)
      echo "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

# Function to get valid input
get_input() {
  local prompt="$1"
  local var_name="$2"
  local default="$3"
  local value=""
  
  if [ -n "$default" ]; then
    prompt="$prompt [$default]"
  fi
  
  while [ -z "$value" ]; do
    read -p "$prompt: " value
    if [ -z "$value" ] && [ -n "$default" ]; then
      value="$default"
    fi
    
    if [ -z "$value" ]; then
      echo "Error: Input cannot be empty. Please try again."
    fi
  done
  
  eval "$var_name=\"$value\""
}

# Interactive mode
if [ "$INTERACTIVE" = true ]; then
  echo "=== Google Cloud Service Account Creator ==="
  echo ""

  # List available projects if project ID not provided
  if [ -z "$PROJECT_ID" ]; then
    echo "Available projects:"
    gcloud projects list --format="table[box](projectId,name)"
    echo ""
    get_input "Enter the project ID" PROJECT_ID
  fi

  # Get service account details if not provided
  if [ -z "$ACCOUNT_NAME" ]; then
    get_input "Enter service account name (e.g., q-for-carlos)" ACCOUNT_NAME
  fi
  
  if [ -z "$DISPLAY_NAME" ]; then
    get_input "Enter display name" DISPLAY_NAME "$ACCOUNT_NAME"
  fi
  
  if [ "$DESCRIPTION" = "Service account for cloud access" ]; then
    get_input "Enter description" DESCRIPTION "$DESCRIPTION"
  fi

  # Get roles if not provided
  if [ ${#ROLES[@]} -eq 0 ]; then
    echo ""
    echo "Common roles:"
    echo "1. roles/aiplatform.user - AI Platform User"
    echo "2. roles/aiplatform.admin - AI Platform Admin"
    echo "3. roles/storage.objectViewer - Storage Object Viewer"
    echo "4. roles/bigquery.dataViewer - BigQuery Data Viewer"
    echo "5. roles/bigquery.jobUser - BigQuery Job User"
    echo "6. roles/editor - Editor"
    echo "7. roles/viewer - Viewer"
    echo "8. roles/aiplatform.user AND roles/aiplatform.admin - Both AI Platform roles"
    echo ""

    while true; do
      read -p "Enter a role (number 1-8 or full role name, or 'done' to finish): " ROLE_INPUT
      
      if [ "$ROLE_INPUT" = "done" ]; then
        break
      fi
      
      # Convert number to role name
      case "$ROLE_INPUT" in
        1) ROLE="roles/aiplatform.user" ;;
        2) ROLE="roles/aiplatform.admin" ;;
        3) ROLE="roles/storage.objectViewer" ;;
        4) ROLE="roles/bigquery.dataViewer" ;;
        5) ROLE="roles/bigquery.jobUser" ;;
        6) ROLE="roles/editor" ;;
        7) ROLE="roles/viewer" ;;
        8) 
          ROLES+=("roles/aiplatform.user")
          ROLES+=("roles/aiplatform.admin")
          echo "Added roles: roles/aiplatform.user and roles/aiplatform.admin"
          continue
          ;;
        *) ROLE="$ROLE_INPUT" ;;
      esac
      
      if [ "$ROLE_INPUT" != "8" ]; then
        ROLES+=("$ROLE")
        echo "Added role: $ROLE"
      fi
    done
  fi
else
  # Non-interactive mode - validate required parameters
  if [ -z "$PROJECT_ID" ] || [ -z "$ACCOUNT_NAME" ]; then
    echo "Error: In non-interactive mode, you must specify at least --project and --account"
    show_help
    exit 1
  fi
  
  # Set default display name if not provided
  if [ -z "$DISPLAY_NAME" ]; then
    DISPLAY_NAME="$ACCOUNT_NAME"
  fi
  
  # Set default role if none provided
  if [ ${#ROLES[@]} -eq 0 ]; then
    echo "No roles specified. Adding default role: roles/viewer"
    ROLES+=("roles/viewer")
  fi
fi

# Verify project exists and switch to it
if ! gcloud projects describe "$PROJECT_ID" &>/dev/null; then
  echo "Error: Project '$PROJECT_ID' not found or you don't have access to it."
  exit 1
fi

echo "Switching to project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Full service account email
SERVICE_ACCOUNT="${ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Key filename if not specified
if [ -z "$KEY_FILE" ]; then
  KEY_FILE="${ACCOUNT_NAME}-key.json"
fi

echo ""
echo "Creating service account '${ACCOUNT_NAME}' in project '${PROJECT_ID}'..."

# Create the service account
gcloud iam service-accounts create ${ACCOUNT_NAME} \
  --display-name="${DISPLAY_NAME}" \
  --description="${DESCRIPTION}"

echo "Assigning roles to the service account..."

# Assign the roles
for ROLE in "${ROLES[@]}"; do
  echo "Assigning role: $ROLE"
  gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="$ROLE"
done

echo "Generating key file '${KEY_FILE}'..."

# Create and download a key
gcloud iam service-accounts keys create ${KEY_FILE} \
  --iam-account=${SERVICE_ACCOUNT}

echo ""
echo "Service account creation complete!"
echo "Service account email: ${SERVICE_ACCOUNT}"
echo "Key file: ${KEY_FILE}"
echo "Assigned roles: ${ROLES[*]}"
echo ""
echo "IMPORTANT: Share the key file securely and ensure it's not committed to public repositories."

# Set executable permissions
chmod +x "$0"
