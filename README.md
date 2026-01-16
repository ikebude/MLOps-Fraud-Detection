# MLOps Fraud Detection - End-to-End Solution

A production-grade MLOps solution for fraud detection that includes data ingestion, model training, model storage, real-time inference, and a web dashboard for client IT teams.

## 🎯 Overview

This solution provides:

- **Automated Training Pipeline**: Airflow DAGs for scheduled model training
- **Model Registry**: MLflow for experiment tracking and model versioning
- **Real-time Inference**: REST API service for fraud detection
- **Fraud Guard Dashboard**: Web UI for monitoring and managing fraud detection
- **Azure Ready**: Full support for deployment to Azure Kubernetes Service (AKS) and Azure Container Registry (ACR)

## 🏗️ Architecture

```
┌─────────────────┐
│  Fraud API      │
│  (Data Source)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   Airflow       │────▶│   Training   │────▶│   MLflow    │
│   (Orchestrator)│     │   Pipeline   │     │  (Registry) │
└─────────────────┘     └──────────────┘     └──────┬──────┘
                                                      │
                                                      ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Fraud Guard    │────▶│  Inference   │────▶│   MinIO     │
│  (Web UI)       │     │   Service    │     │  (Storage)  │
└─────────────────┘     └──────────────┘     └─────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker Compose v2+
- 8GB+ RAM allocated to Docker
- Git

### Local Development

1. **Clone and setup**
   ```bash
   git clone <repository-url>
   cd MLOps_Fraud_Detection
   
   # Run setup script
   chmod +x scripts/setup-local.sh
   ./scripts/setup-local.sh
   ```

2. **Configure environment**
   ```bash
   cd src
   # Edit .env file (copy from .env.example if needed)
   # Set FRAUD_API_URL and other required variables
   ```

3. **Build and start**
   ```bash
   docker compose build
   docker compose up -d
   ```

4. **Access services**
   - **Fraud Guard**: http://localhost:5000
   - **Airflow**: http://localhost:8080 (airflow/airflow)
   - **MLflow**: http://localhost:5500
   - **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
   - **Inference API**: http://localhost:8000
   - **Flower (Celery UI)**: http://localhost:5555 (if enabled with `docker compose --profile flower up`)

5. **Run training**
   - Open Airflow UI → Enable `fraud_detection_training` DAG → Trigger run

## 📁 Project Structure

```
MLOps_Fraud_Detection/
├── fraudguard/              # Fraud Guard web application
│   ├── app.py              # Flask application
│   ├── Dockerfile          # Container definition
│   ├── templates/          # HTML templates
│   └── static/             # CSS, JS, images
├── src/
│   ├── airflow/            # Airflow configuration
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── mlflow/             # MLflow server
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── inference/          # Inference service
│   │   ├── Dockerfile
│   │   ├── main.py         # Inference logic
│   │   ├── api_server.py   # REST API server
│   │   └── requirements.txt
│   ├── dags/               # Airflow DAGs
│   │   └── fraud_detection_training_dag.py
│   ├── plugins/            # Airflow plugins
│   ├── utils/              # Utility functions
│   ├── models/             # Trained models (mounted volume)
│   ├── config.yaml         # Configuration file
│   └── docker-compose.yml  # Docker Compose configuration
├── k8s/                    # Kubernetes manifests for Azure
├── scripts/                # Deployment scripts
│   ├── setup-local.sh
│   ├── build-images.sh
│   └── deploy-to-azure.sh
├── .env.example            # Environment variables template
└── README.md              # This file
```

## 🔧 Configuration

### Environment Variables

Key environment variables (see `.env.example` for complete list):

- `FRAUD_API_URL`: API endpoint for transaction data
- `FRAUD_API_MAX_RECORDS`: Max records for training (default: 100000)
- `MLFLOW_TRACKING_URI`: MLflow server URL
- `INFERENCE_SERVICE_URL`: Inference API URL
- `POSTGRES_*`: Database configuration
- `MINIO_*`: Object storage configuration

### Memory Configuration

Adjust `FRAUD_API_MAX_RECORDS` based on available memory:

- **50k records**: ~1GB peak, 2 min training, fits 2GB workers
- **100k records**: ~2GB peak, 4 min training, fits 3GB workers  
- **150k records**: ~3GB peak, 8 min training, requires 4GB+ workers

## 🌐 Azure Deployment

### Prerequisites

- Azure CLI installed and configured
- Azure subscription
- kubectl installed

### Quick Deploy

```bash
# 1. Create Azure resources (one-time setup)
az group create --name mlops-rg --location eastus
az acr create --resource-group mlops-rg --name mlopsacr12345 --sku Basic
az aks create --resource-group mlops-rg --name mlops-aks --node-count 3 --attach-acr mlopsacr12345

