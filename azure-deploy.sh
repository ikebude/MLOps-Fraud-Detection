#!/bin/bash

# Azure VM Deployment Script for MLOps Fraud Detection
# Usage: ./azure-deploy.sh

set -e

# Configuration
RESOURCE_GROUP="fraud-detection-rg"
LOCATION="westus2"
VM_NAME="fraud-detection-vm"
VM_SIZE="Standard_D8s_v5"
ADMIN_USERNAME="azureuser"
SSH_KEY_PATH="$HOME/.ssh/id_rsa.pub"

# Network settings
VNET_NAME="fraud-detection-vnet"
SUBNET_NAME="fraud-detection-subnet"
NSG_NAME="fraud-detection-nsg"

echo "Creating Azure Resource Group..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

echo "Creating Virtual Network..."
az network vnet create \
  --resource-group $RESOURCE_GROUP \
  --name $VNET_NAME \
  --address-prefix 10.0.0.0/16 \
  --subnet-name $SUBNET_NAME \
  --subnet-prefix 10.0.1.0/24

echo "Creating Network Security Group..."
az network nsg create \
  --resource-group $RESOURCE_GROUP \
  --name $NSG_NAME

# Allow SSH (22)
az network nsg rule create \
  --resource-group $RESOURCE_GROUP \
  --nsg-name $NSG_NAME \
  --name allow-ssh \
  --protocol tcp \
  --direction inbound \
  --priority 1000 \
  --source-address-prefixes '*' \
  --source-port-ranges '*' \
  --destination-address-prefixes '*' \
  --destination-port-ranges 22 \
  --access allow

# Allow HTTP (5000, 8000, 5500, 8080, 9001)
for port in 5000 8000 5500 8080 9001; do
  az network nsg rule create \
    --resource-group $RESOURCE_GROUP \
    --nsg-name $NSG_NAME \
    --name allow-http-$port \
    --protocol tcp \
    --direction inbound \
    --priority $((1000 + $port)) \
    --source-address-prefixes '*' \
    --source-port-ranges '*' \
    --destination-address-prefixes '*' \
    --destination-port-ranges $port \
    --access allow
done

echo "Creating Public IP..."
az network public-ip create \
  --resource-group $RESOURCE_GROUP \
  --name "${VM_NAME}-pip" \
  --allocation-method static \
  --sku standard

echo "Creating Network Interface..."
az network nic create \
  --resource-group $RESOURCE_GROUP \
  --name "${VM_NAME}-nic" \
  --vnet-name $VNET_NAME \
  --subnet $SUBNET_NAME \
  --network-security-group $NSG_NAME \
  --public-ip-address "${VM_NAME}-pip"

echo "Creating Virtual Machine..."
az vm create \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --computer-name $VM_NAME \
  --size $VM_SIZE \
  --admin-username $ADMIN_USERNAME \
  --ssh-key-values $SSH_KEY_PATH \
  --nics "${VM_NAME}-nic" \
  --image Canonical:0001-com-ubuntu-server-focal:20_04-lts-gen2:latest \
  --custom-data cloud-init.yaml

echo "Getting VM Public IP..."
PUBLIC_IP=$(az vm show --resource-group $RESOURCE_GROUP --name $VM_NAME --show-details --query "publicIps" --output tsv)

echo "Deployment completed!"
echo "VM Public IP: $PUBLIC_IP"
echo "SSH command: ssh $ADMIN_USERNAME@$PUBLIC_IP"
echo ""
echo "Next steps:"
echo "1. SSH into the VM: ssh $ADMIN_USERNAME@$PUBLIC_IP"
echo "2. Clone the repository and run the setup script"
echo "3. Access services at: http://$PUBLIC_IP:<port>"
