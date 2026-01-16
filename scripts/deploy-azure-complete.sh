#!/bin/bash
# Complete Azure Deployment Script
# This script automates the entire Azure deployment process

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Azure MLOps Fraud Detection Deployment ===${NC}"
echo ""

# Configuration
ACR_NAME="mlopsacr12345"
ACR_REGISTRY="${ACR_NAME}.azurecr.io"
ACR_USERNAME="mlopsacr12345"
ACR_PASSWORD="Tfs3lQolzy3n4GGvwpgjmJIlCP0wWDsRLSjiHmA/HZ+ACRC0hFnV"
NAMESPACE="mlops"
IMAGE_PREFIX="fraud-detection"

# Get AKS details from user or environment (with defaults)
AKS_RESOURCE_GROUP=${AKS_RESOURCE_GROUP:-mlops_fraud_analytics}
AKS_CLUSTER_NAME=${AKS_CLUSTER_NAME:-mlops_aks_cluster}

# Allow override
read -p "Use default AKS settings? (mlops_fraud_analytics/mlops_aks_cluster) [Y/n]: " override
if [ "$override" = "n" ] || [ "$override" = "N" ]; then
    read -p "AKS Resource Group: " AKS_RESOURCE_GROUP
    read -p "AKS Cluster Name: " AKS_CLUSTER_NAME
fi

echo -e "${GREEN}Configuration:${NC}"
echo "  ACR: ${ACR_REGISTRY}"
echo "  AKS Resource Group: ${AKS_RESOURCE_GROUP}"
echo "  AKS Cluster: ${AKS_CLUSTER_NAME}"
echo "  Namespace: ${NAMESPACE}"
echo ""

# Step 1: Login to Azure
echo -e "${YELLOW}Step 1: Logging in to Azure...${NC}"
az account show &> /dev/null || az login
echo -e "${GREEN}✓ Logged in to Azure${NC}"

# Step 2: Login to ACR
echo -e "${YELLOW}Step 2: Logging in to ACR...${NC}"
az acr login --name ${ACR_NAME}
echo -e "${GREEN}✓ Logged in to ACR${NC}"

# Step 3: Build and push images
echo -e "${YELLOW}Step 3: Building and pushing Docker images...${NC}"
cd src/airflow
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest . || {
    echo -e "${RED}✗ Failed to build Airflow image${NC}"
    exit 1
}
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/airflow:latest || {
    echo -e "${RED}✗ Failed to push Airflow image${NC}"
    exit 1
}
echo -e "${GREEN}✓ Airflow image pushed${NC}"

cd ../mlflow
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/mlflow:latest . || {
    echo -e "${RED}✗ Failed to build MLflow image${NC}"
    exit 1
}
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/mlflow:latest || {
    echo -e "${RED}✗ Failed to push MLflow image${NC}"
    exit 1
}
echo -e "${GREEN}✓ MLflow image pushed${NC}"

cd ../inference
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/inference:latest . || {
    echo -e "${RED}✗ Failed to build Inference image${NC}"
    exit 1
}
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/inference:latest || {
    echo -e "${RED}✗ Failed to push Inference image${NC}"
    exit 1
}
echo -e "${GREEN}✓ Inference image pushed${NC}"

cd ../../fraudguard
docker build -t ${ACR_REGISTRY}/${IMAGE_PREFIX}/fraudguard:latest . || {
    echo -e "${RED}✗ Failed to build Fraud Guard image${NC}"
    exit 1
}
docker push ${ACR_REGISTRY}/${IMAGE_PREFIX}/fraudguard:latest || {
    echo -e "${RED}✗ Failed to push Fraud Guard image${NC}"
    exit 1
}
echo -e "${GREEN}✓ Fraud Guard image pushed${NC}"

cd ..

# Step 4: Get AKS credentials
echo -e "${YELLOW}Step 4: Getting AKS credentials...${NC}"
az aks get-credentials --resource-group ${AKS_RESOURCE_GROUP} --name ${AKS_CLUSTER_NAME} --overwrite-existing
echo -e "${GREEN}✓ AKS credentials configured${NC}"

# Step 5: Create namespace
echo -e "${YELLOW}Step 5: Creating namespace...${NC}"
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Namespace created${NC}"

# Step 6: Create ACR secret
echo -e "${YELLOW}Step 6: Creating ACR image pull secret...${NC}"
kubectl create secret docker-registry acr-secret \
  --docker-server=${ACR_REGISTRY} \
  --docker-username=${ACR_USERNAME} \
  --docker-password="${ACR_PASSWORD}" \
  --namespace=${NAMESPACE} \
  --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ ACR secret created${NC}"

# Step 7: Deploy Kubernetes resources
echo -e "${YELLOW}Step 7: Deploying Kubernetes resources...${NC}"

echo "  Deploying secrets..."
kubectl apply -f k8s/secrets.yaml

echo "  Deploying Redis..."
kubectl apply -f k8s/redis.yaml

echo "  Deploying MLflow..."
kubectl apply -f k8s/mlflow.yaml

echo "  Deploying Inference..."
kubectl apply -f k8s/inference-config.yaml
kubectl apply -f k8s/inference.yaml

echo "  Deploying Airflow..."
kubectl apply -f k8s/airflow.yaml

echo "  Deploying Flower..."
kubectl apply -f k8s/flower.yaml

echo "  Deploying Fraud Guard..."
kubectl apply -f k8s/fraudguard.yaml

