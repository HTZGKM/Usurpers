FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY restaurant ./restaurant
USER 10001
CMD ["python", "-m", "restaurant.scheduler", "--interval", "15"]
