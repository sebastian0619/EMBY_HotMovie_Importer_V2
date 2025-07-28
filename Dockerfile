FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 创建输出目录
RUN mkdir -p /app/output

# 设置默认时区为亚洲/上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置环境变量，可以在 docker-compose.yml 中覆盖
ENV PYTHONUNBUFFERED=1

# 创建一个非 root 用户运行应用
RUN adduser --disabled-password --gecos "" appuser
RUN chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"] 