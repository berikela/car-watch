# myauto.ge watcher

Emails you when a new car matching your filters is listed on [myauto.ge](https://www.myauto.ge).
It runs for free on GitHub Actions every 10 minutes - no server needed.

- `config.toml` - what to look for (edit this to change cars / filters)
- `watcher.py` - the script
- `.github/workflows/watch.yml` - the schedule
- `seen.json` - created automatically; the listings already reported

## Setup

1. **Create a Gmail app password** (the script sends the email from your own Gmail to yourself).
   Turn on 2-Step Verification on your Google account, then open
   <https://myaccount.google.com/apppasswords>, create a password and copy the 16 letters.
2. **Create a new public repository** on <https://github.com/new> (no README), then upload this folder:
   ```
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
3. **Add the secrets**: repository → Settings → Secrets and variables → Actions → New repository secret
   - `EMAIL_USER` - your Gmail address
   - `EMAIL_PASSWORD` - the app password from step 1
   - `EMAIL_TO` - optional, only if the alerts should go to a different address
4. **Test it**: repository → Actions → "Watch myauto.ge" → Run workflow → tick
   "Send a test email" → Run. You should get an email with the 3 newest matching cars.

After that it runs by itself. The first normal run only remembers the cars that are already
listed; from then on you get an email for each new one.

## Changing what you watch

Edit `config.toml` (you can do it directly on github.com with the pencil button) and commit.
All available filters are listed there as comments. When you change a search, the next run
remembers the current matches silently and alerts only for cars listed after that.

## Running on your own computer

```
python watcher.py --dry-run
```

Needs Python 3.11 or newer, nothing else to install.

## Notes

- GitHub switches scheduled workflows off after 60 days without any commit in the repository.
  If that happens GitHub emails you, and you re-enable it with one click on the Actions tab.
- If a run fails (for example myauto.ge is down), GitHub emails you about the failed run and
  the next run tries again.
