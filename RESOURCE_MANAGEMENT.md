# Kubernetes Resource Management Guide

Understanding how resource requests and limits work in Kubernetes.

## Resource Requests vs Limits

### Requests
- **What it is**: The minimum amount of resources guaranteed to the pod
- **Purpose**: Used by the scheduler to decide which node can fit the pod
- **Example**: `memory: "128Mi"` means "I need at least 128Mi to run"
- **If not available**: Pod won't be scheduled (stays in Pending state)

### Limits
- **What it is**: The maximum amount of resources a pod can use
- **Purpose**: Prevents a pod from consuming all node resources
- **Example**: `memory: "256Mi"` means "I can use up to 256Mi, but no more"
- **If exceeded**: Pod gets throttled (CPU) or killed (OOMKilled for memory)

## What Happens When Pod Needs More?

### Memory (RAM)

**Scenario**: Pod requests 128Mi, limit is 256Mi, but needs 300Mi

1. **Up to 256Mi**: Pod runs normally
2. **At 256Mi**: Kubernetes starts throttling memory usage
3. **Above 256Mi**: Pod gets **OOMKilled** (Out Of Memory)
   - Pod is terminated
   - Kubernetes restarts it (if restart policy allows)
   - You'll see `CrashLoopBackOff` status

**How to fix:**
```yaml
resources:
  requests:
    memory: "256Mi"  # Increase request
  limits:
    memory: "512Mi"  # Increase limit
```

### CPU

**Scenario**: Pod requests 100m (0.1 CPU), limit is 200m, but needs 300m

1. **Up to 200m**: Pod gets full CPU time
2. **At 200m**: Kubernetes throttles CPU usage
3. **Above 200m**: Pod is throttled (slowed down), but NOT killed
   - Pod continues running but slower
   - Tasks take longer to complete
   - You'll see high CPU throttling in metrics

**How to fix:**
```yaml
resources:
  requests:
    cpu: "200m"  # Increase request
  limits:
    cpu: "500m"  # Increase limit
```

## Real-World Example

### Current Configuration (Reduced for Small Node)

```yaml
# Redis
requests: memory: 128Mi, cpu: 50m
limits:   memory: 256Mi, cpu: 100m
```

### If Redis Needs More Memory

**Symptoms you'll see:**
```bash
kubectl get pods -n mlops
# redis-xxx   0/1   OOMKilled   3   5m

kubectl logs redis-xxx -n mlops
# Error: Out of memory
```

**Solution: Increase resources**
```yaml
resources:
  requests:
    memory: "256Mi"  # Was 128Mi
    cpu: "100m"      # Was 50m
  limits:
    memory: "512Mi"  # Was 256Mi
    cpu: "200m"      # Was 100m
```

## How to Monitor Resource Usage

### Check Current Usage
```bash
# See actual resource usage
kubectl top pods -n mlops

# Example output:
# NAME                          CPU(cores)   MEMORY(bytes)
# redis-xxx                     45m          180Mi
# mlflow-xxx                    120m         420Mi
# inference-xxx                 80m          200Mi
```

### Check if Pods are Being Throttled
```bash
# Describe pod to see events
kubectl describe pod <pod-name> -n mlops

# Look for:
# - "OOMKilled" (memory limit exceeded)
# - "CPU throttling" (CPU limit exceeded)
```

## Scaling Strategies

### Option 1: Increase Resources in Manifests

Edit the YAML files and increase limits:

```yaml
# k8s/redis.yaml
resources:
  requests:
    memory: "256Mi"  # Increase from 128Mi
    cpu: "100m"      # Increase from 50m
  limits:
    memory: "512Mi"  # Increase from 256Mi
    cpu: "200m"      # Increase from 100m
```

Then apply:
```bash
kubectl apply -f k8s/redis.yaml -n mlops
```

### Option 2: Scale Your AKS Cluster

If your node is too small, add more nodes or use larger VMs:

```bash
# Scale node pool (add more nodes)
az aks scale \
  --resource-group mlops_fraud_analytics \
  --name mlops-aks-cluster \
  --node-count 3

# Or resize nodes to larger VM size
az aks nodepool update \
  --resource-group mlops_fraud_analytics \
  --cluster-name mlops-aks-cluster \
  --name nodepool1 \
  --vm-size Standard_D4s_v3  # 4 vCPUs, 16GB RAM
```

### Option 3: Use Horizontal Pod Autoscaling (HPA)

Automatically scale pods based on resource usage:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: redis-hpa
  namespace: mlops
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: redis
  minReplicas: 1
  maxReplicas: 3
  metrics:
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## Recommended Resource Sizes

### For Development/Small Clusters
```yaml
# Light services (Redis, Flower)
requests: memory: 128Mi, cpu: 50m
limits:   memory: 256Mi, cpu: 100m

# Medium services (MLflow, Inference, Fraud Guard)
requests: memory: 256Mi, cpu: 100m
limits:   memory: 512Mi, cpu: 200m

# Heavy services (Airflow)
requests: memory: 512Mi, cpu: 200m
limits:   memory: 1Gi, cpu: 500m
```

### For Production
```yaml
# Light services
requests: memory: 256Mi, cpu: 100m
limits:   memory: 512Mi, cpu: 200m

# Medium services
requests: memory: 512Mi, cpu: 200m
limits:   memory: 1Gi, cpu: 500m

# Heavy services (Airflow workers)
requests: memory: 1Gi, cpu: 500m
limits:   memory: 2Gi, cpu: 1000m
```

## Best Practices

1. **Start Small, Scale Up**: Begin with lower resources and increase as needed
2. **Monitor First**: Use `kubectl top pods` to see actual usage before adjusting
3. **Set Limits**: Always set limits to prevent one pod from consuming all resources
4. **Match Requests to Limits**: Keep requests at 50-80% of limits for headroom
5. **Watch for OOMKilled**: If pods are being killed, increase memory limits

## Quick Commands

```bash
# Check resource usage
kubectl top pods -n mlops
kubectl top nodes

# Check pod status and events
kubectl describe pod <pod-name> -n mlops

# Edit deployment resources on the fly
kubectl set resources deployment redis -n mlops \
  --requests=memory=256Mi,cpu=100m \
  --limits=memory=512Mi,cpu=200m

# View resource quotas
kubectl describe quota -n mlops
```

## Summary

- **Requests**: Minimum needed (for scheduling)
- **Limits**: Maximum allowed (prevents resource hogging)
- **If exceeded**: Memory = OOMKilled, CPU = Throttled
- **Solution**: Increase limits in YAML or scale cluster
- **Monitor**: Use `kubectl top pods` to see actual usage

---

**Remember**: It's better to start with lower resources and scale up based on actual usage than to over-provision from the start!
