# Install ingress-nginx manually
# Run this script if you missed the ingress-nginx installation during deployment

Write-Host "=== Installing ingress-nginx ==="

# Check if helm is installed
try {
    & "C:\helm\windows-amd64\helm.exe" version | Out-Null
    Write-Host "[OK] Helm found"
    $helmCommand = "C:\helm\windows-amd64\helm.exe"
} catch {
    Write-Host "[ERROR] Helm not found. Please install Helm first."
    Write-Host "Visit: https://helm.sh/docs/intro/install/"
    exit 1
}

# Add ingress-nginx repository
Write-Host "Adding ingress-nginx repository..."
& $helmCommand repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
& $helmCommand repo update

# Install ingress-nginx
Write-Host "Installing ingress-nginx..."
& $helmCommand upgrade --install ingress-nginx ingress-nginx/ingress-nginx `
    --namespace ingress-nginx `
    --create-namespace `
    --set controller.service.type=LoadBalancer `
    --set controller.replicaCount=2

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
        Write-Host "  http://$ip/fraudguard"
        Write-Host "  http://$ip/airflow"  
        Write-Host "  http://$ip/mlflow"
        Write-Host "  http://$ip/inference"
        Write-Host "  http://$ip/flower"
    } else {
        Write-Host "[WARN] Could not get external IP. Check with: kubectl get svc -n ingress-nginx"
    }
} else {
    Write-Host "[ERROR] Failed to install ingress-nginx"
    exit 1
}
