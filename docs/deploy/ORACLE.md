# Always-on backend on Oracle Cloud

_Part 1 (provisioning) written 2026-11-08 for plan task P0c.1. Sections 2–4 are written in P0c.8. Plan: [`PLAN.md`](../plans/2026-11-redesign/PLAN.md), phase P0c._

This guide moves the API, Postgres and the scheduled jobs off Render and Supabase onto one Oracle Cloud (OCI) VM, at $0. You click through the OCI console; the repo's scripts do the rest. Never paste a secret (DuckDNS token, SSH private key, database password) into chat, an issue or git. Where this guide shows `<…>`, put in your own value.

## 0. What we're building

```
Browser ──▶ Vercel (Next.js frontend, unchanged)
               │ HTTPS
               ▼
https://<name>.duckdns.org   (DuckDNS: name → the VM's public IP)
               │
┌──────────────▼── VM "f1ai": VM.Standard.A1.Flex, 2 OCPU / 8 GB, Ubuntu 24.04 arm64 ──┐
│ caddy     :80 / :443, Let's Encrypt certificate, WebSocket upgrade                   │
│   └▶ api  uvicorn, one worker, ENABLE_LOCAL_MODELS=true (rulebook search + recall)   │
│        └▶ postgres  pgvector/pgvector:pg17, Docker network and 127.0.0.1 only        │
│ systemd timers: PU ingest · nightly pg_dump · weekly restore check · DuckDNS refresh │
│ /srv/f1ai on a 100 GB block volume: pgdata, FastF1 cache, f1db, model cache, .env    │
└──────────────────────────────────────┬───────────────────────────────────────────────┘
                                       ▼
                     Object Storage bucket f1ai-backups (dumps kept 14 days)
```

- All three services run in Docker Compose (`deploy/oracle/`, written in P0c.5).
- A push to `main` builds the arm64 image on GitHub Actions, pushes it to GHCR and runs `deploy.sh` on the VM over SSH. A failed health check rolls back to the previous image.
- The VM never sleeps, its disk survives restarts, and it has its own IP. That ends the cold start and turns rulebook search and chat-memory recall back on.

