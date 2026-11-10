# Always-on backend on Oracle Cloud

_Part 1 (provisioning) written 2026-11-08 for plan task P0c.1; parts 2–4 (cutover, rollback, operations) 2026-11-09 for P0c.8. Plan: [`PLAN.md`](../plans/2026-11-redesign/PLAN.md), phase P0c._

This guide moves the API, Postgres and the scheduled jobs off Render and Supabase onto one Oracle Cloud (OCI) VM, at $0. You click through the OCI console; the repo's scripts do the rest. Never paste a secret (DuckDNS token, SSH private key, database password) into chat, an issue or git. Where this guide shows `<…>`, put in your own value.

## 0. What we're building

```
Browser ──▶ Vercel (Next.js frontend, unchanged)
               │ HTTPS
               ▼
https://<name>.duckdns.org   (DuckDNS: name → the VM's public IP)
               │
┌──────────────▼── VM "f1ai": VM.Standard.A1.Flex, 2 OCPU / 6 GB, Ubuntu 24.04 arm64 ──┐
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
| Ampere A1 compute | 1,500 OCPU hours + 9,000 GB hours a month = 2 OCPU and 12 GB, split freely | One VM, 2 OCPU / 6 GB                         |
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
   - Pick one near Vercel's US regions. At cutover (§2.10), Vercel's function region is set to the one nearest your Oracle region:

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
   - **Image and shape → Change shape:** **Instance type** Virtual machine → **Shape series** Ampere → `VM.Standard.A1.Flex` → **Number of OCPUs** `2`, **Amount of memory (GB)** `6` → **Select shape**. Leave **Burstable** off.
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
8. Check that you can log in (the Ubuntu image's user is `ubuntu`), then log out. Don't install anything yet; `bootstrap.sh` (§2.3) does it.

   ```bash
   ssh -i ~/.ssh/f1ai ubuntu@<public-ip>
   ```

**"Out of host capacity".** Oracle's meaning: a temporary lack of Always Free A1 hosts in your home region. Its guidance is to create the instance in another availability domain, or to wait and try again (its third suggestion, upgrading, is ruled out). A free-only account can see this for hours or days. Retry the same settings; never raise the shape above 2 OCPU / 6 GB to get through.

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
4. Don't format or mount it. `deploy/oracle/bootstrap.sh` (§2.3) formats it and mounts it at `/srv/f1ai`.

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
5. The **token** at the top of the page goes into `/srv/f1ai/.env` on the VM at cutover (§2.4). Keep it there only: never in chat, git or GitHub.

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

Oracle's page names no exemption for Pay As You Go accounts, so upgrading wouldn't avoid it either. We stay clear on memory. P0c.3 measured the API at about 0.65 GB with its local models loaded (macOS, before its caches fill); with Postgres, Caddy and the OS the VM should hold about 2 GB around the clock, roughly a third of 6 GB. That's why the VM has 6 GB rather than the full 12: the more memory it has, the harder it is to stay above 20%.

**Week-1 check** (the first week the stack runs):

1. **Compute → Instances → f1ai → Monitoring** tab [Resources → Metrics] → metric namespace `oci_computeagent` → **Memory Utilization**. It should read at or above 25% across the week.
2. If the charts are empty: **Oracle Cloud Agent** tab → **Compute Instance Monitoring** → Enabled. Data appears within about 10 minutes.
3. If memory reads under 25%, lower the denominator rather than add load. On the instance page: **More actions** → **Edit** → **Edit shape** → **Amount of memory (GB)** `4` → **Save changes**. The VM reboots; 2 GB of 4 is 50%. Never go below 4 GB: FastF1 race loads need the headroom.

### 1.9 Stay at $0

- The account is never upgraded (1.1).
- Only resources with the **Always Free-eligible** label, and only those in this guide.
- A1 in total: at most 2 OCPU and 12 GB across all instances.
- Block storage in total: at most 200 GB, boot volumes included; no volume backup policies.
- Object Storage: under 20 GB (the lifecycle rule keeps 14 dumps).
- Everything in the home region.
- No reserved or extra public IPs; the VM's free ephemeral IPv4 is the only one.
- **Billing & Cost Management → Cost Analysis** shows $0. Check it after provisioning and in the weekly checks (§4.9).

### 1.10 Send back

Send these, and nothing else:

- the VM's public IPv4 address;
- the DuckDNS name (`<name>.duckdns.org`);
- the home region (for Vercel's function region at cutover).

None of these is secret. The DuckDNS token and the SSH private key stay with you.

## 2. Cutover

The order matters, and each step names what success looks like. Steps 2.1–2.7 change nothing anyone sees: Render and Supabase keep serving while the VM is built and checked, so take as long as they need. Steps 2.8–2.10 are one sitting of about 30 minutes, during which the site has no API for roughly 10. Steps 2.11–2.13 follow with the site already on the VM.

"On your Mac" means a terminal on your machine; "on the VM" means an SSH session as `ubuntu` (`ssh -i ~/.ssh/f1ai ubuntu@<public-ip>`). `<name>` is your DuckDNS subdomain.

### 2.1 Before you start

- §1 is done: you have the VM's public IP, the DuckDNS name and the admin key `~/.ssh/f1ai`.
- The P0c pull request (`feat: always-on backend on Oracle Cloud`) is merged into `main`. `bootstrap.sh` and the deploy files are fetched from `main`, so this comes first. Merging changes nothing in production: `deploy-oracle.yml` skips while the `ORACLE_HOST` variable is unset, Render deploys the merge and keeps serving, and its boot adds the `version` column to Supabase's `app_documents`.
- On your Mac: `gh` signed in with admin rights on `amurark3/F1-AI` (`gh auth status`), plus `jq`, `openssl`, `ssh` and `curl`.
- Signed in, in browser tabs: Render, Vercel, Supabase, duckdns.org, the OCI console, and the repository's **Actions** tab.
- A password-manager entry for the VM's `.env` values. The file lives only on the data volume; if that volume is ever lost, you type them in again (§4.6).

### 2.2 Deploy key

GitHub Actions logs in to the VM with a key of its own, which can run only `deploy.sh`. On your Mac:

```bash
ssh-keygen -t ed25519 -N "" -C f1ai-deploy -f ~/.ssh/f1ai-deploy
gh secret set ORACLE_SSH_KEY --repo amurark3/F1-AI < ~/.ssh/f1ai-deploy
scp -i ~/.ssh/f1ai ~/.ssh/f1ai-deploy.pub ubuntu@<public-ip>:
```

- No passphrase: Actions can't type one. `gh secret set` reads the private half from the file, so it never appears on screen or in your shell history.
- **Success:** `gh secret list --repo amurark3/F1-AI` lists `ORACLE_SSH_KEY`.
- Keep `~/.ssh/f1ai-deploy`; §2.7 uses it once. Whatever it asks for, the VM runs only `deploy.sh`.

### 2.3 Bootstrap the VM

On the VM:

```bash
curl -fsSLO https://raw.githubusercontent.com/amurark3/F1-AI/main/deploy/oracle/bootstrap.sh
sudo bash bootstrap.sh "$(cat f1ai-deploy.pub)"
```

What it does, in order:

1. Installs Docker Engine and the Compose plugin from Docker's apt repository.
2. Adds a 2 GB swap file.
3. Formats the block volume, only if it is blank, mounts it at `/srv/f1ai` (fstab `_netdev,nofail`), and makes Docker wait for that mount.
4. Creates the `deploy` user and the data directories.
5. Opens TCP 80, TCP 443 and UDP 443 in the image's iptables rules, live and in `/etc/iptables/rules.v4`.
6. Turns on unattended upgrades, and sets SSH to keys only with no root login.
7. Installs the deploy key as `restrict,command="/srv/f1ai/app/deploy/oracle/deploy.sh"`.
8. Clones `deploy/oracle` from `main` into `/srv/f1ai/app` (sparse and shallow).
9. Creates `/srv/f1ai/.env` from `env.example` (mode 600, owner `deploy`).
10. Installs the systemd units and enables the five timers.

**Success:** the last line is `[bootstrap] done. Next: fill in /srv/f1ai/.env (docs/deploy/ORACLE.md, cutover), then deploy.` On the way it prints `data volume: … is blank; formatting it ext4 (f1ai-data)`, `data volume: UUID=… mounted at /srv/f1ai`, `sshd: keys only` and `deploy key: installed (SHA256:…)`.

Before closing this session, check from a second terminal that you can still log in: `ssh -i ~/.ssh/f1ai ubuntu@<public-ip>`.

**If it stops:**

| Message                                                                  | Meaning and fix                                                                                                                      |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `no unmounted data disk; attach the block volume first (ORACLE.md §1.4)` | The volume isn't attached yet. Attach it (§1.4), wait for **Attached**, run the same command again.                                  |
| `several candidate disks (…); rerun with F1AI_DATA_DEVICE=/dev/<disk>`   | Find the 100 GB disk with `lsblk`, then `sudo F1AI_DATA_DEVICE=/dev/<disk> bash bootstrap.sh "$(cat f1ai-deploy.pub)"`.              |
| `… holds …, not ext4; set F1AI_DATA_DEVICE to the right disk`            | It found a disk that already holds something. It never formats a disk that isn't blank; point it at the right one as above.          |
| `the argument is not a single SSH public key line`                       | Pass the one line of `f1ai-deploy.pub`, as above.                                                                                    |
| An apt or download error                                                 | Usually a mirror hiccup: run it again. It already waits up to 10 minutes for the apt lock that a fresh VM's first upgrade run holds. |

Running it again is always safe: every step checks before it changes anything. Without an argument it keeps the installed deploy key. Until §2.4–2.6 are done the timers fail (the DuckDNS one every 5 minutes); that's expected, and §2.7 clears the record. The reboot test comes in §2.7, once the stack runs.

**Optional, HTTP/3:** add a third ingress rule in §1.5's security list: Source CIDR `0.0.0.0/0`, IP Protocol **UDP**, Destination Port Range `443`. Without it browsers use HTTP/2, which works the same.

### 2.4 Fill in `/srv/f1ai/.env`

On the VM, make the database password, then open the file:

```bash
openssl rand -hex 32
sudo -u deploy nano /srv/f1ai/.env
```

Copy the 64 hex characters into `POSTGRES_PASSWORD` and into `DATABASE_URL`. Every other value is in the table; Render's are at **Render dashboard → the F1-AI service → Environment**. Paste values only into this file, in this terminal.

| Variable                                                             | Value                                                                                                                         |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `POSTGRES_PASSWORD`                                                  | the `openssl rand -hex 32` output                                                                                             |
| `DATABASE_URL`                                                       | `postgresql://f1ai:<POSTGRES_PASSWORD>@postgres:5432/f1ai`, with the same hex string (`postgres` is the Compose service name) |
| `API_HOST`                                                           | `<name>.duckdns.org`, without `https://`                                                                                      |
| `DUCKDNS_DOMAIN`                                                     | `<name>`                                                                                                                      |
| `DUCKDNS_TOKEN`                                                      | the token at the top of duckdns.org                                                                                           |
| `OCI_BUCKET`                                                         | `f1ai-backups` (already filled in)                                                                                            |
| `OCI_NAMESPACE`                                                      | OCI console → Profile menu → **Tenancy** → **Object storage namespace**. Empty also works: each backup then asks OCI for it.  |
| `ENVIRONMENT`                                                        | `production` (already filled in)                                                                                              |
| `ALLOWED_ORIGINS`                                                    | Render's value: the Vercel production origin(s), comma-separated, no trailing slash                                           |
| `TOKENLAB_API_KEY`, `GOOGLE_API_KEY`                                 | Render's values                                                                                                               |
| `TAVILY_API_KEY`, `OPENWEATHERMAP_API_KEY`, `SENTRY_DSN`, `HF_TOKEN` | Render's values; leave empty any that Render doesn't have                                                                     |
| `GITHUB_TOKEN`                                                       | Render's value if it has one; otherwise optional: a GitHub token with no scopes (raises the f1db release lookup's limit)      |

