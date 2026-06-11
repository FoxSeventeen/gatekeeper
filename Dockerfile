FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    bash \
    git \
    python3 \
    python3-pip \
    ripgrep \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["sleep", "infinity"]
