# 1. Обновляем пакеты
sudo apt update && sudo apt upgrade -y

# 2. Устанавливаем зависимости
sudo apt install -y ca-certificates curl gnupg

# 3. Добавляем GPG-ключ Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 4. Добавляем репозиторий Docker
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. Устанавливаем Docker Engine + Compose v2 plugin
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 6. Добавляем себя в группу docker (чтобы не писать sudo)
sudo usermod -aG docker $USER

# 7. Проверяем
docker --version
docker compose version

# wsl --shutdown
# systemctl status docker
