Hacker News

[Hacker News](https://news.ycombinator.com) | [new](https://news.ycombinator.com/newest) | [past](https://news.ycombinator.com/past) | [comments](https://news.ycombinator.com/newcomments) | [ask](https://news.ycombinator.com/ask) | [show](https://news.ycombinator.com/show) | [jobs](https://news.ycombinator.com/jobs) | [submit](https://news.ycombinator.com/submit)

---

▲ **Why I switched from Kubernetes to plain Docker Compose** (matduggan.com)
1,247 points by matduggan 18 hours ago | hide | past | favorite | 532 comments

---

# Why I switched from Kubernetes to plain Docker Compose

I've been running production workloads on Kubernetes for five years. Last month, I migrated everything to Docker Compose. Here's what happened and why.

## Background

I manage infrastructure for a B2B SaaS product with about 200 daily active users. We have 12 microservices, a PostgreSQL database, Redis, and a handful of background workers. Our Kubernetes cluster ran on 3 nodes in AWS EKS.

Monthly infrastructure cost: **$2,400/month** on Kubernetes. Monthly infrastructure cost after migration: **$340/month** on a single Hetzner dedicated server.

That's an 86% cost reduction. But cost was only part of the story.

## The Problem with Kubernetes at Small Scale

Kubernetes is an extraordinary piece of technology. It solves real problems — service discovery, rolling deployments, auto-scaling, self-healing, secret management. But it solves these problems at a scale most companies never reach.

For my workload:
- **Auto-scaling**: Our traffic is predictable. A single server handles 10x our peak load.
- **Self-healing**: Docker Compose has `restart: always`. Systemd can restart Docker. Uptime Robot pings the endpoints.
- **Rolling deployments**: `docker compose up -d --no-deps service-name` achieves zero-downtime deployment for stateless services.
- **Service discovery**: Docker Compose networking. Services talk to each other by name.
- **Secret management**: Environment files. They work.

What Kubernetes was actually providing me: **complexity that justified its own existence**.

## The Migration

I spent a weekend doing it. The steps:

1. Wrote a `docker-compose.yml` mapping each K8s deployment to a service
2. Set up a Hetzner dedicated server (AMD Ryzen 5, 64GB RAM, 2x1TB NVMe)
3. Installed Docker, set up automatic security updates
4. Migrated the database with `pg_dump`/`pg_restore`
5. Configured Caddy as reverse proxy (automatic HTTPS)
6. Set up simple monitoring with Uptime Robot + Grafana

```yaml
services:
  api:
    image: registry.example.com/api:latest
    restart: always
    env_file: .env
    depends_on:
      - postgres
      - redis
    labels:
      caddy: api.example.com
      caddy.reverse_proxy: "{{upstreams 3000}}"

  postgres:
    image: postgres:16
    restart: always
    volumes:
      - pgdata:/var/lib/postgresql/data
    env_file: .env.db
```

Total migration time: 14 hours including testing.

## What I Gave Up

Honest assessment of what I lost:

- **Multi-node failover**: If the server dies, there's downtime. I accept this. Our SLA is 99.9% (8.7 hours/year). A single modern server with RAID gives me that.
- **Horizontal scaling**: If we 10x our users, I'll need to think about scaling again. But a single server handles our load with 90% headroom.
- **Cool YAML**: No more HPA, PDB, NetworkPolicy manifests. Huge loss.

## What I Gained

- **$2,060/month** in savings ($24,720/year)
- **Simplicity**: One server. One docker-compose.yml. One brain to understand it.
- **Speed**: Deployments went from 3-5 minutes (K8s rolling update) to 10-15 seconds.
- **Debugging**: `docker logs service-name` instead of `kubectl get pods -n production | grep api | head -1 | xargs kubectl logs -f`
- **Sleep**: I no longer get paged because a node got OOM-killed at 3am.

## The Lesson

The lesson isn't "Kubernetes bad." It's **use the right tool for the scale you're at**. Most B2B SaaS companies with < 1000 users don't need Kubernetes. A $50/month server will outperform a $2,400/month cluster for these workloads.

The real question is: are you building infrastructure to serve your users, or to serve your resume?

---

**matduggan** 18h | prev | next [–]

I want to be clear: I'm not saying K8s is bad. I'm saying it's overkill for small teams.

reply

---

**throwaway_devops** 17h | [–]

This is spot on. I managed a K8s cluster for a startup with 3 engineers and 50 users. The cognitive overhead was absurd. We had more YAML than actual application code.

reply

  **matduggan** 16h | [–]

  Exactly! And every K8s upgrade was a white-knuckle experience.

  reply

---

**k8s_enthusiast** 17h | [–]

Counter-argument: what happens when your single server's disk fails? K8s with proper PVCs and multi-AZ deployments handles this transparently.

reply

  **matduggan** 16h | [–]

  The server has RAID-1 NVMe. If both disks fail simultaneously, I restore from the hourly pg_dump backup to S3. RTO is about 30 minutes. For my SLA, that's fine. For a bank? Absolutely use K8s.

  reply

---

**pragmatic_sre** 15h | [–]

Best take on this topic I've read in years. The Kubernetes industrial complex has convinced everyone they need a container orchestration platform. Most of them need a single server and Caddy.

▲ 342

reply

---

More comments (527)

---

Guidelines | FAQ | Lists | API | Security | Legal | Apply to YC | Contact

Search:
