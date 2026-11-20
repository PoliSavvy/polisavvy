# One-time setup (about 30 minutes)

You only do this once. After that the site runs itself and you only approve
held items from your phone.

## 1. Put the code on GitHub (10 min)

1. Create a free GitHub account if you don't have one, and install the GitHub
   mobile app (that's where review notifications arrive).
2. Create a new **private** repository called `polisavvy`.
3. Upload this folder to it. Or connect GitHub to Claude and ask Claude to push it.

## 2. Let Claude reach the government sites (2 min)

In Claude on the web: **Settings > Capabilities**, add these allowed domains,
then ask Claude to build the live connectors:

```
parl.ca
www.parl.ca
www.ourcommons.ca
www.pm.gc.ca
lobbycanada.gc.ca
gazette.gc.ca
www.canada.ca
open.canada.ca
```

## 3. Add the AI key (5 min)

1. Create an account at console.anthropic.com, add a payment method and set a
   monthly spending limit (start with $20).
2. Create an API key.
3. In the GitHub repository: **Settings > Secrets and variables > Actions >
   New repository secret**. Name: `ANTHROPIC_API_KEY`. Value: your key.

## 4. Turn on the website (2 min)

In the repository: **Settings > Pages > Source: GitHub Actions**.
Then **Actions > Build and deploy > Run workflow**. Your site appears at
`https://YOUR-USERNAME.github.io/polisavvy/` within a minute or two.

## 5. Turn on notifications (1 min)

In the GitHub app, watch the repository and allow notifications for issues.
When something needs review you'll get a "Review needed" issue.

## Later

- **Custom domain:** buy one (about $15 a year) and add it under Settings > Pages.
- **Accounts and emails:** phase 2 adds Supabase (accounts) and Resend (email).
  Both have free starter plans.
