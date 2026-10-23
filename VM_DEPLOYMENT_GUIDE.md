# HIAS Deployment & Operations Guide

This guide documents the complete containerized deployment architecture, Docker Compose orchestration, CI/CD pipeline automation, and operational procedures for **HIAS** (Hostel Intelligent Access System).

---

## 1. System Architecture & Port Mapping

HIAS consists of two primary services orchestrated via Docker Compose:
- **Backend Service (`hias-backend`)**: FastAPI REST & SSE controller interacting with Matrix COSEC devices and SQLite / PostgreSQL.
  - Internal Container Port: `8000`
  - **Host Mapped Port: `8026`** (`8026:8000`)
  - Healthcheck: `curl -f http://localhost:8000/health`
- **Frontend Service (`hias-frontend`)**: React + Vite static dashboard served via `serve`.
  - Internal Container Port: `5173`
  - **Host Mapped Port: `5183`** (`5183:5173`)
  - Healthcheck: `wget -q --spider http://localhost:5173/ || exit 1`

```
┌────────────────────────────────────────────────────────────────┐
│ Host / VM / Raspberry Pi                                      │
│                                                                │
│  [Host Port 5183] ──> [Container Port 5173] Frontend Dashboard │
│  [Host Port 8026] ──> [Container Port 8000] Backend API Core   │
│                                           │                    │
│                                           ├──> Matrix COSEC    │
│                                           └──> hias_data Volume│
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Environment Configuration

Separate environment files are configured for backend and frontend services:

### Backend Environment (`backend/.env` or `backend.env`)
```env
# Matrix COSEC Device Configuration
COSEC_BASE_URL=http://192.168.1.100
COSEC_USERNAME=admin
COSEC_PASSWORD=password123
COSEC_POLL_INTERVAL=2.0

# Database Configuration
DATABASE_URL=sqlite:///./hias.db

# Server Configuration
PORT=8000
```
> **Note for Persistent Production Volumes:** To persist SQLite data across Docker volume updates in production, `DATABASE_URL=sqlite:///./data/hias.db` can be set so data is written into `/app/data` mounted to Docker volume `hias_data`.

### Frontend Environment (`frontend/.env` or `frontend.env`)
```env
VITE_API_URL=http://localhost:8026
```
> In local development without Docker, use `http://localhost:8000`. Inside Docker or remote VM, Docker Compose and CI/CD map the backend to host port `8026`.

---

## 3. Local Docker Compose Workflow

### Build and Start Services
From the repository root (`HIAS`):
```bash
# Build and run containers in detached mode
docker compose up -d --build

# View container status and health
docker compose ps

# View service logs
docker compose logs -f
```

### Accessing Endpoints
- **Frontend Web Dashboard:** `http://localhost:5183`
- **Backend API Health:** `http://localhost:8026/health`
- **Backend API Swagger Docs:** `http://localhost:8026/docs`

### Stop Services
```bash
docker compose down
```

---

## 4. GitHub Actions CI/CD Pipeline

The automated CI/CD pipeline is located at `.github/workflows/cicd.yml`.

### Pipeline Stages
1. **Validate**:
   - Renders compose file from `docker-compose.production.template.yml` using commit short SHA (`${{ GITHUB_SHA::7 }}`).
   - Generates stub environment files and executes `docker compose config` schema validation.
2. **Build**:
   - Sets up Docker Buildx and authenticates to Docker Hub.
   - Builds and tags production container images:
     - `bhiv/hias-backend:<SHA>` and `:latest`
     - `bhiv/hias-frontend:<SHA>` and `:latest` (with build argument `VITE_API_URL`)
   - Pushes images to registry.
3. **Deploy**:
   - Securely generates environment files on runner from GitHub Secrets.
   - Creates a compressed deployment tarball (`deployment.tar.gz`).
   - SSH/SCP into the target host (`~/HIAS` or custom directory).
   - Pulls validated images, executes `docker compose up -d --remove-orphans`.
   - Executes a 120-second active health verification loop for backend and frontend.
   - Prunes stale Docker images (`until=168h`).
   - Records successful deployment in `docs/RELEASE_HISTORY.md` and `/var/tmp/HIAS/RELEASE_HISTORY.md`.
4. **Automated Rollback**:
   - If deployment fails or containers fail the healthcheck threshold, automatically extracts the last known healthy commit SHA from `RELEASE_HISTORY.md`.
   - Restores the previous operational image version and re-verifies health.

### Required GitHub Secrets

Configure the following secrets in GitHub Repository Settings (`Settings` > `Secrets and variables` > `Actions`):

| Secret Name | Description | Example |
|---|---|---|
| `DOCKER_USERNAME` | Docker Hub username | `bhiv` |
| `DOCKER_PASSWORD` | Docker Hub password or personal access token | `dckr_pat_...` |
| `VM_IP` | Host IP address (VM / Raspberry Pi) | `192.168.1.50` |
| `VM_PORT` | SSH port on target machine | `22` |
| `VM_USERNAME` | Target machine user account | `pi` or `ubuntu` |
| `VM_PASSWORD` | SSH password for target account | `******` |
| `HIAS_BACKEND_ENV_FILE` | Complete backend `.env` file content | *(See Section 2)* |
| `HIAS_FRONTEND_ENV_FILE` | Complete frontend `.env` file content | `VITE_API_URL=http://<VM_IP>:8026` |
| `VM_DEPLOY_DIR` *(Optional)* | Target deployment folder on VM | `~/HIAS` |

---

## 5. Maintenance & Useful Commands

### Check Live Health
```bash
curl -f http://localhost:8026/health
wget -q --spider http://localhost:5183/
```

### Inspect Container Health Details
```bash
docker inspect --format='{{json .State.Health}}' hias_backend
docker inspect --format='{{json .State.Health}}' hias_frontend
```

### Launch Kiosk / Dashboard Script
```bash
./launch_browser.sh
```