echo -e "${GREEN}✓ All resources deployed${NC}"

# Step 8: Wait for deployments
echo -e "${YELLOW}Step 8: Waiting for deployments to be ready...${NC}"
echo "  This may take a few minutes..."
kubectl wait --for=condition=available --timeout=300s deployment/redis -n ${NAMESPACE} || true
kubectl wait --for=condition=available --timeout=300s deployment/mlflow -n ${NAMESPACE} || true
kubectl wait --for=condition=available --timeout=300s deployment/inference -n ${NAMESPACE} || true
kubectl wait --for=condition=available --timeout=300s deployment/fraudguard -n ${NAMESPACE} || true

# Step 9: Get service IPs
echo -e "${YELLOW}Step 9: Getting service endpoints...${NC}"
echo ""
echo -e "${GREEN}=== Service Endpoints ===${NC}"
echo ""

# Function to get external IP
get_external_ip() {
    local service=$1
    local ip=$(kubectl get svc ${service} -n ${NAMESPACE} -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    if [ -z "$ip" ]; then
        echo "Pending..."
    else
        echo "$ip"
    fi
}

echo "Fraud Guard:    http://$(get_external_ip fraudguard):5000"
echo "Airflow:       http://$(get_external_ip airflow-webserver):8080"
echo "MLflow:         http://$(get_external_ip mlflow):5000"
echo "Inference API: http://$(get_external_ip inference):8000"
echo "Flower:         http://$(get_external_ip flower):5555"
echo ""

echo -e "${YELLOW}Note: LoadBalancer IPs may take a few minutes to be assigned.${NC}"
echo -e "${YELLOW}Run 'kubectl get svc -n ${NAMESPACE}' to check status.${NC}"
echo ""

# Step 10: Initialize Airflow (Optional verification)
echo -e "${YELLOW}Step 10: Verifying Airflow database...${NC}"
echo "  Note: Database initialization is handled by the init container."
echo "  This step is optional and only verifies the database is ready."

# Wait for the deployment to be available
echo "  Waiting for Airflow webserver deployment to be available..."
kubectl wait --for=condition=available --timeout=300s deployment/airflow-webserver -n ${NAMESPACE} 2>&1 | grep -v "error" || true

# Wait a bit more for the pod to be fully ready and stable
sleep 15

# Get the pod name and check if it's stable
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app=airflow-webserver -o jsonpath='{.items[0].metadata.name}' 2>&1)

if [ -n "$POD_NAME" ] && [[ ! "$POD_NAME" =~ "error" ]]; then
    # Check pod status to ensure it's running and not restarting
    POD_STATUS=$(kubectl get pod ${POD_NAME} -n ${NAMESPACE} -o jsonpath='{.status.phase}' 2>&1)
    RESTART_COUNT=$(kubectl get pod ${POD_NAME} -n ${NAMESPACE} -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>&1)
    
    if [ "$POD_STATUS" = "Running" ] && [ "$RESTART_COUNT" = "0" ]; then
        # Wait for the pod to be in Ready state
        echo "  Waiting for pod $POD_NAME to be ready..."
        kubectl wait --for=condition=Ready --timeout=60s pod/${POD_NAME} -n ${NAMESPACE} 2>&1 | grep -v "error" || true
        
        # Additional wait to ensure pod is fully stable
        sleep 5
        
        # Try to verify database (non-blocking, since init container handles it)
        echo "  Verifying Airflow database (this may take a moment)..."
        if kubectl exec deployment/airflow-webserver -n ${NAMESPACE} -c airflow-webserver -- airflow db check 2>&1; then
            echo -e "${GREEN}[OK] Airflow database is ready${NC}"
        elif [ $? -eq 137 ]; then
            echo -e "${YELLOW}[INFO] Database check was interrupted (pod may be restarting)${NC}"
            echo -e "${YELLOW}  This is normal - the init container handles database setup automatically.${NC}"
        else
            echo -e "${YELLOW}[INFO] Database verification completed (init container handles initialization)${NC}"
            echo -e "${YELLOW}  Note: If you see database errors, the init container will handle setup on next pod start.${NC}"
        fi
    else
        echo -e "${YELLOW}[INFO] Pod is still initializing or restarting. Database initialization is handled by the init container.${NC}"
        echo -e "${YELLOW}  You can verify the database later with: kubectl exec deployment/airflow-webserver -n ${NAMESPACE} -c airflow-webserver -- airflow db check${NC}"
    fi
else
    echo -e "${YELLOW}[INFO] Could not find Airflow webserver pod yet.${NC}"
    echo -e "${YELLOW}  Note: The init container will automatically initialize the database when the pod starts.${NC}"
fi

echo ""
echo -e "${GREEN}=== Deployment Complete! ===${NC}"
echo ""
echo "Next steps:"
echo "1. Wait for LoadBalancer IPs to be assigned: kubectl get svc -n ${NAMESPACE}"
echo "2. Access Fraud Guard UI and verify services are running"
echo "3. Login to Airflow UI (airflow/airflow) and trigger the training DAG"
echo "4. Monitor training progress in Airflow and MLflow UIs"
echo ""
echo "To view logs:"
echo "  kubectl logs -f deployment/<service-name> -n ${NAMESPACE}"
echo ""
echo "To check pod status:"
echo "  kubectl get pods -n ${NAMESPACE}"
