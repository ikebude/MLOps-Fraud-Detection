#!/bin/bash
# Azure Deployment Script for MLOps Fraud Detection
# This script builds and pushes Docker images to ACR and deploys to AKS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Configuration
ACR_NAME=${ACR_NAME:-mlopsacr12345}
ACR_REGISTRY="${ACR_NAME}.azurecr.io"
AKS_RESOURCE_GROUP=${AKS_RESOURCE_GROUP:-mlops-rg}
AKS_CLUSTER_NAME=${AKS_CLUSTER_NAME:-mlops-aks}
AKS_NAMESPACE=${AKS_NAMESPACE:-mlops}
IMAGE_PREFIX=${ACR_IMAGE_PREFIX:-fraud-detection}

echo -e "${GREEN}Starting Azure deployment...${NC}"

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}Azure CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Login to Azure (if not already logged in)
echo -e "${YELLOW}Checking Azure login...${NC}"
az account show &> /dev/null || az login

# Login to ACR
echo -e "${YELLOW}Logging in to Azure Container Registry...${NC}"
az acr login --name $ACR_NAME

# Build and push images
echo -e "${YELLOW}Building and pushing Docker images...${NC}"

# Build Airflow image
echo -e "${GREEN}Building Airflow image...${NC}"
cd src/airflow
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest .
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest
cd ../..

# Build MLflow image
echo -e "${GREEN}Building MLflow image...${NC}"
cd src/mlflow
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/mlflow:latest .
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/mlflow:latest
cd ../..

# Build Inference image
echo -e "${GREEN}Building Inference image...${NC}"
cd src/inference
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/inference:latest .
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/inference:latest
cd ../..

# Build Fraud Guard image
echo -e "${GREEN}Building Fraud Guard image...${NC}"
cd fraudguard
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/fraudguard:latest .
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/fraudguard:latest
cd ..

# Get AKS credentials
echo -e "${YELLOW}Getting AKS credentials...${NC}"
az aks get-credentials --resource-group $AKS_RESOURCE_GROUP --name $AKS_CLUSTER_NAME --overwrite-existing

# Create namespace if it doesn't exist
echo -e "${YELLOW}Creating namespace if needed...${NC}"
kubectl create namespace $AKS_NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Apply Kubernetes manifests
echo -e "${YELLOW}Applying Kubernetes manifests...${NC}"
kubectl apply -f k8s/secrets.yaml -n $AKS_NAMESPACE
kubectl apply -f k8s/mlflow.yaml -n $AKS_NAMESPACE
kubectl apply -f k8s/inference-config.yaml -n $AKS_NAMESPACE
kubectl apply -f k8s/inference.yaml -n $AKS_NAMESPACE
kubectl apply -f k8s/airflow.yaml -n $AKS_NAMESPACE

# Wait for deployments to be ready
echo -e "${YELLOW}Waiting for deployments to be ready...${NC}"
kubectl wait --for=condition=available --timeout=300s deployment/mlflow -n $AKS_NAMESPACE || true
kubectl wait --for=condition=available --timeout=300s deployment/inference -n $AKS_NAMESPACE || true

echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${YELLOW}To check status, run:${NC}"
echo "  kubectl get pods -n $AKS_NAMESPACE"
echo "  kubectl get services -n $AKS_NAMESPACE"
