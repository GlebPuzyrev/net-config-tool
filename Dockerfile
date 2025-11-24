# 1. Base Image: Use lightweight Python 3.12
FROM python:3.12-slim

# 2. Environment Variables
# Prevents Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout and stderr (logs appear immediately)
ENV PYTHONUNBUFFERED=1

# 3. Set Working Directory
WORKDIR /app

# 4. Copy Dependencies
# We copy requirements first to leverage Docker cache layers.
# If requirements.txt doesn't change, this step is cached.
COPY requirements.txt .

# 5. Install Dependencies
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy Application Code
COPY . .

# 7. Expose Streamlit Port
EXPOSE 8501

# 8. Healthcheck (Optional)
# Verifies that Streamlit is responsive
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 9. Entrypoint Command
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]

