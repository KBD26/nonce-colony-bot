# 8004 NONCE agent — drop-in (no code to edit)

This whole folder is a ready-to-run agent: a copy of your KOINE bot, already retargeted to 8004 NONCE. You don't touch any code.

## Launch it — 5 steps

1. **New GitHub repo.** Create one (e.g. `nonce-colony-bot`, private is fine). **Upload everything in this folder** into it — drag all the files *and the `.github` folder* into GitHub's *Add file → Upload files*.
2. **New Colony agent.** On The Colony, under your account (the one that runs `@koine_daemon`): create an agent — handle **`nonce_daemon`**, display **DAEMON**, avatar = an 8004 NONCE image. Copy its **`col_…` API key** (shown once).
3. **Add the secrets.** Repo → **Settings → Secrets and variables → Actions**:
   - Secret **`MISTRAL_API_KEY`** = your existing Mistral key
   - Secret **`COLONY_API_KEY`** = the new `col_…` key
   - Variable **`DRY_RUN`** = `true`
4. **Test.** **Actions** tab → *DAEMON on The Colony* → **Run workflow**. Read the log — it prints the intro post but posts nothing (DRY_RUN).
5. **Go live.** Set Variable **`DRY_RUN`** = `false` → **Run workflow**. It posts the intro. After that it runs every 6h: ≤1 post/day (intro → finding → challenge → the rarity question), and replies to comments on its own posts.

That's it. Same engine as KOINE; only `persona.md`, `seeds.json`, and the handle changed.

## Notes
- If your handle isn't `nonce_daemon`, add Variable **`COLONY_USERNAME`** = your handle.
- The **subtle rarity clue** lives in two places: the 4th seed in `seeds.json` and the **THE QUESTION** section of `persona.md`. It's deliberately sparse — never explains the inversion.
- Use the **Run workflow** button, never "Re-run jobs" (that reuses an old commit).
- **Timing:** the intro/finding/challenge are fine to post anytime (the genesis is real and verifiable), but the agent must **not promise a public-mint date** until you've flipped `openPublic`.
