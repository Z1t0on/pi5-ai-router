---
name: pi5-ssh-deploy
description: Déploiement et administration autonome du Raspberry Pi 5 (ai-router) via SSH/SCP depuis Windows 11 sans intervention manuelle.
---

# Paramètres de connexion SSH
- **Hôte cible** : `olivier@192.168.1.44` (alias réseau local : `olivier@ai-router.local`). Toujours utiliser l'option `-o BatchMode=yes` sur chaque commande `ssh` et `scp` pour éviter tout blocage interactif.
- **Dossier distant** : `~/pi5-ai-router`

# Procédure de déploiement autonome
1. **Vérification architecture et espace** : Tester la connexion et vérifier l'espace disque disponible avec `ssh -o BatchMode=yes olivier@192.168.1.44 "uname -m && df -h /"`.
2. **Installation automatique de Docker (si absent)** :
   Exécuter `ssh -o BatchMode=yes olivier@192.168.1.44 "command -v docker >/dev/null 2>&1 || (curl -fsSL https://docker.com | sh && sudo usermod -aG docker \$USER)"`.
3. **Transfert des fichiers depuis Windows** :
   Utiliser `scp -r` pour copier `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env`, `config/` et `app/` vers `olivier@192.168.1.44:~/pi5-ai-router/`.
4. **Démarrage et vérification des logs** :
   Lancer `ssh -o BatchMode=yes olivier@192.168.1.44 "cd ~/pi5-ai-router && sg docker -c 'docker compose up -d --build'"`.
   Vérifier ensuite l'état de santé avec `ssh -o BatchMode=yes olivier@192.168.1.44 "curl -s http://localhost:4000/health"`.
