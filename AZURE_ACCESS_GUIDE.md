# Azure Portal Access Guide

This guide explains how to access all MLOps Fraud Detection services deployed on Azure Kubernetes Service (AKS).

## 📋 Table of Contents

- [Finding Service Endpoints](#finding-service-endpoints)
- [Accessing Services via LoadBalancer IPs](#accessing-services-via-loadbalancer-ips)
- [Accessing Services via Port Forwarding](#accessing-services-via-port-forwarding)
- [Accessing Services via Azure Portal](#accessing-services-via-azure-portal)
- [Service URLs and Credentials](#service-urls-and-credentials)
- [Troubleshooting](#troubleshooting)

---

## Finding Service Endpoints

### Method 1: Using kubectl (Recommended)

```powershell
# Get all services with their external IPs
kubectl get svc -n mlops

# Get specific service IP
kubectl get svc airflow-webserver -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc fraudguard -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc mlflow -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc inference -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get svc flower -n mlops -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

### Method 2: Using Azure Portal

1. **Navigate to your AKS cluster:**
   - Go to [Azure Portal](https://portal.azure.com)
   - Search for your resource group: `mlops_fraud_analytics`
   - Click on your AKS cluster: `mlops-aks-cluster`

2. **Find Services:**
   - In the left menu, scroll down to **"Workloads"** section
   - Click on **"Services and ingresses"**
   - You'll see all services listed with their types and external IPs

3. **View Service Details:**
   - Click on any service (e.g., `airflow-webserver`)
   - The **"Overview"** tab shows the external IP address
   - The **"YAML"** tab shows full service configuration

---

## Accessing Services via LoadBalancer IPs

Once LoadBalancer IPs are assigned (may take 5-10 minutes), you can access services directly:

### Available Services

| Service | Port | URL Format | Current Status |
|---------|------|------------|----------------|
| **MLflow** | 5000 | `http://172.175.191.31:5000` | ✅ Available |
| **Inference API** | 8000 | `http://68.220.239.80:8000` | ✅ Available |
| **Airflow** | 8080 | `http://<airflow-ip>:8080` | ⏳ Pending (use port-forward) |
| **Fraud Guard** | 5000 | `http://<fraudguard-ip>:5000` | ⏳ Pending (use port-forward) |
| **Flower** | 5555 | `http://<flower-ip>:5555` | ⏳ Pending (use port-forward) |

**Note:** MLflow and Inference API have LoadBalancer IPs assigned. Airflow, Fraud Guard, and Flower are still waiting for IPs. Use port forwarding for immediate access.

### Check if IPs are Ready

```powershell
# Watch for IPs to be assigned
kubectl get svc -n mlops -w

# Check specific service
kubectl get svc airflow-webserver -n mlops
```

**Note:** If you see `<pending>` in the EXTERNAL-IP column, the LoadBalancer is still being provisioned. Wait a few minutes and check again.

---

## Accessing Services via Port Forwarding

If LoadBalancer IPs are not yet assigned, you can use port forwarding for immediate access:

### Port Forward Commands

```powershell
# Airflow (in one terminal)
kubectl port-forward -n mlops svc/airflow-webserver 8080:8080

# Fraud Guard (in another terminal)
kubectl port-forward -n mlops svc/fraudguard 5000:5000

# MLflow (in another terminal)
kubectl port-forward -n mlops svc/mlflow 5000:5000

# Inference API (in another terminal)
kubectl port-forward -n mlops svc/inference 8000:8000

# Flower (in another terminal)
kubectl port-forward -n mlops svc/flower 5555:5555
```

### Access via Localhost

Once port forwarding is active, access services at:
- **Airflow**: http://localhost:8080
- **Fraud Guard**: http://localhost:5000
- **MLflow**: http://localhost:5000
- **Inference API**: http://localhost:8000
- **Flower**: http://localhost:5555

**Note:** Port forwarding runs in the foreground. Keep the terminal windows open. Press `Ctrl+C` to stop.

---

## Accessing Services via Azure Portal

### Option 1: Using Azure Cloud Shell

1. **Open Cloud Shell:**
   - Click the Cloud Shell icon (```>_```) in the Azure Portal top bar
   - Choose **PowerShell** or **Bash**

2. **Connect to AKS:**
   ```powershell
   # Set variables
   $resourceGroup = "mlops_fraud_analytics"
   $aksCluster = "mlops-aks-cluster"
   
   # Get AKS credentials
   az aks get-credentials --resource-group $resourceGroup --name $aksCluster
   
   # Get service IPs
   kubectl get svc -n mlops
   ```

3. **Use Port Forwarding:**
   - Cloud Shell supports port forwarding
   - Run the port-forward commands as shown above
   - Access services via the Cloud Shell web preview

### Option 2: Using Azure Portal Kubernetes View

1. **Navigate to AKS Cluster:**
   - Go to Azure Portal → Resource Groups → `mlops_fraud_analytics`
   - Click on `mlops-aks-cluster`

2. **Access Kubernetes Resources:**
   - In the left menu, under **"Kubernetes resources"**, click **"Services and ingresses"**
   - You'll see all services with their external IPs
   - Click on a service to view details

3. **View Pod Logs:**
   - Go to **"Workloads"** → **"Pods"**
   - Click on any pod to view logs and details
   - Useful for troubleshooting

### Option 3: Using Azure Bastion (if configured)

If you have Azure Bastion configured:
1. Connect to a VM in the same VNet
2. Install `kubectl` and `az` CLI
3. Connect to AKS and use port forwarding

---

## Service URLs and Credentials

### Airflow Web UI

- **URL**: `http://<airflow-ip>:8080` or `http://localhost:8080` (port-forward)
- **Default Username**: `airflow`
- **Default Password**: `airflow`
- **⚠️ Important**: Change these credentials for production!

**To create a new user:**
```powershell
kubectl exec -it deployment/airflow-webserver -n mlops -- airflow users create \
  --username admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com \
  --password YourSecurePassword
```

### MLflow Tracking UI

- **URL**: `http://<mlflow-ip>:5000` or `http://localhost:5000` (port-forward)
- **Authentication**: None (add authentication for production)
- **Features**: Model registry, experiment tracking, artifact storage

### Fraud Guard Dashboard

- **URL**: `http://<fraudguard-ip>:5000` or `http://localhost:5000` (port-forward)
- **Authentication**: None (add authentication for production)
- **Features**: 
  - Real-time fraud alerts
  - Transaction monitoring
  - System health dashboard
  - Inference triggering

### Inference API

- **URL**: `http://<inference-ip>:8000` or `http://localhost:8000` (port-forward)
- **Endpoints**:
  - `GET /health` - Health check
  - `POST /inference/run` - Run inference
  - `GET /inference/results` - Get results
  - `GET /inference/stats` - Get statistics

**Example:**
```powershell
# Health check
curl http://<inference-ip>:8000/health

# Run inference
curl -X POST http://<inference-ip>:8000/inference/run \
  -H "Content-Type: application/json" \
  -d '{"max_records": 1000}'
```

### Flower (Celery Monitoring)

- **URL**: `http://<flower-ip>:5555` or `http://localhost:5555` (port-forward)
- **Authentication**: None (add authentication for production)
- **Features**: Monitor Celery workers, tasks, and queues

---

## Troubleshooting

### LoadBalancer IP Stuck on `<pending>`

**Possible causes:**
1. Azure is still provisioning the LoadBalancer (wait 5-10 minutes)
2. Insufficient quota for public IPs
3. Network configuration issues

**Solutions:**
```powershell
# Check service events
kubectl describe svc airflow-webserver -n mlops

# Check for quota issues in Azure Portal
# Go to: Subscriptions → Your Subscription → Usage + quotas
# Search for "Public IP addresses"

# Use port forwarding as temporary workaround
kubectl port-forward -n mlops svc/airflow-webserver 8080:8080
```

### Cannot Connect to Service

**Check:**
1. Service is running: `kubectl get pods -n mlops`
2. Service exists: `kubectl get svc -n mlops`
3. External IP is assigned: `kubectl get svc <service-name> -n mlops`
4. Firewall rules allow traffic on the port

**Test connectivity:**
```powershell
# From your local machine
Test-NetConnection -ComputerName <external-ip> -Port 8080

# From within cluster
kubectl run -it --rm debug --image=busybox --restart=Never -n mlops -- wget -O- http://<service-name>:<port>
```

### Port Forwarding Not Working

**Check:**
1. `kubectl` is configured correctly: `kubectl cluster-info`
2. You have access to the namespace: `kubectl get pods -n mlops`
3. Service exists: `kubectl get svc <service-name> -n mlops`
4. Port is not already in use locally

**Try different local port:**
```powershell
kubectl port-forward -n mlops svc/airflow-webserver 18080:8080
# Then access at http://localhost:18080
```

### Service Shows as "Pending" in Azure Portal

This is normal during initial deployment. Wait 5-10 minutes for Azure to provision the LoadBalancer and assign a public IP.

**Check status:**
```powershell
# Watch service status
kubectl get svc -n mlops -w

# Check service events
kubectl describe svc airflow-webserver -n mlops
```

---

## Quick Reference Commands

```powershell
# Get all service IPs at once
kubectl get svc -n mlops -o custom-columns=NAME:.metadata.name,EXTERNAL-IP:.status.loadBalancer.ingress[0].ip,PORT:.spec.ports[0].port

# Port forward all services (run in separate terminals)
kubectl port-forward -n mlops svc/airflow-webserver 8080:8080
kubectl port-forward -n mlops svc/fraudguard 5000:5000
kubectl port-forward -n mlops svc/mlflow 5000:5000
kubectl port-forward -n mlops svc/inference 8000:8000
kubectl port-forward -n mlops svc/flower 5555:5555

# Check pod status
kubectl get pods -n mlops

# View service details
kubectl describe svc <service-name> -n mlops

# View pod logs
kubectl logs <pod-name> -n mlops
```

---

## Security Notes

⚠️ **Important Security Considerations:**

1. **Change Default Credentials**: Airflow default credentials (`airflow`/`airflow`) should be changed immediately
2. **Add Authentication**: MLflow, Fraud Guard, and Flower currently have no authentication
3. **Use HTTPS**: Configure TLS/SSL certificates for production
4. **Network Security**: Consider using Azure Private Link or VPN for internal access
5. **Firewall Rules**: Restrict access to specific IP ranges if possible
6. **Secrets Management**: Use Azure Key Vault for sensitive credentials

---

## Next Steps

1. **Access Airflow UI** and trigger the `fraud_detection_training` DAG
2. **Access Fraud Guard** to monitor fraud detection
3. **Access MLflow** to view model experiments and versions
4. **Access Flower** to monitor Celery workers
5. **Test Inference API** to run fraud detection predictions

For more information, see:
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Full deployment guide
- [UI_ENDPOINTS.md](./UI_ENDPOINTS.md) - API endpoint documentation
- [AZURE_DEPLOYMENT.md](./AZURE_DEPLOYMENT.md) - Azure-specific deployment steps
