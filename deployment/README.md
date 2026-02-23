# Cloud Deployment — AI Employee (Platinum Tier)

Deploy the AI Employee to an Oracle Cloud Free Tier ARM VM so watchers run
24/7 without your local machine being on.

---

## 1. Create an Oracle Cloud Free Tier Account

1. Go to **https://cloud.oracle.com** → click **Start for free**
2. Enter your name, email, and home region
   - Choose a region close to you (e.g. `us-ashburn-1`, `eu-frankfurt-1`)
   - **Region cannot be changed later**
3. Complete phone and credit card verification (card is NOT charged for Always Free)
4. Sign in to the Oracle Cloud Console

---

## 2. Create the Always Free ARM VM

Oracle gives you **4 OCPUs + 24 GB RAM** for free on ARM (Ampere A1).

### 2a. Launch Instance

1. Console → **Compute** → **Instances** → **Create Instance**
2. Name: `ai-employee`
3. **Image**: Ubuntu 22.04 (click "Change Image" → Ubuntu → 22.04 Minimal)
4. **Shape**: Click "Change Shape" → **Ampere** → `VM.Standard.A1.Flex`
   - OCPUs: `2` · Memory: `12 GB` (or 4/24 — both are Always Free)
5. **Networking**: Accept defaults (new VCN is fine)
6. **Add SSH keys**:
   - Paste your public key (`~/.ssh/id_rsa.pub` or `~/.ssh/id_ed25519.pub`)
   - Or generate a new key pair and download the private key
7. Click **Create**

### 2b. Open Firewall Port (optional — only if you expose a web UI later)

Console → **Networking** → **Virtual Cloud Networks** → your VCN →
**Security Lists** → **Default Security List** → **Add Ingress Rules**

| Source CIDR | Protocol | Destination Port |
|-------------|----------|-----------------|
| 0.0.0.0/0   | TCP      | 22 (SSH — already open) |

---

## 3. Connect via SSH

```bash
# Replace with your VM's public IP from the Instances page
ssh ubuntu@<PUBLIC_IP>
```

If you used a custom key:
```bash
ssh -i ~/.ssh/your-key.pem ubuntu@<PUBLIC_IP>
```

---

## 4. Run the VM Setup Script

Copy the project to the VM first (see Section 6 for git-based sync), then:

```bash
cd ~/ai-employee-bronze
chmod +x deployment/cloud_setup.sh
./deployment/cloud_setup.sh
```

This installs all dependencies, sets up Python/Node/PM2, and installs
Playwright's Chromium browser.

---

## 5. Configure Secrets

**Never put secrets in git.** Transfer them manually over SSH:

```bash
# From your LOCAL machine — copy secrets folder to VM
scp -r ./secrets ubuntu@<PUBLIC_IP>:~/ai-employee-bronze/secrets

# Copy your .env file
scp .env ubuntu@<PUBLIC_IP>:~/ai-employee-bronze/.env
```

---

## 6. Sync Vault (Git-based)

```bash
# On the VM — initial pull
cd ~/ai-employee-bronze
./deployment/sync_vault.sh pull

# On your local machine — push changes to cloud
./deployment/sync_vault.sh push
```

---

## 7. Start Cloud Watchers

```bash
cd ~/ai-employee-bronze
chmod +x deployment/cloud_watchers.sh
./deployment/cloud_watchers.sh
```

This starts the orchestrator under PM2, which survives reboots and
auto-restarts on crash.

---

## 8. Monitor

```bash
pm2 status                        # watcher process health
pm2 logs ai-employee-orchestrator # live log stream
pm2 monit                         # interactive dashboard
```

---

## Architecture on Cloud

```
Oracle Cloud VM (Ubuntu 22.04 ARM)
└── PM2
    └── orchestrator.py  ← manages all watchers with circuit breakers
        ├── filesystem_watcher.py  (vault/Inbox/)
        ├── gmail_watcher.py       (polls Gmail API)
        ├── linkedin_watcher.py    (Playwright headless)
        ├── facebook_watcher.py    (Playwright headless)
        ├── instagram_watcher.py   (Playwright headless)
        └── twitter_watcher.py     (Playwright headless)
```

Browser-based watchers (LinkedIn, Facebook, Instagram, Twitter) require
saved session files in `secrets/`. Transfer these from your local machine
after authenticating with `python setup/save_social_sessions.py`.

---

## Cost

| Resource | Spec | Cost |
|----------|------|------|
| VM.Standard.A1.Flex | 4 OCPU / 24 GB ARM | **Always Free** |
| Block Volume | 200 GB boot | **Always Free** |
| Egress | 10 TB/month | **Always Free** |

No credit card charges if you stay within Always Free limits.
