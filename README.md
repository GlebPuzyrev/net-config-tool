# 🛠️ NetConfig Tool: Vendor Agnostic Provisioner

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31-ff4b4b?logo=streamlit)](https://streamlit.io/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed?logo=docker)](https://hub.docker.com/)
[![Nornir](https://img.shields.io/badge/Automation-Nornir-green)](https://nornir.tech/)

A lightweight, web-based network automation tool designed for **Day-1 provisioning** and **configuration management**. Built with **Python**, **Nornir**, and **Streamlit**.

It features **Dynamic Template Parsing**: just upload a Jinja2 template, and the UI automatically generates the necessary input forms (including default values).

![App Screenshot](https://via.placeholder.com/800x400?text=Screenshot+of+NetConfig+Tool)
*(Add your screenshot here)*

---

## 🚀 Key Features

* **Vendor Agnostic:** Supports Cisco (IOS-XE, NX-OS), Arista EOS, Juniper Junos, Aruba (AOS-S, CX), and Fortinet.
* **Dynamic UI Generation:** The tool parses Jinja2 templates via AST to detect variables (`{{ var }}`) and defaults (`{{ var | default('val') }}`), creating input fields automatically.
* **Safe Staging:** Review and edit the generated config in a terminal-like editor before pushing it to the device.
* **Lab Friendly:** Optimized for **GNS3 / EVE-NG** environments (supports legacy SSH algorithms automatically).
* **Dockerized:** Runs anywhere with a single command.

---

## 📦 Quick Start (Docker)

The easiest way to run the tool is using Docker. No Python installation required.

### Option 1: One-Liner (Linux/MacOS)
```bash
docker run -d -p 8501:8501 --name net-tool --restart unless-stopped your_dockerhub_username/config-tool:latest

