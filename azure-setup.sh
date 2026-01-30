#!/bin/bash

# Azure VM Setup Script for MLOps Fraud Detection
# Run this script after SSH into the Azure VM

set -e

echo "Setting up MLOps Fraud Detection on Azure VM..."

# Update system packages
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
echo "Installing Docker and Docker Compose..."
sudo apt install -y docker.io docker-compose git curl wget htop unzip

# Start and enable Docker
sudo systemctl enable docker
sudo systemctl start docker

# Add user to docker group
sudo usermod -aG docker $USER

# Install Node.js for frontend dependencies
echo "Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -
sudo apt install -y nodejs

# Create application directory
echo "Creating application directory..."
sudo mkdir -p /opt/fraud-detection
sudo chown $USER:$USER /opt/fraud-detection

# Navigate to application directory
cd /opt/fraud-detection

# Clone repository
echo "Cloning MLOps Fraud Detection repository..."
git clone https://github.com/Chidi-3consulting/MLOps_Fraud_Detection.git .

# Checkout the correct branch (change as needed)
BRANCH_NAME="Azure-VM-run-office"  # Change this to your desired branch
echo "Checking out branch: $BRANCH_NAME"
git checkout $BRANCH_NAME

# Run setup script
echo "Running local setup script..."
chmod +x scripts/setup-local.sh
./scripts/setup-local.sh

# Build Docker images
echo "Building Docker images..."
cd src
docker compose -f azure-docker-compose.yml build

# Start services
echo "Starting MLOps services..."
docker compose -f azure-docker-compose.yml up -d

# Initialize Airflow database
echo "Initializing Airflow database..."
docker compose -f azure-docker-compose.yml up airflow-init

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 60

# Check service status
echo "Checking service status..."
docker compose -f azure-docker-compose.yml ps

# Get VM public IP
PUBLIC_IP=$(curl -s ifconfig.me)

echo ""
echo "Setup completed successfully!"
echo ""
echo "Service URLs:"
echo "- FraudGuard: http://$PUBLIC_IP:5000"
echo "- Airflow: http://$PUBLIC_IP:8080 (airflow / airflow)"
echo "- MLflow: http://$PUBLIC_IP:5500"
echo "- MinIO Console: http://$PUBLIC_IP:9001 (minioadmin / minioadmin)"
echo "- Inference API: http://$PUBLIC_IP:8000"
echo ""
echo "Next steps:"
echo "1. Access Airflow UI and enable the fraud_detection_training DAG"
echo "2. Trigger the training DAG to train the model"
echo "3. Use FraudGuard dashboard to run inference and view metrics"
echo ""
echo "To manage services:"
echo "- Stop: docker compose -f azure-docker-compose.yml down"
echo "- Restart: docker compose -f azure-docker-compose.yml restart"
echo "- Logs: docker compose -f azure-docker-compose.yml logs -f"
