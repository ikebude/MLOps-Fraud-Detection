# OCI OKE Deployment (Fraud Detection MLOps)

This repo has been adapted to run on **Oracle Cloud Infrastructure (OCI)** using **OKE (Oracle Kubernetes Engine)**, **OCIR (Oracle Container Registry)**, **OCI Object Storage (S3-compatible endpoint)**, and an **in-cluster PostgreSQL** backend for Airflow + MLflow.

## What you need (inputs)

- OKE cluster access (kubeconfig)
- OCIR registry info
  - Region: `af-johannesburg-1`
  - Registry: `af-johannesburg-1.ocir.io`
  - Namespace: `axjkxzqfxgqu`
  - Your OCIR username (OCI username/email)
  - An OCI **Auth Token** (used as Docker password)
- OCI Object Storage S3 credentials
  - S3 Access Key ID
  - S3 Secret Access Key
  - Bucket: `mlops-artifacts`
  - S3 Endpoint:
    - `https://axjkxzqfxgqu.compat.objectstorage.af-johannesburg-1.oraclecloud.com`
- PostgreSQL password (for the in-cluster `postgres` user)

## Deployment (Windows / PowerShell)

1. Ensure you have these tools installed:
   - `kubectl`
   - `docker`
   - (optional) `oci` CLI (only if you want the script to generate kubeconfig)
   - (optional) `helm` (only if you want the script to install ingress-nginx)

2. Run the deployment script:

   - `scripts/deploy-oci-complete.ps1`

   The script will:
   - Build and push images to OCIR
   - Create/update these Kubernetes secrets in namespace `mlops`:
     - `ocir-secret` (image pull secret)
     - `postgres-credentials`
     - `object-storage-credentials`
   - Deploy Postgres, Redis, MLflow, Airflow, Inference, FraudGuard, Flower
   - Apply Ingress rules from `k8s/ingress.yaml`

## Services (via ingress)

Once ingress-nginx has a public IP, the default paths are:

- `/fraudguard`
- `/flower`
- `/mlflow`
- `/airflow`
- `/inference`

Get the external IP:

- `kubectl get svc -n ingress-nginx`

## Notes

- Kubernetes manifests do **not** contain secrets; credentials are created at deploy-time by the script.
- Airflow + MLflow use **in-cluster Postgres** (`Service: postgres`) rather than OCI ADB.
