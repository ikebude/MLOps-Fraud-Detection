#!/bin/bash

# Simple Azure VM Deployment Script for MLOps Fraud Detection
# Uses default networking to avoid student subscription restrictions

set -e

# Configuration
RESOURCE_GROUP="fraud-detection-rg"
LOCATION="westus2"
VM_NAME="fraud-detection-vm"
VM_SIZE="Standard_D8s_v5"
ADMIN_USERNAME="azureuser"

echo "Creating Azure Resource Group..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

echo "Creating Virtual Machine with default networking..."
az vm create \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --image Canonical:0001-com-ubuntu-server-focal:20_04-lts-gen2:latest \
  --size $VM_SIZE \
  --admin-username $ADMIN_USERNAME \
  --generate-ssh-keys \
  --custom-data cloud-init.yaml

echo "Opening required ports..."
# Open SSH
az vm open-port \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --port 22

# Open application ports
for port in 5000 8000 5500 8080 9001; do
  az vm open-port \
    --resource-group $RESOURCE_GROUP \
    --name $VM_NAME \
    --port $port
done

echo "Getting VM Public IP..."
PUBLIC_IP=$(az vm show --resource-group $RESOURCE_GROUP --name $VM_NAME --show-details --query "publicIps" --output tsv)

echo "Deployment completed!"
echo "VM Public IP: $PUBLIC_IP"
echo "SSH command: ssh $ADMIN_USERNAME@$PUBLIC_IP"
echo ""
echo "Next steps:"
echo "1. SSH into the VM: ssh $ADMIN_USERNAME@$PUBLIC_IP"
echo "2. Run: cd /opt/fraud-detection && ./azure-setup.sh"
echo "3. Access services at: http://$PUBLIC_IP:<port>"