- **Don't copy from Render:** `DATABASE_URL` (it is Supabase's), `ENABLE_LOCAL_MODELS` (Render's `false` would turn rulebook search and recall off again), `PYTHON_VERSION`, or any `F1DB_VERSION` (it must stay unset). The image already sets `ENABLE_LOCAL_MODELS=true`, `FASTF1_CACHE_DIR`, `HF_HOME`, `F1DB_PATH` and `GIT_COMMIT`.
- **Format:** `KEY=value`, no spaces around `=`. Put a value that contains `$` in single quotes. Save with Ctrl-O, Enter, then Ctrl-X.

Check it:

```bash
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh config --quiet && echo ok
sudo systemctl start f1ai-duckdns
journalctl -u f1ai-duckdns -n 3
```

**Success:** `ok`, then a journal line ending `<name>.duckdns.org updated`. `dig +short <name>.duckdns.org` on your Mac still prints the VM's IP.

**If not:** `required variable POSTGRES_PASSWORD is missing a value` (or `API_HOST`) means that line is empty or misspelt. `DUCKDNS_DOMAIN … is empty or not a DuckDNS subdomain`, `DUCKDNS_TOKEN … is empty or not a DuckDNS token` and `DuckDNS refused the update` point at the two DuckDNS lines.

### 2.5 GitHub settings

On your Mac:

```bash
gh variable set ORACLE_HOST --repo amurark3/F1-AI --body "<name>.duckdns.org"
ssh-keyscan -t ed25519 <name>.duckdns.org 2>/dev/null > oracle_known_hosts
ssh-keygen -lf oracle_known_hosts
```

On the VM:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

The two `SHA256:…` fingerprints must be identical. If they differ, stop: something other than the VM answered for that name (`dig +short <name>.duckdns.org`). If they match, on your Mac:

```bash
gh variable set ORACLE_KNOWN_HOSTS --repo amurark3/F1-AI < oracle_known_hosts
rm oracle_known_hosts
gh variable list --repo amurark3/F1-AI
```

**Success:** the list shows `ORACLE_HOST` and `ORACLE_KNOWN_HOSTS`, whose value starts with `<name>.duckdns.org ssh-ed25519`. The name at the start of that line must be exactly `ORACLE_HOST`, in lower case; SSH refuses the connection otherwise. With `ORACLE_HOST` set, `retrain.yml` also deploys each promoted model. (The web alternative: repository **Settings → Secrets and variables → Actions**, tabs **Variables** and **Secrets**.)

### 2.6 First deploy

1. **Actions** → **Deploy backend to the Oracle VM** → **Run workflow** → branch `main`, leave **Also re-embed the regulation PDFs into pgvector** unticked → **Run workflow**. Or: `gh workflow run deploy-oracle.yml --repo amurark3/F1-AI --ref main`.
2. The first build is the slowest: nothing is cached yet (allow up to about 20 minutes). Later builds reuse the dependency layer.
3. **The first run fails at "Deploy on the VM", as expected.** It created the GHCR package `f1-ai-api`, new packages are private, and the VM pulls without credentials. The step's log ends `could not pull ghcr.io/amurark3/f1-ai-api:<sha>`, `no previous image to go back to …` and `deploy of <sha> failed …`.
4. **Make the package public:** GitHub → your profile → **Packages** → `f1-ai-api` → **Package settings** → **Danger Zone** → **Change visibility** → **Public** → type `f1-ai-api` → confirm. The image holds only this public repository's code; `backend/.dockerignore` keeps `.env` files and local data out.
5. **Re-run:** the failed run's page → **Re-run jobs** → **Re-run failed jobs**.

If step 3 succeeded instead, the package was already public; skip 4 and 5.

**Success:** the run is green, and its "Deploy on the VM" step ends `api: ready` and `deployed <sha>`. Then, on your Mac:

```bash
curl -s https://<name>.duckdns.org/api/ready | jq '{ready, stage, error, backend: .store.backend, host_kind: .store.host_kind, f1db_version}'
echo | openssl s_client -connect <name>.duckdns.org:443 -servername <name>.duckdns.org 2>/dev/null | openssl x509 -noout -issuer -enddate
```

Expect `"ready": true`, `"backend": "postgres"`, `"host_kind": "self_hosted"` and an f1db version; then an issuer with `O=Let's Encrypt` and an end date about 90 days out. `error` is normally `null`; a value names an outside source that failed during warm-up (GitHub's release downloads, say), which the API retries by itself.

**If it fails:**

- `api: not ready after 180s`: the API's log says why: `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh logs --tail 200 api` on the VM. A first boot downloads f1db from GitHub; during a GitHub outage, wait and re-run.
- `Host key verification failed` or `Permission denied (publickey)`: recheck §2.5 (the name in `ORACLE_KNOWN_HOSTS`) and §2.2 (the secret).
- The run is green but `/api/ready` doesn't answer from your Mac: Caddy has no certificate. `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh logs --tail 50 caddy` names the reason; usually the DuckDNS name doesn't point at the VM, or ports 80/443 aren't open in the security list (§1.5).

### 2.7 First-boot checks

Nothing users see depends on the VM yet, so prove now the parts no local rehearsal could. On the VM unless marked.

- [ ] **Docker**, from Docker's repository, on arm64: `docker --version; docker compose version; dpkg --print-architecture` prints both versions and `arm64`.
- [ ] **The image is arm64:** `sudo docker image inspect ghcr.io/amurark3/f1-ai-api:$(cat /srv/f1ai/state/api_tag) --format '{{.Architecture}}'` → `arm64`.
- [ ] **The data volume:** `findmnt /srv/f1ai` shows an ext4 device; `grep /srv/f1ai /etc/fstab` → `UUID=… /srv/f1ai ext4 defaults,_netdev,nofail 0 2`; `systemctl cat docker | grep RequiresMountsFor` → `RequiresMountsFor=/srv/f1ai`.
- [ ] **The firewall:** `sudo iptables -L INPUT -n --line-numbers` lists ACCEPT for `tcp dpt:80`, `tcp dpt:443` and `udp dpt:443` above the REJECT line; `grep -c 'dport \(80\|443\) ' /etc/iptables/rules.v4` → `3`.
- [ ] **SSH takes keys only:** `sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin) '` → all three `no`. On your Mac, `ssh -o PubkeyAuthentication=no ubuntu@<public-ip>` → `Permission denied (publickey).`
- [ ] **The deploy key runs nothing else.** On your Mac: `ssh -i ~/.ssh/f1ai-deploy deploy@<name>.duckdns.org hello` (accept the host key if asked; it is the fingerprint from §2.5) → `rejected request: hello` and `usage: deploy <40-hex commit sha> | ingest-rulebook`.
- [ ] **The deploy files sit at the deployed commit:** `cd / && sudo -u deploy git -C /srv/f1ai/app rev-parse HEAD` prints the same SHA as `cat /srv/f1ai/state/api_tag`; `sudo -u deploy git -C /srv/f1ai/app sparse-checkout list` → `deploy/oracle`.
- [ ] **The timers run as `deploy`:** `systemctl list-timers 'f1ai-*'` lists five, each with a NEXT time; `systemctl show f1ai-backup.service -p User` → `User=deploy`; `journalctl -u f1ai-duckdns -n 3` shows `updated` lines 5 minutes apart.
- [ ] **Backups reach Object Storage**, under instance-principal auth. `sudo systemctl start f1ai-backup`; the first run pulls Oracle's OCI CLI image (1.36 GB), so allow several minutes; the command returns when the backup is done. Then `journalctl -u f1ai-backup -n 20` shows `dumped … to /srv/f1ai/backups/f1ai-<UTC>.dump; rows: …` and `uploaded f1ai-<UTC>.dump to f1ai-backups` (and the `.counts` file), and OCI console → **Buckets** → `f1ai-backups` → **Objects** lists both. `NotAuthorizedOrNotFound` in the journal means the dynamic group's rule or the policy (§1.7) doesn't match this instance.
- [ ] **The restore check passes:** `sudo systemctl start f1ai-restore-check`, then `journalctl -u f1ai-restore-check -n 5` → `ok: f1ai-<UTC>.dump restores to the same rows: …`.
- [ ] **A reboot brings everything back.** `sudo reboot`; after a minute or two, log in again and check `findmnt /srv/f1ai` (mounted), `swapon --show` (`/swapfile`, 2G), `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh ps` (postgres and api `healthy`, caddy up), the firewall check above, and §2.6's `/api/ready` command from your Mac. If the stack stayed down, `systemctl status docker` says whether it is waiting for `/srv/f1ai`.
- [ ] **No failed units:** `systemctl --failed` → `0 loaded units listed`. If failures from before the `.env` was filled are listed, clear them with `sudo systemctl reset-failed`.
- [ ] **Memory, with Postgres's 768 MB buffers:** run §2.13's rulebook search once so the models load, then `free -m` and `sudo docker stats --no-stream`. Expect about 1.5–2 GB used in all, the API around 0.5–0.7 GB of it. The week-1 OCI check (§1.8) confirms it over days.

### 2.8 Freeze writes to Supabase

From step 4 below until §2.10's redeploy is live, the site has no API: pages load, but their data sections fail and the restart notice says "Server isn't responding". Plan for about 10 minutes: the migration takes 1–2, Vercel's build most of the rest (Vercel's **Deployments** list shows how long your last build took). Do 2.8–2.10 in one sitting.

**Why freeze first.** The alternative order (migrate while Render still serves, switch Vercel, then suspend Render) would shorten the outage to Vercel's build, but every write to Supabase after the dump would be lost: chat turns, profiles and prediction snapshots from Render, and the PU Action's documents. It would also fail the migration's own check, which counts the source again after the restore and stops on any difference. So writes stop first.

1. **Pick the time:** a Tuesday after 07:00 UTC, or a Wednesday. Not a race weekend: the PU Action runs hourly from Thursday to Monday, and that's when visitors come. Not Tuesday 06:00–07:00 UTC, when `retrain.yml` may merge a new model to `main`. Merge nothing to `main` until 2.10 is done.
2. **Record what production says now,** to compare in §2.13. On your Mac, with `<round>` the latest round that has a prediction (e.g. `20`):

   ```bash
   mkdir -p ~/f1ai-cutover && cd ~/f1ai-cutover
   snap() {  # snap <label> <API base URL>
     for p in standings/drivers/2026 standings/constructors/2026 race-control/power-units/2026 \
       "predictions/2026/<round>/snapshot?phase=post_qualifying"; do
       curl -s --max-time 90 "$2/api/$p" | jq -S . >"$1-$(tr '/?=' '___' <<<"$p").json"
     done
   }
   snap before https://f1-ai.onrender.com
   ls -l
   ```

   Four non-empty files. The first request may wait about 50 s for Render to wake.

3. **Stop the GitHub writers** (or in the browser: **Actions** → the workflow → **⋯** → **Disable workflow**):

   ```bash
   gh workflow disable ingest-power-units.yml --repo amurark3/F1-AI
   gh workflow disable ingest-rulebook.yml --repo amurark3/F1-AI
   gh workflow disable keep-warm.yml --repo amurark3/F1-AI
   gh run list --repo amurark3/F1-AI --status in_progress
   ```

   `keep-warm.yml` writes nothing, but it pings Render, which is about to be suspended, so it would fail and email you on every run; UptimeRobot (§2.12) replaces it. If the last command lists a running **Ingest power-unit documents** run, wait for it to finish. Don't cancel it mid-write.

4. **Suspend Render:** Render dashboard → the F1-AI service → **Settings** → at the bottom, **Suspend Web Service** → confirm. Check on your Mac: `curl -s -o /dev/null -w '%{http_code}\n' https://f1-ai.onrender.com/api/health` no longer prints `200`.

Supabase stays as it is. Nothing is deleted anywhere.

### 2.9 Migrate the data

On the VM, as `deploy`. Type or paste the URL at the hidden prompt only, never on a command line or into chat:

```bash
sudo -iu deploy
read -rsp 'Supabase session pooler URL: ' SOURCE_DATABASE_URL; echo
export SOURCE_DATABASE_URL
/srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --dry-run
/srv/f1ai/app/deploy/oracle/bin/migrate-from-supabase.sh --replace
unset SOURCE_DATABASE_URL
exit
```

Read the dry run's output before starting the real run.

- **The URL** is Supabase's session pooler string, the one Render's `DATABASE_URL` holds (or Supabase → **Connect** → **Session pooler**): `postgresql://postgres.<ref>:<password>@aws-<n>-<region>.pooler.supabase.com:5432/postgres?sslmode=require`, with the password percent-encoded (Render's copy already is), and `?sslmode=require` added if it is missing. Not the transaction pooler (port 6543; the script refuses it) and not the direct `db.<ref>.supabase.co` host (IPv6-only).
- **The dry run** restores into a scratch database and drops it; the live tables and the API are left alone. It ends with `dry run passed; would copy:`, one row count per table and `took <n>s`. Its last line says when the VM's tables already hold rows (the API and the PU timers write a few documents after the first deploy): `the live tables hold rows (…), so the real run needs --replace`.
- **`--replace`** empties the VM's five tables in the same transaction that restores Supabase's rows. A plain run, without it, works only while all five are empty; otherwise it refuses and changes nothing.
- **The real run** stops the API for the restore and the check, then starts it again. Expected ending: `verified: row counts equal the source's; stored vectors: …`, `migrated:` with each table's count (the dry run's numbers), `took <n>s`, `starting the API`, `api: ready`. Exit status 0 (`echo $?`).
- **Duration:** about 15 s for 35 MB (4,850 rulebook vectors) in the rehearsal, plus the transfer from Supabase and the API's restart. Allow 1–2 minutes.

**If it fails,** the last lines say why, and an API the run stopped is started again. A restore that errors is rolled back whole; a `MISMATCH` is found after the restore has committed.

| Ending                                                                             | Meaning                                                                                                                                                        |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SOURCE_DATABASE_URL is not set …`                                                 | The `export` line was skipped, or this is a new shell.                                                                                                         |
| `SOURCE_DATABASE_URL was refused (why is above)`                                   | The URL doesn't parse; libpq's reason is above, with the URL withheld. Usually an unencoded character in the password.                                         |
| `that is Supabase's transaction pooler (port 6543) …`                              | Use the session pooler URL (port 5432).                                                                                                                        |
| `cannot query the source …`                                                        | Wrong password or host, or no route; libpq's message is above.                                                                                                 |
| `the live tables already hold rows: … re-run with --replace`                       | Expected after the first deploy. Use `--replace`.                                                                                                              |
| `MISMATCH …` then `… the source changed after it: stop every writer to Supabase …` | The copy is committed, but something still writes to Supabase. Check that Render is suspended and the Actions are disabled (§2.8), then run `--replace` again. |
| `MISMATCH …` then `the restore does not match the dump`                            | The copy is committed but differs from the dump: a fault in the restore. Run `--replace` once more; if it repeats, roll back (§3) and keep the output.         |
| `the source runs PostgreSQL <n>; pg_dump 17 reads 17 and older only`               | Supabase is on a newer PostgreSQL than the script's client image. Roll back (§3); the image in the script needs a bump.                                        |

### 2.10 Point Vercel at the VM

1. Vercel → the project → **Settings** → **Environment Variables**. For **Production**, set both to `https://<name>.duckdns.org`, no trailing slash: `NEXT_PUBLIC_API_URL`, and `API_URL` (add it if it doesn't exist).
2. **Settings** → **Functions** → **Function Regions**: write down the current region (for §3), then choose the one nearest your Oracle home region (§1.1's table: Ashburn → `iad1`, Chicago → `cle1`, San Jose or Phoenix → `sfo1`) and save.
3. **Deployments** → the latest Production deployment → **⋯** → **Redeploy** → **Redeploy**. Both settings apply only to a new deployment: `NEXT_PUBLIC_API_URL` is compiled into the pages at build time.

**Success:** the new deployment is **Ready**. On the site, the Command Center fills in, and the browser's developer tools (Network tab) show requests going to `<name>.duckdns.org`. The outage ends here.

**If not:** sections that stay empty while the browser console shows CORS errors mean `ALLOWED_ORIGINS` lacks the site's origin: fix it in `/srv/f1ai/.env` and recreate the API (§4.3). Anything else: check `/api/ready` from your Mac (§2.6).

### 2.11 Embed the migrated chat history

Render saved chat turns without vectors, so recall can't find them until they are embedded. The backfill runs beside the live API and fills only rows that have no vector. On the VM:

```bash
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh --profile jobs run --rm jobs python -m scripts.backfill_chat_embeddings
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh --profile jobs run --rm jobs python -m scripts.backfill_chat_embeddings --apply
```

**Expected:** the dry run prints `Chat turns without an embedding: <N>` and `Dry run: nothing written. Re-run with --apply to embed them.` N is at most the `chat_message` count the migration printed (system turns are never embedded). `--apply` prints a `batch <n>: embedded … of … (through id …)` line per 64 turns and ends `Done: embedded <N> turn(s); 0 already had a vector.` Run the dry run again: `Chat turns without an embedding: 0` and `Nothing to backfill.` It takes seconds to a few minutes; the job loads its own copy of the embedder while it runs.

**If not:** `Backfill refused: local models are disabled …` means `.env` sets `ENABLE_LOCAL_MODELS`; delete that line and recreate the API (§4.3). `Backfill failed: …` keeps the batches already committed; run `--apply` again to carry on.

### 2.12 Uptime monitor

UptimeRobot's free plan checks every 5 minutes and emails you when a check fails.

1. Sign up at [uptimerobot.com](https://uptimerobot.com/) on the free plan.
2. **New monitor** → type **HTTP(s)** → URL `https://<name>.duckdns.org/api/health/deep` → interval **5 minutes** → alert contact: your email → create. (A **Keyword** monitor for `"status":"ok"` on the same URL works too.)
3. **Success:** green within one interval. `/api/health/deep` round-trips Postgres and answers 503 when the database is unreachable, so the monitor watches the API and its database, not just the VM.

### 2.13 Smoke checklist

On your Mac unless marked "on the VM".

- [ ] **No cold start.** After an hour with no visits: `curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' https://<name>.duckdns.org/api/health/deep` → `200` in well under a second.
- [ ] **The same answers as before.** In `~/f1ai-cutover` (define `snap` again from §2.8 in a new terminal):

  ```bash
  snap after https://<name>.duckdns.org
  for f in before-*.json; do echo "== $f"; diff "$f" "after-${f#before-}"; done
  ```

  Only timestamps may differ. Standings can also differ if f1db published a release in between; `/api/ready`'s `f1db_version` says which one each side read.

- [ ] **The VM's own database and a current dataset:** `curl -s https://<name>.duckdns.org/api/ready | jq '{ready, host_kind: .store.host_kind, f1db_current: .f1db_sync.up_to_date}'` → `true`, `"self_hosted"`, `true`.
- [ ] **Rulebook search cites the regulations.** The first query loads the models (downloading them once), so it can take a minute:

  ```bash
  curl -s -X POST https://<name>.duckdns.org/api/race-control/rulebook/search \
    -H 'Content-Type: application/json' -d '{"query": "What happens when a race is suspended?"}' \
    | jq '{source, error, pages: [.citations[] | {document, page}]}'
  ```

  → `"source": "pgvector-rag"` with page numbers. `"fallback"` means the search didn't run, and `error` says why. The site's Rules Search shows the same citations.

- [ ] **The AI Engineer cites the rules.** Ask it "What is the penalty for an unsafe release?": the answer quotes regulation articles, and never says rulebook search is unavailable.
- [ ] **Recall finds old conversations.** On the VM, pick a user whose turns now have vectors:

  ```bash
  sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh exec postgres psql -U f1ai -d f1ai -c "SELECT user_id, count(*) FROM chat_message WHERE embedding IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
  ```

  Then on your Mac, with a topic that user talked about: `curl -s --get --data-urlencode "q=<topic>" https://<name>.duckdns.org/api/threads/<user_id>/recall | jq '.matches | length'` → 1 or more.

- [ ] **The live WebSocket connects** through Caddy:

  ```bash
  curl --http1.1 -si --max-time 5 -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
    -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
    https://<name>.duckdns.org/api/live/2026/<round> | head -1
  ```

  → `HTTP/1.1 101 Switching Protocols`. During the next live session, the Command Center's timing tower fills.

- [ ] **Timers**, on the VM: `systemctl list-timers 'f1ai-*'` shows five with NEXT times; `systemctl --failed` lists none.
- [ ] **A backup of the real data**, on the VM: `sudo systemctl start f1ai-backup`, then `sudo systemctl start f1ai-restore-check`. `journalctl -u f1ai-backup -n 5` shows the migrated row counts and `uploaded …`; `journalctl -u f1ai-restore-check -n 3` ends `ok: …`. From now on the timer does this at 03:30 UTC.
- [ ] **Sentry gets the deployed commit** (when `SENTRY_DSN` is set), on the VM: `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh exec api printenv GIT_COMMIT` prints the SHA in `/srv/f1ai/state/api_tag`. The backend project's next event carries it as its release.
- [ ] **Still $0:** OCI → **Billing & Cost Management** → **Cost Analysis**.
- [ ] **UptimeRobot** is green.

The VM now serves production. After 7 stable days, P0c.9 retires Render, Supabase and the old workflows (§4.12).

## 3. Rollback

Use this when the VM can't serve and §4 can't fix it soon. Render and Supabase still hold everything as it was at §2.8.

1. **Supabase.** Open the project. If it is paused (Supabase pauses a Free project after 7 days of low activity), click **Resume project** and wait for it. Supabase's docs (read 2026-11-09) say a paused Free project can be resumed for up to a year after it was paused; after that only its backup can be downloaded.
2. **Carry back the VM's writes, if you need them** (below). Do it now, before Render resumes.
3. **Render:** dashboard → the F1-AI service → **Resume Web Service**. Its environment still points at Supabase. Check: `curl -s --max-time 90 https://f1-ai.onrender.com/api/ready | jq '{ready, host_kind: .store.host_kind}'` → `true`, `"supabase_pooler"`.
4. **Vercel:** for Production, set `NEXT_PUBLIC_API_URL` and `API_URL` back to `https://f1-ai.onrender.com` and the Function Region back to the one written down in §2.10, then **Redeploy** the latest Production deployment.
5. **GitHub:** re-enable the workflows, and stop deploying to the VM (without `ORACLE_HOST`, `deploy-oracle.yml` and `retrain.yml`'s deploy step skip again, and Render deploys `main` by itself):

   ```bash
   gh workflow enable ingest-power-units.yml --repo amurark3/F1-AI
   gh workflow enable ingest-rulebook.yml --repo amurark3/F1-AI
   gh workflow enable keep-warm.yml --repo amurark3/F1-AI
   gh variable delete ORACLE_HOST --repo amurark3/F1-AI
   ```

6. **UptimeRobot:** pause the VM's monitor.
7. **The VM** can stay up for a second attempt. A VM whose CPU, network and memory all idle below 20% for 7 days may be reclaimed (§1.8), so don't leave it stopped long if you want it back.

**Lost without the carry-back:** everything written on the VM after §2.9: chat turns and profiles, prediction snapshots and history, and power-unit documents (the PU Action collects anything newer on its next run, and its daily run re-reads every event page). The analysis cache rebuilds on demand. The rulebook changes only with the PDFs; re-run `ingest-rulebook.yml` if they changed.

**Carrying the VM's data back.** The VM's five tables hold Supabase's rows as of §2.9 plus everything since, so copy them back whole, replacing Supabase's. Supabase's host, user and `<ref>` come from the session pooler URL (§2.9); the password is the plain one, not percent-encoded. On the VM:

```bash
sudo systemctl stop f1ai-pu-ingest.timer f1ai-pu-ingest-daily.timer
sudo -iu deploy
cd /srv/f1ai/app/deploy/oracle
bin/compose.sh stop api
bin/compose.sh exec -T postgres pg_dump -U f1ai -d f1ai --data-only \
  --table=public.app_documents --table=public.analysis_cache --table=public.chat_message \
  --table=public.user_profile --table=public.rulebook_chunk >~/vm-data.sql
export PGHOST=aws-<n>-<region>.pooler.supabase.com PGPORT=5432 PGDATABASE=postgres PGUSER=postgres.<ref> PGSSLMODE=require
read -rsp 'Supabase database password: ' PGPASSWORD; echo; export PGPASSWORD
{ echo 'TRUNCATE public.app_documents, public.analysis_cache, public.chat_message, public.user_profile, public.rulebook_chunk;'; cat ~/vm-data.sql; } |
  docker run --rm -i -e PGHOST -e PGPORT -e PGDATABASE -e PGUSER -e PGPASSWORD -e PGSSLMODE \
    pgvector/pgvector:pg17 psql -X -q -v ON_ERROR_STOP=1 --single-transaction -f -
unset PGPASSWORD
rm ~/vm-data.sql
exit
```

- **Success:** `psql` prints nothing and exits 0; any error rolls the whole transaction back, leaving Supabase as it was. Then resume Render (step 3).
- The dump's `COPY` lines name their columns and set the sequences, and Supabase has the same tables (Render's boot after the P0c merge added `version` to `app_documents`).
- The VM's API and PU timers stay stopped. For a second attempt: `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh start api` and `sudo systemctl start f1ai-pu-ingest.timer f1ai-pu-ingest-daily.timer`, then §2.8 onwards again.

## 4. Operations

Log in as `ubuntu`: `ssh -i ~/.ssh/f1ai ubuntu@<name>.duckdns.org`. The stack's commands run as `deploy`, which owns `.env` and has Docker access: `sudo -u deploy …` for one command, `sudo -iu deploy` for a shell. Commands that run git as `deploy` (`deploy.sh`) start with `cd /`, because git needs a working directory `deploy` can read, and `ubuntu`'s home isn't one. To type less, add an alias once: `echo "alias f1c='sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh'" >>~/.bashrc`.

### 4.1 What lives where

| Path                                                            | What                                                                                       |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `/srv/f1ai/.env`                                                | every setting and secret (mode 600, owner `deploy`)                                        |
| `/srv/f1ai/app/deploy/oracle/`                                  | `compose.yaml`, `Caddyfile`, the scripts and the units, checked out at the deployed commit |
| `/srv/f1ai/state/api_tag`, `api_tag.previous`                   | the live image tag (a commit SHA) and the one before it                                    |
| `/srv/f1ai/pgdata`                                              | Postgres                                                                                   |
| `/srv/f1ai/backups`                                             | the three newest nightly dumps with their `.counts` files (the bucket keeps 14 days)       |
| `/srv/f1ai/f1db`, `/srv/f1ai/f1_cache`, `/srv/f1ai/huggingface` | the f1db dataset, FastF1's cache, the embedder and reranker                                |
| `/srv/f1ai/caddy`                                               | Caddy's certificates and state                                                             |

Timers (all UTC): `f1ai-pu-ingest` hourly at :17 from Thursday to Monday; `f1ai-pu-ingest-daily` at 05:47 with `--all-events`; `f1ai-backup` at 03:30; `f1ai-restore-check` on Wednesdays at 04:30; `f1ai-duckdns` every 5 minutes.

### 4.2 Logs

```bash
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh ps
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh logs --tail 200 api
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh logs -f --since 1h api
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh logs --tail 100 caddy
journalctl -u f1ai-backup -n 50
journalctl -u 'f1ai-*' --since today
```

- The API, Postgres and Caddy log to Docker: three 10 MB files per container, so old lines roll off. Sentry keeps the backend's errors.
- The timers' jobs log to the journal. Nothing alerts on a failed timer; the weekly check (§4.9) is where you see one.

### 4.3 Restart, and changing `.env`

```bash
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh restart api
```

A restart keeps the container's old environment. After editing `/srv/f1ai/.env` (`sudo -u deploy nano /srv/f1ai/.env`), recreate the container instead:

```bash
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh up -d --no-deps --force-recreate api
```

Use `caddy` in place of `api` after changing `API_HOST`. `compose.sh` keeps the deployed image, so neither command changes the code. The API is back after its warm-up (under a minute with f1db on disk); meanwhile the site shows its restart notice.

### 4.4 Deploys

- **Normal:** merge to `main`. A push that touches `backend/**`, `deploy/oracle/**` or the workflow file builds and deploys; a frontend-only merge leaves the API alone. A model that `retrain.yml` promotes is deployed once its PR merges.
- **By hand, from GitHub:** **Actions** → **Deploy backend to the Oracle VM** → **Run workflow**. Tick **Also re-embed the regulation PDFs into pgvector** to re-ingest the rulebook after the deploy.
- **By hand, on the VM**, for any commit the workflow has built:

  ```bash
  cd / && sudo -u deploy /srv/f1ai/app/deploy/oracle/deploy.sh deploy <40-hex commit sha>
  ```

- **Back one deploy** (the previous image is kept on the VM, so nothing is built):

  ```bash
  cd / && sudo -u deploy /srv/f1ai/app/deploy/oracle/deploy.sh deploy "$(cat /srv/f1ai/state/api_tag.previous)"
  ```

A deploy checks out `deploy/oracle` at the commit, pulls `ghcr.io/amurark3/f1-ai-api:<sha>`, restarts the stack on it and waits up to 180 s for `/api/ready` and `/api/health/deep`. If the new image never gets there, it puts the previous one back (`rolling back to …`, `rolled back: … is serving`) and exits 1. One deploy runs at a time; a second waits up to 15 minutes. Only the live and the previous images stay on disk.

### 4.5 A `psql` shell

On the VM:

```bash
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh exec postgres psql -U f1ai -d f1ai
```

From your Mac, through an SSH tunnel (Postgres listens only on the VM's loopback). Port 55433 is just a free local port; your Mac already uses 5432 and 55432:

```bash
ssh -i ~/.ssh/f1ai -N -L 55433:127.0.0.1:5432 ubuntu@<name>.duckdns.org
```

Leave it running, and in another terminal: `psql -h 127.0.0.1 -p 55433 -U f1ai -d f1ai` (or a GUI client on `127.0.0.1:55433`). Type `POSTGRES_PASSWORD` at the prompt; `sudo -u deploy grep '^POSTGRES_PASSWORD=' /srv/f1ai/.env` on the VM shows it. The tunnel needs the admin key: the deploy key can't forward ports.

### 4.6 Restore from a backup

The three newest dumps are on the VM in `/srv/f1ai/backups`, and 14 days of them in the bucket. Restore into a new database, then swap it in, so a failed restore never touches the live data. As `deploy`:

```bash
sudo -iu deploy
cd /srv/f1ai/app/deploy/oracle
ls -l /srv/f1ai/backups
```

To fetch an older dump from the bucket, with the OCI CLI image `backup.sh` pins and the VM's instance-principal auth:

```bash
img=$(sed -n 's/^OCI_CLI_IMAGE="\(.*\)"$/\1/p' bin/backup.sh)
oci() { docker run --rm -i --network host "$img" --auth instance_principal "$@"; }
ns=$(oci os ns get --query data --raw-output)
oci os object list --namespace "$ns" --bucket-name f1ai-backups --query 'data[].name'
oci os object get --namespace "$ns" --bucket-name f1ai-backups --name f1ai-<UTC>.dump --file - >/srv/f1ai/backups/f1ai-<UTC>.dump
```

Restore it into `f1ai_restored`; exit status 0 means every object restored:

```bash
bin/compose.sh exec -T postgres psql -U f1ai -d postgres -c "CREATE DATABASE f1ai_restored"
bin/compose.sh exec -T postgres pg_restore -U f1ai -d f1ai_restored --no-owner --no-privileges --exit-on-error </srv/f1ai/backups/f1ai-<UTC>.dump
echo $?
```

Swap it in, at a moment when no deploy or timer job is running:

```bash
bin/compose.sh stop api
bin/compose.sh exec -T postgres psql -U f1ai -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'f1ai'" \
  -c "ALTER DATABASE f1ai RENAME TO f1ai_before_restore" \
  -c "ALTER DATABASE f1ai_restored RENAME TO f1ai"
bin/compose.sh start api
```

Check `/api/ready` and the site; once they look right, `bin/compose.sh exec -T postgres psql -U f1ai -d postgres -c "DROP DATABASE f1ai_before_restore"`.

**Lost the data volume?** `.env` was on it too. Create and attach a new blank 100 GB volume (§1.4), delete the old `/srv/f1ai` line from `/etc/fstab` (`sudo nano /etc/fstab`; `bootstrap.sh` stops at a line naming another disk), fetch and run `bootstrap.sh` as in §2.3 (no argument: the deploy key is on the boot disk), fill in `.env` from your password manager (§2.4, with the same `POSTGRES_PASSWORD` or a new one), deploy (§2.6, **Run workflow**), then restore the newest dump from the bucket as above.

### 4.7 One-off jobs

Scripts run in the `jobs` container: the deployed image, with the API's `.env` and data, against the VM's database. `--rm` removes the container afterwards.

```bash
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh --profile jobs run --rm jobs python -m scripts.backfill_predictions
sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh --profile jobs run --rm jobs python -m scripts.backfill_predictions --apply --backup-dir /var/lib/f1ai/f1_cache/prediction-backups
```

- **Prediction backfill:** the first command is a dry run that prints the plan. `--apply` needs `--backup-dir` here: its default, `data/backups`, is inside the image's read-only code. `/var/lib/f1ai/f1_cache` is FastF1's cache volume, so the copy lands in `/srv/f1ai/f1_cache/prediction-backups` and survives. Other flags: `--year`, `--through-round <n>`, `--recompute`. The running API serves the new snapshots within a minute; no restart.
- **Rulebook re-ingest**, after a PDF change that didn't come through a normal deploy: `cd / && sudo -u deploy /srv/f1ai/app/deploy/oracle/deploy.sh ingest-rulebook`, or the workflow's tick box (§4.4). A push that changes `backend/data/raw/**` re-ingests by itself.
- **Power-unit ingest now:** `sudo systemctl start f1ai-pu-ingest` (or `f1ai-pu-ingest-daily` for `--all-events`), then `journalctl -u f1ai-pu-ingest -n 20`.
- **Any other script:** `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh --profile jobs run --rm jobs python -m scripts.<name> [arguments]`.

### 4.8 Rotating secrets

- **API keys** (`TOKENLAB_API_KEY`, `GOOGLE_API_KEY`, `TAVILY_API_KEY`, `OPENWEATHERMAP_API_KEY`, `SENTRY_DSN`, `HF_TOKEN`, `GITHUB_TOKEN`): edit `/srv/f1ai/.env`, then recreate the API (§4.3).
- **DuckDNS token:** put the new one in `DUCKDNS_TOKEN`, then `sudo systemctl start f1ai-duckdns` and check `journalctl -u f1ai-duckdns -n 3`.
- **Postgres password.** `POSTGRES_PASSWORD` is read only when the database is first created, so the database's own password changes in SQL. On the VM:

  ```bash
  openssl rand -hex 32
  sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh exec postgres psql -U f1ai -d f1ai -c '\password f1ai'
  ```

  `\password` asks for the new value twice at a hidden prompt (the `ALTER USER` it sends carries only a hash). Then put the same value in `POSTGRES_PASSWORD` and inside `DATABASE_URL` in `.env`, and recreate the API (§4.3).

- **Deploy key:** make a new pair and set the secret (§2.2's first two commands; answer `y` to overwrite), copy the `.pub` to the VM (§2.2's `scp`), then `sudo bash /srv/f1ai/app/deploy/oracle/bootstrap.sh "$(cat f1ai-deploy.pub)"`, which replaces the old key.
- **Admin key** (`~/.ssh/f1ai`): append the new public key to `~/.ssh/authorized_keys` on the VM, log in with it from a second terminal, then delete the old line.

### 4.9 Weekly checks

About ten minutes. On the VM:

```bash
systemctl --failed
systemctl list-timers 'f1ai-*'
journalctl -u f1ai-restore-check -n 3
sudo ls -l /srv/f1ai/backups
free -m
df -h / /srv/f1ai
cat /var/run/reboot-required.pkgs 2>/dev/null
```

- [ ] `systemctl --failed` → `0 loaded units listed`. A failed unit: `journalctl -u <unit> -n 50` says why; after fixing the cause, `sudo systemctl reset-failed`.
- [ ] The restore check (Wednesdays) ended `ok: …`; three recent dumps on the VM, and about 14 days of them in OCI → **Buckets** → `f1ai-backups`.
- [ ] Memory: OCI's **Memory Utilization** for the week (§1.8) at or above 25%.
- [ ] Disk: plenty free on both. The boot disk holds two API images (about 2.6 GB each) and the OCI CLI image (1.36 GB); `/srv/f1ai` grows with the database and FastF1's cache.
- [ ] No pending reboot (the last command prints nothing); otherwise §4.11.
- [ ] **Cost Analysis** shows $0 (§1.9).
- [ ] Sentry: no new backend issues you haven't looked at. UptimeRobot: no incidents.
- [ ] `curl -s https://<name>.duckdns.org/api/ready | jq .f1db_sync.up_to_date` on your Mac → `true` (if not, `DEPLOYMENT.md` § "F1 dataset freshness").

### 4.10 After a change to the systemd units

A deploy updates `/srv/f1ai/app/deploy/oracle/`, but not the unit copies systemd runs from `/etc/systemd/system`. When a merge changes `deploy/oracle/systemd/` or `bootstrap.sh`, re-run it after that deploy, without an argument (the deploy key stays):

```bash
sudo bash /srv/f1ai/app/deploy/oracle/bootstrap.sh
```

It prints `deploy key: keeping the installed one`, `repo: left at the deployed commit …` and `systemd: … enabled`, and ends `[bootstrap] done. …`.

### 4.11 Kernel updates and reboots

Unattended upgrades install security updates daily but never reboot. When `/var/run/reboot-required` exists (the weekly check shows its package list), reboot at a quiet time, never during a session: `sudo reboot`. The API is gone for a minute or two, and the site shows its restart notice. Then check `findmnt /srv/f1ai`, `sudo -u deploy /srv/f1ai/app/deploy/oracle/bin/compose.sh ps` and `/api/ready`, as in §2.7.

### 4.12 Decommission

After 7 stable days on the VM, plan task P0c.9 deletes `render.yaml` and the Render-era workflows (`keep-warm.yml`, `ingest-power-units.yml`, `ingest-rulebook.yml`). Then you delete the GitHub secret `DATABASE_URL` (and `HF_TOKEN` and the `BACKEND_URL` variable, if present), archive a final Supabase dump to the bucket, delete the Supabase project two weeks later, and delete the Render service. See [`PLAN.md`](../plans/2026-11-redesign/PLAN.md), P0c.9. Until then, §3 stays possible.
