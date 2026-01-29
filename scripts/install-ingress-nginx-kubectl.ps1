# Install ingress-nginx using kubectl (alternative to Helm)
# This bypasses network issues with Helm chart downloads

Write-Host "=== Installing ingress-nginx via kubectl ==="

# Create namespace
Write-Host "Creating ingress-nginx namespace..."
kubectl create namespace ingress-nginx --dry-run=client -o yaml | kubectl apply -f -

# Apply mandatory resources
Write-Host "Applying ingress-nginx mandatory resources..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.0-beta.0/deploy/static/provider/cloud/deploy.yaml

# Wait for deployment
Write-Host "Waiting for ingress-nginx controller to be ready..."
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=300s

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] ingress-nginx installed successfully"
    
    # Wait for external IP
    Write-Host "Waiting for LoadBalancer external IP..."
    $ip = ""
    $attempts = 0
    $maxAttempts = 30
    
    while ($ip -eq "" -and $attempts -lt $maxAttempts) {
        $ip = kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>$null
        if ($ip -eq "") {
            Write-Host "Attempt $($attempts + 1)/$maxAttempts - Waiting for IP..."
            Start-Sleep 10
            $attempts++
        }
    }
    
    if ($ip -ne "") {
        Write-Host "[OK] LoadBalancer IP: $ip"
        Write-Host "You can now access services via:"
        Write-Host "  FraudGuard: http://$ip/fraudguard"
        Write-Host "  Airflow:   http://$ip/airflow"  
        Write-Host "  MLflow:    http://$ip/mlflow"
        Write-Host "  Inference: http://$ip/inference"
        Write-Host "  Flower:    http://$ip/flower"
    } else {
        Write-Host "[WARN] Could not get external IP. Check with: kubectl get svc -n ingress-nginx"
    }
} else {
    Write-Host "[ERROR] Failed to install ingress-nginx"
    exit 1
}
