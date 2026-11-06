# Host independently of your laptop

Run the synthetic-data demo on a Linux Docker server with a domain and Caddy HTTPS. No hosting purchase or remote deployment has been performed.

1. Install Docker Engine with Compose on the server, clone the repository and enter niyamit/.
2. Point domain A/AAAA records at the server. Allow TCP 80/443 and restrict SSH. Remove incorrect IPv6 DNS records.
3. Copy backend/.env.example to backend/.env and .env.hosted.example to .env.hosted. Generate a strong SECRET_KEY. Set DOMAIN to the bare hostname and POSTGRES_PASSWORD to a random hex string in .env.hosted.
4. In backend/.env set PUBLIC_APP_URL=https://YOUR-DOMAIN, COOKIE_SECURE=true, TRUSTED_PROXY_HOPS=2, APP_ENV=development and DEMO_MODE=true. This is a labelled demo with public demo credentials and simulated billing; use fictional records only.
5. Configure optional Twilio/AI credentials privately. Provider charges and trial restrictions still apply. Set spending/abuse controls before broad sharing; development OTP can be used with fictional numbers.

```bash
docker compose --env-file .env.hosted -f compose.hosted.yml config --quiet
docker compose --env-file .env.hosted -f compose.hosted.yml up -d --build --wait
docker compose --env-file .env.hosted -f compose.hosted.yml ps
```

Use these same file/env arguments for later operations. Only the proxy exposes host ports. PostgreSQL, Redis, API and frontend stay inside Docker. Caddy manages HTTPS when the domain resolves and ports are reachable. Official references: https://caddyserver.com/docs/automatic-https and https://caddyserver.com/docs/quick-starts/reverse-proxy.

## Acceptance and persistence

Open /, /patient, /login and /register-clinic on your domain. Run TESTING.md checks, including clinic isolation, OTP mode, uploads/review, invitations and demo billing. Local configuration validation does not verify DNS, certificate issuance or remote hosting.

The project name niyamit-hosted-demo creates separate database/artifact/Caddy volumes. It does not copy laptop records. Back up PostgreSQL, artifacts and encryption configuration together using DEPLOYMENT.md with the hosted arguments. Never run down -v on data you need.

After SSH into the server, inspect the private database:

```bash
docker compose --env-file .env.hosted -f compose.hosted.yml exec db psql -U niyamit -d niyamit
```

Restart policies recover when Docker starts after reboot. This is one host, not high availability. Add monitoring, tested backups and operational procedures before depending on it.

## Real-patient production

Complete DEPLOYMENT.md launch gates. Only then use APP_ENV=production, DEMO_MODE=false, HTTPS/secure cookies and verified real providers in a separate non-demo environment. Demo subscription activation is disabled there. Simulated billing does not grant a paid membership. Never seed public demo credentials into production.