# 2. Configure .env with Azure values
# Update ACR_NAME, AKS_RESOURCE_GROUP, AKS_CLUSTER_NAME

# 3. Deploy
chmod +x scripts/deploy-to-azure.sh
./scripts/deploy-to-azure.sh
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

For Azure deployment, see [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md).

For all UI endpoints reference, see [UI_ENDPOINTS.md](UI_ENDPOINTS.md).

## 📊 Usage

### Training a Model

1. **Via Airflow UI**:
   - Navigate to http://localhost:8080
   - Find `fraud_detection_training` DAG
   - Enable and trigger manually or wait for schedule

2. **Via API**:
   ```bash
   curl -X POST http://localhost:8000/inference/run \
     -H "Content-Type: application/json" \
     -d '{"max_records": 10000}'
   ```

### Running Inference

1. **Via Fraud Guard UI**:
   - Navigate to http://localhost:5000
   - Click "Run Inference" or use API endpoints

2. **Via REST API**:
   ```bash
   # Run inference
   curl -X POST http://localhost:8000/inference/run \
     -H "Content-Type: application/json" \
     -d '{"max_records": 1000}'
   
   # Get results
   curl http://localhost:8000/inference/results
   
   # Get statistics
   curl http://localhost:8000/inference/stats
   ```

### Monitoring

- **Fraud Guard Dashboard**: Real-time fraud detection metrics
- **MLflow UI**: Model experiments and versions
- **Airflow UI**: Pipeline execution status
- **MinIO Console**: Artifact storage

## 🔍 API Endpoints

### Inference Service (`http://localhost:8000`)

- `GET /health` - Health check
- `POST /inference/run` - Run inference on transactions
- `GET /inference/results` - Get latest inference results
- `GET /inference/stats` - Get inference statistics

### Fraud Guard (`http://localhost:5000`)

- `GET /` - Dashboard
- `GET /api/health` - Service health check
- `POST /api/inference/run` - Trigger inference
- `GET /api/inference/results` - Get inference results

## 🛠️ Development

### Building Images

```bash
# Build all images
./scripts/build-images.sh

# Build specific service
cd src/airflow && docker build -t fraud-detection/airflow:latest .
```

### Running Tests Locally

```bash
# Start services
cd src && docker compose up -d

# Run inference test
curl -X POST http://localhost:8000/inference/run -d '{"max_records": 100}'

# Check logs
docker compose logs -f inference
```

### Making Changes

1. Make code changes
2. Rebuild affected service: `docker compose build [service]`
3. Restart service: `docker compose up -d [service]`
4. Check logs: `docker compose logs -f [service]`

## 📝 Key Features

- ✅ **End-to-End Pipeline**: Data ingestion → Training → Storage → Inference
- ✅ **Production Ready**: Health checks, logging, error handling
- ✅ **Scalable**: Docker Compose for local, Kubernetes for production
- ✅ **Azure Integrated**: Ready for AKS and ACR deployment
- ✅ **Real-time Inference**: REST API for fraud detection
- ✅ **Web Dashboard**: Fraud Guard UI for client IT teams
- ✅ **Model Management**: MLflow for experiment tracking
- ✅ **Automated Training**: Scheduled Airflow DAGs

## 🐛 Troubleshooting

### Services not starting
```bash
docker compose logs [service-name]
docker compose ps
```

### Out of memory
- Reduce `FRAUD_API_MAX_RECORDS` in `.env`
- Increase Docker Desktop memory allocation

### Port conflicts
- Check if ports are in use: `netstat -an | grep [port]`
- Update port mappings in `docker-compose.yml`

See [DEPLOYMENT.md](DEPLOYMENT.md) for more troubleshooting tips.

## 📚 Documentation

- [Deployment Guide](DEPLOYMENT.md) - Detailed deployment instructions
- [API Documentation](src/inference/api_server.py) - Inference API reference
- [Airflow DAGs](src/dags/) - Training pipeline documentation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally with Docker Compose
5. Submit a pull request

## 📄 License

[Add your license here]

## 🙏 Acknowledgments

- Apache Airflow for workflow orchestration
- MLflow for model management
- XGBoost for fraud detection model
- Flask for web application framework

---

**Ready to deploy?** Start with `docker compose build` and `docker compose up -d`!
