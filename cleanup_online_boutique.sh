#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print with color
print_status() {
    echo -e "${GREEN}[*]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[!]${NC} $1"
}

# Check and install Google Cloud SDK if needed
if ! command -v gcloud &> /dev/null; then
    print_status "Installing Google Cloud SDK..."
    # For macOS, use the official installer
    if [[ "$OSTYPE" == "darwin"* ]]; then
        curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-446.0.0-darwin-arm.tar.gz
        tar -xf google-cloud-cli-446.0.0-darwin-arm.tar.gz
        ./google-cloud-sdk/install.sh --quiet
        ./google-cloud-sdk/bin/gcloud init
        source ./google-cloud-sdk/path.bash.inc
        rm google-cloud-cli-446.0.0-darwin-arm.tar.gz
    else
        print_error "Please install Google Cloud SDK manually for your OS"
        exit 1
    fi
fi

# Deactivate virtual environment temporarily to access system PATH
if [ -n "$VIRTUAL_ENV" ]; then
    print_status "Temporarily deactivating virtual environment..."
    # Save the virtual env path
    VENV_PATH="$VIRTUAL_ENV"
    # Deactivate
    deactivate
    # Add common binary paths to PATH
    export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
fi

# Find or install kubectl
KUBECTL=""
if command -v kubectl &> /dev/null; then
    KUBECTL="$(command -v kubectl)"
    print_status "Found kubectl at: $KUBECTL"
elif [ -f "/usr/local/bin/kubectl" ]; then
    KUBECTL="/usr/local/bin/kubectl"
    print_status "Found kubectl at: $KUBECTL"
elif [ -f "/opt/homebrew/bin/kubectl" ]; then
    KUBECTL="/opt/homebrew/bin/kubectl"
    print_status "Found kubectl at: $KUBECTL"
else
    print_status "Installing kubectl using Homebrew..."
    if ! command -v brew &> /dev/null; then
        if [ -f "/opt/homebrew/bin/brew" ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -f "/usr/local/bin/brew" ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        else
            print_error "Homebrew not found. Please install it first."
            exit 1
        fi
    fi
    brew install kubectl || {
        print_error "Failed to install kubectl"
        exit 1
    }
    KUBECTL="$(command -v kubectl)"
fi

if [ -z "$KUBECTL" ] || ! $KUBECTL version --client &> /dev/null; then
    print_error "Could not find or install kubectl"
    exit 1
fi

# Reactivate virtual environment if we deactivated it
if [ -n "$VENV_PATH" ]; then
    print_status "Reactivating virtual environment..."
    source "$VENV_PATH/bin/activate"
fi

# Verify installations
print_status "Verifying installations..."
gcloud --version || {
    print_error "gcloud not properly installed"
    exit 1
}
$KUBECTL version --client || {
    print_error "kubectl not properly installed"
    exit 1
}

print_status "Starting cleanup of Online Boutique..."

# Delete the Online Boutique deployment
print_status "Deleting Online Boutique deployment..."
$KUBECTL delete -f https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml || {
    print_warning "Failed to delete some resources. This is normal if they don't exist."
}

# Delete the GKE cluster
print_status "Deleting GKE cluster..."
CLUSTER_NAME="online-boutique"
REGION="us-central1"

gcloud container clusters delete "$CLUSTER_NAME" \
    --region "$REGION" \
    --quiet || {
    print_warning "Failed to delete cluster. It might not exist or you might not have permissions."
}

# Clean up local kubectl context
print_status "Cleaning up kubectl context..."
$KUBECTL config delete-context gke_$(gcloud config get-value project)_${REGION}_${CLUSTER_NAME} 2>/dev/null || {
    print_warning "Failed to delete kubectl context. It might not exist."
}

print_status "Cleanup complete!"
print_status "Note: If you want to completely remove all Google Cloud resources, you can delete the project:"
print_status "gcloud projects delete $(gcloud config get-value project)"
