# WSL Setup

## Check Current Environment

```bash
python check_wsl_dependencies.py \
  --output-json reports/wsl_dependency_report.json \
  --output-md reports/wsl_dependency_report.md \
  --zeek-mode docker \
  --zeek-docker-image zeek/zeek:latest
```

Current smoke run status:

- Python 3.12.3 in WSL2
- `.venv-wsl` usable
- Docker, docker compose, tcpdump, tshark, and nmap present
- Python packages present: pandas, numpy, scikit-learn, pyarrow, joblib, xgboost, torch
- Host `zeek` is not installed; Docker Zeek is the intended path
- Docker socket access may require group permission on some shells

## Project Python Environment

```bash
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## WSL Ubuntu System Packages

Review before running because this requires sudo:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip docker.io docker-compose-plugin tcpdump tshark nmap
```

Host Zeek is optional when Docker Zeek is available:

```bash
docker pull zeek/zeek:latest
docker run --rm zeek/zeek:latest zeek --version
```

If Docker permission fails:

```bash
sudo usermod -aG docker $USER
newgrp docker
```
