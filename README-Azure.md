# Azure VM Deployment Guide - MLOps Fraud Detection

## Overview

This guide helps you deploy the MLOps Fraud Detection solution on an Azure Virtual Machine with all services running via Docker Compose.

## Prerequisites

- Azure CLI installed and configured
- SSH key pair for VM access
- Azure subscription with appropriate permissions

## Quick Deployment

### 1. Deploy Azure VM

```bash
# Make the deployment script executable
chmod +x azure-deploy.sh

# Run the deployment
./azure-deploy.sh
```

This creates:
- Resource Group: `fraud-detection-rg`
- VM Size: `Standard_D8s_v5` (8 vCPUs, 32GB RAM)
- Network Security Group with required ports open
- Ubuntu 20.04 with Docker pre-installed

### 2. SSH into the VM

```bash
# Get the public IP from the deployment output
ssh azureuser@<PUBLIC_IP>
```

### 3. Setup Application

```bash
# Clone and setup the application
cd /opt/fraud-detection
git clone <YOUR_REPOSITORY_URL> .
chmod +x azure-setup.sh
./azure-setup.sh
```

## Service Access

Once deployed, access services at:

| Service | URL | Credentials |
|---------|-----|-------------|
| FraudGuard Dashboard | `http://<PUBLIC_IP>:5000` | - |
| Airflow Web UI | `http://<PUBLIC_IP>:8080` | airflow / airflow |
| MLflow Tracking | `http://<PUBLIC_IP>:5500` | - |
| MinIO Console | `http://<PUBLIC_IP>:9001` | minioadmin / minioadmin |
| Inference API | `http://<PUBLIC_IP>:8000` | - |

## Resource Requirements

### Minimum VM Configuration
- **vCPUs**: 8 (for concurrent Airflow workers)
- **RAM**: 32GB (Docker requires 8GB+, recommend 32GB for production)
- **Storage**: 200GB Premium SSD
- **Network**: Standard bandwidth

### Estimated Monthly Cost
- **VM**: $150-300/month (depending on region)
- **Storage**: $20-50/month
- **Network**: $10-30/month
- **Total**: ~$200-400/month

## Configuration

### Environment Variables
Edit `/opt/fraud-detection/src/.env` to customize:
- `FRAUD_API_URL`: Data source URL
- `FRAUD_API_MAX_RECORDS`: Training data limit
- Database credentials
- MLflow settings

### Scaling
- **Airflow Workers**: Modify `replicas` in `azure-docker-compose.yml`
- **Memory**: Adjust `deploy.resources.limits.memory` per service
- **Storage**: Expand VM disk size as needed

## Monitoring

### Health Checks
```bash
# Check all services
docker compose -f azure-docker-compose.yml ps

# View logs
docker compose -f azure-docker-compose.yml logs -f

# Service-specific logs
docker compose -f azure-docker-compose.yml logs -f airflow-webserver
```

### Performance Monitoring
- Use `htop` for system resources
- Monitor Docker container stats: `docker stats`
- Check service health endpoints

## Security Considerations

### Network Security
- NSG configured to allow only necessary ports
- Consider VPN for additional security
- Use Azure Firewall for advanced protection

### Data Protection
- Regular backups of PostgreSQL and MinIO
- Enable Azure Backup for VM
- Use Azure Key Vault for secrets

### Access Control
- Change default passwords
- Use Azure AD for authentication
- Implement role-based access control

## Backup Strategy

### Automated Backup Script
```bash
#!/bin/bash
# backup-azure.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker exec postgres pg_dump -U airflow airflow > $BACKUP_DIR/postgres_$DATE.sql

# Backup MinIO data
docker run --rm -v minio_data:/data -v $BACKUP_DIR:/backup alpine tar czf /backup/minio_$DATE.tar.gz -C /data .

# Backup configuration
tar czf $BACKUP_DIR/config_$DATE.tar.gz /opt/fraud-detection/src/.env /opt/fraud-detection/src/config.yaml

echo "Backup completed: $BACKUP_DIR"
```

## Troubleshooting

### Common Issues

1. **Services not starting**
   ```bash
   # Check Docker logs
   docker compose -f azure-docker-compose.yml logs
   
   # Check system resources
   free -h
   df -h
   ```

2. **Memory issues**
   ```bash
   # Reduce FRAUD_API_MAX_RECORDS in .env
   # Scale down Airflow workers
   # Increase VM size if needed
   ```

3. **Network connectivity**
   ```bash
   # Check NSG rules
   az network nsg rule list --resource-group fraud-detection-rg --nsg-name fraud-detection-nsg
   
   # Test port connectivity
   telnet <PUBLIC_IP> <PORT>
   ```

### Performance Optimization

1. **Database tuning**
   - Adjust PostgreSQL connection pools
   - Optimize queries and indexes

2. **Docker optimization**
   - Use Docker image caching
   - Clean up unused images: `docker system prune`

3. **Resource allocation**
   - Monitor memory usage per container
   - Adjust resource limits in docker-compose.yml

## Maintenance

### Regular Tasks
- Update Docker images monthly
- Monitor disk usage and clean up logs
- Review and rotate credentials
- Apply security patches

### Updates
```bash
# Pull latest code
cd /opt/fraud-detection
git pull

# Rebuild and restart services
cd src
docker compose -f azure-docker-compose.yml build
docker compose -f azure-docker-compose.yml up -d
```

## Support

For issues:
1. Check Azure VM status in Azure Portal
2. Review service logs
3. Verify network connectivity
4. Check resource utilization

## Cost Optimization

- Use Azure Reserved Instances for long-term deployments
- Enable auto-shutdown for non-production environments
- Monitor and optimize storage usage
- Consider Azure Spot VMs for development/testing
