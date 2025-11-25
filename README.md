# ⚡ Network Config Tool

A simple web tool to generate and push configurations to network devices using **Jinja2 templates**.

It automatically reads your templates, creates a form for variables (like `{{ hostname }}`), and pushes the config via SSH.


## 🚀 Quick Start


```bash
docker run -d -p 8501:8501 --name net-tool --restart GlebPuzyrev/config-tool:latest
