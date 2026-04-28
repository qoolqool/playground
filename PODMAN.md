for Podman
### Prerequisites
 
- Podman installed with a rootful machine running (`podman machine inspect --format '{{.Rootful}}'` returns `true`)

- Podman REST API exposed on TCP 2375 inside the VM (persistent system unit)
 
``` 
podman machine ssh -- "sudo tee /etc/systemd/system/podman-tcp.service > /dev/null << 'EOF'
[Unit]
Description=Podman REST API (TCP 2375)
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/podman system service --time=0 tcp:0.0.0.0:2375
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now podman-tcp.service"
# Verify
podman machine ssh "ss -tlnp | grep 2375"
```
 

### 3. Find the Podman VM IP and set `PODMAN_VM_IP`
The `docker-compose.yml` reads `${PODMAN_VM_IP:-192.168.127.2}`. The default works on most macOS + gvproxy setups, but verify it:
```bash
podman machine inspect --format '{{range .NetworkSettings.Interfaces}}{{range .IPAddresses}}{{.IP}} {{end}}{{end}}'
```
If your VM IP differs from `192.168.127.2`, export it before running `podman compose`:
```bash
export PODMAN_VM_IP=<your-vm-ip>
```
 
 
the diff between podman vs docker (environment), for cap_add, you can ignore if you dont need pcap/change the network interface setting
 
  tooling:
    build:
      context: ./tooling
      dockerfile: Dockerfile
    container_name: poc-tooling
    hostname: tooling
    cap_add:
      - NET_ADMIN
      - NET_RAW
    environment:
      - DOCKER_HOST=tcp://${PODMAN_VM_IP:-192.168.127.2}:2375
 
