# OCI Credentials Reference

This document provides a reference for OCI credentials needed for deployment.

## Required Credentials

### 1. OCIR (Oracle Cloud Infrastructure Registry)
- **Registry URL**: `af-johannesburg-1.ocir.io`
- **Username**: `omololadada436@gmail.com`
- **Auth Token**: `841vJ:8i}T#XEO4cjE5P`
- **Namespace**: `axjkxzqfxgqu`

### 2. Object Storage (S3-Compatible)
- **Endpoint URL**: `https://axjkxzqfxgqu.compat.objectstorage.af-johannesburg-1.oraclecloud.com`
- **Region**: `af-johannesburg-1`
- **Access Key ID**: `615ca352d47705fc18f201c0a5a9d284e0e5f661`
- **Secret Access Key**: `bqfLqk7SvGvOYUuMNZU/890K2m3a3HUzL05YZVyyZls=`
- **Bucket**: `mlops-artifacts`

### 3. Autonomous Database (ADB)
- **Connection String**: From ADB wallet (tnsnames.ora)
- **Admin User**: `admin`
- **Admin Password**: Set during ADB creation
- **Wallet Path**: `./Wallet_MLOPSDB`
- **Service Names**: 
  - `mlopsdb_high` (full service)
  - `mlopsdb_tp` (transaction processing)
  - `mlopsdb_medium` (medium workload)
  - `mlopsdb_low` (low priority)
- **Host**: `adb.af-johannesburg-1.oraclecloud.com`
- **Port**: `1522` (SSL)

### 4. Kubernetes Cluster (OKE)
- **Cluster Name**: MLOps cluster
- **Region**: af-johannesburg-1
- **Kubeconfig**: Downloaded from OCI Console

## Environment Setup

Before running deployment scripts, ensure these credentials are:
1. Set as environment variables, OR
2. Stored securely in OCI Secrets Manager, OR
3. Configured in the deployment script prompts

## Security Notes
- Never commit credentials to version control
- Use OCI Secrets Manager for production
- Rotate auth tokens regularly
- Limit IAM policies to least privilege

## Deployment Integration

The deployment script (`deploy-oci-adb-complete.ps1`) will prompt for:
1. OCIR credentials (username, auth token)
2. Object Storage credentials (access key, secret key)
3. ADB credentials (admin password, wallet path)
4. Kubernetes cluster context

Ensure all credentials are available before starting deployment.
