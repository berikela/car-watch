# myauto.ge watcher

Notifies you by email when a new car matching your filters is listed on
[myauto.ge](https://www.myauto.ge). It runs for free on GitHub Actions every 10 minutes -
no server needed.

- `config.toml` - what to look for (edit this to change cars / filters)
- `watcher.py` - the script
- `.github/workflows/watch.yml` - the schedule
- `seen.json` - created automatically; the listings already reported

## Setup

1. **Create a new public repository** on <https://github.com/new> (no README), then upload this folder:
   ```
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
2. **Choose how you get notified** (see below). The simple way needs no further setup.
3. **Test it**: repository → Actions → "Watch myauto.ge" → Run workflow → tick
   "Send a test notification" → Run. You should get an email within a minute or two.

After that it runs by itself. The first normal run remembers the cars that are already
listed and notifies you only about those listed in the last 24 hours; from then on you get
a notification for each new one.

### Simple way: GitHub emails you (no password, no 2-step verification)

With no secrets set, the watcher opens an *issue* in your repository for each new car, and
GitHub emails that issue to you at the address of your GitHub account. Check two things once:

- On the repository page: **Watch** (top right) is set to **All Activity**.
- In <https://github.com/settings/notifications>: **Email** is ticked under "Watching", and
  the address shown there is the one you want.

### Alternative: email straight from a Gmail account

Google only allows this with an *app password*, which requires 2-Step Verification on the
sending account. You can use a secondary Gmail account as the sender.

1. On the sending account turn on 2-Step Verification, then create an app password at
   <https://myaccount.google.com/apppasswords>.
2. Repository → Settings → Secrets and variables → Actions → New repository secret:
   - `EMAIL_USER` - the sending Gmail address
   - `EMAIL_PASSWORD` - the app password
   - `EMAIL_TO` - where alerts should arrive, if different from `EMAIL_USER`

When these secrets exist the watcher emails directly and opens no issues.

## Changing what you watch

Edit `config.toml` (you can do it directly on github.com with the pencil button) and commit.
All available filters are listed there as comments. When you change a search, the next run
remembers the current matches and alerts only for those listed in the last 24 hours, then
for every car listed after that.

## Running on your own computer

```
python watcher.py --dry-run
```

Needs Python 3.11 or newer, nothing else to install.

## Notes

- GitHub switches scheduled workflows off after 60 days without a commit in the repository.
  To prevent that, the workflow commits `heartbeat.txt` whenever the last commit is more
  than 30 days old.
- If a run fails (for example myauto.ge is down), GitHub emails you about the failed run and
  the next run tries again.