**Why $0 holds.** The account is Always Free only (never upgraded), so Oracle cannot charge it, and everything below fits the Always Free allowances (Oracle's [resource reference](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm), checked 2026-11-08):

| Resource          | Always Free allowance                                                      | This setup                                    |
| ----------------- | -------------------------------------------------------------------------- | --------------------------------------------- |
| Ampere A1 compute | 1,500 OCPU hours + 9,000 GB hours a month = 2 OCPU and 12 GB, split freely | One VM, 2 OCPU / 8 GB                         |
| AMD E2.1.Micro    | Two VMs, 1/8 OCPU and 1 GB each                                            | Not used                                      |
| Block Volume      | 200 GB in total, boot volumes included; five volume backups                | 50 GB boot + 100 GB data = 150 GB; no backups |
| Object Storage    | 20 GB; 50,000 API requests a month                                         | 14 nightly dumps; a few requests a day        |
| Outbound data     | 10 TB a month                                                              | API JSON to Vercel and browsers               |
| Region            | Always Free compute and volumes only in the home region                    | Everything in the home region                 |

## 1. Provisioning

You need: a card and a phone for Oracle's identity check, an SSH client, and about an hour. Console paths below follow the current OCI console; where an older layout differs, the alternative is in brackets.

### 1.1 Account

1. Go to [oracle.com/cloud/free](https://www.oracle.com/cloud/free/) → **Start for free** and fill in the sign-up form.
2. **Home Region:** choose carefully; you can't change it later, and Always Free compute and volumes exist only there.
   - It must offer Ampere A1. A1 can't be created in South Korea North (Chuncheon).
   - Pick one near Vercel's US regions. At cutover (P0c.8), Vercel's function region is set to the one nearest your Oracle region:

     | Oracle home region          | Nearest Vercel region |
     | --------------------------- | --------------------- |
     | US East (Ashburn)           | `iad1` Washington, DC |
     | US Midwest (Chicago)        | `cle1` Cleveland      |
     | US West (San Jose, Phoenix) | `sfo1` San Francisco  |

   - Oracle publishes no capacity figures. If a region keeps answering "Out of host capacity" (1.3), that's the region, not you.

3. Oracle asks for a card to verify you. Its Free Tier docs say the card is not charged unless you upgrade.
4. **Never upgrade to Pay As You Go.** Don't open Billing & Cost Management → **Upgrade and Manage Payment**. This is a project decision: an Always Free account cannot be charged.
5. The first 30 days include $300 of trial credits, so the console will let you create paid resources. Oracle reclaims them when the trial ends. Worse, if your A1 instances total more than 2 OCPU or 12 GB when the trial ends, Oracle disables **all** of them and deletes them 30 days later. Create only what this guide lists.

### 1.2 SSH key

On your own machine:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/f1ai -C "f1ai-admin"
cat ~/.ssh/f1ai.pub   # the one line you paste into the console
```

The private key (`~/.ssh/f1ai`) never leaves your machine.

### 1.3 VM

1. Navigation menu → **Compute** → **Instances** → **Create instance**. Leave the compartment on the root compartment (the default for a new account).
2. **Basic information:**
   - **Name:** `f1ai`.
   - **Placement → Availability domain:** the first one (AD-1). Single-AD regions have only one.
   - **Image and shape → Change shape:** **Instance type** Virtual machine → **Shape series** Ampere → `VM.Standard.A1.Flex` → **Number of OCPUs** `2`, **Amount of memory (GB)** `8` → **Select shape**. Leave **Burstable** off.
   - **Image and shape → Change image:** Ubuntu → **Canonical Ubuntu 24.04** (not "Minimal") → **Select image**. The image summary should name an `aarch64` build; if it doesn't, pick the aarch64 build.
   - Both should carry the **Always Free-eligible** label.
3. **Security:** leave the defaults.
4. **Networking** [Primary VNIC information]:
   - **Primary network:** Create new virtual cloud network (the default name is fine).
   - **Subnet:** Create new public subnet.
   - **Automatically assign public IPv4 address:** on.
   - **Add SSH keys:** Paste public keys → the line from `~/.ssh/f1ai.pub`.
5. **Storage → Boot volume:** 50 GB. If the console shows a smaller default, tick **Specify a custom boot volume size** and enter `50`.
6. **Review** → **Create**. Wait for **Running**.
7. On the instance's details page, copy two values: the **Public IPv4 address**, and the instance **OCID** (Instance information → OCID → Copy; you need it in 1.7).
8. Check that you can log in (the Ubuntu image's user is `ubuntu`), then log out. Don't install anything yet; `bootstrap.sh` (P0c.5) does it.

   ```bash
   ssh -i ~/.ssh/f1ai ubuntu@<public-ip>
   ```

**"Out of host capacity".** Oracle's meaning: a temporary lack of Always Free A1 hosts in your home region. Its guidance is to create the instance in another availability domain, or to wait and try again (its third suggestion, upgrading, is ruled out). A free-only account can see this for hours or days. Retry the same settings; never raise the shape above 2 OCPU / 8 GB to get through.

### 1.4 Block volume

1. Navigation menu → **Storage** → **Block Storage** → **Block Volumes** → **Create block volume**:

   | Field                                           | Value                                                     |
   | ----------------------------------------------- | --------------------------------------------------------- |
   | Name                                            | `f1ai-data`                                               |
   | Create in compartment                           | the same as the VM (root)                                 |
   | Availability domain                             | **the VM's availability domain**                          |
   | Volume size and performance                     | **Custom** (Default creates 1,024 GB, over the allowance) |
   | Volume size (in GB)                             | `100`                                                     |
   | Target volume performance                       | Balanced (the default)                                    |
   | Backup policies                                 | none (five volume backups is the free limit)              |
   | Cross-region replication, customer-managed keys | off                                                       |

2. Wait for **Available**.
3. **Compute → Instances → f1ai → Storage** tab [Resources → Attached block volumes] → **Attach block volume**:
   - **Volume:** `f1ai-data`.
   - **Device path:** `/dev/oracleoci/oraclevdb`, if the console offers one.
   - **Attachment type:** Paravirtualized. It needs no iSCSI commands; the disk appears on the VM once the state is **Attached**.
   - **Access:** Read/write.
4. Don't format or mount it. `deploy/oracle/bootstrap.sh` (P0c.5) formats it and mounts it at `/srv/f1ai`.

Storage used: 50 GB boot + 100 GB data = 150 GB of the 200 GB free.

### 1.5 Network

The VM wizard created a VCN with a public subnet. Its Default Security List already allows SSH (TCP 22) from anywhere. Add the web ports:

1. Navigation menu → **Networking** → **Virtual cloud networks** → the VCN from 1.3 → **Security** tab [Resources → Security Lists] → **Default Security List for** the VCN → **Security rules** tab [Resources → Ingress Rules] → **Add Ingress Rules**.
2. Add two rules (the second through **+ Another Ingress Rule**), leaving **Source Port Range** empty:

   | Stateless | Source Type | Source CIDR | IP Protocol | Destination Port Range | Description                       |
   | --------- | ----------- | ----------- | ----------- | ---------------------- | --------------------------------- |
   | off       | CIDR        | `0.0.0.0/0` | TCP         | `80`                   | HTTP: certificate check, redirect |
   | off       | CIDR        | `0.0.0.0/0` | TCP         | `443`                  | HTTPS: the API                    |

3. Leave the TCP 22 rule as it is.

Ubuntu's own firewall (iptables) on OCI images also blocks 80 and 443; `bootstrap.sh` opens them. Until it runs, nothing answers on those ports, and that's expected.

### 1.6 DuckDNS

1. Sign in at [duckdns.org](https://www.duckdns.org/) (GitHub, Google and others work).
2. Under **domains**, add a subdomain, e.g. `<name>`. The API's address becomes `https://<name>.duckdns.org`.
3. In that row's **current ip** field, enter the VM's public IP → **update ip**.
4. Check from your machine: `dig +short <name>.duckdns.org` prints the IP.
5. The **token** at the top of the page goes into `/srv/f1ai/.env` on the VM at cutover (P0c.8). Keep it there only: never in chat, git or GitHub.

### 1.7 Backups to Object Storage

The VM uploads nightly dumps with instance-principal auth: OCI recognises the VM itself, so no API key or config file sits on its disk.

1. **Bucket.** Navigation menu → **Storage** → **Object Storage & Archive Storage** → **Buckets** → **Create Bucket**:
   - **Bucket name:** `f1ai-backups`.
   - **Default storage tier:** Standard. Auto-tiering, object versioning and object events: off.
   - **Encryption:** Oracle-managed keys (the default).
   - It is private by default; keep it that way.
2. **Dynamic group.** Navigation menu → **Identity & Security** → **Domains** → **Default** → **Dynamic groups** → **Create dynamic group** [tenancies without identity domains: Identity & Security → Dynamic Groups]:
   - **Name:** `f1ai-instances`.
   - **Matching rule 1:** `instance.id = '<instance OCID>'`, with the OCID from 1.3. Oracle checks the rule's syntax but not the OCID, so compare it with the instance page.
3. **Policy.** Navigation menu → **Identity & Security** → **Policies** → compartment: root → **Create Policy**:
   - **Name:** `f1ai-backups`. **Compartment:** root.
   - **Policy Builder:** Show manual editor, then:

   ```
   Allow dynamic-group f1ai-instances to manage objects in compartment <compartment> where target.bucket.name='f1ai-backups'
   Allow dynamic-group f1ai-instances to read buckets in compartment <compartment>
   Allow service objectstorage-<region-identifier> to manage object-family in compartment <compartment>
   ```

   - **`<compartment>`:** the bucket's compartment. If it is the root compartment (the default for a new account), write `in tenancy` in place of `in compartment <compartment>`.
   - **`<region-identifier>`:** your home region's identifier, e.g. `us-ashburn-1` (region menu → Manage regions). The third statement lets Object Storage run the lifecycle rule in step 4; Oracle requires it.
   - An unprefixed group name means the Default identity domain. If the editor rejects `f1ai-instances`, write `dynamic-group 'Default'/'f1ai-instances'`.

4. **Lifecycle rule.** **Buckets** → `f1ai-backups` → **Policies** tab [Resources → Lifecycle Policy Rules] → **Lifecycle policy rules** → **Create Rule**:
   - **Name:** `delete-after-14-days`. **Lifecycle action:** Delete. **Number of days:** `14`. **State:** enabled. No object name filters.
   - If the console says Object Storage lacks permission, the third policy statement is missing or names the wrong region.

### 1.8 Idle reclamation

Oracle's rule: it deems a VM idle, and may reclaim an Always Free one, when over 7 days **all three** hold:

- CPU utilization at the 95th percentile is under 20%;
- network utilization is under 20%;
- memory utilization is under 20% (counted on A1 shapes only).

Oracle's page names no exemption for Pay As You Go accounts, so upgrading wouldn't avoid it either. We stay clear on memory: the API with its local models loaded plus Postgres uses about 3 GB (P0c.3 measures it), roughly 40% of 8 GB, around the clock. That's why the VM has 8 GB rather than the full 12.

**Week-1 check** (the first week the stack runs):

1. **Compute → Instances → f1ai → Monitoring** tab [Resources → Metrics] → metric namespace `oci_computeagent` → **Memory Utilization**. It should read at or above 25% across the week.
2. If the charts are empty: **Oracle Cloud Agent** tab → **Compute Instance Monitoring** → Enabled. Data appears within about 10 minutes.
3. If memory reads under 25%, lower the denominator rather than add load. On the instance page: **More actions** → **Edit** → **Edit shape** → **Amount of memory (GB)** `6` → **Save changes**. The VM reboots; 3 GB of 6 is 50%.

### 1.9 Stay at $0

- The account is never upgraded (1.1).
- Only resources with the **Always Free-eligible** label, and only those in this guide.
- A1 in total: at most 2 OCPU and 12 GB across all instances.
- Block storage in total: at most 200 GB, boot volumes included; no volume backup policies.
- Object Storage: under 20 GB (the lifecycle rule keeps 14 dumps).
- Everything in the home region.
- No reserved or extra public IPs; the VM's free ephemeral IPv4 is the only one.
- **Billing & Cost Management → Cost Analysis** shows $0. Check it after provisioning and in the weekly checks (P0c.8).

### 1.10 Send back

Send these, and nothing else:

- the VM's public IPv4 address;
- the DuckDNS name (`<name>.duckdns.org`);
- the home region (for Vercel's function region at cutover).

None of these is secret. The DuckDNS token and the SSH private key stay with you.

## 2. Cutover

Written in P0c.8.

## 3. Rollback

Written in P0c.8.

## 4. Operations

Written in P0c.8.
