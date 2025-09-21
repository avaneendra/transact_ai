#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for required tools
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}$1 is not installed${NC}"
        return 1
    fi
    echo -e "${GREEN}$1 is installed${NC}"
    return 0
}

# Install Google Cloud SDK for macOS using Homebrew
install_gcloud() {
    echo -e "${YELLOW}Installing Google Cloud SDK via Homebrew...${NC}"
    
    # First, ensure Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo -e "${YELLOW}Installing Homebrew...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        
        # Add Homebrew to PATH for Apple Silicon Macs
        if [[ $(uname -m) == 'arm64' ]]; then
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    fi
    
    # Install Python 3.10 (latest stable that works well with gcloud)
    echo -e "${YELLOW}Installing Python 3.10...${NC}"
    brew install python@3.10
    
    # Create a new virtual environment for gcloud
    echo -e "${YELLOW}Creating virtual environment for gcloud...${NC}"
    python3.10 -m venv ~/.gcloud_venv
    source ~/.gcloud_venv/bin/activate
    
    # Install required packages
    pip install --upgrade pip
    pip install importlib-metadata typing-extensions crcmod
    
    # Install Google Cloud SDK
    echo -e "${YELLOW}Installing Google Cloud SDK...${NC}"
    brew install --cask google-cloud-sdk
    
    # Add gcloud to PATH
    echo -e "${YELLOW}Configuring gcloud...${NC}"
    source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
    source "$(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc"
    
    # Set Python interpreter for gcloud
    export CLOUDSDK_PYTHON=~/.gcloud_venv/bin/python
    
    # Initialize gcloud
    echo -e "${YELLOW}Initializing gcloud...${NC}"
    gcloud init --skip-diagnostics --console-only \
        --project=${PROJECT_ID}
    
    # Install kubectl
    echo -e "${YELLOW}Installing kubectl...${NC}"
    gcloud components install kubectl --quiet
}

# Verify kubectl installation
verify_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}kubectl not found. Installing via gcloud components...${NC}"
        gcloud components install kubectl --quiet
    else
        echo -e "${GREEN}kubectl is installed${NC}"
    fi
}

# Set Google Cloud project details
export PROJECT_ID=calcium-doodad-471920-c1
export REGION=us-central1

# Function to clean up previous installations
cleanup_previous_install() {
    echo -e "${YELLOW}Cleaning up previous installations...${NC}"
    
    # Remove previous installations
    rm -rf ~/google-cloud-sdk ~/.gcloud_venv
    
    # Uninstall via Homebrew if present
    if brew list --cask | grep -q "google-cloud-sdk"; then
        echo -e "${YELLOW}Removing previous Homebrew installation...${NC}"
        brew uninstall --cask google-cloud-sdk
    fi
    
    # Remove Python 3.10 if no other tools use it
    read -p "Remove Python 3.10? Only do this if no other tools use it (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        brew uninstall python@3.10
    fi
    
    # Clean up any remaining files
    sudo rm -rf /usr/local/Caskroom/google-cloud-sdk
    
    echo -e "${GREEN}Cleanup complete${NC}"
}

# Function to verify gcloud installation
verify_gcloud() {
    # Check if gcloud is in PATH
    if ! command -v gcloud &> /dev/null; then
        echo -e "${RED}gcloud not found in PATH${NC}"
        echo -e "${YELLOW}Current PATH: $PATH${NC}"
        return 1
    fi
    
    # Check if gcloud can run
    if ! gcloud --version &> /dev/null; then
        echo -e "${RED}gcloud installation appears broken${NC}"
        return 1
    fi
    
    echo -e "${GREEN}gcloud installation verified${NC}"
    return 0
}

# Clean up any existing broken installation
echo -e "${YELLOW}Checking for existing installations...${NC}"
if command -v gcloud &> /dev/null && ! gcloud --version &> /dev/null; then
    echo -e "${RED}Found broken gcloud installation. Cleaning up...${NC}"
    cleanup_previous_install
fi

# Install gcloud if needed
if ! check_command gcloud || ! gcloud --version &> /dev/null; then
    echo -e "${YELLOW}Installing Google Cloud SDK...${NC}"
    cleanup_previous_install
    install_gcloud
    
    # Verify installation
    if ! verify_gcloud; then
        echo -e "${RED}Failed to install Google Cloud SDK${NC}"
        echo -e "${YELLOW}Please try installing manually:${NC}"
        echo "1. Visit: https://cloud.google.com/sdk/docs/install"
        echo "2. Download and install the SDK"
        echo "3. Run: source ~/.zshrc"
        echo "4. Run this script again"
        exit 1
    fi
fi

# Check for kubectl
if ! check_command kubectl; then
    echo -e "${YELLOW}Installing kubectl...${NC}"
    install_kubectl
fi

# Verify gcloud auth
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null; then
    echo -e "${YELLOW}Please login to Google Cloud:${NC}"
    gcloud auth login
fi

# Set Google Cloud project details
export PROJECT_ID=calcium-doodad-471920-c1
export REGION=us-central1

echo -e "${YELLOW}Setting up Google Cloud project...${NC}"

# Configure gcloud defaults
gcloud config set project ${PROJECT_ID}
gcloud config set compute/region ${REGION}

# Verify project access with detailed error reporting
echo -e "${YELLOW}Verifying project access...${NC}"
if ! gcloud projects describe ${PROJECT_ID} 2>/tmp/gcloud_error; then
    error_msg=$(cat /tmp/gcloud_error)
    echo -e "${RED}Cannot access project ${PROJECT_ID}${NC}"
    echo -e "${RED}Error: ${error_msg}${NC}"
    echo -e "${YELLOW}Please verify:${NC}"
    echo "1. You are logged in with the correct account"
    echo "2. You have access to the project"
    echo "3. The project ID is correct"
    echo -e "${YELLOW}Current account: $(gcloud config get-value account)${NC}"
    echo -e "${YELLOW}Try running: gcloud auth login${NC}"
    exit 1
fi

# Check billing with detailed error reporting
echo -e "${YELLOW}Checking billing status...${NC}"
if ! gcloud beta billing projects describe ${PROJECT_ID} 2>/tmp/gcloud_error; then
    error_msg=$(cat /tmp/gcloud_error)
    echo -e "${RED}Billing check failed for project ${PROJECT_ID}${NC}"
    echo -e "${RED}Error: ${error_msg}${NC}"
    echo -e "${YELLOW}Please:${NC}"
    echo "1. Enable billing at: https://console.cloud.google.com/billing/projects"
    echo "2. Verify you have billing viewer permissions"
    echo "3. Wait a few minutes after enabling billing"
    exit 1
fi

# Enable required APIs with progress reporting
echo -e "${YELLOW}Enabling required APIs...${NC}"

echo -e "${YELLOW}1. Enabling Cloud Resource Manager API...${NC}"
gcloud services enable cloudresourcemanager.googleapis.com --project=${PROJECT_ID} 2>/tmp/gcloud_error || {
    error_msg=$(cat /tmp/gcloud_error)
    echo -e "${RED}Failed to enable Cloud Resource Manager API${NC}"
    echo -e "${RED}Error: ${error_msg}${NC}"
    exit 1
}

echo -e "${YELLOW}2. Enabling Compute Engine API...${NC}"
gcloud services enable compute.googleapis.com --project=${PROJECT_ID} 2>/tmp/gcloud_error || {
    error_msg=$(cat /tmp/gcloud_error)
    echo -e "${RED}Failed to enable Compute Engine API${NC}"
    echo -e "${RED}Error: ${error_msg}${NC}"
    exit 1
}

echo -e "${YELLOW}3. Enabling Kubernetes Engine API...${NC}"
gcloud services enable container.googleapis.com --project=${PROJECT_ID} 2>/tmp/gcloud_error || {
    error_msg=$(cat /tmp/gcloud_error)
    echo -e "${RED}Failed to enable Kubernetes Engine API${NC}"
    echo -e "${RED}Error: ${error_msg}${NC}"
    exit 1
}

echo -e "${YELLOW}4. Enabling Cloud Billing API...${NC}"
gcloud services enable cloudbilling.googleapis.com --project=${PROJECT_ID} 2>/tmp/gcloud_error || {
    error_msg=$(cat /tmp/gcloud_error)
    echo -e "${RED}Failed to enable Cloud Billing API${NC}"
    echo -e "${RED}Error: ${error_msg}${NC}"
    exit 1
}

# Wait for APIs to be fully enabled
echo -e "${YELLOW}Waiting for APIs to be ready...${NC}"
sleep 30

# Create GKE cluster
echo -e "${YELLOW}Creating GKE cluster...${NC}"
gcloud container clusters create-auto online-boutique \
    --project=${PROJECT_ID} \
    --region=${REGION}

# Get cluster credentials
echo -e "${YELLOW}Getting cluster credentials...${NC}"
gcloud container clusters get-credentials online-boutique \
    --project=${PROJECT_ID} \
    --region=${REGION}

# Clone Online Boutique repository
echo -e "${YELLOW}Cloning Online Boutique repository...${NC}"
git clone --depth 1 --branch v0 https://github.com/GoogleCloudPlatform/microservices-demo.git
cd microservices-demo/

# Deploy Online Boutique
echo -e "${YELLOW}Deploying Online Boutique...${NC}"
kubectl apply -f ./release/kubernetes-manifests.yaml

# Wait for pods to be ready
echo -e "${YELLOW}Waiting for pods to be ready...${NC}"
kubectl wait --for=condition=ready pod --all --timeout=300s

# Get frontend external IP
echo -e "${YELLOW}Getting frontend external IP...${NC}"
EXTERNAL_IP=""
while [ -z "$EXTERNAL_IP" ]; do
    EXTERNAL_IP=$(kubectl get service frontend-external | awk 'NR==2{print $4}')
    if [ -z "$EXTERNAL_IP" ]; then
        echo -e "${YELLOW}Waiting for external IP...${NC}"
        sleep 10
    fi
done

echo -e "${GREEN}Online Boutique is ready!${NC}"
echo -e "${GREEN}Frontend URL: http://$EXTERNAL_IP${NC}"
echo -e "${GREEN}Save this IP for API integration${NC}"

# Save the IP for our application
echo "BOUTIQUE_API_URL=http://$EXTERNAL_IP" > .env.boutique
