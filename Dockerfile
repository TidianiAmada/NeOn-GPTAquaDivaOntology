FROM python:3.11-slim

# Avoid Python buffering (logs visible immediately)
ENV PYTHONUNBUFFERED=1

# Install system dependencies (optional but safe)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Run your pipeline
CMD ["python", "run_pipeline_for_prompts.py"]